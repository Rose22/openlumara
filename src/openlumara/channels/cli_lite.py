import openlumara.core as core

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
            response = await self.send({"role": "user", "content": user_input})
            print(response.get("content"), flush=True)

    async def on_push(self, message):
        print("\n"+message.get("content"), flush=True)
