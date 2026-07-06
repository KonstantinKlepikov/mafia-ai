import pytest
from pydantic import ValidationError

from schemas.llm_schemas import (
    GenerateRequest,
    GenerateResponse,
    MessageItem,
    Usage,
)


def _make_usage(prompt: int = 10, completion: int = 5) -> Usage:
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
    )


def _make_response(text: str = 'hello') -> GenerateResponse:
    return GenerateResponse(text=text, usage=_make_usage())


def _make_request(**kwargs) -> GenerateRequest:
    defaults = {
        'system_prompt': 'You are a helpful assistant.',
        'messages': [MessageItem(role='user', content='Hi')],
        'max_tokens': 128,
    }
    defaults.update(kwargs)
    return GenerateRequest(**defaults)


class TestGenerateRequest:
    """Test GenerateRequest model validation."""

    def test_valid_request_accepted(self) -> None:
        """Test valid GenerateRequest is constructed without errors."""
        req = _make_request()
        assert req.system_prompt == 'You are a helpful assistant.', (
            'system_prompt should match input'
        )

    def test_default_max_tokens_is_512(self) -> None:
        """Test max_tokens defaults to 512 when not provided."""
        req = GenerateRequest(
            system_prompt='sys',
            messages=[],
        )
        assert req.max_tokens == 512, 'default max_tokens must be 512'

    def test_max_tokens_zero_rejected(self) -> None:
        """Test max_tokens=0 violates gt=0 constraint."""
        with pytest.raises(ValidationError):
            GenerateRequest(system_prompt='sys', messages=[], max_tokens=0)

    def test_max_tokens_negative_rejected(self) -> None:
        """Test negative max_tokens violates gt=0 constraint."""
        with pytest.raises(ValidationError):
            GenerateRequest(system_prompt='sys', messages=[], max_tokens=-1)

    def test_messages_default_empty(self) -> None:
        """Test messages list is empty by default."""
        req = GenerateRequest(system_prompt='sys')
        assert req.messages == [], 'messages should default to empty list'

    def test_messages_stored_in_order(self) -> None:
        """Test multiple messages are preserved in insertion order."""
        msgs = [
            MessageItem(role='user', content='first'),
            MessageItem(role='assistant', content='second'),
        ]
        req = GenerateRequest(system_prompt='sys', messages=msgs)
        assert [m.content for m in req.messages] == ['first', 'second'], (
            'messages must be stored in insertion order'
        )
