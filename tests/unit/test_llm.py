from types import MethodType

from core.llm import LLM
from schemas.llm_schemas import GenerateRequest, GenerateResponse, MessageItem, Usage


class TestLLM:
    """Test LLM class.

    TODO: test otger methods
    """

    async def test_llm_generate_success(self, llm: LLM) -> None:
        """Test successful generation via subprocess."""

        request = GenerateRequest(
            system_prompt='You are a helpful assistant.',
            messages=[MessageItem(role='user', content='Hello!')],
            max_tokens=100,
        )

        mock_response = GenerateResponse(
            text='Hello from LLM!',
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )

        async def mock_call_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
            return mock_response

        llm._call_ollama_subprocess = MethodType(mock_call_ollama, llm)  # type: ignore

        response = await llm.generate(request)

        assert response.text == 'Hello from LLM!', 'wrong response'
        assert response.usage.prompt_tokens == 0, 'wrong prompt tokens'
        assert response.usage.completion_tokens == 0, 'wrong completions tokens'
        assert response.usage.total_tokens == 0, 'wrong total tokens'

    # async def test_ollama_runner_concurrency(self) -> None:
    #     """Test concurrent generation with semaphore."""
    #     runner = OllamaRunner(
    #         binary_path='ollama',
    #         model_name='llama3.1:8b',
    #         timeout=120,
    #         pool_size=2,  # Max 2 concurrent
    #     )

    #     request = GenerateRequest(
    #         system_prompt='Test',
    #         messages=[MessageItem(role='user', content='Hi')],
    #         max_tokens=50,
    #     )

    #     # Mock subprocess
    #     from schemas.llm_schemas import (
    #         GenerateResponse,
    #         Usage,
    #     )

    #     call_count = 0

    #     async def mock_call_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
    #         nonlocal call_count
    #         call_count += 1
    #         return GenerateResponse(
    #             text='Response',
    #             usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    #         )

    #     runner._call_ollama_subprocess = MethodType(mock_call_ollama, runner)

    #     # Run 4 concurrent generations (should queue due to pool_size=2)
    #     import asyncio

    #     results = await asyncio.gather(
    #         runner.generate(request),
    #         runner.generate(request),
    #         runner.generate(request),
    #         runner.generate(request),
    #     )

    #     assert len(results) == 4
    #     assert all(r.text == 'Response' for r in results)
    #     assert call_count == 4

    # async def test_ollama_runner_subprocess_error(self) -> None:
    #     """Test subprocess execution error handling."""
    #     runner = OllamaRunner(
    #         binary_path='ollama',
    #         model_name='llama3.1:8b',
    #         timeout=120,
    #         pool_size=2,
    #     )

    #     request = GenerateRequest(
    #         system_prompt='Test',
    #         messages=[MessageItem(role='user', content='Hi')],
    #         max_tokens=50,
    #     )

    #     # Mock subprocess failure
    #     async def mock_call_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
    #         raise RuntimeError('Subprocess failed')

    #     runner._call_ollama_subprocess = MethodType(mock_call_ollama, runner)

    #     with pytest.raises(RuntimeError, match='Subprocess failed'):
    #         await runner.generate(request)
