import core
import datetime
import os

class Logger(core.channel.Channel):
    """Logs console logs to a file of your choice"""

    settings = {
        "path": "lumara.log"
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = self.config.get("path")

        self.logfile = None

        try:
            new_logfile = False
            if not os.path.exists(self.path):
                new_logfile = True

            self.logfile = open(self.path, "a", encoding="utf-8")

            # write divider
            if not new_logfile:
                self.logfile.write("-"*40)
                self.logfile.write("\n")
                self.logfile.flush()

            self.log("logger", f"started logging to file {self.path}")
        except Exception as e:
            print(f"Error while opening log file: {core.detail_error(e)}")

    async def run(self):
        pass

    def on_log(self, category, message):
        if not self.logfile:
            return False

        if self.logfile.closed:
            return False

        timestamp = datetime.datetime.now().strftime("%c")

        self.logfile.write(f"{timestamp} | {category.upper()} | {message}\n")
        self.logfile.flush()

    async def on_shutdown(self):
        self.logfile.close()
