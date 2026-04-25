import os
import core
import re
import inspect
import json
import asyncio

class Module:
    """Base class for modules/plugins"""

    # can be defined by modules, contains default settings that can be changed by the user
    settings = {}

    def __init__(self, manager, is_user_module=False, channel=None):
        self.manager = manager
        self.channel = channel # later set by the channel base class, _set_as_active_channel()
        self.name = core.modules.get_name(self) # shorthand alias
        self.disabled_tools = [] # gets scanned when adding tools from the module. you can alter this in a module's __init__() to selectively disable tools.
        self.unsafe = False # unsafe flag for special display of unsafe modules in UI's

        # load module config
        config_target = "modules" if not is_user_module else "user_modules"
        self.config = core.config.get(config_target, {}).get("settings", {}).get(self.name, {})

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Scan the class for methods decorated with @command
        for attr_name in dir(cls):
            method = getattr(cls, attr_name)
            # Check if it's a function and has our custom attribute
            if callable(method) and hasattr(method, "_is_command"):
                cmd_name = method._command_name
                register_command_handler(cmd_name, cls, method)

    async def _start(self):
        """run the startup sequence for a module"""

        # run startup methods
        if hasattr(self, "on_ready"):
            await self.on_ready()
        if hasattr(self, "on_background"):
            if not core.module.is_empty_coroutine(self.on_background):
                task = asyncio.create_task(self.on_background(), name=self.name)
                task.add_done_callback(self.manager._remove_async_task)
                self.manager._async_tasks.add(task)
                core.log("core", f"Started background task {self.name}")

        return True

    def result(self, data, success=True):
        """unified way of returning tool results"""
        return {
            "status": "success" if success else "error",
            "content": data
        }

    async def on_system_prompt(self):
        """Overridable method that will insert it's return value into the system prompt if something is returned (defaults to None)"""
        return None
    async def on_end_prompt(self):
        """Overridable method that will insert it's return value into the end of the context (after the conversation history) if something is returned (defaults to None). Useful for things that change frequently, such as the time. Using the prompt at the end of conversation history means history does not have to be reprocessed if the prompt changes."""
        return None

    async def on_ready(self):
        """This method will run once the module is ready to be used. Use it instead of __init__() if you can."""
        pass

    async def on_background(self):
        """This method will be added as a background task that will run contineously in the background. Use it for things like schedulers, cronjobs, etc!"""
        pass

    async def on_user_message(self, message: dict):
        """Triggers when the user sends a message)"""
        pass

    async def on_assistant_message(self, message: dict):
        """Triggers when the assistant sends a message"""
        pass

# --------------
# command decorator (@core.module.command)
# Registry format: {"command_name": [(class_type, method), ...]}
_command_registry = {}

def command(name, help=None, temporary=False):
    """
    Decorator to register a method as a command handler.
    Accepts a string description or a dictionary for subcommand help.
    If not provided, falls back to the function's docstring (first line).
    """
    def decorator(func):
        func._is_command = True
        func._is_temporary = temporary
        func._command_name = name.lower().strip()

        desc = help

        # Fallback to docstring if no help provided
        if desc is None:
            doc = func.__doc__
            if doc:
                # Grab the first line of the docstring for the help text
                desc = doc.strip().split('\n')[0]

        func._command_description = desc or ""
        return func
    return decorator

def register_command_handler(command_name, cls, method):
    if command_name not in _command_registry:
        _command_registry[command_name] = []
    _command_registry[command_name].append((cls, method))

def command_is_temporary(command_name):
    """Check if a command is marked as temporary."""
    if command_name not in _command_registry:
        return False
    for registered_cls, method in _command_registry[command_name]:
        if getattr(method, '_is_temporary', False):
            return True
    return False

def get_command_description(command_name):
    """Get the description for a command."""
    if command_name not in _command_registry:
        return None
    for registered_cls, method in _command_registry[command_name]:
        return getattr(method, '_command_description', '')
    return None

def is_empty_coroutine(func):
    """
    Checks if a coroutine function body is effectively empty
    (only contains 'pass', '...', or docstrings).
    """
    try:
        # Get the source code lines of the function
        source_lines, _ = inspect.getsourcelines(func)
        source = "".join(source_lines)

        # Remove the function definition line (def ...)
        # This regex is simple; it looks for the first 'def ...' and strips it
        body = re.sub(r"^\s*(async\s+)?def\s+\w+\(.*?\):\s*", "", source, count=1)

        # Remove docstrings (simple heuristic)
        body = re.sub(r'""".*?"""', '', body, flags=re.DOTALL)
        body = re.sub(r"'''.*?'''", '', body, flags=re.DOTALL)

        # Remove comments and whitespace
        body = re.sub(r'#.*', '', body)
        body = body.strip()

        # If what remains is just 'pass' or '...' or empty string, it's empty.
        return not body or body in ('pass', '...')

    except (TypeError, OSError):
        # Fallback if source cannot be retrieved (e.g., built-in or dynamic)
        # We assume it's not empty to be safe.
        return False
