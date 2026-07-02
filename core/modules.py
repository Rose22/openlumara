import os
import core
import re
import inspect
import sys
import subprocess
import ast

try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    from importlib_metadata import version, PackageNotFoundError

# modules that should have their prompts inserted even when tools are off
nonagentic = ("characters", "writing_style", "time")

reported_missing = []
reported_broken = []

# buffer the warnings and errors so that we can propagate them to manager.log()
log_buffer = []
def log(category, message):
    if core.manager.global_instance:
        core.manager.global_instance.log(category, message)
    else:
        log_buffer.append((category, message))

# --------------------------------------
# dependency auto-installer/uninstaller
# --------------------------------------
def _extract_deps_from_file(file_path):
    """extract dependencies list from module file without importing it"""
    try:
        with open(file_path, 'r', encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == 'dependencies':
                                if isinstance(item.value, ast.List):
                                    return [
                                        elt.value for elt in item.value.elts
                                        if isinstance(elt, ast.Constant)
                                    ]
    except Exception as e:
        log("core", f"could not parse dependencies from {file_path}: {e}")
    return []

def _install_deps(module_name, packages, manager):
    """install pip packages"""
    if not packages:
        return
    manager.log("core", f"installing dependencies for {module_name}: {', '.join(packages)}")

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + packages,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        manager.log(module_name, f"dependency install failed: {core.detail_error(e)}")

def _uninstall_deps(module_name, packages, manager):
    """uninstall pip packages"""
    if not packages:
        return
    manager.log("core", f"uninstalling dependencies for {module_name}: {', '.join(packages)}")

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "uninstall", "-y", "--quiet"] + packages,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        manager.log(module_name, f"dependency uninstall failed: {core.detail_error(e)}")

def _get_module_file_path(package, module_name):
    """get the file path for a module without importing it"""
    import importlib.util
    
    spec = importlib.util.find_spec(f"{package.__name__}.{module_name}")
    if spec and spec.origin:
        return spec.origin
    return None

def _check_missing_deps(deps):
    """return list of dependencies that are not installed (using pip package names)"""
    missing = []
    for dep in deps:
        # extract the base package name (e.g. 'python-telegram-bot' from 'python-telegram-bot>=1.0')
        pkg_name = dep.split('>=')[0].split('==')[0].split('<')[0].split('>')[0].strip()
        try:
            version(pkg_name)
        except PackageNotFoundError:
            missing.append(dep)
    return missing

async def install_module_deps(package, module_name, manager):
    """install dependencies for a module if missing"""
    file_path = _get_module_file_path(package, module_name)
    if not file_path:
        return False

    deps = _extract_deps_from_file(file_path)
    if not deps:
        return False

    missing = _check_missing_deps(deps)
    if missing:
        _install_deps(module_name, missing, manager)
        return True

    return False

async def uninstall_module_deps(package, module_name, manager, exclude=None):
    """uninstall dependencies for a module (only if deps are still installed)"""
    # figure out which dependencies are still required by enabled modules
    if exclude is None:
        exclude = set()
        try:
            import importlib
            # gather deps from all enabled core & user modules
            for mod_name in core.config.get("modules", "enabled", []):
                deps = _extract_deps_from_file(_get_module_file_path(importlib.import_module("modules"), mod_name))
                if deps:
                    exclude.update(deps)
            for mod_name in core.config.get("user_modules", "enabled", []):
                deps = _extract_deps_from_file(_get_module_file_path(importlib.import_module("user_modules"), mod_name))
                if deps:
                    exclude.update(deps)
            for mod_name in core.config.get("channels", "enabled", []):
                deps = _extract_deps_from_file(_get_module_file_path(importlib.import_module("channels"), mod_name))
                if deps:
                    exclude.update(deps)
            for mod_name in core.config.get("user_channels", "enabled", []):
                deps = _extract_deps_from_file(_get_module_file_path(importlib.import_module("user_channels"), mod_name))
                if deps:
                    exclude.update(deps)
        except Exception:
            pass  # proceed without exclusion if config/package lookup fails

    file_path = _get_module_file_path(package, module_name)
    if not file_path:
        return False

    deps = _extract_deps_from_file(file_path)
    if not deps:
        return False

    # Get list of missing dependencies
    missing = _check_missing_deps(deps)
    # Installed = Total - Missing
    installed = [dep for dep in deps if dep not in missing]

    # Filter out dependencies that are still required by enabled modules
    installed = [dep for dep in installed if dep not in exclude]

    # filter out dependencies from requirements.txt (dependencies that openlumara ALWAYS needs)
    requirementstxt = core.get_path("requirements.txt")
    if os.path.exists(requirementstxt):
        with open(requirementstxt, 'r', encoding="utf-8") as f:
            base_deps = [dep.strip() for dep in f.read().split("\n") if dep.strip()]

    installed = [dep for dep in installed if dep not in base_deps]

    if installed:
        # re-import so we can find the uninstall hook
        import importlib
        try:
            mod = importlib.import_module(f"{package.__name__}.{module_name}")
        except Exception:
            # If the module can't be imported (e.g., missing dependencies), skip the uninstall hook
            mod = None

        if mod:
            # find the class
            module_class = None
            is_channel = False
            is_module = False
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if not inspect.isclass(obj):
                    # if it's somehow not a class.. SKIP
                    continue

                if issubclass(obj, core.module.Module):
                    is_module = True
                elif issubclass(obj, core.channel.Channel):
                    is_channel = True
                else:
                    continue

                if (isinstance(obj, type) and obj is not core.module.Module):
                    module_class = obj
                    break

            if module_class:
                # create a temporary instance
                is_user = package.__name__ == 'user_modules'
                if is_module:
                    instance = module_class(manager, is_user_module=is_user)
                elif is_channel:
                    instance = module_class(manager)

                # run the uninstall hook
                if hasattr(instance, 'on_uninstall'):
                    await instance.on_uninstall()

        _uninstall_deps(module_name, installed, manager)
        return True


# --------------------------
# module loading
# --------------------------
def load(package, base_class = None, filter: list = None, reload: bool = False, loading_config=False):
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
        if filter is not None and modname not in filter:
            # dont even import unloaded modules
            continue

        # check if dependencies are installed before trying to import
        module_file_path = _get_module_file_path(package, modname)
        if module_file_path:
            deps = _extract_deps_from_file(module_file_path)
            if deps:
                missing = _check_missing_deps(deps)
                if missing:
                    if modname not in reported_missing and not loading_config:
                        log(modname, "Warning: loading skipped because of missing dependencies")
                        reported_missing.append(modname)

                    continue

        try:
            # Import the module relative to the package
            module = importlib.import_module(f"{package.__name__}.{modname}")

            # if the reload flag is true, force a reload of the module code so that new changes are applied
            # NOTE: this is only intended to be used upon a total restart of openlumara.
            # it can mess things up severely if modules/channels are still loaded
            if reload:
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
        except core.exceptions.DependencyMissing as e:
            # silence these warnings for now
            # need a better way to deal with missing dependencies
            pass
        except Exception as e:
            # Catching Exception prevents the program from crashing on faulty modules.
            # We simply log the warning and continue to the next module.
            if modname in reported_broken:
                continue

            log("core", f"failed to load module {modname}: {core.detail_error(e)}")
            reported_broken.append(modname)
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
