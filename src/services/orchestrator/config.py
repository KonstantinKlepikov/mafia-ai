from pydantic_settings import BaseSettings, SettingsConfigDict


class OrchestratorSettings(BaseSettings):
    """Orchestrator service settings loaded from environment variables.

    Attrs:
        amqp_url: AMQP connection URL for RabbitMQ.
        vectordb_host: ChromaDB server hostname.
        vectordb_port: ChromaDB server HTTP port.
        agent_count: Total number of agents in the game.
        mafia_count: Number of mafia agents to assign.
        phase_duration_seconds: Max duration per NIGHT / DAY speaking phase.
        vote_timeout_seconds: Timeout when waiting for all votes to arrive.
        agent_http_port: Base port; agent-n listens on base+n (8101..8110).
        agent_host_pattern: Docker service hostname pattern; ``{n}`` = agent index.
        docker_socket_url: Docker socket URL for container lifecycle management.

    """

    amqp_url: str

    vectordb_host: str
    vectordb_port: int

    agent_count: int
    mafia_count: int

    phase_duration_seconds: int
    vote_timeout_seconds: int

    agent_http_port: int
    agent_host_pattern: str

    docker_socket_url: str = 'unix:///var/run/docker.sock'

    model_config = SettingsConfigDict(env_prefix='', extra='ignore')
