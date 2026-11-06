# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
modules/calendar - event CRUD, range queries and the webui routes.

integration level: real Calendar module on FakeManager, real tmp-dir
StorageList. _schedule_notification is stubbed so no notification timers
fire during the suite.

intent under test:
- add_event stores a parseable date + ULID id; invalid dates are rejected
  outright (ValueError from datetime, surfaced to the toolcall layer).
- edit_event changes only what it is given; delete_event removes and
  persists; ids are looked up whitespace-tolerantly.
- read_calendar_range boundaries are inclusive on both ends; malformed
  input and empty results return error envelopes.
- the system-prompt range honours include_past_events and the day range.
- webui routes validate their form input; unlike edit_event, the update
  route can actually turn notifications off.
"""

import datetime

import pytest

import core
from harness import apply_config
from modules.calendar.module import Calendar


@pytest.fixture
def cal(fake_manager, monkeypatch):
    apply_config(
        api={"max_context": 16768},
        model={"name": "test-model", "use_tools": False, "dynamic_tool_loading": False},
        modules={"disabled_prompts": []},
        core={"cmd_prefix": "/"},
    )
    mod = Calendar(fake_manager)
    mod.events = core.storage.StorageList("calendar", "json")

    # stub the notification scheduler: no live timers during the suite
    scheduled = []

    async def fake_schedule(event):
        scheduled.append(event)

    monkeypatch.setattr(mod, "_schedule_notification", fake_schedule)
    mod.scheduled = scheduled
    return mod


async def add(cal, title, dt, should_notify=False):
    res = await cal.add_event(
        title=title, year=dt.year, month=dt.month, day=dt.day,
        hour=dt.hour, minute=dt.minute, should_notify=should_notify,
    )
    assert res["status"] == "success"
    return cal.events[-1]["id"]


# ---------------------------------------------------------------------------
# add / edit / delete
# ---------------------------------------------------------------------------

async def test_add_event_stores_and_schedules(cal):
    dt = datetime.datetime.now() + datetime.timedelta(days=1)

    eid = await add(cal, "dentist", dt, should_notify=True)

    event = cal.events[0]
    assert event["id"] == eid
    assert event["title"] == "dentist"
    assert event["notify"] is True
    # add_event stores at minute precision (seconds/micros are dropped by design)
    assert datetime.datetime.fromisoformat(event["date"]) == dt.replace(second=0, microsecond=0)
    assert cal.scheduled == [event]


async def test_add_event_without_notify_skips_scheduling(cal):
    await add(cal, "quiet", datetime.datetime.now() + datetime.timedelta(days=1))
    assert cal.scheduled == []
    assert cal.events[0]["notify"] is False


async def test_add_event_invalid_date_is_rejected(cal):
    with pytest.raises(ValueError):
        await cal.add_event(
            title="impossible", year=2027, month=13, day=1, hour=0, minute=0,
            should_notify=False,
        )


async def test_edit_event_changes_only_given_fields(cal):
    dt = datetime.datetime(2027, 5, 1, 15, 30)
    eid = await add(cal, "old title", dt)

    res = await cal.edit_event(id=eid, title="new title")

    assert res["status"] == "success"
    assert cal.events[0]["title"] == "new title"
    assert cal.events[0]["date"] == dt.isoformat()  # untouched


async def test_edit_event_can_move_the_date(cal):
    eid = await add(cal, "x", datetime.datetime(2027, 5, 1, 15, 30))

    await cal.edit_event(id=eid, year=2028, month=6, day=2, hour=8, minute=45)

    assert cal.events[0]["date"] == datetime.datetime(2028, 6, 2, 8, 45).isoformat()


async def test_edit_event_unknown_id(cal):
    res = await cal.edit_event(id="ghost", title="x")
    assert res["status"] == "error" and "does not exist" in res["content"]


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: edit_event merges with `or`, so provided falsy "
    "values (hour=0, should_notify=False) are silently ignored instead of "
    "being applied - the tool docstring promises provided fields are changed",
)
async def test_edit_event_can_move_to_midnight(cal):
    eid = await add(cal, "late night", datetime.datetime(2027, 5, 1, 15, 30))

    await cal.edit_event(id=eid, hour=0, minute=0)

    assert datetime.datetime.fromisoformat(cal.events[0]["date"]).hour == 0


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: same `or` merge as hour=0 - the webui update "
    "route exists specifically because edit_event cannot disable notify",
)
async def test_edit_event_can_disable_notifications(cal):
    dt = datetime.datetime(2027, 5, 1, 15, 30)
    eid = await add(cal, "noisy", dt, should_notify=True)

    await cal.edit_event(id=eid, should_notify=False)

    assert cal.events[0]["notify"] is False


async def test_delete_event(cal):
    eid = await add(cal, "gone", datetime.datetime(2027, 5, 1))
    assert (await cal.delete_event(id=eid))["status"] == "success"
    assert list(cal.events) == []
    assert (await cal.delete_event(id=eid))["status"] == "error"


async def test_get_event_by_id_is_whitespace_tolerant(cal):
    eid = await add(cal, "x", datetime.datetime(2027, 5, 1))
    assert await cal._get_event_by_id(f"  {eid}  ") == 0
    assert await cal._get_event_by_id("ghost") == -1


# ---------------------------------------------------------------------------
# range queries
# ---------------------------------------------------------------------------

async def test_read_calendar_range_boundaries_inclusive(cal):
    cal.events.extend([
        {"id": "e1", "title": "start boundary", "date": "2027-05-01T10:00:00"},
        {"id": "e2", "title": "end boundary", "date": "2027-05-02T10:00:00"},
        {"id": "e3", "title": "outside", "date": "2027-05-02T10:00:01"},
    ])

    res = await cal.read_calendar_range(
        start_date="2027-05-01T10:00:00", end_date="2027-05-02T10:00:00"
    )

    assert res["status"] == "success"
    assert "start boundary" in res["content"] and "end boundary" in res["content"]
    assert "outside" not in res["content"]


async def test_read_calendar_range_validation(cal):
    res = await cal.read_calendar_range(start_date="nope", end_date="2027-05-01")
    assert res["status"] == "error" and "Invalid date format" in res["content"]

    res = await cal.read_calendar_range(start_date="2027-05-01", end_date="2027-05-02")
    assert res["status"] == "error" and "No events found" in res["content"]


async def test_events_in_range_honours_include_past(cal):
    now = datetime.datetime.now()
    cal.events.append({"id": "f", "title": "future", "date": (now + datetime.timedelta(hours=1)).isoformat()})
    cal.events.append({"id": "p", "title": "past", "date": (now - datetime.timedelta(hours=2)).isoformat()})

    matches = await cal._get_events_in_range()  # include_past defaults to False
    assert [e["title"] for e in matches] == ["future"]

    apply_config(
        api={"max_context": 16768},
        model={"name": "test-model", "use_tools": False, "dynamic_tool_loading": False},
        modules={"disabled_prompts": [], "settings": {"calendar": {"include_past_events": True, "range": 7}}},
        core={"cmd_prefix": "/"},
    )
    matches = await cal._get_events_in_range()
    assert sorted(e["title"] for e in matches) == ["future", "past"]


async def test_events_in_range_future_boundary(cal):
    now = datetime.datetime.now()
    cal.events.append({"id": "in", "title": "in range", "date": (now + datetime.timedelta(days=6)).isoformat()})
    cal.events.append({"id": "out", "title": "beyond", "date": (now + datetime.timedelta(days=8)).isoformat()})

    matches = await cal._get_events_in_range()  # range defaults to 7 days
    assert [e["title"] for e in matches] == ["in range"]


async def test_on_system_prompt_lists_events_in_range(cal):
    assert await cal.on_system_prompt() is None

    now = datetime.datetime.now()
    eid = await add(cal, "standup", now + datetime.timedelta(hours=1))
    await add(cal, "next month", now + datetime.timedelta(days=30))

    prompt = await cal.on_system_prompt()
    assert eid in prompt and "standup" in prompt
    assert "next month" not in prompt


# ---------------------------------------------------------------------------
# /calendar command
# ---------------------------------------------------------------------------

async def test_cmd_calendar_without_args_uses_configured_range(cal):
    assert await cal.cmd_calendar([]) == "No events found in this range."


async def test_cmd_calendar_invalid_format(cal):
    out = await cal.cmd_calendar(["not-a-date"])
    assert "Invalid date format" in out


async def test_cmd_calendar_custom_range(cal):
    cal.events.append({"id": "e", "title": "checkup", "date": "2027-05-01T12:00:00"})

    out = await cal.cmd_calendar(["2027-05-01"])
    assert "checkup" in out

    out = await cal.cmd_calendar(["2027-06-01"])
    assert "No events found" in out


# ---------------------------------------------------------------------------
# webui routes
# ---------------------------------------------------------------------------

def test_ui_parse_dt(cal):
    assert cal._ui_parse_dt("2027-05-01", "14:30") == datetime.datetime(2027, 5, 1, 14, 30)
    with pytest.raises(ValueError):
        cal._ui_parse_dt("01/05/2027", "14:30")
    with pytest.raises(ValueError):
        cal._ui_parse_dt("2027-05-01", "25:00")


async def test_route_create_validation(cal):
    res = await cal._route_create(body={"title": "   "})
    assert res["status"] == "error" and "title cannot be empty" in res["content"]

    res = await cal._route_create(body={"title": "x", "date": "nope", "time": "00:00"})
    assert res["status"] == "error" and "invalid date/time" in res["content"]


async def test_route_create_happy_path(cal):
    res = await cal._route_create(
        body={"title": "from ui", "date": "2027-05-01", "time": "14:30", "notify": False}
    )
    assert res["status"] == "success"
    assert cal.events[0]["date"] == "2027-05-01T14:30:00"


async def test_route_update_can_disable_notify_where_edit_event_cannot(cal):
    dt = datetime.datetime(2027, 5, 1, 15, 30)
    eid = await add(cal, "noisy", dt, should_notify=True)

    res = await cal._route_update(body={"id": eid, "notify": False})

    assert res["status"] == "success"
    assert cal.events[0]["notify"] is False


async def test_route_update_validation(cal):
    assert (await cal._route_update(body={}))["status"] == "error"
    assert (await cal._route_update(body={"id": "ghost"}))["status"] == "error"

    eid = await add(cal, "x", datetime.datetime(2027, 5, 1))
    res = await cal._route_update(body={"id": eid, "date": "garbage"})
    assert res["status"] == "error"


async def test_route_delete(cal):
    eid = await add(cal, "x", datetime.datetime(2027, 5, 1))
    assert (await cal._route_delete(body={}))["status"] == "error"
    assert (await cal._route_delete(body={"id": eid}))["status"] == "success"
    assert list(cal.events) == []


async def test_route_upcoming_sorts_and_skips_garbage(cal):
    now = datetime.datetime.now()
    day = datetime.timedelta(days=1)
    cal.events.extend([
        {"id": "late", "title": "later", "date": (now + 3 * day).isoformat()},
        {"id": "soon", "title": "sooner", "date": (now + day).isoformat()},
        {"id": "bad", "title": "broken", "date": "not-a-date"},
        {"id": "far", "title": "too far", "date": (now + 40 * day).isoformat()},
    ])
    cal.events.save()

    items = await cal._route_upcoming(query={"days": 30})

    assert [i["id"] for i in items] == ["soon", "late"]