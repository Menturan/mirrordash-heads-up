from mirrordash_heads_up.waiting import MAX_WAITING, Waiting


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def test_first_in_first_out():
    queue = Waiting(Clock(), 100)
    for text in "abc":
        queue.add(text, 15)
    assert [queue.take() for _ in range(4)] == [("a", 15), ("b", 15), ("c", 15), None]


def test_when_full_the_oldest_is_dropped():
    queue = Waiting(Clock(), 100)
    for n in range(MAX_WAITING + 1):
        queue.add(str(n), 15)
    assert len(queue) == MAX_WAITING and queue.take() == ("1", 15)


def test_expiry_counts_from_arrival_for_every_waiting_one():
    clock = Clock()
    queue = Waiting(clock, 100)
    queue.add("old", 15)
    clock.t = 60
    queue.add("new", 15)
    clock.t = 120  # old waited 120 s, new 60 s
    assert len(queue) == 1 and queue.take() == ("new", 15)
    clock.t = 161
    assert queue.take() is None


def test_clear_empties_it():
    queue = Waiting(Clock(), 100)
    queue.add("a", 15)
    queue.clear()
    assert len(queue) == 0
