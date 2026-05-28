import datetime
import asyncio
import core
import ulid
import re


class Scheduler(core.module.Module):
    """Lets your AI perform actions on your behalf at specified times! Supports recurring actions."""

    settings = {
        "insert_system_prompt": {
            "description": "Whether to insert a list of all currently scheduled jobs in the system prompt. This will make your AI aware of upcoming scheduled jobs at all times!",
            "default": True
        },
        "prompt_strategy": {
            "type": "select",
            "default": "minimize tokens",
            "options": {
                "minimize tokens": "Token-efficient, sends only the scheduled instruction. Drastically reduces token use and cost, but may induce prompt reprocessing due to context switching.",
                "send full context": "Sends the entire context window + the scheduled instruction. This makes many API's use the prompt cache to prevent reprocessing, but it will also send your entire history along with the scheduled instructions, which is a lot of tokens."
            }
        },
        "allow_recurring_jobs": True
    }

    async def on_ready(self, *args, **kwargs):
        """Initialize storage, start dispatcher, and schedule existing jobs."""
        self.schedule = core.storage.StorageList("schedule", type="json")

        # Event used to signal the dispatcher that the schedule has changed
        self._reschedule_event = asyncio.Event()

        # The single dispatcher task
        self._dispatcher_task = asyncio.create_task(self._dispatcher_loop())

    async def on_unload(self, *args, **kwargs):
        """Clean up the dispatcher task on module unload."""
        if hasattr(self, '_dispatcher_task') and self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass

    # ---------------------------------------------------------
    # Dispatcher (Single Task Architecture)
    # ---------------------------------------------------------

    async def _dispatcher_loop(self):
        """Single loop that sleeps until the next job is due, then executes it."""
        while True:
            try:
                next_job, delay = self._get_next_due_job()

                if next_job is None:
                    # No jobs scheduled; wait for a signal that the schedule changed
                    self._reschedule_event.clear()
                    await self._reschedule_event.wait()
                    self._reschedule_event.clear()
                    continue

                if delay <= 0:
                    # Job is overdue — handle it
                    job_id = next_job.get("id")
                    idx = self._get_index(job_id)
                    if idx == -1:
                        continue

                    job = self.schedule[idx]

                    if job.get("recurring"):
                        # Advance recurring job to future without executing missed instances
                        self._advance_recurring_to_future(job)
                        core.log("scheduler", f"advanced missed recurring job {job_id} to next future time")
                    else:
                        # Overdue one-time job: execute immediately
                        await self._job_wrapper(job)
                    continue

                # Wait until the job is due or until the schedule changes
                self._reschedule_event.clear()
                try:
                    await asyncio.wait_for(
                        self._reschedule_event.wait(),
                        timeout=delay
                    )
                    # Event was set — schedule changed, restart loop
                    self._reschedule_event.clear()
                    continue
                except asyncio.TimeoutError:
                    # Timer expired — time to execute the job
                    pass

                # Re-fetch job from storage (might have been edited/removed)
                job_id = next_job.get("id")
                idx = self._get_index(job_id)
                if idx == -1:
                    continue

                job = self.schedule[idx]
                await self._job_wrapper(job)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                core.log_error("[SCHEDULER] error in dispatcher loop", e)
                # Brief sleep to avoid tight error loops
                await asyncio.sleep(5)

    def _get_next_due_job(self):
        """
        Returns (job_dict, delay_seconds) for the job with the earliest trigger_time.
        Returns (None, None) if no jobs are scheduled.
        """
        now = datetime.datetime.now()
        earliest_job = None
        earliest_delay = None

        for job in self.schedule:
            try:
                trigger_time = datetime.datetime.fromisoformat(job.get("trigger_time", ""))
            except (ValueError, TypeError):
                continue

            delay = (trigger_time - now).total_seconds()

            if earliest_delay is None or delay < earliest_delay:
                earliest_delay = delay
                earliest_job = job

        return earliest_job, earliest_delay

    def _signal_reschedule(self):
        """Signal the dispatcher to re-evaluate the schedule."""
        self._reschedule_event.set()

    # ---------------------------------------------------------
    # Job Execution
    # ---------------------------------------------------------

    async def _job_wrapper(self, job: dict) -> None:
        """Executes the job and handles cleanup or recurrence."""
        job_id = job.get("id")
        if not job_id:
            return

        try:
            await self._execute_job(job)

            # Check if the job still exists in storage (might have been removed during execution)
            idx = self._get_index(job_id)
            if idx == -1:
                return

            if job.get("recurring"):
                # Refresh job data from storage to catch any edits made during execution
                idx = self._get_index(job_id)
                if idx >= 0:
                    current_job = self.schedule[idx]
                    self._reschedule_recurring_job(current_job)
            else:
                # One-time job: remove from storage
                self._remove_job_from_storage(job_id)

        except Exception as e:
            core.log_error(f"[SCHEDULER] error executing job {job_id}", e)

    def _reschedule_recurring_job(self, job: dict) -> None:
        """Updates a recurring job's trigger_time to the next future occurrence."""
        recur = job.get("recurs_in", {})

        # Calculate next time based on the current trigger_time (not now)
        # This preserves cadence
        try:
            current_trigger = datetime.datetime.fromisoformat(job.get("trigger_time", ""))
        except (ValueError, TypeError):
            current_trigger = datetime.datetime.now()

        next_time = self._calculate_next_from(current_trigger, recur)

        if next_time is None:
            core.log("scheduler", f"could not reschedule recurring job {job.get('id')}: invalid interval")
            return

        # If next_time is still in the past, advance until it's in the future
        now = datetime.datetime.now()
        max_iterations = 10000
        iteration = 0
        while next_time <= now and iteration < max_iterations:
            next_time = self._calculate_next_from(next_time, recur)
            if next_time is None:
                core.log("scheduler", f"could not reschedule recurring job {job.get('id')}: invalid interval")
                return
            iteration += 1

        if next_time <= now:
            core.log("scheduler", f"could not advance job {job.get('id')} to future after {max_iterations} iterations")
            return

        # Update the trigger time in storage
        idx = self._get_index(job.get("id"))
        if idx >= 0:
            self.schedule[idx]["trigger_time"] = next_time.isoformat()
            self.schedule.save()

        # Signal dispatcher to pick up the new time
        self._signal_reschedule()

    def _advance_recurring_to_future(self, job: dict) -> None:
        """Advance a recurring job's trigger_time until it's in the future (without executing)."""
        recur = job.get("recurs_in", {})

        try:
            current_trigger = datetime.datetime.fromisoformat(job.get("trigger_time", ""))
        except (ValueError, TypeError):
            current_trigger = datetime.datetime.now()

        now = datetime.datetime.now()
        next_time = current_trigger
        max_iterations = 10000
        iteration = 0

        while next_time <= now and iteration < max_iterations:
            candidate = self._calculate_next_from(next_time, recur)
            if candidate is None:
                core.log("scheduler", f"could not advance job {job.get('id')}: invalid interval")
                return
            next_time = candidate
            iteration += 1

        if next_time <= now:
            core.log("scheduler", f"could not advance job {job.get('id')} to future after {max_iterations} iterations")
            return

        # Update in storage
        idx = self._get_index(job.get("id"))
        if idx >= 0:
            self.schedule[idx]["trigger_time"] = next_time.isoformat()
            self.schedule.save()

        # Signal dispatcher
        self._signal_reschedule()

    def _remove_job_from_storage(self, job_id: str) -> None:
        """Removes a job from storage list."""
        idx = self._get_index(job_id)
        if idx >= 0:
            self.schedule.pop(idx)
            self.schedule.save()
        self._signal_reschedule()

    # ---------------------------------------------------------
    # Execution
    # ---------------------------------------------------------

    async def _execute_job(self, job: dict) -> None:
        """Performs the actual action of the job using a private context copy."""
        job_id = job.get("id")

        # Determine the target channel for this job
        channel_name = (job.get("channel") or "").lower().strip()
        job_channel = self.manager.channels.get(channel_name)
        if job_channel is None and self.channel:
            job_channel = self.channel

        if job_channel is None:
            core.log("scheduler", f"error executing job {job_id}: no channel available")
            return

        if not hasattr(job_channel, 'context') or job_channel.context is None:
            core.log("scheduler", f"error executing job {job_id}: channel has no valid context")
            return

        # Filter out scheduler tools to prevent circular scheduling
        tools = [
            t for t in self.manager.tools
            if not t.get("function", {}).get("name", "").startswith("scheduler_")
        ]

        use_token_efficient = True
        if self.config.get("prompt_strategy") == "send full context":
            use_token_efficient = False

        instr_role = "system"
        if not use_token_efficient:
            instr_role = "developer" if job_channel.manager.API.supports_developer_role else "user"

        action = job.get("action")

        instruction_message = {
            "role": instr_role,
            "content": (
                "[AUTOMATED SYSTEM INSTRUCTION]\n"
                "Please follow these instructions:\n\n"
                f"{action}\n"
                "Use tools if needed. For simple reminders, do not use tools."
            )
        }

        instruction_message_pure = {
            "role": "system",
            "content": action
        }

        # Retry loop with exponential backoff
        max_retries = 10
        base_delay = 5  # seconds
        max_delay = 300  # 5 minutes cap
        response = None

        while True:
            try:
                # Build a fresh private copy each attempt (context may have changed)
                base_messages = await job_channel.context.get(end_prompt=False)
                private_messages = list(base_messages) + [instruction_message]

                # allow a choice between sending full context or sending only the instruction
                final_messages = [instruction_message_pure] if use_token_efficient else private_messages

                response = await self.manager.API.send(
                    final_messages,
                    use_tools=True,
                    tools=tools
                )

                if response:
                    break  # Success

                # response is None/empty — treat as transient failure
                core.log("scheduler", f"job {job_id}: empty response on attempt {attempt + 1}/{max_retries}")

            except Exception as e:
                core.log("scheduler", f"job {job_id}: attempt {attempt + 1}/{max_retries} failed: {e}")

            # Don't sleep after the last attempt
            if attempt < max_retries - 1:
                delay = min(base_delay * (2 ** attempt), max_delay)
                core.log("scheduler", f"job {job_id}: retrying in {delay}s")
                await asyncio.sleep(delay)

        # Process response
        final_content = response.get("content", "")
        tool_calls = response.get("tool_calls")

        if tool_calls and job_channel:
            tool_content_list = []
            async for token in job_channel.tc_manager.process(response, push=True):
                if token.get("type") == "content":
                    tool_content_list.append(token.get("content", ""))
            tool_content = "".join(tool_content_list)
            if tool_content:
                final_content = f"{final_content}\n{tool_content}".strip()
        elif tool_calls:
            core.log("scheduler", f"error executing job {job_id}: tool calls found but no valid channel")
            return

        if final_content and job_channel:
            try:
                await job_channel.push(final_content)
                await job_channel.context.chat.add({"role": "assistant", "content": final_content})
            except Exception as e:
                core.log_error(f"[SCHEDULER] error announcing job {job_id} result", e)

    # ---------------------------------------------------------
    # Time Calculations
    # ---------------------------------------------------------

    def _calculate_next_trigger(self, recur: dict) -> datetime.datetime:
        """Calculates the next trigger datetime from now based on recurrence dict."""
        return self._calculate_next_from(datetime.datetime.now(), recur)

    def _calculate_next_from(self, base: datetime.datetime, recur: dict) -> datetime.datetime:
        """
        Calculate the next trigger time strictly after `base`.
        Supports two modes:
          1. Specific clock time (target_hour set)
          2. Relative delta (weeks/days/hours/minutes/seconds)
        """
        if recur is None:
            return None

        # MODE 1: Specific Clock Time
        if recur.get("target_hour") is not None:
            target_hour = recur["target_hour"]
            target_minute = recur.get("target_minute", 0)
            target_second = recur.get("target_second", 0)

            candidate = base.replace(
                hour=target_hour,
                minute=target_minute,
                second=target_second,
                microsecond=0
            )

            if recur.get("target_weekday") is not None:
                target_weekday = recur["target_weekday"]
                days_until = (target_weekday - candidate.weekday()) % 7
                if days_until == 0 and candidate <= base:
                    days_until = 7
                candidate += datetime.timedelta(days=days_until)

            elif recur.get("weekdays_only"):
                if candidate <= base:
                    candidate += datetime.timedelta(days=1)
                while candidate.weekday() >= 5:
                    candidate += datetime.timedelta(days=1)

            else:
                interval_days = recur.get("days", 0) or 1
                if candidate <= base:
                    candidate += datetime.timedelta(days=interval_days)

            return candidate

        # MODE 2: Relative Delta
        delta = datetime.timedelta(
            weeks=recur.get("weeks", 0),
            days=recur.get("days", 0),
            hours=recur.get("hours", 0),
            minutes=recur.get("minutes", 0),
            seconds=recur.get("seconds", 0)
        )

        if delta.total_seconds() == 0:
            return None

        return base + delta

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def _get_index(self, job_id: str) -> int:
        """Finds the index of a job by ID. Returns -1 if not found."""
        if job_id is None:
            return -1
        for index, job in enumerate(self.schedule):
            if str(job.get("id", "")) == str(job_id):
                return index
        return -1

    def __str__(self) -> str:
        """Displays schedule as a human-readable list."""
        result = []
        for job in self.schedule:
            job_id = job.get("id", "unknown")
            action = job.get("action", "")
            chan_str = job.get("channel", "unknown channel")
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
            if hour == 0:
                h = 12
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
        try:
            trigger_dt = datetime.datetime.fromisoformat(job.get("trigger_time", ""))
            delta = trigger_dt - datetime.datetime.now()
            total_seconds = int(delta.total_seconds())

            if total_seconds < 0:
                return "one-time, overdue"

            h, rem = divmod(total_seconds, 3600)
            m, s = divmod(rem, 60)

            parts = []
            if h > 0:
                parts.append(f"{h} hour{'s' if h != 1 else ''}")
            if m > 0:
                parts.append(f"{m} minute{'s' if m != 1 else ''}")
            if s > 0 or not parts:
                parts.append(f"{s} second{'s' if s != 1 else ''}")

            return f"one-time, {', '.join(parts)} from now"
        except (ValueError, TypeError):
            return "one-time, invalid time"

    def _weekday_name(self, weekday: int) -> str:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return days[weekday] if 0 <= weekday < 7 else "Unknown"

    async def on_system_prompt(self) -> str:
        if not self.config.get("insert_system_prompt", True):
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
        """Adds a scheduled job. MODE 1 - RELATIVE TIME: Use relative_duration (e.g., '2d 4h 30m'). MODE 2 - SPECIFIC CLOCK TIME: Use target_time (e.g., '14:30'). Optionally set target_weekday (0=Monday) or weekdays_only=True. Action is what action should be performed at the scheduled time. Action is an instruction/prompt for the AI to follow, so write it in second person form. Use the word 'user' to refer to the user."""
        if recurring and not self.config.get("allow_recurring_jobs"):
            return self.result(
                "Error: Recurring scheduler jobs are disabled by security policy. Please inform the user.",
                success=False
            )

        weeks = days = hours = minutes = seconds = 0
        target_hour = target_minute = target_second = None

        # Parse relative_duration (e.g., "2d 4h")
        if relative_duration:
            pattern = r'(\d+)\s*([wdhms])'
            matches = re.findall(pattern, relative_duration)
            for val, unit in matches:
                val = int(val)
                if unit == 'w':
                    weeks = val
                elif unit == 'd':
                    days = val
                elif unit == 'h':
                    hours = val
                elif unit == 'm':
                    minutes = val
                elif unit == 's':
                    seconds = val

        # Parse target_time (e.g., "14:30:00")
        if target_time:
            parts = target_time.split(':')
            if len(parts) >= 2:
                try:
                    target_hour = int(parts[0])
                    target_minute = int(parts[1])
                    if len(parts) == 3:
                        target_second = int(parts[2])

                    if not (0 <= target_hour <= 23):
                        return self.result("error: hour must be between 0 and 23", False)
                    if not (0 <= target_minute <= 59):
                        return self.result("error: minute must be between 0 and 59", False)
                    if target_second is not None and not (0 <= target_second <= 59):
                        return self.result("error: second must be between 0 and 59", False)
                except ValueError:
                    return self.result("error: invalid time format, use HH:MM or HH:MM:SS", False)
            else:
                return self.result("error: invalid time format, use HH:MM or HH:MM:SS", False)

        # Validate target_weekday
        if target_weekday is not None and not (0 <= target_weekday <= 6):
            return self.result("error: target_weekday must be between 0 (Monday) and 6 (Sunday)", False)

        try:
            # Build recurrence dict
            recur = {
                "weeks": weeks,
                "days": days,
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "target_weekday": target_weekday,
                "weekdays_only": weekdays_only
            }
            if target_hour is not None:
                recur["target_hour"] = target_hour
                recur["target_minute"] = target_minute or 0
                if target_second is not None:
                    recur["target_second"] = target_second

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

            # Signal dispatcher to pick up the new job
            self._signal_reschedule()

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
        weekdays_only: bool = None,
        recurring: bool = None,
    ):
        """Edits an existing scheduled job. Only provided parameters will be changed. Use None/omit parameters to keep existing values."""
        index = self._get_index(id)
        if index == -1:
            return self.result("id does not exist", False)

        existing = self.schedule[index]
        existing_recur = existing.get("recurs_in") or {}

        # Resolve recurring flag
        final_recurring = recurring if recurring is not None else existing.get("recurring", False)

        if final_recurring and not self.config.get("allow_recurring_jobs"):
            return self.result(
                "Error: Recurring scheduler jobs are disabled by security policy. Please inform the user.",
                success=False
            )

        try:
            weeks = days = hours = minutes = seconds = None
            target_hour = target_minute = target_second = None

            # Parse relative_duration if provided
            if relative_duration is not None:
                pattern = r'(\d+)\s*([wdhms])'
                matches = re.findall(pattern, relative_duration)
                weeks = days = hours = minutes = seconds = 0
                for val, unit in matches:
                    val = int(val)
                    if unit == 'w':
                        weeks = val
                    elif unit == 'd':
                        days = val
                    elif unit == 'h':
                        hours = val
                    elif unit == 'm':
                        minutes = val
                    elif unit == 's':
                        seconds = val

            # Parse target_time if provided
            if target_time is not None:
                parts = target_time.split(':')
                if len(parts) >= 2:
                    try:
                        target_hour = int(parts[0])
                        target_minute = int(parts[1])
                        if len(parts) == 3:
                            target_second = int(parts[2])

                        if not (0 <= target_hour <= 23):
                            return self.result("error: hour must be between 0 and 23", False)
                        if not (0 <= target_minute <= 59):
                            return self.result("error: minute must be between 0 and 59", False)
                        if target_second is not None and not (0 <= target_second <= 59):
                            return self.result("error: second must be between 0 and 59", False)
                    except ValueError:
                        return self.result("error: invalid time format, use HH:MM or HH:MM:SS", False)
                else:
                    return self.result("error: invalid time format, use HH:MM or HH:MM:SS", False)

            # Validate target_weekday if provided
            if target_weekday is not None and not (0 <= target_weekday <= 6):
                return self.result("error: target_weekday must be between 0 (Monday) and 6 (Sunday)", False)

            # Build recurrence dict using provided values or existing ones
            final_weekdays_only = weekdays_only if weekdays_only is not None else existing_recur.get("weekdays_only", False)

            recur = {
                "weeks": weeks if weeks is not None else existing_recur.get("weeks", 0),
                "days": days if days is not None else existing_recur.get("days", 0),
                "hours": hours if hours is not None else existing_recur.get("hours", 0),
                "minutes": minutes if minutes is not None else existing_recur.get("minutes", 0),
                "seconds": seconds if seconds is not None else existing_recur.get("seconds", 0),
                "target_weekday": target_weekday if target_weekday is not None else existing_recur.get("target_weekday"),
                "weekdays_only": final_weekdays_only
            }

            # Handle time fields
            if target_hour is not None:
                recur["target_hour"] = target_hour
                recur["target_minute"] = target_minute or 0
                if target_second is not None:
                    recur["target_second"] = target_second
            elif "target_hour" in existing_recur:
                recur["target_hour"] = existing_recur["target_hour"]
                recur["target_minute"] = existing_recur.get("target_minute", 0)
                if "target_second" in existing_recur:
                    recur["target_second"] = existing_recur["target_second"]

            # Determine if we need to recalculate trigger_time
            time_params_changed = (
                relative_duration is not None or
                target_time is not None or
                target_weekday is not None or
                weekdays_only is not None
            )

            if time_params_changed:
                new_trigger_time = self._calculate_next_trigger(recur)
                if new_trigger_time is None:
                    return self.result("error: invalid schedule parameters (zero interval)", False)
                trigger_time_str = new_trigger_time.isoformat()
            else:
                trigger_time_str = existing.get("trigger_time")

            # Build updated job
            updated_job = {
                "id": id,
                "action": action if action is not None else existing.get("action"),
                "channel": channel if channel is not None else existing.get("channel"),
                "trigger_time": trigger_time_str,
                "recurring": final_recurring,
                "recurs_in": recur if final_recurring else None
            }

            self.schedule[index] = updated_job
            self.schedule.save()

            # Signal dispatcher to pick up changes
            self._signal_reschedule()

            return self.result("job edited")

        except Exception as e:
            return self.result(f"error: {e}", False)

    async def remove_job(self, id: str):
        """Removes a scheduled job by ID."""
        index = self._get_index(id)
        if index == -1:
            return self.result("id does not exist", False)

        self.schedule.pop(index)
        self.schedule.save()

        # Signal dispatcher to re-evaluate
        self._signal_reschedule()

        return self.result("job deleted")
