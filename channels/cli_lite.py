import core
import asyncio

class CliLite(core.channel.Channel):
    """Lightweight version of the CLI channel that uses basic python input and doesn't use streaming"""

    settings = {
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        }
    }

    async def run(self):
        while True:
            # run blocking input in a worker thread so background tasks and event loop don't freeze
            user_input = await asyncio.to_thread(input, "> ")
            if not user_input.strip():
                continue
            response = await self.send(user_input, commands_authorized=True)
            if response and isinstance(response, dict):
                content = response.get("content")
                if content:
                    print(content, flush=True)

    def on_log(self, category, message):
        if core.quiet:
            return

        # allow hiding the category string for special formatting and stuff
        cat_str = f"[{category.upper()}] " if category else ""
        print(f"{cat_str}{message}", flush=True)

    async def on_push(self, message):
        content = message.get("content") if isinstance(message, dict) else str(message)
        if content:
            print("\n" + str(content), flush=True)
