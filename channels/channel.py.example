import core

class ExampleChannel(core.channel.Channel):
    async def run(self):
        """main loop. this gets launched as a background task by the framework when opticlaw boots"""
        while True:
            user_input = input("User> ")
            response = self.send_stream({"role": "user", "content": user_input})
            print(f"AI:\n{response}")

    async def _announce(self, message: str, type: str):
        """handles "announcements", which are basically messages emitted by the framework without having to prompt the AI into it"""
        # handle individual types however you like.
        print(f"[ANNOUNCEMENT {type}] {message}")
