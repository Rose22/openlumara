# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
"""Scheduler trigger-time math and add_job validation, on a frozen clock."""

import asyncio
import datetime
import types

import pytest

import core
from modules.scheduler import module as scheduler_module

NOW = datetime.datetime(2026, 10, 26, 10, 0)  # a Monday
FRI = datetime.datetime(2026, 10, 23, 10, 0)
SAT = datetime.datetime(2026, 10, 24, 8, 0)


def at(day, hour, minute=0):
    return datetime.datetime(2026, 10, day, hour, minute)


class FrozenDatetime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


@pytest.fixture
def sched(manager, tmp_path, monkeypatch, set_config):
    monkeypatch.setattr(scheduler_module, "datetime",
                        types.SimpleNamespace(datetime=FrozenDatetime, timedelta=datetime.timedelta))
    # bare-bool settings get no schema fallback, so set it like a real config file would
    set_config(modules={"settings": {"scheduler": {"allow_recurring_jobs": True}}})
    mod = scheduler_module.Scheduler(manager)
    # what on_ready sets up, minus the dispatcher task
    mod.schedule = core.storage.StorageList("schedule", type="json", path=str(tmp_path))
    mod._reschedule_event = asyncio.Event()
    return mod


@pytest.mark.parametrize("base, recur, expected", [
    (NOW, {"target_hour": 14, "target_minute": 30}, at(26, 14, 30)),          # later today
    (NOW, {"target_hour": 9}, at(27, 9)),                                     # passed, tomorrow
    (NOW, {"target_hour": 10}, at(27, 10)),                                   # exactly now is not "after"
    (NOW, {"target_hour": 9, "days": 2}, at(28, 9)),                          # every other day
    (NOW, {"target_hour": 14, "target_weekday": 2}, at(28, 14)),              # wednesday this week
    (NOW, {"target_hour": 9, "target_weekday": 0}, datetime.datetime(2026, 11, 2, 9)),  # monday passed
    (FRI, {"target_hour": 9, "weekdays_only": True}, at(26, 9)),              # skips the weekend
    (SAT, {"target_hour": 9, "weekdays_only": True}, at(26, 9)),
    (NOW, {"days": 1, "hours": 2, "minutes": 30}, at(27, 12, 30)),            # relative delta
    (NOW, {"weeks": 1}, datetime.datetime(2026, 11, 2, 10)),
])
def test_next_trigger(sched, base, recur, expected):
    assert sched._calculate_next_from(base, recur) == expected


@pytest.mark.parametrize("recur", [None, {}, {"days": 0, "hours": 0}])
def test_zero_interval_has_no_next_trigger(sched, recur):
    assert sched._calculate_next_from(NOW, recur) is None


@pytest.mark.parametrize("reschedule", ["_reschedule_recurring_job", "_advance_recurring_to_future"])
@pytest.mark.parametrize("recur, last, expected", [
    ({"target_hour": 9}, at(23, 9), at(27, 9)),          # missed fri/sat/sun/mon, next is tue
    ({"hours": 2}, at(26, 7, 30), at(26, 11, 30)),       # keeps the :30 cadence, not now + 2h
])
def test_recurring_reschedule_skips_missed_and_keeps_cadence(sched, reschedule, recur, last, expected):
    sched.schedule.append({"id": "r", "recurring": True, "recurs_in": recur, "trigger_time": last.isoformat()})

    getattr(sched, reschedule)(sched.schedule[0])

    assert sched.schedule[0]["trigger_time"] == expected.isoformat()
    assert sched._reschedule_event.is_set()


def test_recurring_with_invalid_interval_left_alone(sched, manager):
    sched.schedule.append({"id": "r", "recurring": True, "recurs_in": {}, "trigger_time": at(23, 9).isoformat()})

    sched._reschedule_recurring_job(sched.schedule[0])

    assert sched.schedule[0]["trigger_time"] == at(23, 9).isoformat()
    assert "invalid interval" in manager.logs[-1][1]


async def test_add_job_relative(sched):
    res = await sched.add_job("water the plants", relative_duration="2d 4h 30m")

    assert res["status"] == "success"
    job = sched.schedule[0]
    assert job["trigger_time"] == at(28, 14, 30).isoformat()
    assert job["channel"] == "webui"
    assert job["recurring"] is False and job["recurs_in"] is None
    assert sched._reschedule_event.is_set()


async def test_add_job_recurring_clock_time(sched):
    await sched.add_job("standup", channel="Telegram", target_time="09:15", weekdays_only=True, recurring=True)

    job = sched.schedule[0]
    assert job["trigger_time"] == at(27, 9, 15).isoformat()
    assert job["channel"] == "telegram"
    assert job["recurs_in"]["target_hour"] == 9 and job["recurs_in"]["weekdays_only"]


@pytest.mark.parametrize("kwargs", [
    {"target_time": "24:00"},
    {"target_time": "10:60"},
    {"target_time": "10:00:61"},
    {"target_time": "noon"},
    {"target_time": "10"},
    {"target_time": "10:00", "target_weekday": 7},
    {},  # no time at all
])
async def test_add_job_rejects_bad_input(sched, kwargs):
    assert (await sched.add_job("x", **kwargs))["status"] == "error"
    assert list(sched.schedule) == []


async def test_recurring_jobs_can_be_disabled(sched, set_config):
    set_config(modules={"settings": {"scheduler": {"allow_recurring_jobs": False}}})

    assert (await sched.add_job("x", target_time="09:00", recurring=True))["status"] == "error"
    assert list(sched.schedule) == []
