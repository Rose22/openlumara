Making modules for openlumara requires basic python coding knowledge, (or of course you can just have your AI make it for you). But once you get the hang of it, it's really easy and really powerful!

First of all, start every file with
```
import core
```

That imports all required libraries in one fell swoop. See `core/__init__.py` if you want to see how that works.

Then, define a class, that uses core.module.Module as its parent. So:
```
class MyModule(core.module.Module):
```

You can define settings like this. They show up in any UI or channel that supports it, such as the webUI:
```
class MyModule(core.module.Module):
    settings = {
        "enable_sparkles": {
            "type": "bool", # can be any of: bool (True/False), long_text (for long inputs), number, select
            "description": "Insert sparkles everywhere because why not",
            "default": False
        },
        "number_of_sparkles": {
            "type": number,
            "description": "how many sparkles to insert",
            "default": 5
        },
        "sparkle_mode": {
            "type": "select",
            "description": "What kind of sparkles to insert",
            "options": {
                "pink sparkles": "so many pink sparkles!",
                "rainbow sprinkles": "yum icecream",
                "cats": "...because cats are sparkles now i guess"
            },
            "default": "pink sparkles"
        }
    }
```

then to make a tool that the AI can use:
```
@core.module.tool
async def sparkle(any_argument: str, of_any_type: int):
    """the docstring gets passed to the AI as the tool's description"""
    # you can do basically anything in here that python lets you do
    # you have complete and total freedom. there are no restrictions to what modules can do
    # that includes running code written in other languages

    # but here are a few handy things you can do from within modules:

    # access the value of a setting
    setting_value = self.config.get("enable_sparkles")

    # act on that setting
    if setting_value is True: # (you can just use `if setting_value`, but for readability im doing it this way here)
        self._insert_sparkles()

    # you can access the current channel using self.channel
    await self.channel.push("this message gets pushed to the chat without having to prompt the AI!")
```

or a command the user can use with `/your_command`:
```
@core.module.command("your_command", help={
    "": "does a thing",
    "repeat": "does a thing many times"
})
async def your_command(self, args: list):
    if not args:
        return "hi! i did a thing!"
    if args[0] == "repeat":
        output = []
        for i in range(0, 10):
            output.append("hi! i did a thing many times!")

        return "\n".join(output)
```

you can also define custom routes for the webui:
```
import channels.webui.api as webui

class MyModule(core.module.Module):

    @webui.route("my_thing/list")
    async def _route_my_thing_list(self, body=None, query=None):
        return {"items": [...]}

    @webui.route("my_thing/do", method="POST")
    async def _route_my_thing_do(self, body=None, query=None):
        name = (body or {}).get("name")
        ...
```
which you can then access as `/api/ext/my_module/list` and `/api/ext/my_module/my_thing/do`

<!-- TODO: webui extension docs -->
