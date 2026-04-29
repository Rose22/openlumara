import core
import re
import inspect

# modules that should have their prompts inserted even when tools are off
nonagentic = ("characters", "time")

def load(package, base_class = None, filter: list = None):
    """
    loops through the specified package imported with `import whatever`, then checks inside those packages for any classes that derive from base_class, and return a tuple of those classes so we can use them as modules, channels etc

    this is what powers dynamic module/channel importing. we use it like so:
    import my_folder_with_classes as dynamic_folder
    self.load_modules(dynamic_folder, core.module.Module)
    """
    import importlib
    import pkgutil

    discovered = []

    if not hasattr(package, '__path__'):
        return ()

    for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
        if filter and modname not in filter:
            # dont even import unloaded modules
            continue

        try:
            # Import the module relative to the package
            module = importlib.import_module(f"{package.__name__}.{modname}")
            
            # Force reload to ensure we get the latest version of the module
            # This is crucial for restarts where code might have been modified
            importlib.reload(module)

            for attr_name in dir(module):
                target_class = getattr(module, attr_name)

                # Ensure it is a class
                if not isinstance(target_class, type):
                    continue

                # Filter by base class if provided
                if base_class:
                    if target_class is base_class:
                        continue
                    if not issubclass(target_class, base_class):
                        continue

                # skip modules not in filter if filter is enabled
                if filter and core.modules.get_name(target_class) not in filter:
                    continue

                discovered.append(target_class)

        except Exception as e:
            # Catching Exception prevents the program from crashing on faulty modules.
            # We simply log the warning and continue to the next module.
            core.log_error(f"failed to load module {modname}", e)
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
