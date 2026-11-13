import asyncio
import time

import pytest
from conftest import DEFAULTS, SCHEMA, make_module

from mirrordash_heads_up.plugin import GAP, WAKE_WAIT


async def shown_module(**settings):
    """A module whose card is on the screen and past the wake wait."""
    module = make_module(**settings)
    await module.on_shown(True)
    module.now.t += WAKE_WAIT
    return module


@pytest.mark.asyncio
async def test_nothing_shows_before_a_text_arrives():
    assert await (await shown_module()).render() == ""


@pytest.mark.asyncio
async def test_a_text_shows_for_the_duration_and_then_the_card_is_empty():
    module = await shown_module()
    module.push("Someone is at the door")
    assert module.changed.is_set()  # drawn at once
    assert "Someone is at the door" in await module.render()
    module.now.t += module.duration - 1
    assert "Someone is at the door" in await module.render()
    module.now.t += 1
    assert await module.render() == ""


@pytest.mark.asyncio
async def test_the_text_is_escaped_stripped_and_limited():
    module = await shown_module()
    for evil in ("<script>alert(1)</script>", "<b>x</b>"):
        module.push(evil)
        shown = await module.render()
        assert evil not in shown and "&lt;" in shown
        module.now.t += module.duration + GAP
    module.push("  two\n lines\t ")
    assert '>two lines</div>' in await module.render()
    module.now.t += module.duration + GAP
    module.push("x" * 1000)
    assert module.text == "x" * 255


@pytest.mark.asyncio
async def test_a_text_that_arrives_while_one_shows_waits_its_turn_with_a_gap_between():
    module = await shown_module()
    module.push("first")
    module.now.t += 10
    module.push("second")
    assert ">first</div>" in await module.render()
    module.now.t += 5  # the first one ends
    assert await module.render() == ""
    module.now.t += GAP - 0.1
    assert await module.render() == ""  # still the gap
    module.now.t += 0.1
    assert ">second</div>" in await module.render()


@pytest.mark.asyncio
async def test_the_end_time_counts_from_the_start_of_showing_not_from_arrival():
    module = await shown_module()
    module.push("first")
    module.push("second", 20)
    module.now.t += 15 + GAP  # the second starts now, 15.8 s after it arrived
    assert ">second</div>" in await module.render() and module.until == module.now.t + 20
    assert 'style="--seconds: 20;' in await module.render()  # the animation covers its own seconds


@pytest.mark.asyncio
async def test_the_count_goes_up_per_started_text_so_the_same_text_redraws():
    module = await shown_module()
    module.push("again")
    module.push("again")
    first = await module.render()
    module.now.t += module.duration + GAP
    assert await module.render() != first  # identical HTML isn't sent, and its animation wouldn't restart
    assert module.count == 2


@pytest.mark.asyncio
async def test_a_text_that_arrives_while_the_card_is_off_is_kept_and_starts_after_the_wake_wait():
    module = make_module()
    await module.on_shown(False)
    module.push("while you were away")
    assert await module.render() == ""
    module.now.t += 3600
    await module.on_shown(True)
    assert await module.render() == ""  # the screen is still fading in
    module.now.t += WAKE_WAIT
    assert "while you were away" in await module.render()


@pytest.mark.asyncio
async def test_a_text_older_than_the_setting_is_dropped_and_age_counts_from_arrival():
    module = make_module(keep_hours=1)
    await module.on_shown(False)
    module.push("old")
    module.now.t += 1800
    module.push("newer")
    module.now.t += 1900  # old: 3700 s, newer: 1900 s
    await module.on_shown(True)
    module.now.t += WAKE_WAIT
    shown = await module.render()
    assert ">newer</div>" in shown


@pytest.mark.asyncio
async def test_the_card_going_away_ends_the_text_showing():
    module = await shown_module()
    module.push("cut")
    await module.on_shown(False)
    assert await module.render() == ""


@pytest.mark.asyncio
async def test_mqtt_sends_a_text_into_the_queue_and_an_empty_one_clears_showing_and_queue():
    module = await shown_module()
    await module.on_control("other", "ignored")
    assert await module.render() == ""
    await module.on_control("heads_up", "one")
    await module.on_control("heads_up", "two")
    assert "one" in await module.render() and len(module.waiting) == 1
    await module.on_control("heads_up", "   ")
    assert await module.render() == "" and len(module.waiting) == 0
    module.now.t += 60
    assert await module.render() == ""  # nothing comes back


@pytest.mark.asyncio
async def test_push_ignores_an_empty_text_and_checks_seconds():
    module = await shown_module()
    assert module.push("  ") is False and module.push("x", 5) is True
    assert module.seconds == 5
    for bad in (2, 121, "9", 7.5, True, None):
        module.now.t += 200
        module.push("y", bad)
        module.advance()
        assert module.seconds == module.duration


@pytest.mark.asyncio
async def test_a_long_text_is_set_one_size_smaller_and_large_is_larger():
    assert "display-lg" in await show_text(await shown_module(), "short")
    assert "heads-up-long" in await show_text(await shown_module(), "x " * 60)
    assert "display-xl" in await show_text(await shown_module(size="large"), "short")


async def show_text(module, text):
    module.push(text)
    return await module.render()


@pytest.mark.asyncio
async def test_the_preview_shows_the_example_and_takes_nothing():
    module = make_module(preview=True)
    assert "Someone is at the door" in await module.render()
    assert module.push("x") is False


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
    await module.on_shown(True)
    module.next_at = 0  # no wake wait: the test is about the loop
    module.push("hello")
    await asyncio.sleep(0.5)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop  # the mirror stopping the module: nothing is left pending
    assert [bool(html) for html in drawn] == [False, True, False]


@pytest.mark.asyncio
async def test_a_source_that_is_started_ends_with_the_loop():
    module = make_module(watch_url="http://x/", watch_seconds=10)
    module.fetch = lambda *a, **k: asyncio.sleep(3600)  # a poll stuck in a call

    async def broadcast(name, html):
        pass

    loop = asyncio.create_task(module.run_loop(broadcast))
    await asyncio.sleep(0.05)
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and t is not loop]
    assert tasks  # the poll runs
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop
    assert all(t.done() for t in tasks)


def test_the_settings_have_bounds_and_defaults_inside_them():
    for key in ("duration", "keep_hours", "watch_seconds"):
        prop = SCHEMA["properties"][key]
        assert prop["minimum"] <= prop["default"] <= prop["maximum"]
    assert (DEFAULTS["keep_hours"], DEFAULTS["token"], DEFAULTS["watch_url"]) == (12, "", "")


def test_the_entity_is_a_text_with_control_at_the_platforms_limit():
    assert SCHEMA["exposes"]["heads_up"] == {"type": "text", "title": "Heads-up", "maxLength": 255, "control": True}
