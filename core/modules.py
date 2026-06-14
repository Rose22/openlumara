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
nonagentic = ("characters", "time")

reported_missing = []

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
        core.log("warning", f"could not parse dependencies from {file_path}: {e}")
    return []

def _install_deps(module_name, packages):
    """install pip packages"""
    if not packages:
        return
    core.log(module_name, f"installing dependencies: {', '.join(packages)}")

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet"] + packages,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        core.log_error("dependency install failed", e)

def _uninstall_deps(module_name, packages):
    """uninstall pip packages"""
    if not packages:
        return
    core.log(module_name, f"uninstalling dependencies: {', '.join(packages)}")

    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "uninstall", "-y", "--quiet"] + packages,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        core.log_error("dependency uninstall failed", e)

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

async def install_module_deps(package, module_name):
    """install dependencies for a module if missing"""
    file_path = _get_module_file_path(package, module_name)
    if not file_path:
        return False

    deps = _extract_deps_from_file(file_path)
    if not deps:
        return False

    missing = _check_missing_deps(deps)
    if missing:
        _install_deps(module_name, missing)
        return True

    return False

async def uninstall_module_deps(package, module_name, manager):
    """uninstall dependencies for a module (only if still installed)"""
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

    if installed:
        # re-import so we can find the uninstall hook
        import importlib
        mod = importlib.import_module(f"{package.__name__}.{module_name}")

        # find the class
        module_class = None
        is_channel = False
        is_module = False
        for attr in dir(mod):
            obj = getattr(mod, attr)
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

        _uninstall_deps(module_name, installed)
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
        if filter and modname not in filter:
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
                        core.log(modname, "Warning: loading skipped because of missing dependencies")
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
