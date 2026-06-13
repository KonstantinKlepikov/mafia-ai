"""LLM service: ModelPool-based parallel inference wrapping Ollama chat API.

Requests are handled by a pool of Ollama clients for parallel processing.
"""

from loguru import logger

from ..config import settings
from ..schemas.llm_schemas import GenerateRequest, GenerateResponse
from .pool import ModelPool
from .resource_detection import calculate_pool_size, detect_hardware


class LLMService:
    """Parallel inference facade over the Ollama chat API.

    Uses a ModelPool to handle multiple concurrent requests.
    """

    def __init__(self, pool_size: int | None = None) -> None:
        """Initialize LLM service with model pool.

        Args:
            pool_size: Number of parallel model instances (None = auto-detect).

        """
        # Auto-detect pool size if not specified
        if pool_size is None or pool_size == 0:
            hardware = detect_hardware()
            pool_size = calculate_pool_size(hardware, settings.ollama_model)
            logger.info(f'Auto-detected pool size: {pool_size}')
        else:
            logger.info(f'Using manual pool size: {pool_size}')

        self._pool = ModelPool(
            ollama_url=settings.ollama_url.unicode_string(),
            model_name=settings.ollama_model,
            pool_size=pool_size,
        )

    async def start(self) -> None:
        """Start the service (no-op for pool-based implementation)."""
        logger.info('LLMService started with ModelPool')

    async def stop(self) -> None:
        """Stop the service and cleanup resources."""
        await self._pool.close()
        logger.info('LLMService stopped')

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate a response using the model pool.

        Args:
            request: Generation request with system prompt and messages.

        Returns:
            Generated response with text and token usage.

        Raises:
            Exception: If Ollama client call fails.

        """
        return await self._pool.generate(request)
