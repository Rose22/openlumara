import os
import regex as re
import ast
import core
import inspect
import sys
import site
import shutil
import subprocess
import asyncio
import importlib
import importlib.util

# get the correct importlib stuff
try:
    from importlib.metadata import distributions
except ImportError:
    from importlib_metadata import distributions

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

        # there has GOT to be a cleaner way..
        # this is awful syntax lol
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

def _pip_prefix():
    """use uv's pip interface when available, plain pip otherwise"""
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip"], True
    return [sys.executable, "-m", "pip"], False

def _install_deps(module_name, packages, manager, target):
    """install packages using uv (or pip as fallback)"""
    if not packages:
        return False

    if not target:
        manager.log(module_name, "no writable dependency directory is available; skipping install")
        return False

    # pyinstaller sets sys.frozen when the app is packaged by it
    if getattr(sys, "frozen", False):
        manager.log(
            module_name,
            "runtime dependency installation is unavailable in this build; "
            "vendor the dependencies in the module's site-packages/ folder"
        )
        return False

    prefix, using_uv = _pip_prefix()
    manager.log(
        "core",
        f"installing dependencies for {module_name} with {'uv' if using_uv else 'pip'} "
        f"into {target}: {', '.join(packages)}"
    )

    cmd = [*prefix, "install", "--quiet", "--upgrade", "--target", target]
    env = os.environ.copy()
    if using_uv:
        cmd += ["--python", sys.executable, "--no-python-downloads"]
        if sys.prefix != sys.base_prefix:
            env.setdefault("VIRTUAL_ENV", sys.prefix)
    cmd += packages

    os.makedirs(target, exist_ok=True)
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        return True
    except subprocess.CalledProcessError as e:
        manager.log(module_name, f"dependency install failed: {core.detail_error(e)}")
        return False

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
    """list module/channel names from the filesystem without importing them"""
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
    module_file, _ = _prepare_module_paths(package, module_name)
    if not module_file:
        raise ImportError(f"no entry file ({' or '.join(ENTRY_FILENAMES)}) found for {package.__name__}.{module_name}")

    full_name = f"{package.__name__}.{module_name}"
    mod_dir = os.path.dirname(module_file)

    existing = sys.modules.get(full_name)
    if existing is not None:
        if getattr(existing, "__file__", None):
            # already a loaded module, so reload it instead
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

_added_site_dirs = set()

def _module_site_packages(module_file):
    return os.path.join(os.path.dirname(module_file), "site-packages")

def _add_site_dir(path):
    if not path or path in _added_site_dirs or not os.path.isdir(path):
        return
    known_paths = set(sys.path)
    site.addsitedir(path)
    # addsitedir also appends .pth entries, which must not count as base-environment paths
    _added_site_dirs.update(set(sys.path) - known_paths)
    importlib.invalidate_caches()

def _prepare_module_paths(package, module_name):
    """return (entry file, writable target dir) and add the module's vendored and
    installed dependency dirs to sys.path before any dependency check or import"""
    module_file = _get_module_file_path(package, module_name)
    if not module_file:
        return None, None

    _add_site_dir(_module_site_packages(module_file))

    try:
        target = core.get_module_deps_path(package.__name__, module_name)
    except ValueError as e:
        log("core", f"invalid dependency path for {package.__name__}.{module_name}: {e}")
        target = None

    if target:
        _add_site_dir(target)

    return module_file, target

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

        module_file, target = _prepare_module_paths(package, parts[1])
        if not module_file:
            return None

        # if dependencies are missing, don't throw an error, simply don't execute the main module.py.
        # but let things still import from other files in the module's folder
        # used for webui/api.py, among other things
        deps = _extract_deps_from_file(module_file)
        if deps and _check_missing_deps(deps, _own_dep_paths(module_file, target)):
            return None

        return importlib.util.spec_from_file_location(
            fullname, module_file, submodule_search_locations=[os.path.dirname(module_file)]
        )

if not any(isinstance(f, _EntryFileFinder) for f in sys.meta_path):
    sys.meta_path.insert(len(sys.path_hooks), _EntryFileFinder())

def _dep_name(dep):
    """package name from a requirement string, e.g. 'python-telegram-bot>=1.0[e2e]' -> 'python-telegram-bot'"""
    return re.split(r"[<>=!~;\[\s]", dep, maxsplit=1)[0].strip().lower().replace("_", "-")

def _dep_names_in(paths):
    """installed distribution names found in the given paths"""
    names = set()
    for dist in distributions(path=paths):
        name = dist.metadata["Name"]
        if name:
            names.add(_dep_name(name))
    return names

_base_dep_names_cache = None

def _base_dep_names():
    """dependency names provided outside module dependency dirs, so every module can rely on them"""
    global _base_dep_names_cache
    if _base_dep_names_cache is None:
        base_paths = [path for path in sys.path if path and path not in _added_site_dirs]
        _base_dep_names_cache = _dep_names_in(base_paths)
    return _base_dep_names_cache

def _own_dep_paths(module_file, target):
    """dependency dirs owned by a single module: its vendored site-packages and its install target"""
    return [path for path in (_module_site_packages(module_file), target) if path]

def _check_missing_deps(deps, own_paths=()):
    """return dependencies missing from the base env and the module's own dependency dirs.
    other modules' dependency dirs intentionally don't count, so no module can borrow another's packages"""
    present = _base_dep_names() | _dep_names_in(list(own_paths))
    return [dep for dep in deps if _dep_name(dep) not in present]

async def install_module_deps(package, module_name, manager):
    """install dependencies for a module if missing"""
    file_path, target = _prepare_module_paths(package, module_name)
    if not file_path:
        return False

    deps = _extract_deps_from_file(file_path)
    if not deps:
        return False

    missing = _check_missing_deps(deps, _own_dep_paths(file_path, target))
    if not missing:
        return False

    installed = await asyncio.to_thread(_install_deps, module_name, missing, manager, target)
    if not installed:
        return False

    # the target may have been created by this install: pick up its packages now
    if target:
        _add_site_dir(target)
    return True

async def uninstall_module_deps(package, module_name, manager):
    """remove a module's runtime-installed dependency directory"""
    file_path, target = _prepare_module_paths(package, module_name)
    if not file_path or not target or not os.path.isdir(target):
        return False

    # run the uninstall hook while the module and its deps are still importable
    try:
        mod = import_entry(package, module_name)
    except Exception:
        mod = None

    if mod:
        module_class = None
        is_channel = False
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

            origin = getattr(obj, "__module__", "")
            if origin != mod.__name__ and not origin.startswith(f"{mod.__name__}."):
                continue

            module_class = obj
            break

        if module_class:
            try:
                if is_channel:
                    instance = module_class(manager)
                else:
                    is_user = package.__name__ == "user_modules"
                    instance = module_class(manager, is_user_module=is_user)
                await instance.on_uninstall()
            except Exception as e:
                manager.log(module_name, f"dependency uninstall hook failed: {core.detail_error(e)}")

    try:
        await asyncio.to_thread(shutil.rmtree, target)
    except OSError as e:
        manager.log(module_name, f"could not remove dependencies at {target}: {e}")
        return False

    while target in sys.path:
        sys.path.remove(target)
    _added_site_dirs.discard(target)
    importlib.invalidate_caches()
    manager.log("core", f"removed dependencies for {module_name} from {target}")
    return True


# --------------------------
# module loading
# --------------------------
def _module_has_folder(package, module_name, folder_name):
    """checks whether a module folder contains a subfolder with the given name"""
    if not folder_name:
        return False

    module_file = _get_module_file_path(package, module_name)
    if module_file:
        return os.path.isdir(os.path.join(os.path.dirname(module_file), folder_name))

    for sub_path in getattr(package, "__path__", []):
        if os.path.isdir(os.path.join(sub_path, module_name, folder_name)):
            return True
    return False


def _insert_setting(target_class, setting_name, setting_value, position="append"):
    """inserts a setting into a module class's settings dict if it is missing.

    position can be "append" or "top". Returns True when the setting was newly
    inserted, otherwise False.
    """
    if not setting_name:
        return False

    settings = getattr(target_class, "settings", None)
    if not isinstance(settings, dict):
        settings = {}
    else:
        settings = dict(settings)

    if setting_name in settings:
        return False

    if position == "top":
        new_settings = {setting_name: setting_value}
        new_settings.update(settings)
    else:
        settings[setting_name] = setting_value
        new_settings = settings

    target_class.settings = new_settings
    return True


def _ensure_webui_extension_setting(package, module_name, target_class):
    """auto-adds the enable_webui_extension setting if a module ships webui assets"""
    if package.__name__.split(".")[-1] not in ("modules", "user_modules"):
        return
    if not _module_has_folder(package, module_name, "webui"):
        return

    _insert_setting(
        target_class,
        "enable_webui_extension",
        {
            "default": True,
            "description": "Whether to load this module's WebUI Extensions, which extend the WebUI with module-specific features, sidebars, panels, etc"
        },
        position="top"
    )


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
        module_file_path, target = _prepare_module_paths(package, modname)
        if module_file_path:
            deps = _extract_deps_from_file(module_file_path)
            if deps:
                missing = _check_missing_deps(deps, _own_dep_paths(module_file_path, target))
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

                _ensure_webui_extension_setting(package, modname, target_class)

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
