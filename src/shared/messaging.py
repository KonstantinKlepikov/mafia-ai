"""Shared RabbitMQ messaging client for mafia-ai services.

Uses the `game_events` topic exchange declared in infra/rabbitmq/definitions.json.
Queues are created dynamically (exclusive, auto-delete) per subscriber so that
each service instance gets its own copy of matching messages.
"""

from collections.abc import Awaitable, Callable

import aio_pika

from .models import Message, VoteEvent

EXCHANGE_NAME = 'game_events'

# Payload types published to the exchange
Payload = Message | VoteEvent

# Callback signature: (routing_key, raw JSON body)
MessageCallback = Callable[[str, bytes], Awaitable[None]]


class MessagingClient:
    """Async RabbitMQ client backed by aio_pika.

    Provides `publish` and `subscribe` over the `game_events` topic exchange.
    Queues for subscribers are exclusive and auto-delete — they exist only while
    the consumer connection is open, matching the per-service ephemerality model.

    Usage::

        async with MessagingClient("amqp://guest:guest@rabbitmq/") as client:
            await client.subscribe("message.all", my_callback)
            await client.publish("message.all", my_message)

    Args:
        amqp_url: AMQP connection URL, e.g. ``amqp://user:pass@host/``.

    """

    def __init__(self, amqp_url: str) -> None:
        self._url = amqp_url
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self) -> None:
        """Open connection, channel and declare the exchange."""
        await self.close()
        self._connection = await aio_pika.connect_robust(self._url)
        self._channel = await self._connection.channel()
        # Declare is idempotent — safe to call even if the exchange already exists
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

    async def close(self) -> None:
        """Close the underlying connection (also closes channel and consumers)."""
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
            self._channel = None
            self._exchange = None

    async def __aenter__(self) -> 'MessagingClient':
        await self.connect()
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()

    def _require_connected(
        self,
    ) -> tuple[aio_pika.abc.AbstractChannel, aio_pika.abc.AbstractExchange]:
        if self._channel is None or self._exchange is None:
            raise RuntimeError(
                'MessagingClient is not connected. Call connect() '
                'or use as async context manager.'
            )
        return self._channel, self._exchange

    async def publish(self, routing_key: str, payload: Payload) -> None:
        """Serialize *payload* as JSON and publish it to the exchange.

        Args:
            routing_key: Routing key string, e.g. ``message.all`` or ``vote.day``.
            payload: A :class:`~shared.models.Message`
                or :class:`~shared.models.VoteEvent`
                instance to publish.

        Raises:
            RuntimeError: If the client is not connected.

        """
        _, exchange = self._require_connected()
        body = payload.model_dump_json().encode()
        await exchange.publish(
            aio_pika.Message(
                body=body,
                content_type='application/json',
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=routing_key,
        )

    async def subscribe(
        self,
        routing_key_pattern: str,
        callback: MessageCallback,
    ) -> None:
        """Create an exclusive queue bound to *routing_key_pattern* and start consuming.

        Each call creates a separate anonymous queue, so multiple subscriptions
        on the same client or different clients each receive their own copy of
        matching messages.

        The *callback* is invoked for every incoming message as::

            await callback(routing_key, body_bytes)

        Message acknowledgement is handled automatically after a successful
        callback invocation. If the callback raises, the message is nacked and
        requeued once.

        Args:
            routing_key_pattern: AMQP topic pattern, e.g. ``vote.*`` or ``message.#``.
            callback: Async callable ``(routing_key: str, body: bytes) -> None``.

        Raises:
            RuntimeError: If the client is not connected.

        """
        channel, exchange = self._require_connected()

        queue: aio_pika.abc.AbstractQueue = await channel.declare_queue(
            exclusive=True,
            auto_delete=True,
        )
        await queue.bind(exchange, routing_key=routing_key_pattern)

        async def _on_message(
            message: aio_pika.abc.AbstractIncomingMessage,
        ) -> None:
            async with message.process(requeue=True):
                await callback(message.routing_key, message.body)  # type: ignore

        await queue.consume(_on_message)
