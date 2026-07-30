import sys
from typing import Optional

from loguru import logger

LOG_FORMAT = (
    '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
    '<level>{level: <8}</level> | '
    '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - '
    '<level>{message}</level>'
)


def setup_logging(level: str = 'INFO', log_file: Optional[str] = None) -> None:
    """Инициализирует loguru для консоли и (опционально) файла."""
    logger.remove()

    logger.add(
        sys.stderr,
        level=level.upper(),
        format=LOG_FORMAT,
        colorize=True,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

    if log_file:
        logger.add(
            log_file,
            level=level.upper(),
            format=LOG_FORMAT,
            enqueue=True,
            rotation='10 MB',
            retention='14 days',
            compression='gz',
            backtrace=False,
            diagnose=False,
        )
