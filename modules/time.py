import core
import datetime
import zoneinfo

# get all available timezones
TIMEZONES = {"local": "Use your device's local timezone"}
TIMEZONES.update({tz: f"Set your timezone to {tz}" for tz in sorted(zoneinfo.available_timezones())})

class Time(core.module.Module):
    """Makes the AI aware of the current time and date"""

    settings = {
        "method": {
            "type": "select",
            "default": "message injection",
            "description": "What method to use to make your AI aware of time",
            "options": {
                "message injection": "Injects timestamps into the messages you send. This will make your AI able to see when any message was sent, and give it a sense of how much time has passed between each message!",
                "end prompt": "Injects the current time/date at the end of message history, which is a more basic way of making your AI aware of time. It will make your AI only know the current time and have no sense of the passage of time"
            }
        },
        "add_timezone": {
            "default": True,
            "description": "Puts your timezone in the timestamps that are sent to the AI. Makes the AI timezone-aware!"
        },
        "timezone": {
            "default": "local",
            "description": "Your timezone",
            "type": "select",
            "options": TIMEZONES
        },
        "date_format": {
            "default": "%c",
            "description": "A string that describes exactly how to display the date/time to your AI. Uses strftime format (https://github.com/Vishxnu/Python-strftime-cheatsheet)"
        }
    }

    def _get_current_time(self):
        """gets the current time/date, with timezone support"""
        tz_setting = self.config.get("timezone")

        if tz_setting == "local":
            now = datetime.datetime.now().astimezone()
        else:
            tz = zoneinfo.ZoneInfo(tz_setting)
            now = datetime.datetime.now(tz=tz)

        return now

    async def on_end_prompt(self):
        if self.config.get("method") != "end prompt":
            return None

        now = self._get_current_time()
        time_info = [now.strftime(self.config.get("date_format"))]

        if self.config.get("add_timezone"):
            time_info.append(str(now.tzname()))

        time_info_str = " ".join(time_info)
        return f"Current time/date is {time_info_str}"

    async def on_message_inject(self):
        if self.config.get("method") != "message injection":
            return None

        now = self._get_current_time()
        time_info = [now.strftime(self.config.get("date_format"))]

        if self.config.get("add_timezone"):
            time_info.append(str(now.tzname()))

        time_info_str = " ".join(time_info)
        return f"sent on {time_info_str}"
