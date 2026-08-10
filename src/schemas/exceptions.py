from loguru import logger


class RootException(Exception):
    """Root prpoject exception"""

    def __init__(self, msg=''):  # noqa: B042
        self.msg = msg
        logger.warning(msg)

    def __str__(self):
        return self.msg


class EmptySharingException(RootException):
    """Empty sharing error"""


class VotingError(RootException):
    """Voting error"""
