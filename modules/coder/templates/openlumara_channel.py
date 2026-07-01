# ALWAYS import core at the start. very important.
import core

# ALWAYS ensure the class name maps perfectly to the filename.
# the class name is in CamelCase, the filename is the snake_case equivalent of it.
# e.g. ExampleChannel -> example_channel.py
#
# This is ESSENTIAL for the channel to be detected and loaded.
class MyChannel(core.channel.Channel):
    """
    A sample channel demonstrating core features.
    This channel docstring shows up as the channel description all over the framework!
    """

    # -------------------------
    #   CONFIGURATION
    # -------------------------

    # settings defined here will show up in all channels that support it (such as the webUI)
    # for the user to change as they see fit
    # valid types: string, long_text, boolean, number, percentage, select
    settings = {
        # show_reasoning is a special setting that gets used by the channel's format_stream_for_text method to automatically collapse reasoning blocks into a simple "thinking.." indicator
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        },

        # stream_tool_calls is a special setting that also gets used by the channel's format_stream_for_text method to automatically format toolcall streams so that they get formatted in a user-friendly way
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": False
        },

        "example_select": {
            "type": "select",
            "description": "This is an example setting of type `select`. It allows the user to choose from a list of options.",
            "default": "local",
            "options": {
                "local": "127.0.0.1",
                "internet": "0.0.0.0"
            }
        },
        "notification_channel": {
            "type": "select",
            # use core.channel.get_available_channels() to get a list of channels that can be targeted
            "options": {name: f"Send notifications via {name}" for name in core.channel.get_available_channels()}
        },
        "example_list": {
            "type": "list",
            "description": "This is an example setting of type `list`. Will let the user add/remove multiple entries. It's basically an array (a python `list`).",
            "default": []
        },
    }

    # list of dependencies that the module needs in order to work.
    # this is an example, leave empty if no dependencies are needed
    dependencies = ["pytest"]

    # -------------------------
    #   EVENT HANDLERS
    # -------------------------

    # any function starting with `on_` is an event handler and is called by the framework at various points.

    async def on_ready(self):
        """ALWAYS use this instead of the class constructor (__init__) as it runs at the right time during the framework's startup sequence.
        Initialize instance variables here."""

        # use self.config.get() to access a setting's value
        example_setting = self.config.get("example_setting")

        # we can use self.push() to send messages to the user instantly, without the AI having to process anything
        # self.push() can be used in any of the event handlers, this is just for demonstration purposes
        await self.push(f"{self.name} is up and running! example setting set to: {example_setting}")

        # you can also push to another channel by its name:
        target_channel = self.manager.channels.get(
            self.config.get("notification_channel")
        )
        await target_channel.push("piiing!")

        # self.push() is processed by self.on_push, seen later down below in this template

        pass

    async def run(self):
        """This is the main loop"""
        # The flow goes like this:
        # Ask user for input -> send user input to AI -> return result either as an openAI message dict, or as an async generator that can be looped through to stream the tokens

        # Example non-streaming flow:
        while True:
            user_input = input("ask your AI> ")

            # send the request to the AI. supports simple text content and multimodal
            # returns an openAI message dictionary of format {"role": role, "content": content} (or the multimodal equivalent as per openai spec)

            # commands_authorized determines whether the user is able to use /commands to control openlumara on a system level. you can use this, for example, with a UID check on a public bot, to reject commands if the user sending the command isn't the bot admin.
            response_dict = await self.send({"role": "user", "content": user_input}, commands_authorized=True)

            # optionally, run the response dict through format_message to make the output much nicer (formats reasoning headers, toolcalls etc)
            response_dict = self.format_message(response_dict)

            # get the content field from the response dict
            response_content = response_dict.get("content")

            # then print the ai's response to the user
            print(response_content, flush=True)

        # Example streaming flow:
        while True:
            user_input = input("ask your AI> ")

            # send the stream request to the AI. supports simple text content and multimodal
            # returns an async generator that can be looped through, the content being yielded is raw token dicts
            try:
                stream_object = await self.send_stream({"role": "user", "content": user_input}, commands_authorized=True)
            except Exception as e:
                # use self.log to trigger a cross-channel log message.
                # it will be sent to all channels!
                # each channel will display it using its own on_log() method.
                # first param is category, second param is the message
                self.log(self.name, f"error while sending stream: {core.detail_error(e)}")

                # core.detail_error() is a special framework function that displays more details about an error when the user runs the framework with `--debug` enabled

            # the token dicts are of format: {"type": type, "content": content}
            # valid token types: prompt_progress (llamacpp-exclusive, has details about current prompt processing progress), reasoning, content, tool_call_delta (streaming toolcall parts), tool_calls (finished toolcalls), tool (tool response), token_usage, timings

            # you can loop through this and process it manually, like this:
            async for token in stream_object:
                token_type = token.get("type")
                token_content = token.get("content")

                # now you can manually process each token type here
                # the framework automatically handles recursive toolcalls (the "agentic loop") so you don't need to manually parse that
                # just process each token and display as needed

                # this is a very simple example, without proper separation of reasoning, content and toolcalls, just for demonstration purposes. when making your own channel, make sure to actually put in the effort to process token types correctly
                if token_type in ("reasoning", "content"):
                    print(token_content, end="", flush=True)

            # OR, you can use the handy built in formatter:
            format_strings = {
                "thinking_header": "--- Thinking ---",
                "thinking_str": "thinking..",
                "conclusion_header": "--- Conclusion ---",
                "processing_tool": "\n(processing results..)",
                "thinking_newline": "\n"
            }
            async for token in self.format_stream_for_text(stream_object, strings=format_strings):
                # this takes care of all the formatting, all you need to do is output it to your chosen display method. in this case we're using print
                print(token.get('content'), end="", flush=True)

    async def on_push(self, message: dict):
        """Triggers whenever a push message gets sent by anything in the framework"""

        # This is the special magic that makes openlumara able to send messages to the user without the AI first needing to be prompted.
        # It can send a message to the user, at any point in time, using pure code
        # Display it in whatever way you want. In this case we're using a simple print statement for the example
        message_content = message.get("content")
        if not message_content:
            return False

        print(f"[PUSH] {message_content}", flush=True)

    # IMPORTANT: on_log is not async
    def on_log(self, category: stry, message: str):
        """Triggers whenever a log message is sent by the framework. These are system logs, console messages that are meant to convey technical or debug information. Show them in whichever way you prefer."""
        # Using a simple print statement here as an example. Again, display this in a manner that makes the most sense for your channel.
        print(f"[{self.name}] {category}: {message}")

    async def on_install(self):
        """This runs after the channel's dependencies are installed by the framework's auto-installer. Use it for post-installation hooks"""
        pass

    async def on_uninstall(self):
        """This runs after the channel's dependencies are uninstalled by the framework's auto-installer. Use it for post-uninstallation hooks."""
        pass

# Final notes to the AI:
# - The user must copy the created user channel to the openlumara user channels folder (defaults to user_channels, but the path can be manually set by the user)
# - The user must restart openlumara, which will make openlumara detect the new user channel. Then, the user must enable the channel within the config using either the webUI's settings panel, using `/channel module_name_in_snake_case`, or manually editing their config file.
# - The channel will then be activated and ready for use.
# - Any syntax errors from the channel will show up in the console logs. If there is not enough information, the user can use the `--debug` flag when starting openlumara, to see more detail about errors.
