import datetime
import asyncio
import core
import ulid

class Scheduler(core.module.Module):
    """Lets your AI send you scheduled reminders and do things at specified times"""

    settings = {
        "put_scheduled_jobs_in_system_prompt": True
    }

    async def on_ready(self, *args, **kwargs):
        """Initialize storage, manager, and schedule existing jobs."""
        self.schedule = core.storage.StorageList("schedule", type="json")

        # Map of job_id -> asyncio.TimerHandle
        self.scheduled_handles = {}

        # Load persisted jobs and schedule them
        for job in list(self.schedule):
            self._schedule_job(job)

    # ---------------------------------------------------------
    # Scheduling Logic
    # ---------------------------------------------------------

    def _schedule_job(self, job: dict) -> None:
        """
        Schedules a job to run at its trigger_time using asyncio.call_later.
        If a handle already exists for this job, it is cancelled and replaced.
        """
        job_id = job.get("id")

        # Cancel existing handle if present (prevents duplicates on edit/restart)
        if job_id in self.scheduled_handles:
            self.scheduled_handles[job_id].cancel()

        try:
            trigger_time = datetime.datetime.fromisoformat(job.get("trigger_time", ""))
        except (ValueError, TypeError):
            core.log("scheduler", f"invalid trigger_time for job {job_id}")
            return

        now = datetime.datetime.now()
        delay = (trigger_time - now).total_seconds()

        if delay <= 0:
            # Run immediately if due
            asyncio.create_task(self._job_wrapper(job))
        else:
            loop = asyncio.get_running_loop()
            handle = loop.call_later(delay, lambda: asyncio.create_task(self._job_wrapper(job)))
            self.scheduled_handles[job_id] = handle

    async def _job_wrapper(self, job: dict) -> None:
        """Executes the job and handles cleanup or recurrence."""
        job_id = job.get("id")

        # Clear the handle reference since it has fired
        if job_id in self.scheduled_handles:
            del self.scheduled_handles[job_id]

        try:
            await self._execute_job(job)

            # Check if the job still exists in storage before rescheduling.
            # If remove_job was called during execution, this index will be -1.
            if self._get_index(job_id) == -1:
                return

            if job.get("recurring"):
                # Refresh job data from storage to catch any edits made during execution
                idx = self._get_index(job_id)
                if idx >= 0:
                    current_job = self.schedule[idx]
                    self._reschedule_job(current_job)
            else:
                # One-time job: remove from storage
                self._remove_job_from_storage(job_id)

        except Exception as e:
            core.log("scheduler", f"error executing job {job_id}: {e}")

    def _reschedule_job(self, job: dict) -> None:
        """Updates a recurring job's time in-place and reschedules it."""
        recur = job.get("recurs_in", {})
        next_time = self._calculate_next_trigger(recur)

        if next_time:
            # Update the trigger time on the existing object
            job["trigger_time"] = next_time.isoformat()

            # Persist changes
            self.schedule.save()

            # Re-schedule with asyncio
            self._schedule_job(job)
        else:
            core.log("scheduler", f"could not reschedule recurring job {job.get('id')}: invalid interval")

    def _remove_job_from_storage(self, job_id: str) -> None:
        """Removes a job from storage list."""
        idx = self._get_index(job_id)
        if idx >= 0:
            self.schedule.pop(idx)
            self.schedule.save()

    # ---------------------------------------------------------
    # Execution
    # ---------------------------------------------------------

    async def _execute_job(self, job: dict) -> None:
        """Performs the actual action of the job."""
        job_id = job.get("id")

        # Determine the target channel for this job
        channel_name = (job.get("channel") or "").lower().strip()
        job_channel = self.manager.channels.get(channel_name)
        if not job_channel and self.channel:
            job_channel = self.channel

        if not job_channel:
            core.log("scheduler", f"error executing job {job_id}: no channel available for tool calls")
            return

        # Ensure context is available
        if not hasattr(job_channel, 'context') or job_channel.context is None:
            core.log("scheduler", f"error executing job {job_id}: channel has no valid context")
            return

        tools = [
            t for t in self.manager.tools
            if t.get("function", {}).get("name") != "scheduler_add_job"
        ]

        action = job.get("action")

        event_message = {
            "role": "user",
            "content": f"""
    [AUTOMATED SYSTEM INSTRUCTION]
    Please follow these instructions:

    {action}
    Use tools if needed. For simple reminders, do not use tools.
    """.strip()
        }

        await job_channel.context.chat.add(event_message)

        response = await self.manager.API.send(
            await job_channel.context.get(end_prompt=False),
            use_tools=True,
            tools=tools
        )

        # erase the automated instruction from history
        await job_channel.context.chat.pop(-1)

        if not response:
            return

        final_content = ""
        tool_calls = response.get("tool_calls")

        if tool_calls:
            # Use a local manager to avoid race conditions and ensure the correct channel is used
            tc_manager = core.toolcalls.ToolcallManager(job_channel)

            final_content_list = []
            async for token in tc_manager.process(
                tool_calls
            ):
                if token.get("type") == "content":
                    final_content_list.append(token.get("content", ""))
            final_content = "".join(final_content_list)
        else:
            final_content = response.get("content", "")

        if final_content:
            if job_channel:
                await job_channel.announce(final_content, "schedule")
            elif self.channel:
                await self.channel.announce(final_content, "schedule")

    # ---------------------------------------------------------
    # Time Calculations
    # ---------------------------------------------------------

    def _calculate_next_trigger(self, recur: dict) -> datetime.datetime:
        """Calculates the next trigger datetime based on recurrence dict."""
        now = datetime.datetime.now()

        # MODE 1: Specific Clock Time (e.g., "10am daily")
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
                # Specific day of week (e.g., "Mondays")
                target_weekday = recur["target_weekday"]
                days_until = (target_weekday - now.weekday()) % 7
                if days_until == 0 and candidate <= now:
                    days_until = 7
                candidate += datetime.timedelta(days=days_until)

            elif recur.get("weekdays_only"):
                # Weekdays only
                if candidate.weekday() >= 5 or candidate <= now:
                    candidate = self._advance_to_next_weekday(candidate)

            else:
                # Daily interval
                interval_days = recur.get("days", 1)
                if candidate <= now:
                    candidate += datetime.timedelta(days=interval_days)

            return candidate

        # MODE 2: Relative Delta (e.g., "in 5 minutes")
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

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def _get_index(self, job_id: str) -> int:
        """Finds the index of a job by ID."""
        for index, job in enumerate(self.schedule):
            if job_id == str(job.get("id")):
                return index
        return -1

    def __str__(self) -> str:
        """Displays schedule as a human-readable list."""
        result = []
        for job in self.schedule:
            job_id = job.get("id")
            action = job.get("action", "")
            chan_str = job.get("channel")
            time_str = self._format_job_time(job)
            result.append(f"{job_id}: {time_str} on {chan_str}: {action}")
        return "\n".join(result)

    def _format_job_time(self, job: dict) -> str:
        """Formats a job's time for display."""
        if job.get("recurring"):
            return self._format_recurring_time(job.get("recurs_in", {}))
        return self._format_one_time_job(job)

    def _format_recurring_time(self, recur: dict) -> str:
        if recur.get("target_hour") is not None:
            hour = recur["target_hour"]
            minute = recur.get("target_minute", 0)
            period = "AM" if hour < 12 else "PM"
            h = hour if hour <= 12 else hour - 12
            if hour == 0: h = 12
            time_str = f"{h}:{minute:02d} {period}"

            if recur.get("target_weekday") is not None:
                return f"every {self._weekday_name(recur['target_weekday'])} at {time_str}"
            elif recur.get("weekdays_only"):
                return f"every weekday at {time_str}"
            else:
                return f"every day at {time_str}"

        parts = []
        for k in ["weeks", "days", "hours", "minutes", "seconds"]:
            if recur.get(k):
                parts.append(f"{recur[k]} {k}")
        return "every " + ", ".join(parts) if parts else "invalid schedule"

    def _format_one_time_job(self, job: dict) -> str:
        trigger_dt = datetime.datetime.fromisoformat(job.get("trigger_time", ""))
        delta = trigger_dt - datetime.datetime.now()
        total_seconds = int(delta.total_seconds())

        h, rem = divmod(total_seconds, 3600)
        m, s = divmod(rem, 60)

        parts = []
        if h > 0: parts.append(f"{h} hour{'s' if h != 1 else ''}")
        if m > 0: parts.append(f"{m} minute{'s' if m != 1 else ''}")
        if s > 0 or not parts: parts.append(f"{s} second{'s' if s != 1 else ''}")

        return f"one-time, {', '.join(parts)} from now"

    def _weekday_name(self, weekday: int) -> str:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return days[weekday] if 0 <= weekday < 7 else "Unknown"

    async def on_system_prompt(self) -> str:
        if not self.config.get("put_scheduled_jobs_in_system_prompt"):
            return None

        if self.schedule:
            return f"Your scheduler system will trigger these events at the specified times:\n{self}"
        return None

    # ---------------------------------------------------------
    # Tools (LLM Interface)
    # ---------------------------------------------------------

    async def add_job(
        self,
        action: str,
        channel: str = None,
        relative_duration: str = None,
        target_time: str = None,
        target_weekday: int = None,
        weekdays_only: bool = False,
        recurring: bool = False,
    ):
        """Adds a scheduled job. MODE 1 - RELATIVE TIME: Use relative_duration (e.g., '2d 4h 30m'). MODE 2 - SPECIFIC CLOCK TIME: Use target_time (e.g., '14:30'). Optionally set target_weekday (0=Monday) or weekdays_only=True. Action is what action should be performed at the scheduled time. Action is an instruction/prompt for the AI to follow, so write it in second person form."""
        import re
        
        weeks = days = hours = minutes = seconds = 0
        target_hour = target_minute = target_second = None
        
        # Parse relative_duration (e.g., "2d 4h")
        if relative_duration:
            pattern = r'(\d+)\s*([wdhms])'
            matches = re.findall(pattern, relative_duration)
            for val, unit in matches:
                val = int(val)
                if unit == 'w': weeks = val
                elif unit == 'd': days = val
                elif unit == 'h': hours = val
                elif unit == 'm': minutes = val
                elif unit == 's': seconds = val

        # Parse target_time (e.g., "14:30:00")
        if target_time:
            parts = target_time.split(':')
            if len(parts) >= 2:
                target_hour = int(parts[0])
                target_minute = int(parts[1])
                if len(parts) == 3:
                    target_second = int(parts[2])

        try:
            recur = {
                "weeks": weeks, "days": days, "hours": hours, "minutes": minutes, "seconds": seconds,
                "target_hour": target_hour, "target_minute": target_minute, "target_second": target_second,
                "target_weekday": target_weekday, "weekdays_only": weekdays_only
            }

            trigger_time = self._calculate_next_trigger(recur)
            if trigger_time is None:
                return self.result("error: invalid schedule parameters (zero interval)", False)

            resolved_channel = channel or (self.channel.name if self.channel else None)
            if not resolved_channel:
                return self.result("error: no channel context available", False)

            job_id = str(ulid.ULID())
            job = {
                "id": job_id,
                "action": action,
                "channel": str(resolved_channel).lower().strip(),
                "trigger_time": trigger_time.isoformat(),
                "recurring": recurring,
                "recurs_in": recur if recurring else None
            }

            self.schedule.append(job)
            self.schedule.save()
            self._schedule_job(job)

            return self.result(f"job added. ID: {job_id}")

        except Exception as e:
            return self.result(f"error: {e}", False)

    async def edit_job(
        self,
        id: str,
        action: str = None,
        channel: str = None,
        relative_duration: str = None,
        target_time: str = None,
        target_weekday: int = None,
        weekdays_only: bool = False,
        recurring: bool = False
    ):
        index = self._get_index(id)
        if index == -1:
            return self.result("id does not exist", False)

        existing = self.schedule[index]

        try:
            import re
            existing_recur = existing.get("recurs_in", {})
            
            weeks = days = hours = minutes = seconds = 0
            target_hour = target_minute = target_second = None
            
            # Parse relative_duration
            if relative_duration:
                pattern = r'(\d+)\s*([wdhms])'
                matches = re.findall(pattern, relative_duration)
                for val, unit in matches:
                    val = int(val)
                    if unit == 'w': weeks = val
                    elif unit == 'd': days = val
                    elif unit == 'h': hours = val
                    elif unit == 'm': minutes = val
                    elif unit == 's': seconds = val

            # Parse target_time
            if target_time:
                parts = target_time.split(':')
                if len(parts) >= 2:
                    target_hour = int(parts[0])
                    target_minute = int(parts[1])
                    if len(parts) == 3:
                        target_second = int(parts[2])

            recur = {
                "weeks": weeks or existing_recur.get("weeks", 0), "days": days or existing_recur.get("days", 0), "hours": hours or existing_recur.get("hours", 0), "minutes": minutes or existing_recur.get("minutes", 0), "seconds": seconds or existing_recur.get("seconds", 0),
                "target_hour": target_hour or existing_recur.get("target_hour"), "target_minute": target_minute or existing_recur.get("target_minute", 0), "target_second": target_second or existing_recur.get("target_second", 0),
                "target_weekday": target_weekday or existing_recur.get("target_weekday"), "weekdays_only": weekdays_only or existing_recur.get("weekdays_only", False)
            }

            # Update in place
            updated_job = {
                "id": id,
                "action": action or existing.get("action"),
                "channel": channel or existing.get("channel"),
                "trigger_time": existing.get("trigger_time"),
                "recurring": recurring or existing.get("recurring"),
                "recurs_in": recur if (recurring or existing.get("recurring")) else None
            }

            self.schedule[index] = updated_job
            self.schedule.save()

            # Reschedule (cancels old timer, sets new one)
            self._schedule_job(updated_job)

            return self.result("job edited")

        except Exception as e:
            return self.result(f"error: {e}", False)

    async def remove_job(self, id: str):
        index = self._get_index(id)
        if index == -1:
            return self.result("id does not exist", False)

        # Cancel timer if active
        if id in self.scheduled_handles:
            self.scheduled_handles[id].cancel()
            del self.scheduled_handles[id]

        self.schedule.pop(index)
        self.schedule.save()
        return self.result("job deleted")
