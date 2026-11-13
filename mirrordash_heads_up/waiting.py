from collections import deque

MAX_WAITING = 20  # ponytail: when more wait, the oldest is dropped; ceiling = a burst of 21+ loses its first, upgrade = a setting


class Waiting:
    """The heads-ups waiting for their turn, first in, first out. No asyncio: the module gives it a clock."""

    def __init__(self, now, keep_seconds: float):
        self.now = now  # a function giving seconds, like time.monotonic
        self.keep_seconds = keep_seconds
        self.items = deque()  # (arrived, text, seconds)

    def add(self, text: str, seconds: int) -> None:
        self.items.append((self.now(), text, seconds))
        if len(self.items) > MAX_WAITING:
            self.items.popleft()

    def drop_old(self) -> None:
        """Age counts from arrival, for every waiting one: the queue is in arrival order, so only the front can be too old."""
        while self.items and self.now() - self.items[0][0] > self.keep_seconds:
            self.items.popleft()

    def take(self):
        """The next (text, seconds) to show, or None."""
        self.drop_old()
        return self.items.popleft()[1:] if self.items else None

    def clear(self) -> None:
        self.items.clear()

    def __len__(self) -> int:
        self.drop_old()
        return len(self.items)
