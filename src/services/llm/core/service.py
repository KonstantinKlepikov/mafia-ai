"""LLM service: asyncio.Queue-based rate limiter wrapping Ollama chat API.

Each call to `generate()` is enqueued and processed by a single background
worker, preventing parallel requests from overloading the model.
"""

import asyncio
from dataclasses import dataclass

import ollama

from ..config import settings
from ..schemas.llm_schemas import GenerateRequest, GenerateResponse, Usage


@dataclass
class _QueueItem:
    request: GenerateRequest
    future: 'asyncio.Future[GenerateResponse]'


async def _call_ollama(
    client: ollama.AsyncClient, request: GenerateRequest
) -> GenerateResponse:
    """Send a stateless generation request to Ollama.

    Prepends the system prompt as a 'system' role message and forwards the
    full conversation history on every call (no server-side context retained).
    """

    messages: list[dict[str, str]] = [
        {'role': 'system', 'content': request.system_prompt}
    ]
    messages.extend({'role': m.role, 'content': m.content} for m in request.messages)

    response = await client.chat(
        model=settings.ollama_model,
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


class LLMService:
    """Rate-limited facade over the Ollama chat API.

    Requests are serialised through an `asyncio.Queue` so that the model
    receives at most one concurrent call at a time.
    """

    def __init__(self, queue_max_size: int) -> None:
        self._queue: asyncio.Queue[_QueueItem] = asyncio.Queue(maxsize=queue_max_size)
        self._worker_task: asyncio.Task[None] | None = None
        self._client: ollama.AsyncClient = ollama.AsyncClient(
            host=settings.ollama_url.encoded_string()
        )

    async def start(self) -> None:
        """Start the background worker that drains the request queue."""
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Cancel the background worker and wait for it to finish."""
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _worker(self) -> None:
        """Process queue items sequentially, one at a time."""
        while True:
            item = await self._queue.get()
            try:
                result = await _call_ollama(self._client, item.request)
                if not item.future.done():
                    item.future.set_result(result)
            except Exception as exc:  # noqa: BLE001
                if not item.future.done():
                    item.future.set_exception(exc)
            finally:
                self._queue.task_done()

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Enqueue a generation request and await the result.

        Blocks if the queue is full until a slot becomes available.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[GenerateResponse] = loop.create_future()
        await self._queue.put(_QueueItem(request=request, future=future))
        return await future
