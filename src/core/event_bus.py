import asyncio

from loguru import logger

from schemas import AgentAnswer, Message, VoteEvent


class EventBus:
    """Event bus for game events.

    TODO: test me

    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Message | AgentAnswer | VoteEvent] = asyncio.Queue()

    def clean(self) -> None:
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()

    def publish(
        self,
        feed: Message | AgentAnswer | VoteEvent,
    ) -> None:
        """Publish event.

        Invokes all registered callbacks immediately in current thread.

        Args:
            feed: Event data (typically dict or Pydantic model).

        """
        logger.debug(f'Publishing in queue {feed.__class__.__name__}')
        try:
            self._queue.put_nowait(feed)
        except (asyncio.QueueFull, asyncio.QueueShutDown):
            logger.warning(f'Queue dropping event for {feed.__class__.__name__}')

    def get(self) -> Message | AgentAnswer | VoteEvent | None:
        try:
            feed = self._queue.get_nowait()
            self._queue.task_done()
            logger.debug(f'Geting from queue {feed.__class__.__name__}')
            return feed
        except (asyncio.QueueEmpty, asyncio.QueueShutDown):
            logger.warning('Queue is empty or shuttdown')
            return None
