Channels are the easiest thing to make for openlumara. The core concept is very simple: A channel is code that takes user input, in any way you want, and then does something with that input. You can do anything, but the most common thing to do is to send that input to the AI via `self.send_stream()`, and then parse through the resulting tokens!

Start with:
```
import core
```
That imports all required libraries in one fell swoop. See `core/__init__.py` if you want to see how that works.

Then to define a channel, create a class that uses `core.channel.Channel` as its parent:
```
class MyChannel(core.channel.Channel):
```

The main entry point of a channel is its run() method. That method gets launched during OpenLumara's boot sequence. It's the loop where you can take input and do something with it. You will have to ask for input in an asynchronous way to avoid blocking the rest of the program.

```
class MyChannel(core.channel.Channel):
    async def run(self):
        # in this example we're asking for input in a sync way,
        # but this will cause the rest of the program to stall.
        # so for a real-world channel, use an asynchronous way to do it
        # such as prompt_toolkit's PromptAsync (if you're making a CLI channel)
        # or any other asynchronous way of asking for input
        user_input = input("type your request> ")

        # this is the most basic way to send a request to the AI
        response = await self.send("hi there! what can you do?")

        # the resulting response object is a dict that has `content`, and `reasoning_content` if it exists
        if response.get("reasoning_content"):
            print(f"Thonk: {response.get('reasoning_content')})
        print(f"The AI said: {response.get('content')}")

        # but you can also stream tokens. this is what most of the included channels use:
        async for token in self.send_stream("can you search the web for tomato juice recipes?"):
            token_type = token.get("type")
            token_content = token.get("content")

            # possible token types are:
            # - reasoning
            # - content
            # - prompt_progress (this is what you can use to show the progress of a prompt being processed)
            # - timings (timing data detailing how long things took. includes tokens per second data)
            # - tool_calls
            # - tool_call_delta (streaming incomplete toolcalls)
            # - token_usage

            if token_type == "content":
                print(token_content, end="", flush=True)
```

Channels also have on_push:
```
async def on_push(self, message: dict):
    # this is where a message ends up when a module or channel calls self.channel.push()
    msg_content = message.get("content") # this is what you usually want

    print(f"[PUSH] {msg_content}")
```

on_log:
```
async def on_log(self, category: str, content: str):
    # this is where self.channel.log() ends up
    print(f"[{category}] {content}")
```

on_install and on_uninstall can be used to run any code when a module is installed or uninstalled
```
async def on_install(self):
    # do whatever
```

on_stream gets used by push_stream(), which is a version of push() that returns its response as a stream:
```
async def on_stream(self, stream):
    async for token in stream:
        # same logic as channel.send_stream()
        if token.get("type") == "content":
            print(token.get("content"), end="", flush=True)
```
