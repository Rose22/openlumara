import core
import json

class Turnstest(core.channel.Channel):
    running = False

    async def clearscreen(self):
        print("\x1b[2J\033[H")
        print("--- OPENLUMARA TURN GROUPING TEST ---")
        print()

    async def run(self):
        self.running = False
        await self.clearscreen()

        while True:
            usr_input = input("> ")
            if not self.running:
                self.running = True

            async for partial in self.group_stream(self.send_stream(usr_input)):
                if partial.get("type") == "turn":
                    await self.clearscreen()
                    #print(partial.get("content"))
                    print(json.dumps(partial.get("content"), indent=2))

    def on_log(self, category, message):
        if not self.running:
            print(f"[{category}] {message}", flush=True)
