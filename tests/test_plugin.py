import asyncio
import json
import time
from pathlib import Path

import pytest
from jinja2 import (  # the mirror's template engine, the same autoescape
    Environment,
    FileSystemLoader,
    select_autoescape,
)

from mirrordash_heads_up import plugin
from mirrordash_heads_up.plugin import HeadsUpModule

PACKAGE = Path(plugin.__file__).parent
SCHEMA = json.loads((PACKAGE / "config_schema.json").read_text())
DEFAULTS = {key: prop["default"] for key, prop in SCHEMA["properties"].items()}
# The mirror's environment (features/modules/loader.py): templates are .html, so they are autoescaped
ENV = Environment(loader=FileSystemLoader(PACKAGE / "templates"), autoescape=select_autoescape(["html", "xml"]))


class Clock:
    """The module's time, moved by hand."""
    t = 1000.0

    def __call__(self):
        return self.t


def make_module(**settings):
    module = HeadsUpModule({**DEFAULTS, **settings})
    module.render_template = lambda name, **context: ENV.get_template(name).render(translations={}, **context)
    module.now = Clock()
    return module


async def show(module, text):
    await module.on_control("heads_up", text)
    return await module.render()


@pytest.mark.asyncio
async def test_nothing_shows_before_a_text_arrives():
    assert await make_module().render() == ""


@pytest.mark.asyncio
async def test_a_text_shows_for_the_duration_and_then_the_card_is_empty():
    module = make_module()
    assert "Someone is at the door" in await show(module, "Someone is at the door")
    assert module.changed.is_set()  # drawn at once
    module.now.t += module.duration - 1
    assert "Someone is at the door" in await module.render()
    module.now.t += 1
    assert await module.render() == ""


@pytest.mark.asyncio
async def test_the_text_is_escaped_stripped_and_limited():
    module = make_module()
    for evil in ("<script>alert(1)</script>", "<b>x</b>"):
        shown = await show(module, evil)
        assert evil not in shown and "&lt;" in shown
    assert '>two lines</div>' in await show(module, "  two\n lines\t ")
    await module.on_control("heads_up", "x" * 1000)
    assert module.text == "x" * 255


@pytest.mark.asyncio
async def test_a_second_text_replaces_the_first_and_restarts_the_time():
    module = make_module()
    await module.on_control("heads_up", "first")
    module.now.t += 10
    await module.on_control("heads_up", "second")
    module.now.t += 10  # past the first one's end, inside the second's
    shown = await module.render()
    assert "second" in shown and "first" not in shown
    module.now.t += module.duration
    assert await module.render() == ""


@pytest.mark.asyncio
async def test_the_same_text_again_is_a_new_heads_up_so_the_screen_redraws_it():
    module = make_module()
    first = await show(module, "again")
    assert await show(module, "again") != first  # identical HTML isn't sent, and its animation wouldn't restart


@pytest.mark.asyncio
async def test_an_empty_text_clears_at_once():
    module = make_module()
    await module.on_control("heads_up", "something")
    module.changed.clear()
    assert await show(module, "   ") == ""
    assert module.changed.is_set()


@pytest.mark.asyncio
async def test_another_entity_is_ignored():
    module = make_module()
    await module.on_control("other", "text")
    assert await module.render() == ""


@pytest.mark.asyncio
async def test_a_long_text_is_set_one_size_smaller_and_large_is_larger():
    assert "display-lg" in await show(make_module(), "short")
    assert "heads-up-long" in await show(make_module(), "x " * 60)
    assert "display-xl" in await show(make_module(size="large"), "short")


@pytest.mark.asyncio
async def test_run_loop_draws_the_text_then_the_empty_card_by_itself_and_stops_cleanly():
    module = make_module()
    module.now = time.monotonic  # the loop's wait is real
    module.duration = 0.2  # below the setting's minimum, only so the test is quick
    drawn = []

    async def broadcast(name, html):
        drawn.append(html)

    loop = asyncio.create_task(module.run_loop(broadcast))
    await asyncio.sleep(0.05)
    await module.on_control("heads_up", "hello")
    await asyncio.sleep(0.5)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop  # the mirror stopping the module: nothing is left pending
    assert [bool(html) for html in drawn] == [False, True, False]


def test_the_duration_setting_has_bounds_and_a_default_inside_them():
    duration = SCHEMA["properties"]["duration"]
    assert duration["minimum"] == 3 and duration["maximum"] == 120
    assert duration["minimum"] <= duration["default"] <= duration["maximum"]


def test_the_entity_is_a_text_with_control_at_the_platforms_limit():
    assert SCHEMA["exposes"]["heads_up"] == {"type": "text", "title": "Heads-up", "maxLength": 255, "control": True}
