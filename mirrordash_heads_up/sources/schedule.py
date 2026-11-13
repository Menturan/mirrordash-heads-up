import asyncio
import time
from datetime import UTC, datetime, timedelta

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # the core's schedule form: datetime.weekday() order
JUMP = timedelta(minutes=5)  # a longer gap between two looks is a clock that jumped (no RTC: the time is set after boot)


def due(rows, since: datetime, now: datetime) -> list[str]:
    """The texts of the rows whose time falls in (since, now], in the zone of `since`/`now` (aware datetimes).
    Days ticked: none ticked or missing = every day. Compared as instants, so midnight and a DST change are right
    (a time that doesn't exist in the spring gap fires at the instant it would have had)."""
    found = []
    for n in range((now.date() - since.date()).days + 1):
        day = since.date() + timedelta(days=n)
        for row in rows:
            try:
                hours, minutes = map(int, row["time"].split(":"))
                moment = datetime(day.year, day.month, day.day, hours, minutes, tzinfo=now.tzinfo)
            except (KeyError, AttributeError, ValueError):
                continue  # a row without a valid time does nothing
            if (not row.get("days") or DAYS[day.weekday()] in row["days"]) and since < moment.astimezone(UTC) <= now:
                found.append((moment.astimezone(UTC), row.get("text", "")))
    return [text for _, text in sorted(found, key=lambda f: f[0])]


async def run(rows, timezone, push, clock=datetime.now) -> None:
    """Looks once a minute, a moment after it turns (times are whole minutes), rather than working out the next
    due time: one wake-up a minute is nothing, and a changed clock can't leave it asleep for hours.
    Nothing from before the start fires."""
    since = clock(timezone)
    while True:
        await asyncio.sleep(60.5 - time.time() % 60)
        now = clock(timezone)
        if now - since <= JUMP:  # after a jump, start over from now instead of firing what "passed"
            for text in due(rows, since, now):
                push(text)
        since = now
