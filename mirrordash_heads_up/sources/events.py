import re
from functools import partial

PACKAGE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")  # a Python package name: the sender's event is "<package>.heads_up"


def receive(push, data) -> None:
    """Data from another module is untrusted: only {"text": str, "seconds": int (optional)} gets through, and
    push() checks the rest."""
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        push(data["text"], data.get("seconds"))


def listen(event_bus, senders, push) -> list[str]:
    """Subscribe to exactly '<package>.heads_up' of each listed package (the list is the allow-list)."""
    packages = {str(row.get("package", "")).strip() for row in senders if isinstance(row, dict)}
    names = sorted(f"{package}.heads_up" for package in packages if PACKAGE.fullmatch(package))
    for name in names:
        event_bus.subscribe(name, partial(receive, push))
    return names
