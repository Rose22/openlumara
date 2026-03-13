import core
import asyncio
import prompt_toolkit
import prompt_toolkit.patch_stdout
import sys

class Cli(core.channel.Channel):
    running = True

    async def run(self):
        # only activate the CLI channel if running in a real terminal
        if not sys.stdin.isatty():
            return False

        with prompt_toolkit.patch_stdout.patch_stdout():
            prompt_session = prompt_toolkit.PromptSession()
            while self.running:
                msg = await prompt_session.prompt_async("> ")
                message_state = None
                async for token in self.send_stream({"role": "user", "content": msg}):
                    if token.get("type") == "reasoning" and not message_state:
                        print("Reasoning:")
                        message_state = "reasoning"

                    if token.get("type") == "content" and message_state == "reasoning":
                        print()
                        print("Conclusion:")
                        message_state = "final output"

                    print(token.get("content"), end="", flush=True)
                print()

    async def _announce(self, message: str, type: str = None):
        core.log("cli", message)

    def shutdown(self):
        core.log("cli", "shutting down")
        self.running = False
        return True
