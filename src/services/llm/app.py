"""FastAPI application exposing the MCP-compatible LLM endpoints."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request

from .config import settings
from .schemas.llm_schemas import GenerateRequest, GenerateResponse, ResetResponse
from .core.service import LLMService
from loguru import logger


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[dict[str, LLMService], None]:
    service = LLMService(queue_max_size=settings.llm_queue_max_size)
    await service.start()
    logger.info('LLMService starts!')
    try:
        yield {'service': service}
    finally:
        await service.stop()


app = FastAPI(
    title='LLM MCP Service',
    description=(
        'Stateless MCP-compatible wrapper over Ollama. '
        'Full context is forwarded on every request; no server-side state is retained.'
    ),
    version='0.1.0',
    lifespan=_lifespan,
)


@app.post('/mcp/generate', response_model=GenerateResponse)
async def mcp_generate(
    request: Request,
    llm_request: GenerateRequest,
) -> GenerateResponse:
    """Generate a completion for the given system prompt and message history.

    Each invocation is independent — the full context must be supplied by the caller.
    Requests are serialised through an internal queue to avoid overloading the model.
    """
    try:
        return await request.state.service.generate(llm_request)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f'LLM generation failed: {exc}',
        ) from exc


@app.post('/mcp/reset', response_model=ResetResponse)
async def mcp_reset() -> ResetResponse:
    """No-op reset endpoint.

    The service is stateless, so there is no context to clear.
    Provided for MCP protocol compatibility.
    """
    return ResetResponse()
