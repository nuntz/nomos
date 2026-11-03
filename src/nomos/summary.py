"""The one-line summaries `resolve` and `write-tags` end with."""

from collections import Counter
from collections.abc import Iterable
from enum import StrEnum


def photos(count: int) -> str:
    """A count of photos: "1 photo", "2 photos"."""
    return f"{count} {'photo' if count == 1 else 'photos'}"


def summary(counts: Counter, kinds: Iterable[StrEnum]) -> str:
    """One line with the number of photos, then the count of each kind (zero counts included)."""
    return f"{photos(counts.total())}: " + ", ".join(f"{kind} {counts[kind]}" for kind in kinds)
