import asyncio
import time

MAX_LENGTH = 255  # the platform's limit for a text from Home Assistant
LONG = 100  # characters: from here the text steps down one size, so 255 of them still fit the centre
# Settings' size -> the design system's class; a long text takes the next one down
SIZES = {"normal": ("display-lg", "display-lg moment-long"), "large": ("display-xl", "display-lg")}
EXAMPLE = "Someone is at the door"  # the admin page's preview, which never gets a command
END_MARGIN = 0.3  # seconds: the card is fully faded out this long before the module clears it


def clean(value) -> str:
    """What Home Assistant sent, as one line of at most 255 characters. Not escaped here: the template does that."""
    return " ".join(str(value).split())[:MAX_LENGTH]


class MomentModule:
    def __init__(self, config):
        self.config = config
        self.name = "mirrordash_moment"
        self.interval = 3600  # nothing to redraw on a timer: a moment draws itself when it arrives and ends
        self.duration = config["duration"]
        self.size = config["size"]
        self.preview = config.get("preview", False)  # the admin page's preview: shows the example, never ends
        self.changed = asyncio.Event()
        self.text = ""
        self.until = 0.0  # time.monotonic() when the text ends
        self.count = 0  # which moment this is: the same text again is a new moment, so its animation restarts
        self.now = time.monotonic  # a test replaces it

    def showing(self) -> bool:
        return bool(self.text) and self.now() < self.until

    # ── The card ──
    async def run_loop(self, broadcast_func):
        """Draws the card whenever it changes and when the moment ends. One wait with a deadline instead of a
        timer to cancel: a new text wakes it, the mirror stopping the module cancels it."""
        while True:
            await broadcast_func(self.name, await self.render())
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), max(self.until - self.now(), 0) if self.showing() else None)
            except TimeoutError:
                pass  # the moment ended: render() now gives ""
            except asyncio.CancelledError:
                raise  # the mirror stops the module; nothing of ours is left running

    async def render(self) -> str:
        if self.preview:
            return self.html(EXAMPLE, 0)
        return self.html(self.text, self.count) if self.showing() else ""

    def html(self, text: str, count: int) -> str:
        size = SIZES.get(self.size, SIZES["normal"])[len(text) > LONG]
        # Identical HTML isn't redrawn (the animation runs on), so nothing here changes between the renders of
        # one moment: no remaining time, only the whole duration
        return self.render_template("widget.html", text=text, size=size, count=count, seconds=self.duration,
                                    fade=min(1.0, self.duration / 5), margin=END_MARGIN)

    # ── Home Assistant (MQTT) ──
    async def on_control(self, name: str, value):
        """text.set_value on the "moment" entity. A new text replaces the one showing and restarts the time;
        an empty one ends it at once."""
        if name != "moment":
            return
        self.text = clean(value)
        self.until = self.now() + self.duration
        self.count += 1
        self.changed.set()
