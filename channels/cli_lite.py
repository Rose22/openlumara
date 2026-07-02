import core

class CliLite(core.channel.Channel):
    """Lightweight version of the CLI channel that uses basic python input and doesn't use streaming"""

    settings =  {
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        }
    }

    async def run(self):
        while True:
            user_input = input("> ")
            response = await self.send({"role": "user", "content": user_input}, commands_authorized=True)
            print(response.get("content"), flush=True)

    def on_log(self, category, message):
        if core.quiet:
            return

        # allow hiding the category string for special formatting and stuff
        cat_str = f"[{category.upper()}] " if category else ""
        print(f"{cat_str}{message}", flush=True)

    async def on_push(self, message):
        print("\n"+message.get("content"), flush=True)
