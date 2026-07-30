import os
import platform
import subprocess

from loguru import logger

from schemas import HardwareInfo, NvidiaGPUInfo, ResourceException


def _detect_nvidia_gpu() -> NvidiaGPUInfo:
    """Detect NVIDIA GPU via nvidia-smi.

    Returns:
        Tuple of (has_cuda, gpu_count, total_vram_mb).

    """
    has_cuda = False
    gpu_count = 0
    total_vram_mb = 0

    try:
        result = subprocess.run(
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
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            vram_values = [int(line.strip()) for line in lines if line.strip()]
            if vram_values:
                has_cuda = True
                gpu_count = len(vram_values)
                total_vram_mb = sum(vram_values)
                logger.info(
                    f'Detected {gpu_count} NVIDIA GPU(s) '
                    f'with total {total_vram_mb} MB VRAM'
                )
    except FileNotFoundError:
        logger.info('nvidia-smi not found, assuming no CUDA GPU')
    except subprocess.TimeoutExpired:
        logger.warning('nvidia-smi timed out, assuming no CUDA GPU')
    except Exception as exc:
        logger.warning(f'Failed to detect GPU via nvidia-smi: {exc.__str__()}')

    return NvidiaGPUInfo(
        has_cuda=has_cuda,
        gpu_count=gpu_count,
        total_vram_mb=total_vram_mb,
    )


def _detect_system_ram() -> int:
    """Detect total system RAM in MB.

    Returns:
        Total RAM in MB (defaults to 8192 if detection fails).

    """
    total_ram_mb = 0

    if platform.system() == 'Linux':
        try:
            with open('/proc/meminfo', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        # MemTotal is in KB
                        total_ram_kb = int(line.split()[1])
                        total_ram_mb = total_ram_kb // 1024
                        break
        except Exception as exc:
            logger.warning(f'Failed to read /proc/meminfo: {exc.__str__()}')

    if total_ram_mb == 0:
        # Fallback: assume 8GB as safe default
        total_ram_mb = 8192
        logger.warning(f'Could not detect RAM, using default: {total_ram_mb} MB')
    elif total_ram_mb < 8192:
        raise ResourceException(
            f'Not enough RAM available: {total_ram_mb} MB < 8192 MB'
        )
    else:
        logger.info(f'Detected {total_ram_mb} MB total RAM')

    return total_ram_mb


def detect_hardware() -> HardwareInfo:
    """Detect available hardware resources for LLM inference.

    Returns:
        HardwareInfo with detected resources.

    """
    nvidia = _detect_nvidia_gpu()
    cpu_cores = os.cpu_count() or 1
    logger.info(f'Detected {cpu_cores} CPU cores')
    total_ram_mb = _detect_system_ram()

    return HardwareInfo(
        has_cuda=nvidia.has_cuda,
        gpu_count=nvidia.gpu_count,
        total_vram_mb=nvidia.total_vram_mb,
        cpu_cores=cpu_cores,
        total_ram_mb=total_ram_mb,
    )


def calculate_pool_size(hardware: HardwareInfo, model_name: str) -> int:
    """Calculate optimal number of model instances for pool.

    NOTE: preference to CUDA. If no cxuda -> use CPU. If oversize model -> raise!

    Args:
        hardware: Detected hardware info.
        model_name: Name of the Ollama model (e.g. 'llama3.1:8b').

    Raises:
        ResourceException: model to large

    Returns:
        Number of model instances to run in parallel (min 1, max 8).

    """
    # Rough estimate: small models ~4GB VRAM or ~2GB RAM per instance
    # Adjust based on model name if possible
    if '70b' in model_name.lower() or '65b' in model_name.lower():
        # Large models: ~40GB VRAM or ~20GB RAM
        vram_per_model = 40 * 1024
        ram_per_model = 20 * 1024
    elif '13b' in model_name.lower() or '14b' in model_name.lower():
        # Medium models: ~8GB VRAM or ~4GB RAM
        vram_per_model = 8 * 1024
        ram_per_model = 4 * 1024
    else:
        # Small models (7b, 8b, etc): ~4GB VRAM or ~2GB RAM
        vram_per_model = 4 * 1024
        ram_per_model = 2 * 1024

    if hardware.has_cuda and hardware.total_vram_mb > 0:
        # GPU available: use VRAM capacity
        # Keep 20% reserved for system
        usable_vram = int(hardware.total_vram_mb * 0.8)
        pool_size = max(0, usable_vram // vram_per_model)
        logger.info(
            f'GPU mode: usable VRAM {usable_vram} MB, estimated {pool_size} instances'
        )
    else:
        # CPU mode: use RAM capacity
        # Keep 40% reserved for system and other processes
        usable_ram = int(hardware.total_ram_mb * 0.6)
        pool_size = max(0, usable_ram // ram_per_model)
        logger.info(
            f'CPU mode: usable RAM {usable_ram} MB, estimated {pool_size} instances'
        )

    # Cap at reasonable maximum (8 instances)
    pool_size = min(pool_size, 8)

    # Also cap by CPU cores (no point running more models than cores in CPU mode)
    if not hardware.has_cuda:
        pool_size = min(pool_size, hardware.cpu_cores)

    logger.info(f'Final pool size for model {model_name}: {pool_size}')

    if pool_size == 0:
        raise ResourceException('Model to large')

    return pool_size
