from types import MethodType
from unittest.mock import Mock, patch

import pytest

from llm.ollama_runner import OllamaRunner
from llm.resource_detection import (
    HardwareInfo,
    calculate_pool_size,
    detect_hardware,
)
from llm.schemas.llm_schemas import (
    GenerateRequest,
    MessageItem,
)


class TestResourceDetection:
    """Test hardware resource detection."""

    def test_calculate_pool_size_gpu_large_model(self) -> None:
        """Test pool size calculation for large model on GPU."""
        hardware = HardwareInfo(
            has_cuda=True,
            gpu_count=2,
            total_vram_mb=80 * 1024,  # 80GB total
            cpu_cores=16,
            total_ram_mb=64 * 1024,
        )

        # Large model (70b) needs ~40GB VRAM per instance
        pool_size = calculate_pool_size(hardware, 'llama3.1:70b')

        # 80GB * 0.8 = 64GB usable, 64GB / 40GB = 1.6 → 1 instance
        assert pool_size == 1

    def test_calculate_pool_size_gpu_small_model(self) -> None:
        """Test pool size calculation for small model on GPU."""
        hardware = HardwareInfo(
            has_cuda=True,
            gpu_count=1,
            total_vram_mb=24 * 1024,  # 24GB
            cpu_cores=8,
            total_ram_mb=32 * 1024,
        )

        # Small model (8b) needs ~4GB VRAM per instance
        pool_size = calculate_pool_size(hardware, 'llama3.1:8b')

        # 24GB * 0.8 = 19.2GB usable, 19.2GB / 4GB = 4.8 → 4 instances
        assert pool_size == 4

    def test_calculate_pool_size_cpu_mode(self) -> None:
        """Test pool size calculation for CPU mode."""
        hardware = HardwareInfo(
            has_cuda=False,
            gpu_count=0,
            total_vram_mb=0,
            cpu_cores=8,
            total_ram_mb=16 * 1024,  # 16GB
        )

        # Small model on CPU needs ~2GB RAM per instance
        pool_size = calculate_pool_size(hardware, 'llama3.1:8b')

        # 16GB * 0.6 = 9.6GB usable, 9.6GB / 2GB = 4.8 → 4 instances
        # But capped by CPU cores (8), so 4 instances
        assert pool_size == 4

    def test_calculate_pool_size_max_cap(self) -> None:
        """Test pool size capped at maximum (8 instances)."""
        hardware = HardwareInfo(
            has_cuda=True,
            gpu_count=4,
            total_vram_mb=200 * 1024,  # 200GB (unrealistic but for test)
            cpu_cores=64,
            total_ram_mb=256 * 1024,
        )

        # Small model: 200GB * 0.8 / 4GB = 40 instances → capped to 8
        pool_size = calculate_pool_size(hardware, 'llama3.1:8b')

        assert pool_size == 8

    @patch('services.mafia_service.llm.resource_detection.subprocess.run')
    @patch('services.mafia_service.llm.resource_detection.os.cpu_count')
    @patch('services.mafia_service.llm.resource_detection.platform.system')
    def test_detect_hardware_with_gpu(
        self,
        mock_platform: Mock,
        mock_cpu_count: Mock,
        mock_subprocess_run: Mock,
    ) -> None:
        """Test hardware detection with NVIDIA GPU."""
        mock_platform.return_value = 'Linux'
        mock_cpu_count.return_value = 16

        # Mock nvidia-smi output (2 GPUs with 24GB each)
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = '24576\n24576\n'
        mock_subprocess_run.return_value = mock_result

        # Mock /proc/meminfo using unittest.mock.mock_open
        from unittest.mock import mock_open as mock_open_func

        meminfo_content = 'MemTotal:       65536000 kB\n'
        with patch('builtins.open', mock_open_func(read_data=meminfo_content)):
            hardware = detect_hardware()

        assert hardware.has_cuda is True
        assert hardware.gpu_count == 2
        assert hardware.total_vram_mb == 49152  # 24576 * 2
        assert hardware.cpu_cores == 16
        assert hardware.total_ram_mb == 64000  # 65536000 // 1024

    @patch('services.mafia_service.llm.resource_detection.subprocess.run')
    @patch('services.mafia_service.llm.resource_detection.os.cpu_count')
    @patch('services.mafia_service.llm.resource_detection.platform.system')
    def test_detect_hardware_without_gpu(
        self,
        mock_platform: Mock,
        mock_cpu_count: Mock,
        mock_subprocess_run: Mock,
    ) -> None:
        """Test hardware detection without GPU."""
        mock_platform.return_value = 'Linux'
        mock_cpu_count.return_value = 8

        # Mock nvidia-smi not found
        mock_subprocess_run.side_effect = FileNotFoundError()

        # Mock /proc/meminfo
        from unittest.mock import mock_open as mock_open_func

        meminfo_content = 'MemTotal:       16384000 kB\n'
        with patch('builtins.open', mock_open_func(read_data=meminfo_content)):
            hardware = detect_hardware()

        assert hardware.has_cuda is False
        assert hardware.gpu_count == 0
        assert hardware.total_vram_mb == 0
        assert hardware.cpu_cores == 8
        assert hardware.total_ram_mb == 16000


class TestOllamaRunner:
    """Test OllamaRunner class."""

    @pytest.mark.asyncio
    async def test_ollama_runner_generate_success(self) -> None:
        """Test successful generation via subprocess."""
        runner = OllamaRunner(
            binary_path='ollama',
            model_name='llama3.1:8b',
            timeout=120,
            pool_size=2,
        )

        request = GenerateRequest(
            system_prompt='You are a helpful assistant.',
            messages=[MessageItem(role='user', content='Hello!')],
            max_tokens=100,
        )

        # Mock subprocess execution - return GenerateResponse
        from llm.schemas.llm_schemas import (
            GenerateResponse,
            Usage,
        )

        mock_response = GenerateResponse(
            text='Hello from LLM!',
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )

        async def mock_call_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
            return mock_response

        runner._call_ollama_subprocess = MethodType(mock_call_ollama, runner)

        response = await runner.generate(request)

        assert response.text == 'Hello from LLM!'
        assert response.usage.prompt_tokens == 0
        assert response.usage.completion_tokens == 0
        assert response.usage.total_tokens == 0

    @pytest.mark.asyncio
    async def test_ollama_runner_json_response(self) -> None:
        """Test JSON response parsing."""
        runner = OllamaRunner(
            binary_path='ollama',
            model_name='llama3.1:8b',
            timeout=120,
            pool_size=2,
        )

        request = GenerateRequest(
            system_prompt='You are a helpful assistant.',
            messages=[MessageItem(role='user', content='Hello!')],
            max_tokens=100,
        )

        # Mock subprocess with JSON response
        from llm.schemas.llm_schemas import (
            GenerateResponse,
            Usage,
        )

        mock_response = GenerateResponse(
            text='Hello!',
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )

        async def mock_call_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
            return mock_response

        runner._call_ollama_subprocess = MethodType(mock_call_ollama, runner)

        response = await runner.generate(request)

        assert response.text == 'Hello!'

    @pytest.mark.asyncio
    async def test_ollama_runner_concurrency(self) -> None:
        """Test concurrent generation with semaphore."""
        runner = OllamaRunner(
            binary_path='ollama',
            model_name='llama3.1:8b',
            timeout=120,
            pool_size=2,  # Max 2 concurrent
        )

        request = GenerateRequest(
            system_prompt='Test',
            messages=[MessageItem(role='user', content='Hi')],
            max_tokens=50,
        )

        # Mock subprocess
        from llm.schemas.llm_schemas import (
            GenerateResponse,
            Usage,
        )

        call_count = 0

        async def mock_call_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            return GenerateResponse(
                text='Response',
                usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            )

        runner._call_ollama_subprocess = MethodType(mock_call_ollama, runner)

        # Run 4 concurrent generations (should queue due to pool_size=2)
        import asyncio

        results = await asyncio.gather(
            runner.generate(request),
            runner.generate(request),
            runner.generate(request),
            runner.generate(request),
        )

        assert len(results) == 4
        assert all(r.text == 'Response' for r in results)
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_ollama_runner_subprocess_error(self) -> None:
        """Test subprocess execution error handling."""
        runner = OllamaRunner(
            binary_path='ollama',
            model_name='llama3.1:8b',
            timeout=120,
            pool_size=2,
        )

        request = GenerateRequest(
            system_prompt='Test',
            messages=[MessageItem(role='user', content='Hi')],
            max_tokens=50,
        )

        # Mock subprocess failure
        async def mock_call_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError('Subprocess failed')

        runner._call_ollama_subprocess = MethodType(mock_call_ollama, runner)

        with pytest.raises(RuntimeError, match='Subprocess failed'):
            await runner.generate(request)
