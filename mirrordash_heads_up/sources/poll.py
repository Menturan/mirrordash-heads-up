import asyncio
import json

from . import logger


def extract(data: bytes, field: str) -> str:
    """The text of an answer: the plain text, or the value at a dotted path in JSON (state.message, items.0.name).
    "" when it isn't there."""
    text = data.decode(errors="replace").strip()
    if not field:
        return text
    try:
        value = json.loads(text)
        for key in field.split("."):
            value = value[int(key)] if isinstance(value, list) else value[key]
    except (ValueError, KeyError, IndexError, TypeError):
        return ""
    return "" if isinstance(value, (dict, list)) or value is None else str(value)


def news(last, current: str):
    """(what to remember, what to show). The first answer after a start is only remembered; later a changed,
    non-empty text is shown. An empty one is remembered too, so the same text coming back is news again."""
    return current, (current if last is not None and current != last else "")


async def run(module, url: str, every: int, field: str) -> None:
    last, reported = None, None
    while True:
        # max_age=0: a real call (the default reuses an answer younger than the module's interval, an hour)
        data, error = await module.fetch(url, max_age=0, timeout=15)
        problem = error or ("no answer" if data is None else None)  # on an error the data is the last good answer
        if problem:
            if problem != reported:
                logger.warning("Watched address: %s", problem)  # once per kind of problem, not every round
            reported = problem
        else:
            reported = None
            last, text = news(last, extract(data, field))
            if text:
                module.push(text)
        await asyncio.sleep(every)
