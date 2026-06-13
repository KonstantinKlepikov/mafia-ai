"""Model pool for parallel LLM inference with load balancing.

Manages multiple Ollama client instances for concurrent request processing.
"""

import asyncio
from collections.abc import Sequence

import ollama
from loguru import logger

from ..schemas.llm_schemas import GenerateRequest, GenerateResponse, Usage


class ModelPool:
    """Pool of Ollama clients for parallel inference.

    Args:
        ollama_url: Base URL of the Ollama server.
        model_name: Name of the model to use (e.g. 'llama3.1:8b').
        pool_size: Number of concurrent client instances.

    """

    def __init__(self, ollama_url: str, model_name: str, pool_size: int) -> None:
        self._ollama_url = ollama_url
        self._model_name = model_name
        self._pool_size = max(1, pool_size)

        # Create pool_size clients
        self._clients: Sequence[ollama.AsyncClient] = [
            ollama.AsyncClient(host=ollama_url) for _ in range(self._pool_size)
        ]

        # Round-robin index for load balancing
        self._next_client_idx = 0
        self._client_lock = asyncio.Lock()

        # Semaphore to limit concurrent requests to pool_size
        self._semaphore = asyncio.Semaphore(self._pool_size)

        logger.info(
            f'ModelPool initialized: {self._pool_size} clients for {model_name}'
        )

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate response using an available client from the pool.

        Args:
            request: Generation request with system prompt and messages.

        Returns:
            Generated response with text and token usage.

        Raises:
            Exception: If Ollama client call fails.

        """
        async with self._semaphore:
            client = await self._pick_client()
            return await self._call_ollama(client, request)

    async def _pick_client(self) -> ollama.AsyncClient:
        """Pick next client using round-robin strategy.

        Returns:
            Ollama async client from the pool.

        """
        async with self._client_lock:
            client = self._clients[self._next_client_idx]
            self._next_client_idx = (self._next_client_idx + 1) % self._pool_size
            return client

    async def _call_ollama(
        self, client: ollama.AsyncClient, request: GenerateRequest
    ) -> GenerateResponse:
        """Send a stateless generation request to Ollama.

        Prepends the system prompt as a 'system' role message and forwards
        the full conversation history on every call.

        Args:
            client: Ollama async client.
            request: Generation request.

        Returns:
            Generated response with text and token usage.

        """
        messages: list[dict[str, str]] = [
            {'role': 'system', 'content': request.system_prompt}
        ]
        messages.extend(
            {'role': m.role, 'content': m.content} for m in request.messages
        )

        response = await client.chat(
            model=self._model_name,
            messages=messages,  # type: ignore[arg-type]
            options={'num_predict': request.max_tokens},
        )

        prompt_tokens: int = response.prompt_eval_count or 0
        completion_tokens: int = response.eval_count or 0

        return GenerateResponse(
            text=response.message.content,
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    async def close(self) -> None:
        """Close all clients in the pool (optional cleanup).

        Note: ollama.AsyncClient does not require explicit cleanup,
        but this method is provided for API consistency.
        """
        logger.info(f'ModelPool closed ({self._pool_size} clients)')
