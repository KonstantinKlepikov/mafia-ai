"""Unit tests for the LLM MCP service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import ollama
import pytest
from fastapi.testclient import TestClient
from services.llm.schemas.llm_schemas import (
    GenerateRequest,
    GenerateResponse,
    MessageItem,
    ResetResponse,
    Usage,
)
from services.llm.core.service import LLMService, _call_ollama
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# TestGenerateRequest — model validation
# ---------------------------------------------------------------------------


class TestGenerateRequest:
    def test_valid_request_accepted(self) -> None:
        """Test: valid GenerateRequest is constructed without errors"""
        req = _make_request()
        assert req.system_prompt == 'You are a helpful assistant.', (
            'system_prompt should match input'
        )

    def test_default_max_tokens_is_512(self) -> None:
        """Test: max_tokens defaults to 512 when not provided"""
        req = GenerateRequest(
            system_prompt='sys',
            messages=[],
        )
        assert req.max_tokens == 512, 'Default max_tokens must be 512'

    def test_max_tokens_zero_rejected(self) -> None:
        """Test: max_tokens=0 violates gt=0 constraint"""
        with pytest.raises(ValidationError):
            GenerateRequest(system_prompt='sys', messages=[], max_tokens=0)

    def test_max_tokens_negative_rejected(self) -> None:
        """Test: negative max_tokens violates gt=0 constraint"""
        with pytest.raises(ValidationError):
            GenerateRequest(system_prompt='sys', messages=[], max_tokens=-1)

    def test_messages_default_empty(self) -> None:
        """Test: messages list is empty by default"""
        req = GenerateRequest(system_prompt='sys')
        assert req.messages == [], 'messages should default to empty list'

    def test_messages_stored_in_order(self) -> None:
        """Test: multiple messages are preserved in insertion order"""
        msgs = [
            MessageItem(role='user', content='first'),
            MessageItem(role='assistant', content='second'),
        ]
        req = GenerateRequest(system_prompt='sys', messages=msgs)
        assert [m.content for m in req.messages] == ['first', 'second'], (
            'Messages must be stored in insertion order'
        )


# ---------------------------------------------------------------------------
# TestUsageModel
# ---------------------------------------------------------------------------


class TestUsageModel:
    def test_total_tokens_computed_correctly(self) -> None:
        """Test: Usage total_tokens equals prompt + completion"""
        usage = Usage(prompt_tokens=7, completion_tokens=3, total_tokens=10)
        assert usage.total_tokens == 10, (
            'total_tokens must equal prompt_tokens + completion_tokens'
        )


# ---------------------------------------------------------------------------
# TestResetResponse
# ---------------------------------------------------------------------------


class TestResetResponse:
    def test_default_status_is_ok(self) -> None:
        """Test: ResetResponse default status is 'ok'"""
        resp = ResetResponse()
        assert resp.status == 'ok', "Default status must be 'ok'"

    def test_custom_status_accepted(self) -> None:
        """Test: custom status string is stored correctly"""
        resp = ResetResponse(status='cleared')
        assert resp.status == 'cleared', 'Custom status must be stored'


# ---------------------------------------------------------------------------
# TestCallOllama — unit tests for the Ollama adapter function
# ---------------------------------------------------------------------------


class TestCallOllama:
    @pytest.mark.asyncio
    async def test_system_prompt_prepended_as_system_role(self) -> None:
        """Test: system_prompt is prepended as a system-role message"""
        mock_response = MagicMock()
        mock_response.message.content = 'answer'
        mock_response.prompt_eval_count = 4
        mock_response.eval_count = 2

        mock_client = AsyncMock()
        mock_client.chat.return_value = mock_response

        request = _make_request(system_prompt='Be concise.', messages=[])
        await _call_ollama(mock_client, request)

        called_messages = mock_client.chat.call_args.kwargs['messages']
        assert called_messages[0]['role'] == 'system', (
            'First message must have role="system"'
        )
        assert called_messages[0]['content'] == 'Be concise.', (
            'First message content must be the system_prompt'
        )

    @pytest.mark.asyncio
    async def test_history_messages_appended_after_system(self) -> None:
        """Test: conversation history follows the system message"""
        mock_response = MagicMock()
        mock_response.message.content = 'ok'
        mock_response.prompt_eval_count = 5
        mock_response.eval_count = 1

        mock_client = AsyncMock()
        mock_client.chat.return_value = mock_response

        request = _make_request(
            messages=[
                MessageItem(role='user', content='question'),
                MessageItem(role='assistant', content='reply'),
            ]
        )
        await _call_ollama(mock_client, request)

        called_messages = mock_client.chat.call_args.kwargs['messages']
        roles = [m['role'] for m in called_messages]
        assert roles == ['system', 'user', 'assistant'], (
            'Messages must be [system, user, assistant]'
        )

    @pytest.mark.asyncio
    async def test_returned_text_matches_ollama_content(self) -> None:
        """Test: returned GenerateResponse.text equals the model output"""
        mock_response = MagicMock()
        mock_response.message.content = 'generated text'
        mock_response.prompt_eval_count = 8
        mock_response.eval_count = 3

        mock_client = AsyncMock()
        mock_client.chat.return_value = mock_response

        result = await _call_ollama(mock_client, _make_request())

        assert result.text == 'generated text', (
            'GenerateResponse.text must match model output'
        )

    @pytest.mark.asyncio
    async def test_usage_tokens_computed_from_ollama_counts(self) -> None:
        """Test: usage tokens are derived from ollama prompt_eval_count and eval_count"""
        mock_response = MagicMock()
        mock_response.message.content = 'x'
        mock_response.prompt_eval_count = 10
        mock_response.eval_count = 4

        mock_client = AsyncMock()
        mock_client.chat.return_value = mock_response

        result = await _call_ollama(mock_client, _make_request())

        assert result.usage.prompt_tokens == 10, (
            'prompt_tokens must equal prompt_eval_count'
        )
        assert result.usage.completion_tokens == 4, (
            'completion_tokens must equal eval_count'
        )
        assert result.usage.total_tokens == 14, 'total_tokens must be 10 + 4'

    @pytest.mark.asyncio
    async def test_none_eval_counts_treated_as_zero(self) -> None:
        """Test: None ollama counts default to 0 in the Usage model"""
        mock_response = MagicMock()
        mock_response.message.content = 'x'
        mock_response.prompt_eval_count = None
        mock_response.eval_count = None

        mock_client = AsyncMock()
        mock_client.chat.return_value = mock_response

        result = await _call_ollama(mock_client, _make_request())

        assert result.usage.total_tokens == 0, 'None counts must default to 0'


# ---------------------------------------------------------------------------
# TestLLMService — queue and worker behaviour
# ---------------------------------------------------------------------------


class TestLLMService:
    @pytest.mark.asyncio
    async def test_generate_returns_response(self) -> None:
        """Test: LLMService.generate returns the mocked Ollama response"""
        service = LLMService(queue_max_size=5)
        await service.start()

        with patch(
            'services.llm.core.service._call_ollama', new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = _make_response('reply')
            result = await service.generate(_make_request())

        await service.stop()

        assert result.text == 'reply', 'generate() must return mocked response text'

    @pytest.mark.asyncio
    async def test_generate_calls_ollama_once_per_request(self) -> None:
        """Test: each generate() call invokes _call_ollama exactly once"""
        service = LLMService(queue_max_size=5)
        await service.start()

        with patch(
            'services.llm.core.service._call_ollama', new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = _make_response()
            await service.generate(_make_request())

        await service.stop()

        assert mock_call.call_count == 1, '_call_ollama must be called exactly once'

    @pytest.mark.asyncio
    async def test_multiple_requests_all_resolved(self) -> None:
        """Test: multiple concurrent generate() calls are all fulfilled"""
        service = LLMService(queue_max_size=10)
        await service.start()

        responses = ['r1', 'r2', 'r3']
        call_index = 0

        async def side_effect(
            _client: ollama.AsyncClient, _req: GenerateRequest
        ) -> GenerateResponse:
            nonlocal call_index
            text = responses[call_index % len(responses)]
            call_index += 1
            return _make_response(text)

        with patch('services.llm.core.service._call_ollama', side_effect=side_effect):
            results = await asyncio.gather(
                *[service.generate(_make_request()) for _ in range(3)]
            )

        await service.stop()

        texts = {r.text for r in results}
        assert texts == {'r1', 'r2', 'r3'}, (
            'All three concurrent requests must be resolved with distinct responses'
        )

    @pytest.mark.asyncio
    async def test_exception_propagates_to_caller(self) -> None:
        """Test: an Ollama error is propagated as an exception to the caller"""
        service = LLMService(queue_max_size=5)
        await service.start()

        with patch(
            'services.llm.core.service._call_ollama',
            new_callable=AsyncMock,
            side_effect=RuntimeError('ollama down'),
        ):
            with pytest.raises(RuntimeError, match='ollama down'):
                await service.generate(_make_request())

        await service.stop()


# ---------------------------------------------------------------------------
# TestMcpGenerateEndpoint — FastAPI endpoint via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Provide a synchronous TestClient with the app lifespan active."""
    from services.llm.app import app

    with TestClient(app) as c:
        yield c


class TestMcpGenerateEndpoint:
    def test_returns_200_with_text_and_usage(self, client: TestClient) -> None:
        """Test: POST /mcp/generate returns 200 with text and usage fields"""
        mock_resp = _make_response('generated')

        with patch(
            'services.llm.core.service._call_ollama', new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = mock_resp
            response = client.post(
                '/mcp/generate',
                json={
                    'system_prompt': 'sys',
                    'messages': [{'role': 'user', 'content': 'hi'}],
                    'max_tokens': 64,
                },
            )

        assert response.status_code == 200, (
            'Endpoint must return HTTP 200 for a valid request'
        )
        body = response.json()
        assert body['text'] == 'generated', 'Response body must contain "text" field'
        assert 'usage' in body, 'Response body must contain "usage" field'

    def test_missing_system_prompt_returns_422(self, client: TestClient) -> None:
        """Test: POST /mcp/generate without system_prompt returns 422"""
        response = client.post(
            '/mcp/generate',
            json={'messages': [], 'max_tokens': 64},
        )
        assert response.status_code == 422, (
            'Missing required field must result in HTTP 422'
        )

    def test_invalid_max_tokens_returns_422(self, client: TestClient) -> None:
        """Test: POST /mcp/generate with max_tokens=0 returns 422"""
        response = client.post(
            '/mcp/generate',
            json={'system_prompt': 'sys', 'messages': [], 'max_tokens': 0},
        )
        assert response.status_code == 422, 'max_tokens=0 must result in HTTP 422'

    def test_ollama_error_returns_503(self, client: TestClient) -> None:
        """Test: an Ollama failure results in HTTP 503"""
        with patch(
            'services.llm.core.service._call_ollama',
            new_callable=AsyncMock,
            side_effect=ConnectionError('timeout'),
        ):
            response = client.post(
                '/mcp/generate',
                json={'system_prompt': 'sys', 'messages': [], 'max_tokens': 32},
            )

        assert response.status_code == 503, (
            'Ollama connection error must result in HTTP 503'
        )


# ---------------------------------------------------------------------------
# TestMcpResetEndpoint — FastAPI endpoint via TestClient
# ---------------------------------------------------------------------------


class TestMcpResetEndpoint:
    def test_returns_200_with_status_ok(self, client: TestClient) -> None:
        """Test: POST /mcp/reset returns 200 with status='ok'"""
        response = client.post('/mcp/reset')
        assert response.status_code == 200, 'Reset endpoint must return HTTP 200'
        assert response.json()['status'] == 'ok', "Reset response must have status='ok'"

    def test_idempotent_multiple_calls(self, client: TestClient) -> None:
        """Test: calling /mcp/reset multiple times always returns ok"""
        for _ in range(3):
            response = client.post('/mcp/reset')
            assert response.status_code == 200, 'Every reset call must return HTTP 200'
            assert response.json()['status'] == 'ok', (
                "Every reset call must return status='ok'"
            )
