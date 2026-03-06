import core
import re
import inspect

class Module:
    """Base class for modules/plugins"""

    def __init__(self, manager, channel=None):
        self.manager = manager
        self.channel = channel


    def result(self, data, success=True):
        """unified way of returning tool results"""
        return {
            "status": "success" if success else "error",
            "content": str(data)
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

def load(package, base_class, respect_config: bool = True):
    """
    Dynamically discovers classes in a package.

    Args:
        package: The root package module (e.g., `import channels; channels`).
        base_class: Only collect classes inheriting from this base.

    Returns:
        A tuple of discovered classes.
    """
    import importlib
    import pkgutil

    discovered = []

    # Ensure the package has a path to iterate
    if not hasattr(package, '__path__'):
        return tuple(discovered)

    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        try:
            # Import the module relative to the package
            module = importlib.import_module(f"{package.__name__}.{modname}")

            for attr_name in dir(module):
                attr = getattr(module, attr_name)

                # Ensure it is a class
                if not isinstance(attr, type):
                    continue

                # Filter by base class if provided (skip the base class itself)
                if base_class:
                    if attr is base_class:
                        continue
                    if not issubclass(attr, base_class):
                        continue

                # only load enabled modules into memory
                if respect_config:
                    if get_name(attr) not in core.config.get("modules", [])+core.config.get("channels", []):
                        continue

                discovered.append(attr)

        except ImportError as e:
            core.log("warning", f"failed to import {modname}: {e}")
            continue

    return tuple(discovered)

def get_name(obj):
    """converts a name like LifeOrganizer to `life_organizer`"""

    name = None
    if inspect.isclass(obj):
        name = obj.__name__
    else:
        name = obj.__class__.__name__

    re_snakecase = re.compile('(?!^)([A-Z]+)')
    name_snakecase = re.sub(re_snakecase, r'_\1', name).lower()

    return name_snakecase


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
