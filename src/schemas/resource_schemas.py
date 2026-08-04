from typing import Annotated

from pydantic import BaseModel, Field

PositiveInt = Annotated[int, Field(ge=0)]
PositiveCPUInt = Annotated[int, Field(ge=1)]


class NvidiaGPUInfo(BaseModel):
    """NVIDIA GPU info

    Attrs:
        has_cuda: True if NVIDIA GPU with CUDA is available.
        gpu_count: Number of available GPUs (0 if no GPU).
        total_vram_mb: Total VRAM across all GPUs in MB (0 if no GPU).

    NOTE: deprecated

    """

    has_cuda: bool
    gpu_count: PositiveInt
    total_vram_mb: PositiveInt


class HardwareInfo(NvidiaGPUInfo):
    """Hardware resource information.

    Attrs:
        has_cuda: True if NVIDIA GPU with CUDA is available.
        gpu_count: Number of available GPUs (0 if no GPU).
        total_vram_mb: Total VRAM across all GPUs in MB (0 if no GPU).
        cpu_cores: Number of CPU cores.
        total_ram_mb: Total system RAM in MB.

    NOTE: deprecated

    """

    cpu_cores: PositiveCPUInt
    total_ram_mb: PositiveInt
