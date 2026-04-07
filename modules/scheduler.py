
import datetime
import asyncio
import core
import ulid

class Scheduler(core.module.Module):
    async def on_ready(self):
        self.schedule = core.storage.StorageList("schedule", type="json")
        self.tc_manager = core.toolcalls.ToolcallManager(self.channel)

    async def on_background(self):
        """main loop"""
        core.log("init", "scheduler started")
        while True:
            for job in list(self.schedule):
                trigger_time = datetime.datetime.fromisoformat(job.get("trigger_time"))

                if datetime.datetime.now() >= trigger_time:
                    try:
                        tools = self.manager.tools.copy()
                        for index, tool_obj in enumerate(tools):
                            if tool_obj.get("function", {}).get("name") == "scheduler_add_job":
                                del tools[index]

                        action = job.get("action")
                        if self.channel:
                            event_message = {
                                "role": "user",
                                "content": (
                                    f"# An event has triggered!\n"
                                    f"Please follow these instructions:\n"
                                    f"{action}\n"
                                    f"Use tools if needed. For simple reminders, do not use tools."
                                )
                            }

                            response = await self.manager.API.send(
                                [event_message],
                                use_tools=True,
                                tools=tools
                            )

                            final_content = ""

                            if response:
                                tool_calls = response.get("tool_calls")

                                if tool_calls:
                                    final_content_list = []
                                    async for token in self.tc_manager.process(
                                        tool_calls,
                                        initial_content=response.get("content", "")
                                    ):
                                        if token.get("type") in ("content", "reasoning"):
                                            final_content_list.append(token.get("content"))
                                    final_content = "".join(final_content_list)
                                else:
                                    final_content = response.get("content", "")
                                    assistant_msg = {"role": "assistant", "content": final_content}
                                    if response.get("reasoning"):
                                        assistant_msg["reasoning_content"] = response["reasoning"]

                                if final_content:
                                    channel = self.manager.channels.get(job.get("channel"))
                                    if not channel:
                                        channel = self.channel
                                    
                                    await channel.announce(final_content, "schedule")

                            self.schedule.pop(self._get_index(job.get("id")))
                            self.schedule.save()

                            if job.get("recurring"):
                                await self._reschedule_job(job)

                    except Exception as e:
                        core.log("scheduler", f"error: {e}")

            await asyncio.sleep(0.10)

    async def _reschedule_job(self, job: dict):
        """Reschedules a recurring job based on its recurrence pattern."""
        recur = job.get("recurs_in", {})
        next_time = self._calculate_next_trigger(recur)
        if next_time:
            await self.add_job(
                action=job.get("action"),
                recurring=True,
                **recur
            )

    def _calculate_next_trigger(self, recur: dict) -> datetime.datetime | None:
        """
        Calculates the next trigger time based on recurrence pattern.
        Handles both relative (delta) and specific clock times.
        """
        now = datetime.datetime.now()

        if recur.get("target_hour") is not None:
            target_hour = recur["target_hour"]
            target_minute = recur.get("target_minute", 0)
            target_second = recur.get("target_second", 0)

            candidate = now.replace(
                hour=target_hour,
                minute=target_minute,
                second=target_second,
                microsecond=0
            )

            if recur.get("target_weekday") is not None:
                target_weekday = recur["target_weekday"]
                days_until_target = (target_weekday - now.weekday()) % 7
                if days_until_target == 0 and candidate <= now:
                    days_until_target = 7
                candidate += datetime.timedelta(days=days_until_target)

            elif recur.get("weekdays_only"):
                if candidate.weekday() >= 5 or candidate <= now:
                    candidate = self._advance_to_next_weekday(candidate)

            else:
                interval_days = recur.get("days", 1)
                if candidate <= now:
                    candidate += datetime.timedelta(days=interval_days)

            return candidate

        delta = datetime.timedelta(
            weeks=recur.get("weeks", 0),
            days=recur.get("days", 0),
            hours=recur.get("hours", 0),
            minutes=recur.get("minutes", 0),
            seconds=recur.get("seconds", 0)
        )

        if delta.total_seconds() == 0:
            return None

        return now + delta

    def _advance_to_next_weekday(self, candidate: datetime.datetime) -> datetime.datetime:
        """Advances datetime to next valid weekday (Mon-Fri)."""
        candidate += datetime.timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += datetime.timedelta(days=1)
        return candidate

    def _get_index(self, ulid: str):
        """checks if an ID is stored in the job list"""
        for index, job in enumerate(self.schedule):
            if ulid == str(job.get("id")):
                return index
        return -1

    def _weekday_name(self, weekday: int) -> str:
        """Convert weekday number to name (0=Monday, 6=Sunday)"""
        days = [
            "Monday", "Tuesday", "Wednesday",
            "Thursday", "Friday", "Saturday", "Sunday"
        ]
        return days[weekday]

    def __str__(self):
        """displays schedule as a human-readable list"""
        result = []
        for job in self.schedule:
            id = job.get("id")

            if job.get("recurring"):
                recur = job.get("recurs_in", {})
                if recur.get("target_hour") is not None:
                    hour = recur["target_hour"]
                    minute = recur.get("target_minute", 0)
                    period = "AM" if hour < 12 else "PM"
                    display_hour = hour if hour <= 12 else hour - 12
                    if display_hour == 0:
                        display_hour = 12
                    time_str = f"{display_hour}:{minute:02d} {period}"

                    if recur.get("target_weekday") is not None:
                        time_due = f"every {self._weekday_name(recur['target_weekday'])} at {time_str}"
                    elif recur.get("weekdays_only"):
                        time_due = f"every weekday at {time_str}"
                    else:
                        interval_days = recur.get("days", 1)
                        if interval_days == 1:
                            time_due = f"every day at {time_str}"
                        elif interval_days == 7:
                            time_due = f"every week at {time_str}"
                        else:
                            time_due = f"every {interval_days} days at {time_str}"
                else:
                    time_due_list = []
                    for key in ["weeks", "days", "hours", "minutes", "seconds"]:
                        amt = recur.get(key)
                        if amt:
                            time_due_list.append(f"{amt} {key}")
                    time_due = "every " + ", ".join(time_due_list)
            else:
                trigger_dt = datetime.datetime.fromisoformat(job.get("trigger_time"))
                delta = trigger_dt - datetime.datetime.now()
                total_seconds = int(delta.total_seconds())

                hours, remainder = divmod(total_seconds, 3600)
                minutes, seconds = divmod(remainder, 60)

                parts = []
                if hours > 0:
                    parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
                if minutes > 0:
                    parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
                if seconds > 0 or not parts:
                    parts.append(f"{seconds} second" + ("s" if seconds != 1 else ""))

                time_due = f"one-time, {', '.join(parts)} from now"

            result.append(f"{id}: {time_due}: {job['action']}")
        return "\n".join(result)

    async def on_system_prompt(self):
        if self.schedule:
            return f"Your scheduler system will trigger these events at the specified times:\n{self}"

    async def add_job(
        self,
        action: str,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        target_hour: int | None = None,
        target_minute: int = 0,
        target_second: int = 0,
        target_weekday: int | None = None,
        weekdays_only: bool = False,
        recurring: bool = False,
        channel: str = None,
    ):
        """
        Adds a scheduled job to the scheduler.

        Use ONE of these two modes:

        MODE 1 - RELATIVE TIME (from now):
            Use weeks, days, hours, minutes, seconds.
            Example: "every 5 minutes" -> minutes=5, recurring=True
            Example: "in 2 hours" -> hours=2, recurring=False

        MODE 2 - SPECIFIC CLOCK TIME:
            Use target_hour (0-23) and target_minute (0-59).
            Defaults to daily recurrence. Use days=N for longer intervals.
            Optionally set target_weekday (0=Monday, 6=Sunday) for specific days.
            Optionally set weekdays_only=True for weekday-only schedules.
            Example: "every morning at 10am" -> target_hour=10, recurring=True
            Example: "every weekday at 9am" -> target_hour=9, weekdays_only=True, recurring=True
            Example: "every Saturday at 3pm" -> target_hour=15, target_weekday=5, recurring=True
            Example: "every week at 3pm" -> target_hour=15, days=7, recurring=True

        NEVER add a job more than once!
        ALWAYS use the word "user" to refer to the user!

        If the job is a reminder to the user, start with "Remind user to".
        If the job is a task for you (the AI assistant) to perform, start with "You must"
        
        Channel defaults to the current channel by default. ONLY provide a different channel name if user explicitely asks for it! Ex. "remind me on telegram every day at 10am to do my morning routine"
        """

        try:
            recur = {
                "weeks": weeks,
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "target_hour": target_hour,
                "target_minute": target_minute,
                "target_second": target_second,
                "target_weekday": target_weekday,
                "weekdays_only": weekdays_only
            }

            trigger_time = self._calculate_next_trigger(recur)

            if trigger_time is None:
                return self.result("error: invalid schedule parameters (zero interval)", False)

            sched = {
                "id": str(ulid.ULID()),
                "action": action,
                "channel": channel or self.channel.name,
                "trigger_time": trigger_time.isoformat(),
                "recurring": recurring,
                "recurs_in": recur if recurring else None
            }

            self.schedule.append(sched)
            self.schedule.save()
        except Exception as e:
            return self.result(f"error: {e}", False)

        return self.result("job successfully added!")

    async def edit_job(
        self,
        id: str,
        action: str,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        target_hour: int | None = None,
        target_minute: int = 0,
        target_second: int = 0,
        target_weekday: int | None = None,
        weekdays_only: bool = False,
        recurring: bool = False
    ):
        """
        Edits a job in the scheduler.

        ONLY use this if:
            - You've verified the ID
            - User explicitly requested editing of the job
        """
        index = self._get_index(id)
        if index == -1:
            return self.result("id does not exist", False)

        try:
            recur = {
                "weeks": weeks,
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "target_hour": target_hour,
                "target_minute": target_minute,
                "target_second": target_second,
                "target_weekday": target_weekday,
                "weekdays_only": weekdays_only
            }

            trigger_time = self._calculate_next_trigger(recur)

            if trigger_time is None:
                return self.result("error: invalid schedule parameters (zero interval)", False)

            sched = {
                "id": str(ulid.ULID()),
                "action": action,
                "trigger_time": trigger_time.isoformat(),
                "recurring": recurring,
                "recurs_in": recur if recurring else None
            }

            self.schedule[index] = sched
            self.schedule.save()
        except Exception as e:
            return self.result(f"error: {e}", False)

        return self.result("job edited")

    async def remove_job(self, id: str):
        """
        Removes a scheduled job from the scheduler.

        ONLY use this if:
            - You've verified the ID
            - User explicitly requested deletion of the job
        """

        index = self._get_index(id)
        if index == -1:
            return self.result("id does not exist", False)

        self.schedule.pop(index)
        self.schedule.save()
        return self.result("job deleted")
