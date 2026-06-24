import core
import asyncio

class CliLite(core.channel.Channel):
    """Lightweight version of the CLI channel that uses basic python input and doesn't use streaming"""

    settings =  {
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages.",
            "default": False
        }
    }

    ready = False

    async def on_ready(self):
        self.ready = True

    async def run(self):
        # make sure asking for input only starts happening once openlumara has fully started
        while not self.ready:
            await asyncio.sleep(1)

        while True:
            user_input = await asyncio.to_thread(input, "> ")
            print("sending..", end="", flush=True)

            # send request to AI
            response = await self.send({"role": "user", "content": user_input}, commands_authorized=True)

            # remove send indicator and replace with response
            print("\r", end="", flush=True)
            print(response.get("content"), flush=True)

    def on_log(self, category, message):
        print(f"[{category.upper()}] {message}")

    async def on_request_stalled(self):
        print("...please wait for other requests to finish...", flush=True)

    async def on_push(self, message):
        print("\n"+message.get("content"), flush=True)
