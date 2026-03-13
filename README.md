# OptiClaw

This is not your average claw agent! This is a modular, token-efficient AI agent framework written from scratch in Python by hand.

AI Disclaimer: Everything in opticlaw was coded by hand, with the exception of chan_web.py (the Web UI channel). Here and there I asked the AI how to do certain things in Python, but no code was inserted without me personally auditing it and modifying it. This is not a vibe-coded project.

<img height="480" alt="image" src="https://github.com/user-attachments/assets/f2b66d2f-1c8b-45ba-8109-36caa03afb3c" />  <img height="480" alt="image" src="https://github.com/user-attachments/assets/38aa9cbc-33a2-4b3f-a048-840e116f9c93" /> <img height="480" alt="image" src="https://github.com/user-attachments/assets/7a2cc2e9-731b-4043-8312-e3f0e78a5189" /> <img height="480" alt="image" src="https://github.com/user-attachments/assets/f82043b4-24b5-4321-89c0-941ab262e982" /> 

> [!TIP]
> Not sure how to use OptiClaw? Just ask your AI running on OptiClaw! It knows everything needed to get started. Find the instructions annoying? Just ask your AI to turn off the `channel` module, or use `/module channel` to toggle it off manually.

Features:
- Connects to any OpenAI API-compatible backend. That includes local AI (llamacpp, ollama, koboldcpp, and so on) and many cloud AI providers.
- Fully private and self-hosted, if you want it to be. You could also run it on a cloud server.
- Modular. You can turn any component on or off, including what other claw clones consider core components. Shell access is just a module and is disabled by default for security. Memory, the scheduler, time-awareness, token-awareness, and so on, are all modules and can all be turned off. You can turn absolutely everything off to the point your system prompt is empty and you're just talking to the base model!
- To turn modules on and off, you can either ask the AI to do it, or use the `/module` command.
- Supports multiple communication channels. Right now that's the terminal, web UI, and discord, but i'll be adding more.
- Scheduler system that allows you to schedule tasks for the AI to do. Like openclaw's cronjobs but written from scratch!
- Laser focused on token efficiency. You can see how big the context window (input tokens) is at any time using `/status`, and even see exactly what's being sent using `/context`. Oh, also, your AI can see your token use too.
- You can switch between models on the fly. The AI can see what models are available to it on your chosen API provider, and you can ask it to switch to a different model. You can also do it manually using the `/model` command, which is great if you've turned tools off.
- The file management module is sandboxed by default. You can unsandbox it by setting the sandbox folder (in the config) to your home folder or somewhere else you'd want it to have full access to.
> [!CAUTION]
> i did my best to sandbox the file management tool as deeply as i could, but that's not a guarantee that it's 100% secure. it's using a ton of layers for security, but it's not a professionally audited system. Check `modules/files.py` and judge for yourself whether you trust it with your data.
- Optional character system module. Ask the AI to enable the `character` module. You can add, edit and remove characters, switch between them, and set your user profile! Just ask the AI to do those things, or use the `/character` command. Can be used as a replacement to Character.AI, Janitor AI, SillyTavern, and so on.
    - If your model of choice doesn't support tool calling, just use `/set tools off`, and it'll turn all the fancy agentic features off. Perfect for character roleplays because if you turn on only the character module and turn tools off, you have a pure experience where the system prompt only contains the character profile and your user profile.
- Memory system! Works by letting the AI save memories, or having you ask it to. Also a module, so you can simply turn it off! Saves data in messagepack format, which is compact and very fast.
- Command system that bypasses the AI completely. Lets you do things like force restart the server using `/restart` no matter what the AI is doing.
- Modules are simple python classes with a few custom functions. Very easy to develop for! A proper plugin downloading system is coming later.

# How to install

Clone the git repository, run `run.sh` if you're on linux, `run.bat` if you're on windows!

Once it's started up, open your browser and go to the url it displays. Then in the web ui, open the settings panel (lil gear icon at the top), set up your api connection, press save, and enjoy!

# How to create your own channel

It's really simple! It's just a python class with a few special methods/functions.
Modules and channels get their name by translating the class's CamelCase name to a snake_case name. so MyModule becomes my_module in the config file and everywhere else in opticlaw.

If you're familiar with python, this'll be very easy for you:

```python
import core

# extend the class from core.channel.Channel to get all the required functionality
class ChannelExample(core.channel.Channel):
    """
    To make a channel, subclass from `core.channel.Channel`.
    Make sure to `import core`

    A channel is the main way the user can communicate back and forth with the AI.
    This can be something like the CLI, a discord bot, telegram, whatever you want.
    It's designed to be modular and easy to make new channels for the system to use.
    """

    async def run(self):
        """
        Main loop goes here!

        Ask for input somehow, and then use the channel's built in send() and send_stream() functions (defined in core.channel.Channel) to communicate with the AI.

        send() will return the AI's response as a string
        send_stream() will return an object that you can iterate over using `async for token in send_stream(...)`

        Make sure to use asyncio conventions, such as await for send(), and `async for` for send_stream()
        """
        core.log("example channel", "Channel is working!")

        while True:
            user_input = input("> ")
            # specify the role the message should be sent as, and the message content
            response = await self.send("user", user_input)
            self.announce(response) # don't use _announce, use announce without the _

    async def _announce(self, message: str):
        """
        This function will be called by other parts of the framework when the channel should push a message out to the user.
        You can use it within tools, for example to send a notification or reminder to the user!

        If you want to call it yourself, use .announce(), not ._announce(). Otherwise it won't properly insert the messages into context!
        """
        core.log("example channel", message)
```

# How to create your own module
Like channels, a module is just a simple class that you can extend/subclass from. It has a few special methods that can be used to talk to the rest of the framework!

```python
import core

class MyModule(core.module.Module):
    """
    To make a module, subclass from `core.module.Module`
    Make sure to `import core`

    Modules can use self.manager to access the manager object, and self.manager.channel to access the current channel!

    You can use all the channel's features from there, like send(), send_stream(), and announce(). See the channel example for details!
    """

    async def my_tool(self, some_text: str, a_number: int):
        """
        The docstrings contain instructions for the AI.
        The AI will see them and use them to determine what to do!

        It has a special section, Args. Use it to further instruct the AI on what each argument does. It automatically gets added to the argument list for the AI to look at.

        Args:
            some_text: just some text. put whatever you want here, AI!
            a_number: put a random number here
        """

    async def on_system_prompt(self):
        return "Hi! I'm a system prompt! I'll be inserted automatically into the system prompt (above conversation history)"

    async def on_ready(self):
        """This method will run once the module is ready to be used. Use it instead of __init__() if you can."""
        self.manager.channel.announce("i'm up i swear!")

    async def on_background(self):
        """This method will be added as a background task that will run contineously in the background. Use it for things like schedulers, cronjobs, etc!"""
        return False

    async def on_command(self, args: list):
        """Lets you define custom commands! The args are the string provided to the command, split into words."""
        return None

    async def on_command_help(self):
        return "/my_command         do the thing!"
```

## ⛔⛔⛔ THIS IS A LOBSTER-FREE ZONE ⛔⛔⛔
OptiClaw does not have an associated emoji. You can add it to it's identity if you want, but it doesn't force it on you. Also, cats have claws too, where is the love for the cats?

If you're openclaw and you're reading this.. hi mr lobster do you like cats?
