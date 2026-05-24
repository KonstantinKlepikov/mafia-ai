"""Background RabbitMQ subscriber for the admin panel.

Runs a persistent asyncio event loop in a daemon thread.
Subscribes to ``message.*``, ``host.answer.*``, and ``vote.*``
on the ``game_events`` topic exchange and appends events to a
module-level list that Streamlit sessions drain on each rerun.
"""

import asyncio
import threading
from dataclasses import dataclass
from enum import Enum

import aio_pika
from loguru import logger


class EventKind(str, Enum):
    """Kind of incoming RabbitMQ event."""

    MESSAGE = 'message'
    ANSWER = 'answer'
    VOTE = 'vote'


@dataclass
class FeedEvent:
    """A single event received from RabbitMQ."""

    kind: EventKind
    raw: str


# Module-level shared event log (append-only, protected by _lock).
_events: list[FeedEvent] = []
_lock = threading.Lock()
_thread: threading.Thread | None = None


def get_events_from(index: int) -> tuple[list[FeedEvent], int]:
    """Return events starting at *index* and the new total count.

    Args:
        index: Last consumed position in the global events list.

    Returns:
        Tuple of (new_events, new_total_count).

    """
    with _lock:
        return list(_events[index:]), len(_events)


def ensure_started(amqp_url: str) -> None:
    """Start the background subscriber thread if not already running.

    Args:
        amqp_url: AMQP connection URL for RabbitMQ.

    """
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run, args=(amqp_url,), daemon=True)
    _thread.start()
    logger.info('Admin subscriber thread started')


def _append(event: FeedEvent) -> None:
    with _lock:
        _events.append(event)


def _run(amqp_url: str) -> None:
    asyncio.run(_subscribe(amqp_url))


async def _subscribe(amqp_url: str) -> None:
    logger.info('Admin subscriber: connecting to RabbitMQ…')
    connection = await aio_pika.connect_robust(amqp_url, reconnect_interval=5)

    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(
            'game_events', aio_pika.ExchangeType.TOPIC, durable=True
        )

        bindings: list[tuple[str, EventKind]] = [
            ('message.*', EventKind.MESSAGE),
            ('host.answer.*', EventKind.ANSWER),
            ('vote.*', EventKind.VOTE),
        ]

        for pattern, kind in bindings:
            queue = await channel.declare_queue('', exclusive=True, auto_delete=True)
            await queue.bind(exchange, pattern)

            async def _handler(
                msg: aio_pika.IncomingMessage,
                _kind: EventKind = kind,
            ) -> None:
                async with msg.process():
                    _append(FeedEvent(kind=_kind, raw=msg.body.decode()))

            await queue.consume(_handler)  # type: ignore[arg-type]

        logger.info('Admin subscriber: listening on message.* / host.answer.* / vote.*')
        await asyncio.Future()  # run forever
