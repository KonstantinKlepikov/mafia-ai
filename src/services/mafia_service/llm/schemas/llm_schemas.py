"""Pydantic schemas for the LLM MCP API request and response."""

from enum import StrEnum

from pydantic import BaseModel, Field


class MessageRole(StrEnum):
    USER = 'user'
    ASSISTANT = 'assistant'
    SYSTEM = 'system'


class MessageItem(BaseModel):
    """Single message in a conversation turn.

    Attrs:

        role (MessageRole): one of 'user', 'assistant', or 'system'
        content (str): message text

    """

    role: MessageRole = Field(
        ...,
        description="Message role: 'user', 'assistant', or 'system'",
    )
    content: str = Field(..., description='Message content')


class GenerateRequest(BaseModel):
    """Request body for POST /mcp/generate.

    Attrs:

        system_prompt (str): instruction context placed before the conversation
        messages (list[MessageItem]): ordered conversation history
                                      (user/assistant turns)
        max_tokens (int): upper bound on generated tokens. Default to 512.

    """

    system_prompt: str = Field(..., description='System prompt for the model')
    messages: list[MessageItem] = Field(
        default_factory=list,
        description='Conversation history (user/assistant turns)',
    )
    max_tokens: int = Field(
        default=512,
        gt=0,
        description='Maximum tokens to generate',
    )


class Usage(BaseModel):
    """Token usage statistics returned by the model."""

    prompt_tokens: int = Field(..., description='Tokens in the prompt')
    completion_tokens: int = Field(..., description='Tokens in the completion')
    total_tokens: int = Field(..., description='Total tokens used')


class GenerateResponse(BaseModel):
    """Response body for POST /mcp/generate."""

    text: str = Field(..., description='Generated text')
    usage: Usage = Field(..., description='Token usage statistics')


class ResetResponse(BaseModel):
    """Response body for POST /mcp/reset."""

    status: str = Field(default='ok', description='Reset status')
