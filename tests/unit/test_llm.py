from types import MethodType, SimpleNamespace

from core.llm import LLM
from schemas.llm_schemas import MessageItem, MessageRequest


class TestLLM:
    """Test LLM class."""

    async def test_llm_message_success(self, llm: LLM) -> None:
        """Test successful generation via subprocess."""

        request = MessageRequest(
            system_prompt='You are a helpful assistant.',
            conversation='Some previous spiking',
            messages=[MessageItem(role='user', content='Hello!')],
            max_tokens=100,
        )

        mock_response = SimpleNamespace(
            message=SimpleNamespace(content='Hello from LLM!')
        )

        async def mock_call_ollama(*args, **kwargs):  # type: ignore[no-untyped-def]
            return mock_response

        llm.ollama.chat = MethodType(mock_call_ollama, llm.ollama)  # type: ignore

        response = await llm.message(request=request)

        assert response == mock_response.message.content, 'wrong response'
