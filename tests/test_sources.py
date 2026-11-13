import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from conftest import make_module
from fastapi import HTTPException

from mirrordash_heads_up.sources import poll
from mirrordash_heads_up.sources.events import listen, receive
from mirrordash_heads_up.sources.schedule import due

STOCKHOLM = ZoneInfo("Europe/Stockholm")


# ── HTTP ──

async def shown(**settings):
    module = make_module(**settings)
    await module.on_shown(True)
    module.now.t += 10
    return module, module.router.routes[0].endpoint


@pytest.mark.asyncio
async def test_the_web_address_is_open_when_no_token_is_set():
    module, show = await shown()
    assert await show({"text": "hello"}) == {"ok": True, "waiting": 0}  # it started at once
    assert await show({"text": "again"}) == {"ok": True, "waiting": 1}
    assert module.text == "hello"


@pytest.mark.asyncio
async def test_with_a_token_set_a_wrong_or_missing_one_is_refused_and_the_right_one_works_in_header_or_query():
    module, show = await shown(token="s3cret")
    for kwargs in ({}, {"x_token": "wrong"}, {"token": "wrong"}):
        with pytest.raises(HTTPException) as refused:
            await show({"text": "x"}, **kwargs)
        assert refused.value.status_code == 403 and "s3cret" not in str(refused.value.detail)
    assert module.text == ""
    assert (await show({"text": "a"}, x_token="s3cret"))["ok"]
    assert (await show({"text": "b"}, token="s3cret"))["ok"]


@pytest.mark.asyncio
async def test_the_text_may_be_a_query_parameter_and_a_missing_one_is_422():
    module, show = await shown()
    assert (await show(None, text="from a shortcut"))["ok"] and module.text == "from a shortcut"
    for body in (None, {}, {"text": "  "}, {"text": 5}):
        with pytest.raises(HTTPException) as refused:
            await show(body)
        assert refused.value.status_code == 422


@pytest.mark.asyncio
async def test_seconds_come_from_the_body_or_the_query_inside_the_bounds():
    module, show = await shown()
    await show({"text": "a", "seconds": 30})
    assert module.seconds == 30
    module.now.t += 100
    await show({"text": "b"}, seconds=7)
    assert module.seconds == 7
    module.now.t += 100
    await show({"text": "c", "seconds": 500})  # out of bounds: the setting
    assert module.seconds == module.duration


# ── Other modules ──

def test_it_listens_to_exactly_the_listed_packages_and_ignores_bad_names():
    bus = MagicMock()
    names = listen(bus, [{"package": "mirrordash_a"}, {"package": " mirrordash_b "}, {"package": "bad.name"},
                         {"package": "a b"}, {"package": ""}, {"package": "mirrordash_a"}, "text", {}], print)
    assert names == ["mirrordash_a.heads_up", "mirrordash_b.heads_up"]
    assert [call.args[0] for call in bus.subscribe.call_args_list] == names


def test_the_module_subscribes_in_init_but_not_in_the_preview():
    bus = MagicMock()
    make_module(event_bus=bus, senders=[{"package": "mirrordash_a"}])
    bus.subscribe.assert_called_once()
    other = MagicMock()
    make_module(event_bus=other, senders=[{"package": "mirrordash_a"}], preview=True)
    other.subscribe.assert_not_called()


def test_data_from_another_module_is_checked():
    got = []
    push = lambda text, seconds=None: got.append((text, seconds))
    for data in (None, "text", ["x"], {}, {"text": 5}, {"text": None}):
        receive(push, data)
    assert got == []
    receive(push, {"text": "ok", "seconds": 9})
    assert got == [("ok", 9)]


@pytest.mark.asyncio
async def test_a_bad_seconds_from_an_event_falls_back_to_the_setting():
    module, _ = await shown()
    for bad in ("9", 999, 1.5, [3]):
        module.now.t += 100
        receive(module.push, {"text": "x", "seconds": bad})
        module.advance()
        assert module.seconds == module.duration


# ── Schedule ──

def at(day, hour, minute=0, second=0):
    return datetime(2026, 11, day, hour, minute, second, tzinfo=STOCKHOLM)  # 2026-11-13 is a Friday


def test_a_row_is_due_once_when_its_time_falls_in_the_window():
    rows = [{"time": "07:30", "days": [], "text": "Wake up"}]
    assert due(rows, at(13, 7, 29, 30), at(13, 7, 30, 1)) == ["Wake up"]
    assert due(rows, at(13, 7, 30, 1), at(13, 7, 31)) == []  # (since, now]: not twice
    assert due(rows, at(13, 7, 0), at(13, 7, 29, 59)) == []


def test_days_unticked_or_missing_mean_every_day_and_ticked_days_limit_it():
    window = (at(13, 7, 29), at(13, 7, 31))  # a Friday
    assert due([{"time": "07:30", "text": "a"}], *window) == ["a"]
    assert due([{"time": "07:30", "days": [], "text": "a"}], *window) == ["a"]
    assert due([{"time": "07:30", "days": ["fri"], "text": "a"}], *window) == ["a"]
    assert due([{"time": "07:30", "days": ["mon", "sat"], "text": "a"}], *window) == []


def test_across_midnight_and_in_time_order():
    rows = [{"time": "00:05", "days": ["sat"], "text": "late"}, {"time": "23:58", "days": ["fri"], "text": "night"}]
    assert due(rows, at(13, 23, 57), at(14, 0, 6)) == ["night", "late"]


def test_a_row_without_a_valid_time_does_nothing_and_a_dst_change_is_right():
    assert due([{"time": "", "text": "x"}, {"text": "y"}, {"time": "25:99", "text": "z"}], at(13, 0), at(14, 0)) == []
    # Europe/Stockholm moved its clocks back on 2026-10-25: a 12:00 row still comes once, at the real 12:00
    since = datetime(2026, 10, 25, 11, 59, tzinfo=STOCKHOLM)
    assert due([{"time": "12:00", "text": "noon"}], since, since + timedelta(minutes=2)) == ["noon"]
    assert due([{"time": "12:00", "text": "noon"}], since + timedelta(hours=1), since + timedelta(hours=3)) == []


@pytest.mark.asyncio
async def test_the_schedule_loop_fires_only_what_falls_after_its_start(monkeypatch):
    from mirrordash_heads_up.sources import schedule
    times = iter([at(13, 7, 29, 59), at(13, 7, 30, 1), at(13, 7, 31, 1)])  # the start, then two looks
    clock = lambda tz: next(times)
    monkeypatch.setattr(schedule.asyncio, "sleep", AsyncMock(side_effect=[None, None, asyncio.CancelledError()]))
    got = []
    with pytest.raises(asyncio.CancelledError):
        await schedule.run([{"time": "07:30", "text": "now"}, {"time": "07:00", "text": "before start"}],
                           STOCKHOLM, got.append, clock)
    assert got == ["now"]


# ── Watched address ──

def test_extract_plain_text_and_a_json_path():
    assert poll.extract(b"  hello \n", "") == "hello"
    assert poll.extract(b'{"state": {"message": "Door open"}, "n": 3, "l": ["a", "b"]}', "state.message") == "Door open"
    assert poll.extract(b'{"n": 3, "l": ["a", "b"]}', "n") == "3"
    assert poll.extract(b'{"l": ["a", "b"]}', "l.1") == "b"
    for missing in ("nope", "l.5", "l.x", "l"):
        assert poll.extract(b'{"l": ["a", "b"]}', missing) == ""
    assert poll.extract(b"not json", "state") == ""


def test_news_remembers_the_first_answer_and_shows_a_changed_one():
    assert poll.news(None, "a") == ("a", "")  # the first one after a start: remembered, not shown
    assert poll.news("a", "a") == ("a", "")
    assert poll.news("a", "b") == ("b", "b")
    assert poll.news("b", "") == ("", "")  # empty is never shown...
    assert poll.news("", "b") == ("b", "b")  # ...but the text coming back is news


@pytest.mark.asyncio
async def test_the_poll_ignores_errors_and_pushes_changes(monkeypatch):
    module = MagicMock()
    answers = [(b"one", None), (b"one", None), (b"two", None), (b"two", "offline"), (b"zzz", "http 500"),
               (None, "offline"), (b"three", None)]
    module.fetch = AsyncMock(side_effect=answers)
    monkeypatch.setattr(poll.asyncio, "sleep", AsyncMock(side_effect=[None] * 6 + [asyncio.CancelledError()]))
    with pytest.raises(asyncio.CancelledError):
        await poll.run(module, "http://x/", 60, "")
    assert [call.args[0] for call in module.push.call_args_list] == ["two", "three"]
    assert module.fetch.await_args.kwargs["max_age"] == 0  # a real call, not the hour-old saved answer
