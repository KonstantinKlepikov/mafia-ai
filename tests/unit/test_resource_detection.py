import subprocess
from unittest.mock import Mock, patch

import pytest

from core.resource_detection import (
    _detect_nvidia_gpu,
    _detect_system_ram,
    calculate_pool_size,
    detect_hardware,
)
from schemas import HardwareInfo, ResourceException


class TestNvidiaGpu:
    """Test nvidia gpu detection."""

    @patch('core.resource_detection.subprocess.run')
    def test_detect_nvidia_gpu_success(self, mock_subprocess_run: Mock) -> None:
        """Test _detect_nvidia_gpu success with NVIDIA GPU available."""
        mock_result = Mock(returncode=0, stdout='24576\n3072\n')
        mock_subprocess_run.return_value = mock_result

        gpu_info = _detect_nvidia_gpu()

        assert gpu_info.has_cuda is True, 'hasnt cuda'
        assert gpu_info.gpu_count == 2, f'wrong gpu count {gpu_info.gpu_count}'
        assert gpu_info.total_vram_mb == 27648, (
            f'wrong gpu vram mb {gpu_info.total_vram_mb}'
        )
        mock_subprocess_run.assert_called_once_with(
            [
                'nvidia-smi',
                '--query-gpu=memory.total',
                '--format=csv,noheader,nounits',
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )

    @patch('core.resource_detection.subprocess.run')
    def test_detect_nvidia_gpu_when_command_missing(
        self,
        mock_subprocess_run: Mock,
    ) -> None:
        """Test _detect_nvidia_gpu when nvidia-smi is not installed."""
        mock_subprocess_run.side_effect = FileNotFoundError()

        gpu_info = _detect_nvidia_gpu()

        assert gpu_info.has_cuda is False, 'hasnt cuda'
        assert gpu_info.gpu_count == 0, f'wrong gpu count {gpu_info.gpu_count}'
        assert gpu_info.total_vram_mb == 0, (
            f'wrong gpu vram mb {gpu_info.total_vram_mb}'
        )

    @patch('core.resource_detection.subprocess.run')
    def test_detect_nvidia_gpu_when_command_times_out(
        self,
        mock_subprocess_run: Mock,
    ) -> None:
        """Test _detect_nvidia_gpu when nvidia-smi times out."""
        mock_subprocess_run.side_effect = subprocess.TimeoutExpired(
            cmd='nvidia-smi', timeout=5
        )

        gpu_info = _detect_nvidia_gpu()

        assert gpu_info.has_cuda is False, 'hasnt cuda'
        assert gpu_info.gpu_count == 0, f'wrong gpu count {gpu_info.gpu_count}'
        assert gpu_info.total_vram_mb == 0, (
            f'wrong gpu vram mb {gpu_info.total_vram_mb}'
        )


class TestSystemRam:
    """Test system RAM detection."""

    @patch('core.resource_detection.platform.system')
    def test_detect_system_ram_linux_reads_meminfo(
        self,
        mock_platform: Mock,
    ) -> None:
        """Test RAM detection on Linux using /proc/meminfo."""
        mock_platform.return_value = 'Linux'

        from unittest.mock import mock_open as mock_open_func

        meminfo_content = 'MemTotal:       16777216 kB\n'
        with patch('builtins.open', mock_open_func(read_data=meminfo_content)):
            total_ram_mb = _detect_system_ram()

        assert total_ram_mb == 16384, 'wrong total ram'

    @patch('core.resource_detection.platform.system')
    def test_detect_system_ram_linux_raises_for_too_little_ram(
        self,
        mock_platform: Mock,
    ) -> None:
        """Test RAM detection raises when detected memory is below threshold."""
        mock_platform.return_value = 'Linux'

        from unittest.mock import mock_open as mock_open_func

        meminfo_content = 'MemTotal:       4096 kB\n'
        with patch('builtins.open', mock_open_func(read_data=meminfo_content)):
            with pytest.raises(ResourceException, match='RAM'):
                _detect_system_ram()

    @patch('core.resource_detection.platform.system')
    def test_detect_system_ram_linux_uses_default_when_missing(
        self,
        mock_platform: Mock,
    ) -> None:
        """Test RAM detection falls back to default when MemTotal is absent."""
        mock_platform.return_value = 'Linux'

        from unittest.mock import mock_open as mock_open_func

        meminfo_content = 'MemFree:       1024 kB\n'
        with patch('builtins.open', mock_open_func(read_data=meminfo_content)):
            total_ram_mb = _detect_system_ram()

        assert total_ram_mb == 8192, 'wrong total ram'

    @patch('core.resource_detection.platform.system')
    def test_detect_system_ram_non_linux_uses_default(
        self,
        mock_platform: Mock,
    ) -> None:
        """Test RAM detection falls back to default on non-Linux systems."""
        mock_platform.return_value = 'Darwin'

        total_ram_mb = _detect_system_ram()

        assert total_ram_mb == 8192, 'wrong total ram'


class TestCalculatePoolSize:
    """Test calculate pool size."""

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
        assert pool_size == 1, f'wrong pool size {pool_size}'

    def test_calculate_pool_size_gpu_oversize(self) -> None:
        """Test pool size calculation for model, that can be used."""
        hardware = HardwareInfo(
            has_cuda=True,
            gpu_count=2,
            total_vram_mb=12 * 1024,  # 12GB total
            cpu_cores=16,
            total_ram_mb=64 * 1024,
        )

        with pytest.raises(ResourceException):
            calculate_pool_size(hardware, 'llama3.1:70b')

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
        assert pool_size == 4, f'wrong pool size {pool_size}'

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
        assert pool_size == 4, f'wrong pool size {pool_size}'

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

        assert pool_size == 8, f'wrong pool size {pool_size}'

    def test_calculate_pool_size_cpu_oversize(self) -> None:
        """Test pool size calculation for model, that can be used."""
        hardware = HardwareInfo(
            has_cuda=False,
            gpu_count=0,
            total_vram_mb=0,
            cpu_cores=8,
            total_ram_mb=16 * 1024,  # 16GB
        )

        with pytest.raises(ResourceException):
            calculate_pool_size(hardware, 'llama3.1:70b')


class TestDetectHardware:
    """Test detect hardware"""

    @patch('core.resource_detection.subprocess.run')
    @patch('core.resource_detection.os.cpu_count')
    @patch('core.resource_detection.platform.system')
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

    @patch('core.resource_detection.subprocess.run')
    @patch('core.resource_detection.os.cpu_count')
    @patch('core.resource_detection.platform.system')
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
