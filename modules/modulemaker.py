import core
import os

class ModuleMaker(core.module.Module):
    """a class that lets you create custom modules"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = os.path.join(core.get_path(), "user_modules")

    def _get_module_path(self, name):
        # TODO: add good path traversal protection
        name = name.split(".py")[0]
        name = name.replace("..", "") # this is insecure
        return os.path.join(self.path, f"{name}.py")

    async def create_module(self, name: str, python_code: str):
        """
        Create a new module. This can grant you, the AI, new tools for use in the future!
        Follow this spec:

        ```python
        import core

        class YourClassName(core.module.Module):
            \"\"\"You can put a description of your module here\"\"\"

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                # dict that gets saved to persistent storage
                self.saved_dict = core.storage.StorageDict("fancymoduledata", type="json") # available types: json, yaml, msgpack, markdown, text

                # list that gets saved to persistent storage
                self.saved_list = core.storage.StorageList("fancymoduledata", type="json") # available types: json, yaml, msgpack, text

                self.whatever_variables_you_want = "whatever value you want"

            async def on_system_prompt(self):
                return "Return a string here, and it'll appear in your system prompt!"

            async def on_background(self):
                \"\"\"This will be automatically ran as an asyncio background task by the opticlaw framework\"\"\"
                await self.channel.announce("This message pops up every minute. Very annoying!")
                await asyncio.sleep(60)

            async def my_function(self, name: str):
                \"\"\"A tool that can be called by AI. The docstring will show up in your tool description!\"\"\"
                # any code you want here
                name = name.lower()
                # use self.channel.announce to display notifications to the user! this can be during processing, or even in a background loop. this allows you to display messages without being prompted into it
                await self.channel.announce("wow! this message popped up all on its own!")

                try:
                    ohnoididsomethingnaughty()
                except Exception as e:
                    return self.result(f"error while trying to run my tool: {e}", success=False) # use success=False upon errors

                # you can even send a prompt to yourself and return the response!
                response_from_ai = self.channel.send_stream({"role": "user", "content": "how do you do, me?"})
                collected_tokens = []
                async for token in response_from_ai:
                    # do whatever you want with the token. collect it, display it, whatever you want
                    # tokens follow openAI's spec. they are a dict with two keys: type, and content.
                    if token.get("type") == "content":
                        collected_tokens.append(token.get("content"))
                    elif token.get("type") == "reasoning":
                        # do whatever with reasoning
                        pass

                msg_from_ai = " ".join(collected_tokens)

                return self.result(f"this is my tool, {name}! also, {msg_from_ai}", success=True) # using self.result is VITAL to ensure the output of a tool gets properly returned and parsed

            @core.module.command("my_command", temporary=False, help={
                "": "show list of profiles", # this is shown for the command by itself without arguments
                "<name>": "show profile for <name>",
                "<name> <profile>": "set <name>'s profile to <profile>"
            })
            async def my_command(self, args: list):
                # arguments is 0-indexed. args[0] is the first argument, not the name of the command
                match len(args):
                    case 0:
                        return self.saved_dict.keys()
                    case 1:
                        return self.saved_dict.get(args[0], "profile not found")
                    case 2:
                        self.saved_dict[args[0]] = str(args[1])
                        self.saved_dict.save()
                        return "Profile stored!" # we don't use self.result() for user facing commands, only for AI-facing tools
                    case _:
                        return "invalid arguments"
        ```
    """
        with open(self._get_module_path(name), "w") as f:
            f.write(python_code)
        return self.result("Code written! Remind user to enable the module and restart the server (using `/restart` or the restart button in the webUI settings panel)")

    async def read_module(self, name: str):
        """read an already-created module"""

        if not os.path.exists(self._get_module_path(name)):
            return self.result("Module does not exist!", success=False)

        content = None
        with open(self._get_module_path(name), "r") as f:
            content = f.read()
        return self.result(content)

    async def edit_module(self, name: str, python_code: str):
        """edits an existing module. ALWAYS call read_module() first before editing a module!"""
        if not os.path.exists(self._get_module_path(name)):
            return self.result("Module does not exist!", success=False)

        with open(self._get_module_path(name), "w") as f:
            f.write(python_code)

        return self.result("Code written! Remind user to enable the module and restart the server (using `/restart` or the restart button in the webUI settings panel)")
