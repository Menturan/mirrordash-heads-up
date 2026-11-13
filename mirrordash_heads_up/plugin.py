import asyncio
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .sources import events, keep_going, poll, schedule, web
from .waiting import Waiting

MAX_LENGTH = 255  # the platform's limit for a text from Home Assistant
LONG = 100  # characters: from here the text steps down one size, so 255 of them still fit the centre
# Settings' size -> the design system's class; a long text takes the next one down
SIZES = {"normal": ("display-lg", "display-lg heads-up-long"), "large": ("display-xl", "display-lg")}
EXAMPLE = "Someone is at the door"  # the admin page's preview, which never gets a command
END_MARGIN = 0.3  # seconds: the card is fully faded out this long before the module clears it
GAP = 0.8  # seconds of an empty card between two texts: above the core's 0.5 s between two HTMLs, so each starts from nothing
# ponytail: the core fades the cards in for about 2.5 s when the screen wakes, and on_shown(True) arrives as that begins.
# Ceiling: an owner with a longer start delay or fade sees the start of the first text clipped.
# Upgrade: the core passing its fade timing to modules.
WAKE_WAIT = 3.0  # seconds after the card is back on the screen before the first waiting text starts
MIN_SECONDS, MAX_SECONDS = 3, 120  # the "Seconds Shown" setting's bounds, also for a text's own seconds


def clean(value) -> str:
    """What Home Assistant sent, as one line of at most 255 characters. Not escaped here: the template does that."""
    return " ".join(str(value).split())[:MAX_LENGTH]


class HeadsUpModule:
    def __init__(self, config):
        self.config = config
        self.name = "mirrordash_heads_up"
        self.interval = 3600  # nothing to redraw on a timer: a heads-up draws itself when it starts and ends
        self.duration = config["duration"]
        self.size = config["size"]
        self.token = config.get("token", "")  # empty: the web address is open to the home network
        self.preview = config.get("preview", False)  # the admin page's preview: shows the example, never ends
        self.changed = asyncio.Event()
        self.now = time.monotonic  # a test replaces it
        self.waiting = Waiting(lambda: self.now(), config["keep_hours"] * 3600)
        self.shown = False  # is the card on the screen? on_shown says, right at the start
        self.text = ""  # the heads-up showing now
        self.seconds = self.duration  # how long it shows
        self.until = 0.0  # time.monotonic() when it ends
        self.next_at = 0.0  # no waiting text starts before this
        self.count = 0  # which heads-up this is: the same text again is a new one, so its animation restarts
        self.router = web.make_router(self)
        event_bus = config.get("event_bus")  # not there in a test
        if event_bus and not self.preview:
            events.listen(event_bus, config.get("senders", []), self.push)

    # ── The queue ──
    def push(self, text, seconds=None) -> bool:
        """Every way in comes here. False: nothing to show (empty after cleaning) so nothing was queued."""
        text = clean(text)
        if not text or self.preview:
            return False
        ok = type(seconds) is int and MIN_SECONDS <= seconds <= MAX_SECONDS  # untrusted: else the setting
        self.waiting.add(text, seconds if ok else self.duration)
        self.advance()
        self.changed.set()
        return True

    def advance(self) -> None:
        """Ends the text showing when its time is up, and starts the next waiting one when the card is on the
        screen, the wake wait and the gap are over and nothing shows. The end time counts from the start."""
        now = self.now()
        if self.text and now >= self.until:
            self.text = ""
            self.next_at = self.until + GAP
        if not self.text and self.shown and now >= self.next_at and (item := self.waiting.take()):
            self.text, self.seconds = item
            self.until = now + self.seconds
            self.count += 1

    async def on_shown(self, shown):
        self.shown = shown
        if shown:
            self.next_at = self.now() + WAKE_WAIT
        else:
            self.text = ""  # known gap: this only comes after the core's fade-out, so a text cut here was cut
        self.changed.set()

    # ── The card ──
    async def run_loop(self, broadcast_func):
        """Draws the card whenever it changes and when a text ends or the next may start. One wait with a deadline
        instead of timers to cancel: a push wakes it, the mirror stopping the module cancels it, and the sources
        started here end with it."""
        sources = [] if self.preview else self.start_sources()
        try:
            while True:
                self.changed.clear()  # before the draw, so a push during it isn't lost
                await broadcast_func(self.name, await self.render())
                try:
                    await asyncio.wait_for(self.changed.wait(), self.sleep_for())
                except TimeoutError:
                    pass  # a text ended or the next may start: render() sorts it out
                except asyncio.CancelledError:
                    raise  # the mirror stops the module; the finally below ends our sources
        finally:
            for task in sources:
                task.cancel()
            await asyncio.gather(*sources, return_exceptions=True)

    def start_sources(self) -> list:
        sources = []
        if rows := [row for row in self.config.get("timed", []) if isinstance(row, dict)]:
            sources.append(keep_going("schedule", lambda: schedule.run(rows, self.timezone(), self.push)))
        if url := self.config.get("watch_url", "").strip():
            sources.append(keep_going("poll", lambda: poll.run(self, url, self.config["watch_seconds"],
                                                               self.config.get("watch_field", "").strip())))
        return [asyncio.create_task(source) for source in sources]

    def timezone(self):
        try:
            return ZoneInfo(self.config.get("globals", {}).get("timezone", "Europe/Stockholm"))
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def sleep_for(self):
        """Seconds until something changes by itself, or None."""
        if self.text:
            return max(self.until - self.now(), 0)
        if self.shown and len(self.waiting):
            return max(self.next_at - self.now(), 0)
        return None

    async def render(self) -> str:
        if self.preview:
            return self.html(EXAMPLE, 0, self.duration)
        self.advance()
        return self.html(self.text, self.count, self.seconds) if self.text else ""

    def html(self, text: str, count: int, seconds: int) -> str:
        size = SIZES.get(self.size, SIZES["normal"])[len(text) > LONG]
        # Identical HTML isn't redrawn (the animation runs on), so nothing here changes between the renders of
        # one heads-up: no remaining time, only the whole duration
        return self.render_template("widget.html", text=text, size=size, count=count, seconds=seconds,
                                    fade=min(1.0, seconds / 5), margin=END_MARGIN)

    # ── Home Assistant (MQTT) ──
    async def on_control(self, name: str, value):
        """text.set_value on the "heads_up" entity: the text goes in the queue. An empty one keeps its meaning of
        "clear": it ends the text showing and empties the queue."""
        if name != "heads_up":
            return
        if not self.push(value):
            self.text = ""
            self.next_at = self.now() + GAP
            self.waiting.clear()
            self.changed.set()
