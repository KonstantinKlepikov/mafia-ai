from pydantic import BaseModel, Field

from schemas.enums import Role


class MessageItem(BaseModel):
    """Single message in a conversation turn.

    Attrs:

        role (Role): one of 'user', 'assistant', or 'system'
        content (str): message text

    """

    role: Role = Field(..., description='Message role')
    content: str = Field(..., description='Message content')


class MessageRequest(BaseModel):
    """Request body.

    Attrs:

        system_prompt (str): instruction context placed before the conversation
        summarisation (str): summarized conversation history
        max_tokens (int): upper bound on generated tokens. Default to 512.

    """

    system_prompt: str = Field(..., description='System prompt for the model')
    conversation: str = Field(..., description='Summarized conversation history')
    messages: list[MessageItem] = Field(
        default_factory=list,
        description='Conversation history (user/assistant turns)',
    )
    max_tokens: int = Field(
        default=512,
        gt=0,
        description='Maximum tokens to generate',
    )

    def request(self) -> list[dict[str, str]]:
        msg = [
            {
                'role': Role.SYSTEM.value,
                'content': self.system_prompt,
            },
        ]
        if self.conversation:
            msg.append(
                {
                    'role': Role.SYSTEM.value,
                    'content': self.conversation,
                }
            )
        for m in self.messages:
            msg.append(
                {
                    'role': m.role.value,
                    'content': m.content,
                }
            )
        return msg
