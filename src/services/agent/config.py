from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    # Unique agent identifier, e.g. "agent-1"
    agent_id: str

    # Persona ID in VectorDB — either a UUID or a name like "persona_1_good_natured"
    persona_id: str

    # AMQP connection URL for RabbitMQ
    amqp_url: str

    # Base URL of the LLM MCP service
    llm_url: str

    # ChromaDB server hostname and port
    vectordb_host: str
    vectordb_port: int

    # Maximum tokens for regular messages; voting uses a shorter limit
    message_max_tokens: int
    vote_max_tokens: int

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')
