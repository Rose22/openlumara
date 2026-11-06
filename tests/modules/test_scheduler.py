# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
modules/scheduler - trigger math, job storage and the execution lifecycle.

integration level: real Scheduler module on FakeManager/FakeAPI/FakeChannel,
real tmp-dir StorageList (conftest isolation). The dispatcher task is only
started in the on_ready/on_unload wiring test; everything else calls the
internals directly so tests stay deterministic.

intent under test:
- _calculate_next_from: clock-time mode (daily rollover, weekly via
  target_weekday, weekdays_only skipping weekends, interval days) and
  relative-delta mode; zero/None interval -> None.
- add_job/edit_job/remove_job validation and storage round-trips; explicit
  channel beats the configured default; recurring policy gate.
- recurring bookkeeping: reschedule preserves cadence, missed recurring
  jobs are advanced to the future without firing, invalid intervals log and
  leave storage untouched.
- one-time jobs are removed after firing; execution errors are caught.
- _execute_job: prompt strategies, scheduler tools filtered from the tool
  list, APIError/empty-response retries, tool-call output announced,
  missing-channel logging.
- formatting helpers and the webui form builder validation.
"""

import asyncio
import datetime
from types import SimpleNamespace

import pytest

import core
import modules.scheduler.module as sched_mod
from harness import apply_config
from modules.scheduler.module import Scheduler

# a Monday and a Friday, used as fixed bases for trigger math
MON = datetime.datetime(2026, 10, 26, 10, 0)
FRI = datetime.datetime(2026, 10, 23, 10, 0)

MODEL = {
    "name": "test-model",
    "use_tools": False,
    "dynamic_tool_loading": False,
    "keep_reasoning_in_context": False,
    "only_preserve_reasoning_for_current_agentic_loop": False,
    "automatically_compress_context": False,
    "context_compression_threshold": 0.8,
}

SCHED_DEFAULTS = {
    # NOTE: bare-bool module settings (this one!) do NOT get schema-default
    # fallbacks from ModuleConfig - the live config file always carries the
    # written value, so tests must set it explicitly too.
    "allow_recurring_jobs": True,
    "notification_channel": "webui",
    "insert_system_prompt": True,
    "prompt_strategy": "instruction only",
}


def sched_config(**overrides):
    settings = {**SCHED_DEFAULTS, **overrides}
    apply_config(
        api={"max_context": 16768},
        model=MODEL,
        modules={"settings": {"scheduler": settings}},
        core={"cmd_prefix": "/"},
    )


@pytest.fixture
def sched(fake_manager):
    sched_config()
    mod = Scheduler(fake_manager)
    # wire storage + reschedule event by hand; the dispatcher task itself is
    # only exercised in test_on_ready_starts_dispatcher
    mod.schedule = core.storage.StorageList("schedule", type="json")
    mod._reschedule_event = asyncio.Event()
    return mod


# ---------------------------------------------------------------------------
# _calculate_next_from
# ---------------------------------------------------------------------------

def test_next_from_clock_time_before_target_same_day(sched):
    nxt = sched._calculate_next_from(MON, {"target_hour": 14, "target_minute": 30})
    assert nxt == MON.replace(hour=14, minute=30)


def test_next_from_clock_time_after_target_rolls_to_tomorrow(sched):
    nxt = sched._calculate_next_from(MON, {"target_hour": 9, "target_minute": 0})
    assert nxt == (MON + datetime.timedelta(days=1)).replace(hour=9, minute=0)


def test_next_from_clock_time_honours_interval_days(sched):
    nxt = sched._calculate_next_from(MON, {"target_hour": 9, "days": 2})
    assert nxt == (MON + datetime.timedelta(days=2)).replace(hour=9, minute=0)


def test_next_from_weekday_target_this_week(sched):
    # MON is a Monday; target Wednesday (2) at 14:00
    nxt = sched._calculate_next_from(
        MON, {"target_hour": 14, "target_minute": 0, "target_weekday": 2}
    )
    assert nxt == (MON + datetime.timedelta(days=2)).replace(hour=14, minute=0)


def test_next_from_weekday_target_passed_rolls_a_full_week(sched):
    # same weekday as base, but the clock time already passed -> +7 days
    nxt = sched._calculate_next_from(
        MON, {"target_hour": 9, "target_minute": 0, "target_weekday": 0}
    )
    assert nxt == (MON + datetime.timedelta(days=7)).replace(hour=9, minute=0)


def test_next_from_weekdays_only_skips_the_weekend(sched):
    nxt = sched._calculate_next_from(
        FRI, {"target_hour": 9, "target_minute": 0, "weekdays_only": True}
    )
    # fri 09:00 already passed -> sat -> sun -> next monday 09:00
    assert nxt == datetime.datetime(2026, 10, 26, 9, 0)


def test_next_from_relative_delta(sched):
    nxt = sched._calculate_next_from(MON, {"days": 1, "hours": 2})
    assert nxt == MON + datetime.timedelta(days=1, hours=2)


def test_next_from_zero_or_missing_interval_is_none(sched):
    assert sched._calculate_next_from(MON, {}) is None
    assert sched._calculate_next_from(MON, {"days": 0}) is None
    assert sched._calculate_next_from(MON, None) is None


def test_next_trigger_relative_is_relative_to_now(sched):
    nxt = sched._calculate_next_trigger({"hours": 1})
    drift = abs((nxt - datetime.datetime.now() - datetime.timedelta(hours=1)).total_seconds())
    assert drift < 5


# ---------------------------------------------------------------------------
# _get_next_due_job / _get_index
# ---------------------------------------------------------------------------

def test_next_due_job_picks_earliest_and_skips_garbage(sched):
    now = datetime.datetime.now()
    sched.schedule.extend([
        {"id": "a", "trigger_time": (now + datetime.timedelta(hours=5)).isoformat()},
        {"id": "b", "trigger_time": (now + datetime.timedelta(minutes=5)).isoformat()},
        {"id": "c", "trigger_time": "not-a-date"},
    ])
    job, delay = sched._get_next_due_job()
    assert job["id"] == "b"
    assert 0 < delay <= 300


def test_next_due_job_empty_schedule(sched):
    assert sched._get_next_due_job() == (None, None)


def test_get_index(sched):
    sched.schedule.append({"id": "abc"})
    assert sched._get_index("abc") == 0
    assert sched._get_index("nope") == -1
    assert sched._get_index(None) == -1


# ---------------------------------------------------------------------------
# add_job
# ---------------------------------------------------------------------------

async def test_add_job_relative_duration(sched):
    res = await sched.add_job("do a thing", relative_duration="2d 4h 30m")

    assert res["status"] == "success"
    job = sched.schedule[0]
    assert job["action"] == "do a thing"
    assert job["channel"] == "webui"  # configured default
    assert job["recurring"] is False and job["recurs_in"] is None
    delta = datetime.datetime.fromisoformat(job["trigger_time"]) - datetime.datetime.now()
    assert abs(delta.total_seconds() - (2 * 86400 + 4 * 3600 + 30 * 60)) < 5
    assert sched._reschedule_event.is_set()


async def test_add_job_clock_time(sched):
    await sched.add_job("ping", target_time="23:59")
    trig = datetime.datetime.fromisoformat(sched.schedule[0]["trigger_time"])
    assert (trig.hour, trig.minute) == (23, 59)
    assert trig > datetime.datetime.now()


async def test_add_job_explicit_channel_beats_config_default(sched):
    await sched.add_job("x", channel="Telegram", relative_duration="1h")
    assert sched.schedule[0]["channel"] == "telegram"


async def test_add_job_recurring_stores_recurrence(sched):
    res = await sched.add_job("x", target_time="09:00", recurring=True)
    assert res["status"] == "success"
    job = sched.schedule[0]
    assert job["recurring"] is True
    assert job["recurs_in"]["target_hour"] == 9


async def test_add_job_recurring_blocked_by_policy(sched):
    sched_config(allow_recurring_jobs=False)
    res = await sched.add_job("x", target_time="09:00", recurring=True)
    assert res["status"] == "error"
    assert "security policy" in res["content"]
    assert list(sched.schedule) == []


async def test_add_job_validates_input(sched):
    bad_calls = [
        {"target_time": "25:00"},                      # hour out of range
        {"target_time": "10:70"},                      # minute out of range
        {"target_time": "abc"},                        # not a time at all
        {"target_time": "10:00", "target_weekday": 7}, # weekday out of range
        {},                                            # zero interval
    ]
    for kwargs in bad_calls:
        res = await sched.add_job("x", **kwargs)
        assert res["status"] == "error", kwargs
    assert list(sched.schedule) == []


# ---------------------------------------------------------------------------
# edit_job / remove_job
# ---------------------------------------------------------------------------

async def test_edit_job_unknown_id(sched):
    res = await sched.edit_job("ghost", action="x")
    assert res["status"] == "error" and "does not exist" in res["content"]


async def test_edit_job_partial_update_keeps_trigger(sched):
    await sched.add_job("orig", relative_duration="3h")
    job_id = sched.schedule[0]["id"]
    old_trigger = sched.schedule[0]["trigger_time"]

    res = await sched.edit_job(job_id, action="new action")

    assert res["status"] == "success"
    assert sched.schedule[0]["action"] == "new action"
    assert sched.schedule[0]["trigger_time"] == old_trigger


async def test_edit_job_time_change_recalculates_trigger(sched):
    await sched.add_job("orig", relative_duration="3h")
    job_id = sched.schedule[0]["id"]
    old_trigger = sched.schedule[0]["trigger_time"]

    await sched.edit_job(job_id, relative_duration="10h")

    new_trigger = datetime.datetime.fromisoformat(sched.schedule[0]["trigger_time"])
    assert new_trigger > datetime.datetime.fromisoformat(old_trigger)


async def test_remove_job(sched):
    await sched.add_job("x", relative_duration="1h")
    job_id = sched.schedule[0]["id"]

    assert (await sched.remove_job(job_id))["status"] == "success"
    assert list(sched.schedule) == []
    assert (await sched.remove_job(job_id))["status"] == "error"


def test_remove_job_from_storage_signals_reschedule(sched):
    sched.schedule.append({"id": "x"})
    sched._remove_job_from_storage("x")
    assert list(sched.schedule) == []
    assert sched._reschedule_event.is_set()


# ---------------------------------------------------------------------------
# recurring bookkeeping
# ---------------------------------------------------------------------------

def test_reschedule_recurring_preserves_cadence(sched):
    recur = {"target_hour": 9, "target_minute": 0}
    past = (datetime.datetime.now() - datetime.timedelta(days=3)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    sched.schedule.append({
        "id": "r1", "recurring": True, "recurs_in": recur,
        "trigger_time": past.isoformat(),
    })

    sched._reschedule_recurring_job(sched.schedule[0])

    now = datetime.datetime.now()
    new = datetime.datetime.fromisoformat(sched.schedule[0]["trigger_time"])
    assert now < new <= now + datetime.timedelta(days=1)
    assert (new.hour, new.minute) == (9, 0)
    assert sched._reschedule_event.is_set()


def test_reschedule_recurring_invalid_interval_keeps_job(sched, fake_manager):
    sched.schedule.append({
        "id": "r2", "recurring": True, "recurs_in": {},
        "trigger_time": "garbage",
    })

    sched._reschedule_recurring_job(sched.schedule[0])

    assert sched.schedule[0]["trigger_time"] == "garbage"
    assert any("invalid interval" in m for cat, m in fake_manager.logs)


def test_advance_recurring_skips_missed_occurrences_without_firing(sched):
    recur = {"target_hour": 9, "target_minute": 0}
    past = (datetime.datetime.now() - datetime.timedelta(days=5)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    sched.schedule.append({
        "id": "r3", "recurring": True, "recurs_in": recur,
        "trigger_time": past.isoformat(),
    })

    sched._advance_recurring_to_future(sched.schedule[0])

    now = datetime.datetime.now()
    new = datetime.datetime.fromisoformat(sched.schedule[0]["trigger_time"])
    assert now < new <= now + datetime.timedelta(days=1)
    assert (new.hour, new.minute) == (9, 0)


def test_advance_recurring_invalid_interval_is_noop(sched, fake_manager):
    past = datetime.datetime.now() - datetime.timedelta(days=1)
    sched.schedule.append({
        "id": "r4", "recurring": True, "recurs_in": {},
        "trigger_time": past.isoformat(),
    })

    sched._advance_recurring_to_future(sched.schedule[0])

    assert datetime.datetime.fromisoformat(sched.schedule[0]["trigger_time"]) == past
    assert any("could not advance" in m for cat, m in fake_manager.logs)


# ---------------------------------------------------------------------------
# _job_wrapper lifecycle
# ---------------------------------------------------------------------------

async def test_job_wrapper_one_time_job_removed_after_firing(sched, monkeypatch):
    sched.schedule.append({"id": "j1", "action": "a", "recurring": False})
    ran = []

    async def fake_execute(job):
        ran.append(job["id"])

    monkeypatch.setattr(sched, "_execute_job", fake_execute)
    await sched._job_wrapper(sched.schedule[0])

    assert ran == ["j1"]
    assert list(sched.schedule) == []


async def test_job_wrapper_recurring_reschedules_after_firing(sched, monkeypatch):
    recur = {"target_hour": 9, "target_minute": 0}
    past = (datetime.datetime.now() - datetime.timedelta(days=2)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    sched.schedule.append({
        "id": "j2", "action": "a", "recurring": True, "recurs_in": recur,
        "trigger_time": past.isoformat(),
    })

    async def fake_execute(job):
        pass

    monkeypatch.setattr(sched, "_execute_job", fake_execute)
    await sched._job_wrapper(sched.schedule[0])

    assert list(sched.schedule)  # still there
    new = datetime.datetime.fromisoformat(sched.schedule[0]["trigger_time"])
    assert new > datetime.datetime.now()


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: core.module.Module has no log_error() (only log), "
    "so _job_wrapper's error handler itself raises AttributeError instead of "
    "logging and containing the failure - see TEST_PLAN finding 14",
)
async def test_job_wrapper_swallows_execution_errors(sched, fake_manager, monkeypatch):
    sched.schedule.append({"id": "j3", "action": "a", "recurring": False})

    async def boom(job):
        raise RuntimeError("job failed")

    monkeypatch.setattr(sched, "_execute_job", boom)
    await sched._job_wrapper(sched.schedule[0])  # must not raise

    assert any("error executing job" in m for m, e in fake_manager.errors)
    assert len(sched.schedule) == 1  # stays queued for a later retry


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug (finding 14): the AttributeError from _job_wrapper's "
    "broken error handler is caught by the dispatcher loop, whose own "
    "log_error call raises again - the dispatcher task dies and no further "
    "jobs ever fire",
)
async def test_dispatcher_survives_a_failing_job(fake_manager, monkeypatch):
    sched_config()
    mod = Scheduler(fake_manager)
    await mod.on_ready()

    async def boom(job):
        raise RuntimeError("job failed")

    monkeypatch.setattr(mod, "_execute_job", boom)
    past = (datetime.datetime.now() - datetime.timedelta(minutes=5)).isoformat()
    mod.schedule.append({"id": "j9", "action": "a", "recurring": False, "trigger_time": past})
    mod.schedule.save()
    mod._signal_reschedule()

    await asyncio.sleep(0.2)  # give the dispatcher time to fire the overdue job

    alive = not mod._dispatcher_task.done()
    if not alive:
        mod._dispatcher_task.exception()  # retrieve, keeps asyncio GC noise down
    await mod.on_unload()

    assert alive


async def test_job_wrapper_without_id_is_noop(sched):
    await sched._job_wrapper({})


# ---------------------------------------------------------------------------
# _execute_job
# ---------------------------------------------------------------------------

async def test_execute_job_instruction_only_and_pushes_result(
    sched, fake_manager, fake_channel
):
    fake_manager.channels["fake"] = fake_channel
    sched.manager.API.queue_response({"role": "assistant", "content": "the answer"})

    await sched._execute_job({"id": "j", "action": "water the plants", "channel": "fake"})

    sent = sched.manager.API.sent[-1]
    assert sent["context"] == [{"role": "system", "content": "water the plants"}]
    assert fake_channel.pushes == ["the answer"]


async def test_execute_job_filters_scheduler_tools(sched, fake_manager, fake_channel):
    fake_manager.channels["fake"] = fake_channel
    fake_manager.tools = [
        {"function": {"name": "scheduler_add_job"}},
        {"function": {"name": "calendar_add_event"}},
    ]
    sched.manager.API.queue_response({"role": "assistant", "content": "x"})

    await sched._execute_job({"id": "j", "action": "a", "channel": "fake"})

    tools = sched.manager.API.sent[-1]["tools"]
    assert [t["function"]["name"] for t in tools] == ["calendar_add_event"]


async def test_execute_job_system_prompt_strategy(sched, fake_manager, fake_channel):
    ctx = core.context.Context(fake_channel)
    fake_channel.context = ctx
    await ctx.chat.autoload()
    sched_config(prompt_strategy="system prompt + instruction")
    fake_manager.channels["fake"] = fake_channel
    sched.manager.API.queue_response({"role": "assistant", "content": "ok"})

    await sched._execute_job({"id": "j", "action": "do it", "channel": "fake"})

    sent = sched.manager.API.sent[-1]["context"]
    # supports_developer_role is False on FakeAPI -> instruction goes as user
    assert sent[-1]["role"] == "user"
    assert "do it" in sent[-1]["content"]


async def test_execute_job_announces_tool_output(sched, fake_manager, fake_channel):
    fake_manager.channels["fake"] = fake_channel
    sched.manager.API.queue_response(
        {"role": "assistant", "content": "pre", "tool_calls": [{"id": "c1"}]}
    )

    async def fake_process(msg, push=False):
        yield {"type": "content", "content": "post"}

    fake_channel.tc_manager = SimpleNamespace(process=fake_process)

    await sched._execute_job({"id": "j", "action": "a", "channel": "fake"})

    assert fake_channel.pushes == ["pre\npost"]


async def test_execute_job_retries_on_api_error(sched, fake_manager, fake_channel, monkeypatch):
    sleeps = []

    async def fast_sleep(t):
        sleeps.append(t)

    monkeypatch.setattr(sched_mod.asyncio, "sleep", fast_sleep)
    fake_manager.channels["fake"] = fake_channel
    sched.manager.API.queue_response(core.api.APIError("nope"))
    sched.manager.API.queue_response(None)  # also triggers the empty-response retry
    sched.manager.API.queue_response({"role": "assistant", "content": "ok"})

    await sched._execute_job({"id": "j", "action": "a", "channel": "fake"})

    assert sleeps == [5, 5]
    logs = " ".join(m for cat, m in fake_manager.logs)
    assert "API error" in logs and "empty response" in logs
    assert fake_channel.pushes == ["ok"]


async def test_execute_job_without_channel_logs_error(sched, fake_manager):
    await sched._execute_job({"id": "j", "action": "a", "channel": "ghost"})
    assert any("no channel available" in m for cat, m in fake_manager.logs)


async def test_execute_job_without_context_logs_error(sched, fake_manager, fake_channel):
    fake_channel.context = None
    fake_manager.channels["fake"] = fake_channel
    await sched._execute_job({"id": "j", "action": "a", "channel": "fake"})
    assert any("no valid context" in m for cat, m in fake_manager.logs)


# ---------------------------------------------------------------------------
# wiring, system prompt, formatting
# ---------------------------------------------------------------------------

async def test_on_ready_starts_dispatcher_and_on_unload_stops_it(fake_manager):
    sched_config()
    mod = Scheduler(fake_manager)
    await mod.on_ready()

    assert isinstance(mod.schedule, core.storage.StorageList)
    task = mod._dispatcher_task
    assert not task.done()

    await mod.on_unload()
    assert task.done()


async def test_system_prompt_insert_and_opt_out(sched):
    assert await sched.on_system_prompt() is None  # empty schedule

    sched.schedule.append({
        "id": "j1", "action": "do it", "channel": "webui",
        "trigger_time": "2027-05-01T14:30:00", "recurring": False,
    })
    prompt = await sched.on_system_prompt()
    assert "trigger these events" in prompt and "do it" in prompt

    sched_config(insert_system_prompt=False)
    assert await sched.on_system_prompt() is None


def test_str_lists_jobs(sched):
    sched.schedule.append({
        "id": "j1", "action": "do it", "channel": "webui",
        "trigger_time": "2027-05-01T14:30:00", "recurring": False,
    })
    assert str(sched) == "j1: one-time, due 2027-05-01 14:30 on webui: do it"


def test_format_recurring_time_variants(sched):
    fmt = sched._format_recurring_time
    assert fmt({"target_hour": 9, "target_minute": 5}) == "every day at 9:05 AM"
    assert fmt({"target_hour": 13, "target_minute": 0}) == "every day at 1:00 PM"
    assert fmt({"target_hour": 0, "target_minute": 0}) == "every day at 12:00 AM"
    assert fmt({"target_hour": 9, "target_weekday": 0}) == "every Monday at 9:00 AM"
    assert fmt({"target_hour": 9, "weekdays_only": True}) == "every weekday at 9:00 AM"
    assert fmt({"days": 2, "hours": 4}) == "every 2 days, 4 hours"
    assert fmt({}) == "invalid schedule"


def test_format_one_time_job(sched):
    ok = sched._format_one_time_job({"trigger_time": "2027-05-01T14:30:00"})
    assert ok == "one-time, due 2027-05-01 14:30"
    assert sched._format_one_time_job({"trigger_time": "garbage"}) == "one-time, invalid time"


# ---------------------------------------------------------------------------
# on_tool_summary hook (webui one-line result hint, added in dev a4b6d50,
# renamed from _tool_summary to the on_* hook convention in dev aaddc4d)
# ---------------------------------------------------------------------------

def test_on_tool_summary_add_job_prefers_relative_duration(sched):
    assert sched.on_tool_summary(
        "scheduler_add_job", {"relative_duration": "2d 4h", "target_time": "09:00"}, {}
    ) == "2d 4h"


def test_on_tool_summary_add_job_falls_through_to_target_time(sched):
    assert sched.on_tool_summary(
        "scheduler_add_job", {"target_time": "09:00"}, {}
    ) == "09:00"


def test_on_tool_summary_add_job_without_any_time_is_silent(sched):
    assert sched.on_tool_summary("scheduler_add_job", {}, {}) == ""
    # an explicitly empty duration is NOT a missing one (JS ?? semantics)
    assert sched.on_tool_summary(
        "scheduler_add_job", {"relative_duration": None, "target_time": "09:00"}, {}
    ) == "09:00"


def test_on_tool_summary_other_tools_are_silent(sched):
    assert sched.on_tool_summary("scheduler_remove_job", {"id": "x"}, {}) == ""


def test_ui_build_recur_relative(sched):
    recur, err = sched._ui_build_recur("relative", "2d 4h 30m", None, None)
    assert err is None
    assert (recur["days"], recur["hours"], recur["minutes"]) == (2, 4, 30)


def test_ui_build_recur_relative_invalid(sched):
    recur, err = sched._ui_build_recur("relative", "", None, None)
    assert recur is None and "invalid duration" in err


def test_ui_build_recur_clock(sched):
    recur, err = sched._ui_build_recur("clock", None, "14:30", "weekdays")
    assert err is None and recur["target_hour"] == 14 and recur["weekdays_only"] is True

    recur, err = sched._ui_build_recur("clock", None, "08:00", "2")
    assert err is None and recur["target_weekday"] == 2


def test_ui_build_recur_clock_validation(sched):
    assert sched._ui_build_recur("clock", None, "25:00", None)[0] is None
    assert sched._ui_build_recur("clock", None, "10:00", "9")[0] is None
    assert "between 0 (Monday) and 6 (Sunday)" in sched._ui_build_recur("clock", None, "10:00", "9")[1]
    assert sched._ui_build_recur("clock", None, "abc", None)[0] is None