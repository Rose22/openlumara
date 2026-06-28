import core

# ALWAYS ensure the class name maps perfectly to the filename.
# the class name is in CamelCase, the filename is the snake_case equivalent of it.
# e.g. ExampleModule -> example_module.py
#
# This is ESSENTIAL for the module to be detected and loaded.
class ExampleModule(core.module.Module):
    """
    A sample module demonstrating core features.
    This module docstring shows up as the module description all over the framework!
    """

    # -------------------------
    #   CONFIGURATION
    # -------------------------

    # settings defined here will show up in all channels that support it (such as the webUI)
    # for the user to change as they see fit
    settings = {
        "example_setting": {
            "description": "This is an example setting. Settings default to type boolean when a type is not specified.",
            "default": False
        },
        "example_select": {
            "type": "select",
            "description": "This is an example setting of type `select`. It allows the user to choose from a list of options.",
            "default": "standard",
            "options": {
                "standard": "Just your run-of-the-mill system prompt",
                "uwu": "Makes your AI say uwu all the time!",
                "nag": "Makes your AI nag you a lot"
            }
        },
        "allow_ping": {
            "description": "Whether to allow the AI to use the ping tool",
            "default": True
        }
    }

    # list of dependencies that the module needs in order to work.
    # this is an example, leave empty if no dependencies are needed
    dependencies = ["pytest"]

    # -------------------------
    #   EVENT HANDLERS
    # -------------------------

    # any function starting with `on_` is an event handler and is called by the framework at various points. they do not get added to the AI's available tools.

    async def on_ready(self):
        """
        ALWAYS use this instead of the class constructor (__init__) as it runs at the right time during the framework's startup sequence.
        Initialize instance variables here.
        """
        pass

    async def on_shutdown(self):
        """Runs when the framework shuts down or restarts, or the module is reloaded. Use to clean up anything the module may have set up"""
        pass

    async def on_background(self):
        """If this is present, the framework will auto-start this function as an asyncio task to run in the background. Use for contineous background monitoring, background tasks, scheduled reminders, event loops, etc"""
        pass

    async def on_system_prompt(self):
        """Return a string here to inject it into the system prompt. The system prompt lives at the top of the context window, so use it ONLY for information that will not change frequently."""
        return None

    async def on_end_prompt(self):
        """Return a string here to append it to the end of the context window (after the conversation history). Useful for things that change frequently, such as displaying what channel the user is currently in."""
        return None

    async def on_user_message(self, content: str):
        """Runs on every message the user sends. Can be used to do whatever you want with the content of a user's sent message."""
        pass

    async def on_assistant_message(self, content: str):
        """Runs on every message received from the AI assistant. Can be used to do whatever you want with the content of a message received from the AI."""
        pass

    async def on_message_inject(self):
        """Will inject whatever string you return here into the user's message. Very useful for adding extra data that should persist in history. For example, when injecting timestamps, instead of using the end prompt for it (which would only show the AI what time it currently is), it can now give the AI a sense of when every message was sent."""
        pass

    async def on_install(self):
        """This runs after the module's dependencies are installed by the framework's auto-installer. Use it for post-installation hooks"""
        pass

    async def on_uninstall(self):
        """This runs after the module's dependencies are uninstalled by the framework's auto-installer. Use it for post-uninstallation hooks."""
        pass

    # -------------------------
    #   AI TOOLS
    # -------------------------

    # tools are simply class methods. the framework will read the definition
    # and translate the name, arguments and docstring to a tool usable by the AI
    # tools don't need a special decorator
    async def ping(self, latency: int):
        """
        Simulates a ping to the user.

        Args:
            latency: The latency to set for the simulated ping
        """
        # always return results using self.result, which standardizes the json output emitted by toolcalls
        return self.result(f"Pong! latency: {latency}", success=True)

    async def demonstration(self):
        # this tool definition is a guide for you, the AI (or human) reading this template, to know what you can do with the framework API
        # do not copy this section verbatim - use only what you need for your module

        # use this to get the value of a setting (as defined in the `settings` class property)
        my_value = self.config.get("example_setting")

        # use this in order to make calls to the AI model
        ai_response = await self.channel.send({"role": "user", "content": "This message will be sent to the AI. THe response of it will be the AI's response as a string")

        # use this to push a message out to the user
        # this message will appear without the user having to send a message first
        # it is handled by the active channel's on_push() method
        await self.channel.push(ai_response)

        # use this for persistent data
        # StorageDict is a python dict that automatically stores its data on-disk when you call .save() on it
        # valid types are: json, yaml, msgpack, text, and markdown
        # there is also StorageList, which is the python list equivalent of StorageDict
        persistent_data = core.storage.StorageDict("name_of_file", type="json")
        persistent_data["example"] = {
            "description": "this is an example entry"
        }
        persistent_data.save()

        # use this to log messages to the console
        # first param is the message category, second param is the message itself
        # self.name refers to the module's snake_case name
        self.channel.log(self.name, "whatever message you want")

    async def _private_method(self):
        # private methods are not added as tools, and are invisible to the AI. use for helper methods and the like.
        pass

    # -------------------------
    #   USER-FACING COMMANDS
    # -------------------------

    # commands are usable by the user only,
    # this one for example gives the user a `/ping` command,
    # with an optional "cookie" argument
    @core.module.command("ping", help={
        "": "Checks if the module is responsive",
        "cookie": "gives you a cookie"
    })
    async def ping_command(self, args: list):
        if not args:
            return "Pong!"
        elif len(args) >= 1 and args[1] == "cookie":
            return "heres a cookie! :3"
