import core
import datetime
import ulid
import asyncio

class Calendar(core.module.Module):
    """Lets your AI manage a calendar for you"""

    # TODO: add caldav support, iCal support, etc. maybe also google cal

    settings = {
        "insert_system_prompt": {
            "description": "Whether to add the calendar events within your configured range (defined below) to the system prompt. This will make your AI aware of your upcoming appointments at all times!",
            "default": True
        },
        "range": {
            "description": "The range of days relative to today that you want the AI to see the events of",
            "default": 7,
            "depends": "insert_system_prompt"
        },
        "include_past_events": {
            "description": "Whether or not to make the AI aware of calendar events that have already passed. Many local AI's don't handle this very well, so it's recommended to leave this off, or they will start to remind you of appointments that have already happened. It's still included for posterity, in case you're using a model that handles this better.",
            "default": False,
            "depends": "insert_system_prompt"
        },
        "notifications": {
            "description": "Whether to receive notifications about upcoming events",
            "default": True
        },
        "notification_channel": {
            "type": "select",
            "default": "webui",
            "description": "Which channel to send calendar notifications to",
            "options": {name: f"Send notifications via {name}" for name in core.channel.get_available_channels()},
            "depends": "notifications"
        },
        "notification_window": {
            "description": "Amount of minutes in advance you should be notified. You can set this to 0 to be notified at the time of the event.",
            "default": 30,
            "depends": "notifications"
        }
    }

    async def on_ready(self):
        self.events = core.storage.StorageList("calendar", "json")

        # schedule all event notifications
        for event in self.events:
            if event.get("notify"):
                asyncio.create_task(self._schedule_notification(event))

    async def _schedule_notification(self, event: dict):
        """schedules a notification for an event."""
        event_time = datetime.datetime.fromisoformat(event["date"])
        now = datetime.datetime.now()

        window_minutes = int(event.get("notification_window", self.config.get("notification_window")))
        window_seconds = window_minutes * 60

        delay = (event_time - now).total_seconds() - window_seconds

        if delay <= 0:
            # If the event occurred in the past (beyond window), mark it without spamming
            if (now - event_time).total_seconds() > window_seconds:
                index = await self._get_event_by_id(event['id'])
                if index != -1:
                    self.events[index]["notify"] = False
                    self.events.save()
                return

            # If the event is happening right now, trigger immediately
            await self._notify_user(event)
            return

        try:
            loop = asyncio.get_running_loop()
            # We use a lambda to wrap the async function in a task
            # because call_later requires a sync callable.
            loop.call_later(
                delay,
                lambda: asyncio.create_task(self._notify_user(event))
            )
        except Exception as e:
            self.log("calendar", f"failed to schedule notification: {core.detail_error(e)}")

    async def _notify_user(self, event: dict):
        if not event.get("notify"):
            return False

        channel_name = event.get("notify_channel")
        if not channel_name:
            channel_name = self.config.get("notification_channel")

        channel = self.manager.channels.get(channel_name) or self.channel

        if channel:
            event_time = datetime.datetime.fromisoformat(event["date"])
            now = datetime.datetime.now()
            diff_seconds = (event_time - now).total_seconds()
            minutes_left = int(diff_seconds / 60)

            if minutes_left <= 0:
                notify_window_str = "now!"
            elif minutes_left == 1:
                notify_window_str = "in 1 minute"
            else:
                notify_window_str = f"in {minutes_left} minutes"

            message = f"🔔 **Calendar**: {event['title']} is starting {notify_window_str}"
            await channel.push(message)
            # add to context so the AI knows it just notified the user
            await channel.context.chat.messages.add({"role": "assistant", "content": message})

        # disable notification
        index = await self._get_event_by_id(event['id'])
        if index != -1:
            self.events[index]["notify"] = False
            self.events.save()

    async def _get_events_in_range(self):
        # display appointments between certain range
        matches = []

        date_range = int(self.config.get("range", default=7))
        include_past = self.config.get("include_past_events")

        today = datetime.datetime.today()

        # future is always today + the configured range
        future_boundary = today + datetime.timedelta(days=date_range)

        # past boundary depends on the setting. if we want to include past events, it's the configured amount of days into the past
        if include_past:
            past_boundary = today - datetime.timedelta(days=date_range)
        else:
            past_boundary = today

        for event in self.events:
            event_date = datetime.datetime.fromisoformat(event["date"])
            if past_boundary <= event_date <= future_boundary:
                matches.append(event)

        return matches

    async def _get_event_by_id(self, id: str):
        for index, event in enumerate(self.events):
            if event['id'].strip() == id.strip():
                return index

        return -1

    async def on_system_prompt(self):
        matches = await self._get_events_in_range()
        output = []

        for event in matches:
            output.append(f"{event.get('id')}: on {event['date']}: {event['title']}")

        if not output:
            return None

        return "\n".join(output)

    async def add_event(self, title: str, year: int, month: int, day: int, hour: int, minute: int, should_notify: bool = True, notify_channel: str = None):
        event = {
            "id": str(ulid.ULID()),
            "title": title,
            "date": datetime.datetime.isoformat(
                datetime.datetime(
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute
                )
            ),
            "notify": should_notify,
            "notify_channel": notify_channel or self.config.get("notification_channel")
        }

        self.events.append(event)
        self.events.save()

        if should_notify:
            await self._schedule_notification(event)

        return self.result(f"appointment added with ID {event['id']}")

    async def edit_event(self, id: str, title: str = None, year: int = None, month: int = None, day: int = None, hour: int = None, minute: int = None, should_notify: bool = True, notify_channel: str = None):
        index = await self._get_event_by_id(id)
        if index < 0:
            return self.result("Error: Event with that ID does not exist", success=False)

        event = self.events[index]
        event_date = datetime.datetime.fromisoformat(event['date'])
        new_date_iso = datetime.datetime.isoformat(
            datetime.datetime(
                year=year or event_date.year,
                month=month or event_date.month,
                day=day or event_date.day,
                hour=hour or event_date.hour,
                minute=minute or event_date.minute
            )
        )

        self.events[index]["title"] = title or event['title']
        self.events[index]["date"] = new_date_iso
        self.events[index]["notify"] = should_notify or event['notify']
        self.events[index]["notify_channel"] = notify_channel or event['notify_channel']
        self.events.save()

        if should_notify:
            await self._schedule_notification(event)

        return self.result(f"event {event['id']} edited")

    async def delete_event(self, id: str):
        index = await self._get_event_by_id(id)
        if index < 0:
            return self.result("Error: Event with that ID does not exist", success=False)

        self.events.pop(index)
        return self.result(f"event {id} deleted")

    @core.module.command("calendar", send_to_ai=False)
    async def cmd_calendar(self, args: list):
        """Look up calendar events in a date range. Without dates, uses configured range."""
        today = datetime.datetime.today()

        # No args = configured range
        if not args:
            date_range = int(self.config.get("range", default=7))
            include_past = self.config.get("include_past_events")
            if include_past:
                past_boundary = today - datetime.timedelta(days=date_range)
            else:
                past_boundary = today
            future_boundary = today + datetime.timedelta(days=date_range)
        else:
            # Custom range
            try:
                past_boundary = datetime.datetime.fromisoformat(args[0])
                future_boundary = datetime.datetime.fromisoformat(args[1]) if len(args) > 1 else past_boundary + datetime.timedelta(days=1)
            except ValueError:
                return "Error: Invalid date format. Use ISO format (e.g., 2024-01-15)."

        matches = []
        for event in self.events:
            try:
                event_date = datetime.datetime.fromisoformat(event["date"])
                if past_boundary <= event_date <= future_boundary:
                    matches.append(event)
            except (ValueError, KeyError):
                continue

        if not matches:
            return "No events found in this range."

        output = []
        for event in matches:
            date_str = datetime.datetime.fromisoformat(event['date']).strftime("%x at %X")
            output.append(f"{date_str}: {event['title']}")

        return "\n".join(output)

    async def read_calendar_range(self, start_date: str, end_date: str):
        """Read calendar events within a date range. Both dates are required."""
        today = datetime.datetime.today()

        try:
            past_boundary = datetime.datetime.fromisoformat(start_date)
            future_boundary = datetime.datetime.fromisoformat(end_date)
        except ValueError:
            return self.result("Error: Invalid date format. Use ISO format (e.g., 2024-01-15).", success=False)

        matches = []
        for event in self.events:
            try:
                event_date = datetime.datetime.fromisoformat(event["date"])
                if past_boundary <= event_date <= future_boundary:
                    matches.append(event)
            except (ValueError, KeyError):
                continue

        if not matches:
            return self.result("No events found in this range.", success=False)

        output = []
        for event in matches:
            output.append(f"{event.get('id')}: on {event['date']}: {event['title']}")

        return self.result("\n".join(output))
