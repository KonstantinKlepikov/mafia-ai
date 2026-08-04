from loguru import logger
from ollama import AsyncClient

from config import MafiaSettings
from schemas.llm_schemas import MessageRequest


class LLM:
    """Local Ollama inference via subprocess."""

    def __init__(self, settings: MafiaSettings, ollama: AsyncClient) -> None:
        """Initialize LLM.

        Args:
            settings (MafiaSettings): Unified service settings.

        """
        self.settings = settings
        self.ollama = ollama

    async def message(self, request: MessageRequest) -> str:
        """Request ollama model for message.

        TODO: use generate, not a chat

        """
        messages = request.request()
        response = await self.ollama.chat(
            model=self.settings.ollama_model,
            messages=messages,
            format='json',
            options={'num_predict': request.max_tokens},
        )

        if response.message.content is None:
            logger.warning('Empty ollama response')

        return response.message.content if response.message.content else ''
