from collections import Counter

from schemas import VoteEvent


def resolve_votes(votes: list[VoteEvent]) -> int | None:
    """Return the target with a strict majority, or None if no consensus.

    A strict majority requires more than half of all cast votes for a single
    candidate.

    Args:
        votes: List of VoteEvents cast by agents.

    Returns:
        target_id of the candidate to eliminate, or None if no consensus.

    """
    if not votes:
        return None

    counter = Counter(v.target_id for v in votes)
    top_target, top_count = counter.most_common(1)[0]

    if top_count > len(votes) / 2:
        return top_target

    return None
