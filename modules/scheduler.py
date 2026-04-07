import datetime
import asyncio
import core
import ulid

class Scheduler(core.module.Module):
    async def on_ready(self) -> None:
        """Initialize storage, manager, and schedule existing jobs."""
        self.schedule = core.storage.StorageList("schedule", type="json")
        self.tc_manager = core.toolcalls.ToolcallManager(self.channel)

        # Tracks active asyncio.TimerHandles so we can cancel jobs on demand
        self.scheduled_handles = {}

        # Load jobs from storage and schedule them
        # We use list() to snapshot the list to avoid issues if _schedule_job mutates it
        for job in list(self.schedule):
            self._schedule_job(job)

    def _schedule_job(self, job: dict) -> None:
        """
        Schedules a job using asyncio.call_later.
        Calculates delay from trigger_time and registers the callback.
        """
        job_id = job.get("id")

        # If job is already scheduled (e.g. edit), cancel existing timer
        if job_id in self.scheduled_handles:
            self.scheduled_handles[job_id].cancel()

        try:
            trigger_time = datetime.datetime.fromisoformat(job.get("trigger_time", ""))
        except (ValueError, TypeError) as e:
            core.log("scheduler", f"invalid trigger_time for job {job_id}: {e}")
            return

        now = datetime.datetime.now()
        delay = (trigger_time - now).total_seconds()

        if delay <= 0:
            # Job is due now (or overdue). Execute immediately.
            # We use create_task to run it asynchronously without blocking on_ready
            asyncio.create_task(self._job_wrapper(job))
        else:
            # Schedule for the future
            loop = asyncio.get_running_loop()
            # call_later expects a sync callback, so we wrap it in a lambda that creates a task
            handle = loop.call_later(delay, lambda: asyncio.create_task(self._job_wrapper(job)))
            self.scheduled_handles[job_id] = handle

    async def _job_wrapper(self, job: dict) -> None:
        """
        Wrapper that executes the job, handles cleanup, and recursion.
        """
        job_id = job.get("id")

        # Remove handle tracking since it has fired
        if job_id in self.scheduled_handles:
            del self.scheduled_handles[job_id]

        try:
            await self._execute_job(job)

            if job.get("recurring"):
                await self._reschedule_job(job)
            else:
                # One-time jobs are removed from storage after execution
                self._remove_job_from_storage(job_id)

        except Exception as e:
            core.log("scheduler", f"error executing job {job_id}: {e}")

    def _remove_job_from_storage(self, job_id: str) -> None:
        """Removes a job from storage by ID."""
        idx = self._get_index(job_id)
        if idx >= 0:
            self.schedule.pop(idx)
            self.schedule.save()

    async def _execute_job(self, job: dict) -> None:
        """Execute a scheduled job."""
        # Filter out scheduler_add_job to prevent recursive scheduling
        tools = [
            t for t in self.manager.tools
            if t.get("function", {}).get("name") != "scheduler_add_job"
        ]

        action = job.get("action")

        event_message = {
            "role": "user",
            "content": (
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

        if not response:
            return

        final_content = ""
        tool_calls = response.get("tool_calls")

        if tool_calls:
            final_content_list = []
            async for token in self.tc_manager.process(
                tool_calls,
                initial_content=response.get("content", "")
            ):
                if token.get("type") in ("content", "reasoning"):
                    final_content_list.append(token.get("content", ""))
            final_content = "".join(final_content_list)
        else:
            final_content = response.get("content", "")

        if final_content:
            channel = self.manager.channels.get(job.get("channel").lower().strip())
            if not channel and self.channel:
                channel = self.channel

            if not channel:
                return False

            await channel.announce(final_content, "schedule")

    async def _reschedule_job(self, job: dict) -> None:
        """Reschedules a recurring job based on its recurrence pattern."""
        recur = job.get("recurs_in", {})

        # Note: _calculate_next_trigger handles both specific times and deltas
        next_time = self._calculate_next_trigger(recur)

        if next_time:
            # Remove the OLD job from storage (it has been replaced)
            self._remove_job_from_storage(job.get("id"))

            # Create a NEW job entry with the same ID
            new_job = {
                "id": job.get("id", str(ulid.ULID())),
                "action": job.get("action"),
                "channel": job.get("channel"),
                "trigger_time": next_time.isoformat(),
                "recurring": True,
                "recurs_in": recur
            }

            # Add to storage and schedule it
            self.schedule.append(new_job)
            self.schedule.save()
            self._schedule_job(new_job)

    # ---------------------------------------------------------
    # Helper Methods
    # ---------------------------------------------------------

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

        # Relative time logic
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

    def _advance_to_next_weekday(
        self, candidate: datetime.datetime
    ) -> datetime.datetime:
        """Advances datetime to next valid weekday (Mon-Fri)."""
        candidate += datetime.timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += datetime.timedelta(days=1)
        return candidate

    def _get_index(self, job_id: str) -> int:
        """Checks if an ID is stored in the job list."""
        for index, job in enumerate(self.schedule):
            if job_id == str(job.get("id")):
                return index
        return -1

    def _weekday_name(self, weekday: int) -> str:
        """Convert weekday number to name (0=Monday, 6=Sunday)."""
        days = [
            "Monday", "Tuesday", "Wednesday",
            "Thursday", "Friday", "Saturday", "Sunday"
        ]
        if 0 <= weekday < len(days):
            return days[weekday]
        return "Unknown"

    def __str__(self) -> str:
        """Displays schedule as a human-readable list."""
        result = []
        for job in self.schedule:
            job_id = job.get("id")
            action = job.get("action", "")

            if job.get("recurring"):
                recur = job.get("recurs_in", {})
                time_due = self._format_recurring_time(recur)
            else:
                time_due = self._format_one_time_job(job)

            result.append(f"{job_id}: {time_due}: {action}")
        return "\n".join(result)

    def _format_recurring_time(self, recur: dict) -> str:
        """Format a recurring job's schedule for display."""
        if recur.get("target_hour") is not None:
            hour = recur["target_hour"]
            minute = recur.get("target_minute", 0)
            period = "AM" if hour < 12 else "PM"
            display_hour = hour
            if hour == 0:
                display_hour = 12
            elif hour > 12:
                display_hour = hour - 12

            time_str = f"{display_hour}:{minute:02d} {period}"

            if recur.get("target_weekday") is not None:
                return f"every {self._weekday_name(recur['target_weekday'])} at {time_str}"
            elif recur.get("weekdays_only"):
                return f"every weekday at {time_str}"
            else:
                interval_days = recur.get("days", 1)
                if interval_days == 1:
                    return f"every day at {time_str}"
                elif interval_days == 7:
                    return f"every week at {time_str}"
                else:
                    return f"every {interval_days} days at {time_str}"

        time_due_list = []
        for key in ["weeks", "days", "hours", "minutes", "seconds"]:
            amt = recur.get(key)
            if amt:
                time_due_list.append(f"{amt} {key}")
        return "every " + ", ".join(time_due_list) if time_due_list else "invalid schedule"

    def _format_one_time_job(self, job: dict) -> str:
        """Format a one-time job's schedule for display."""
        trigger_dt = datetime.datetime.fromisoformat(job.get("trigger_time", ""))
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

        return f"one-time, {', '.join(parts)} from now"

    async def on_system_prompt(self) -> str | None:
        if self.schedule:
            return f"Your scheduler system will trigger these events at the specified times:\n{self}"
        return None

    # ---------------------------------------------------------
    # Tool Definitions (add, edit, remove)
    # ---------------------------------------------------------

    async def add_job(
        self,
        action: str,
        channel: str | None = None,
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

        Channel defaults to the current channel by default. ONLY provide a different
        channel name if user explicitly asks for it!
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

            job_id = str(ulid.ULID())

            # Default channel handling
            resolved_channel = channel
            if not resolved_channel:
                if self.channel:
                    resolved_channel = self.channel.name
                else:
                    return self.result("error: no channel context available", False)

            sched = {
                "id": job_id,
                "action": action,
                "channel": str(resolved_channel).lower().strip(),
                "trigger_time": trigger_time.isoformat(),
                "recurring": recurring,
                "recurs_in": recur if recurring else None
            }

            self.schedule.append(sched)
            self.schedule.save()

            # Schedule the job with asyncio
            self._schedule_job(sched)

        except Exception as e:
            return self.result(f"error: {e}", False)

        return self.result("job successfully added!")

    async def edit_job(
        self,
        id: str,
        action: str,
        channel: str | None = None,
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

        existing_job = self.schedule[index]

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

            resolved_channel = channel or existing_job.get("channel")

            sched = {
                "id": id,
                "action": action,
                "channel": resolved_channel,
                "trigger_time": trigger_time.isoformat(),
                "recurring": recurring,
                "recurs_in": recur if recurring else None
            }

            # Update storage
            self.schedule[index] = sched
            self.schedule.save()

            # Re-schedule with asyncio (cancels old handle, creates new one)
            self._schedule_job(sched)

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

        # Cancel asyncio handle if it exists
        if id in self.scheduled_handles:
            self.scheduled_handles[id].cancel()
            del self.scheduled_handles[id]

        self.schedule.pop(index)
        self.schedule.save()
        return self.result("job deleted")
