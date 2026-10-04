import os
import ast
import core
import inspect
import sys
import subprocess
import importlib
import importlib.util

try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    from importlib_metadata import version, PackageNotFoundError

# modules that should have their prompts inserted even when tools are off
nonagentic = ("characters", "writing_style", "time")

reported_missing = []
reported_broken = []

# buffer the warnings and errors so that we can propagate them to manager.log()
def log(category, message):
    if core.manager.global_instance:
        core.manager.global_instance.log(category, message)
    else:
        print(f"[{category.upper()}] {message}")

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

# -- AI GENERATED CODE (qwen/Qwen3.8-Flash-Next-Q4) :: 2026-10-03
# folder-based module layout: each module/channel lives in a folder with an entry file (module.py or channel.py).
ENTRY_FILENAMES = ("module.py", "channel.py")
reported_init = []

def _get_module_file_path(package, module_name):
    """get the entry-file path for a module folder without importing it"""
    if not hasattr(package, '__path__'):
        return None

    for sub_path in package.__path__:
        mod_dir = os.path.join(sub_path, module_name)
        if not os.path.isdir(mod_dir):
            continue

        # __init__.py is not allowed in module/channel folders (it would shadow our custom loader)
        if os.path.exists(os.path.join(mod_dir, "__init__.py")):
            warn_key = f"{package.__name__}.{module_name}"
            if warn_key not in reported_init:
                reported_init.append(warn_key)
                log("core", f"skipping {warn_key}: __init__.py is not allowed in module/channel folders, please remove it")
            continue

        for entry in ENTRY_FILENAMES:
            candidate = os.path.join(mod_dir, entry)
            if os.path.isfile(candidate):
                return candidate
    return None

def discover_module_names(package):
    """list module/channel names from the filesystem without importing them (folder-only layout)"""
    names = []
    if not hasattr(package, '__path__'):
        return names

    for sub_path in package.__path__:
        if not os.path.isdir(sub_path):
            continue
        try:
            entries = sorted(os.listdir(sub_path))
        except OSError:
            continue
        for entry_name in entries:
            if entry_name.startswith(('_', '.')):
                continue
            if _get_module_file_path(package, entry_name) is None:
                continue
            if entry_name not in names:
                names.append(entry_name)
    return sorted(names)

def import_entry(package, module_name, reload=False):
    """import a module/channel folder as a real package using its entry file, so relative imports work inside it"""
    module_file = _get_module_file_path(package, module_name)
    if not module_file:
        raise ImportError(f"no entry file ({' or '.join(ENTRY_FILENAMES)}) found for {package.__name__}.{module_name}")

    full_name = f"{package.__name__}.{module_name}"
    mod_dir = os.path.dirname(module_file)

    existing = sys.modules.get(full_name)
    if existing is not None:
        if getattr(existing, "__file__", None):
            # already a properly-loaded module; reload from disk if requested
            if reload:
                importlib.reload(existing)
            return existing
        # namespace package (e.g. someone did `import channels.webui.api` first): promote it in-place
        existing.__path__ = [mod_dir]
        spec = importlib.util.spec_from_file_location(
            full_name, module_file, submodule_search_locations=[mod_dir]
        )
        existing.__spec__ = spec
        existing.__file__ = module_file
        try:
            spec.loader.exec_module(existing)
        except Exception:
            # don't leave a half-initialized module behind, or later calls would treat it as fully loaded
            del sys.modules[full_name]
            raise
        setattr(package, module_name, existing)
        return existing

    spec = importlib.util.spec_from_file_location(
        full_name, module_file, submodule_search_locations=[mod_dir]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[full_name]
        raise

    setattr(package, module_name, module)
    return module

class _EntryFileFinder:
    """meta path finder that resolves `import modules.<name>` / `import channels.<name>` etc to folder entry files (module.py/channel.py),
    since those folders intentionally have no __init__.py and are invisible to python's default finders"""
    _ROOTS = ("modules", "user_modules", "channels", "user_channels")

    def find_spec(self, fullname, path=None, target=None):
        parts = fullname.split(".")
        if len(parts) != 2 or parts[0] not in self._ROOTS:
            return None

        try:
            package = __import__(parts[0])
        except ImportError:
            return None

        module_file = _get_module_file_path(package, parts[1])
        if not module_file:
            return None

        return importlib.util.spec_from_file_location(
            fullname, module_file, submodule_search_locations=[os.path.dirname(module_file)]
        )

if not any(isinstance(f, _EntryFileFinder) for f in sys.meta_path):
    sys.meta_path.insert(len(sys.path_hooks), _EntryFileFinder())

def _check_missing_deps(deps):
    """return list of dependencies that are not installed (using pip package names)"""
    missing = []
    for dep in deps:
        # extract the base package name (e.g. 'python-telegram-bot' from 'python-telegram-bot>=1.0')
        pkg_name = dep.split('>=')[0].split('==')[0].split('<')[0].split('>')[0].strip()
        # strip stuff like [e2e] from the dependency
        pkg_name = pkg_name.split('[')[0].strip()
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

def _deps_of_enabled(section, package_name):
    """gather declared dependencies from every enabled module/channel in a config section"""
    deps = []
    for mod_name in core.config.get(section, "enabled", []):
        file_path = _get_module_file_path(importlib.import_module(package_name), mod_name)
        if file_path:
            deps.extend(_extract_deps_from_file(file_path))
    return deps

async def uninstall_module_deps(package, module_name, manager, exclude=None):
    """uninstall dependencies for a module, but only those that are actually installed
    and no longer needed by any enabled module or by openlumara itself"""
    # figure out which dependencies are still required by other enabled modules
    if exclude is None:
        exclude = set()
        try:
            exclude.update(_deps_of_enabled("modules", "modules"))
            exclude.update(_deps_of_enabled("user_modules", "user_modules"))
            exclude.update(_deps_of_enabled("channels", "channels"))
            exclude.update(_deps_of_enabled("user_channels", "user_channels"))
        except Exception:
            pass  # proceed without exclusion if config/package lookup fails

    file_path = _get_module_file_path(package, module_name)
    if not file_path:
        return False

    deps = _extract_deps_from_file(file_path)
    if not deps:
        return False

    # installed = declared deps that are present on this system
    missing = _check_missing_deps(deps)
    installed = [dep for dep in deps if dep not in missing]

    # keep deps that other enabled modules still need
    installed = [dep for dep in installed if dep not in exclude]

    # keep deps from requirements.txt (dependencies that openlumara ALWAYS needs)
    base_deps = []
    requirementstxt = core.get_path("requirements.txt")
    if os.path.exists(requirementstxt):
        with open(requirementstxt, 'r', encoding="utf-8") as f:
            base_deps = [dep.strip() for dep in f.read().split("\n") if dep.strip()]

    installed = [dep for dep in installed if dep not in base_deps]

    if installed:
        try:
            # import via the folder loader so we can find the uninstall hook
            mod = import_entry(package, module_name)
        except Exception:
            # If the module can't be imported (e.g., missing dependencies), skip the uninstall hook
            mod = None

        if mod:
            # find the module/channel class defined in this folder
            module_class = None
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if not inspect.isclass(obj):
                    continue

                if issubclass(obj, core.module.Module):
                    is_channel = False
                elif issubclass(obj, core.channel.Channel):
                    is_channel = True
                else:
                    continue

                # only classes defined within this module folder count
                origin = getattr(obj, "__module__", "")
                if origin != mod.__name__ and not origin.startswith(f"{mod.__name__}."):
                    continue

                module_class = obj
                break

            if module_class:
                # create a temporary instance
                if is_channel:
                    instance = module_class(manager)
                else:
                    is_user = package.__name__ == 'user_modules'
                    instance = module_class(manager, is_user_module=is_user)

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
    discovered = []

    if not hasattr(package, '__path__'):
        return ()

    for modname in discover_module_names(package):
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
            # Import the module folder via its entry file (real package -> relative imports work)
            module = import_entry(package, modname, reload=reload)

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

                # only discover classes defined in this module folder itself (not imported ones, e.g. modules.http.Http)
                origin = getattr(target_class, "__module__", "")
                if origin != module.__name__ and not origin.startswith(f"{module.__name__}."):
                    continue

                discovered.append(target_class)
        except core.exceptions.DependencyMissing as e:
            # silence these warnings for now
            # need a better way to deal with missing dependencies
            continue
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
    """returns the canonical module/channel name, derived from the folder the class lives in
    (e.g. modules.calendar.module -> 'calendar'). The class name no longer matters.
    Classes defined outside a module/channel folder are not supported."""
    module_name = getattr(obj, "__module__", "")
    parts = module_name.split(".")
    if len(parts) >= 2 and parts[0] in ("modules", "user_modules", "channels", "user_channels"):
        return parts[1]  # works for submodules too (channels.webui.api -> 'webui')

    raise ValueError(f"{obj!r} is not defined inside a module/channel folder")
