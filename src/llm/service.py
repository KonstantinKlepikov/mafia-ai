from loguru import logger

from ..config import MafiaServiceSettings
from .ollama_runner import OllamaRunner
from .resource_detection import calculate_pool_size, detect_hardware
from .schemas.llm_schemas import GenerateRequest, GenerateResponse


class LLMService:
    """Local Ollama inference via subprocess.

    Uses OllamaRunner for direct model execution without HTTP overhead.
    """

    def __init__(self, settings: MafiaServiceSettings) -> None:
        """Initialize LLM service with OllamaRunner.

        Args:
            settings: Unified service settings.

        """
        # Auto-detect pool size if not specified
        pool_size = settings.llm_pool_size
        if pool_size is None or pool_size == 0:
            hardware = detect_hardware()
            pool_size = calculate_pool_size(hardware, settings.ollama_model)
            logger.info(f'Auto-detected pool size: {pool_size}')
        else:
            logger.info(f'Using manual pool size: {pool_size}')

        self._runner = OllamaRunner(
            binary_path=settings.ollama_binary_path,
            model_name=settings.ollama_model,
            timeout=settings.ollama_timeout,
            pool_size=pool_size,
        )

    async def start(self) -> None:
        """Start the service (no-op for subprocess implementation)."""
        logger.info('LLMService started with OllamaRunner')

    async def stop(self) -> None:
        """Stop the service and cleanup resources."""
        await self._runner.close()
        logger.info('LLMService stopped')

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate a response using OllamaRunner subprocess.

        Args:
            request: Generation request with system prompt and messages.

        Returns:
            Generated response with text and token usage.

        Raises:
            RuntimeError: If ollama subprocess fails.
            subprocess.TimeoutExpired: If subprocess exceeds timeout.

        """
        return await self._runner.generate(request)
