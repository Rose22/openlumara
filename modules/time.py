import core
import datetime

class Time(core.module.Module):
    """Makes the AI aware of the current time and date"""

    async def on_end_prompt(self):
        time = datetime.datetime.now().strftime("%x %X")
        return f"Current time/date is {time}"
