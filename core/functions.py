import core
import os
import sys
import errno
import shutil
import time
import traceback
import urllib.parse

def log(category: str, msg: str):
    """
    simple console log
    WARNING: strictly for cases where the manager or channel instance(s) cannot be accessed
    for example during config loading

    using this will print into the terminal if the manager isn't loaded,
    but otherwise will use the proper logging path via the manager

    so this is a last resort
    """
    print(f"[{category.upper()}] {msg}", flush=True)

def detail_error(e: Exception):
    """provides more detail about an exception, but in a compact format"""

    # just return the normal message if debug mode is off
    if not core.debug:
        return str(e)

    # lots of detail for debugging!
    return f"{e} | {e.__traceback__.tb_frame.f_code.co_filename}, {e.__traceback__.tb_frame.f_code.co_name}, ln:{e.__traceback__.tb_lineno}\n\n{traceback.format_exc()}"

def log_error(msg: str, e: Exception):
    """
    console log but with extra spice for errors
    WARNING: strictly for cases where the manager or channel instance(s) cannot be accessed
    for example during config loading
    """
    if not core.manager.global_instance:
        print(f"[ERROR] {msg}: {detail_error(e)}")
        traceback.print_exception(e, file=sys.stdout)
    else:
        tb = traceback.format_exception(e)
        core.manager.global_instance.log("error", f"{msg}: {detail_error(e)}\n{tb}")

def get_path(path: str = "", sandbox=True):
    """get path relative to the project root directory. returns root path if no path is specified."""
    project_root = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        os.pardir
    ))

    if not path:
        return project_root

    if os.path.isabs(path):
        # return an absolute path as-is
        return path
    else:
        # is a relative path, return it sandboxed to the project root
        if sandbox:
            return sandbox_path(project_root, path)
        else:
            return os.path.join(project_root, path)

# a leading dot is a unix convention, so windows gets a plain folder
DEFAULT_HOME = "~/openlumara" if sys.platform == "win32" else "~/.openlumara"

def get_home():
    """get the writable root used for config, data and user content. defaults to ~/.openlumara (~/openlumara on windows).
    env var OPENLUMARA_HOME sets its location, and main.py lets you use --home-dir to override it."""
    home = os.environ.get("OPENLUMARA_HOME") or DEFAULT_HOME

    # realpath so sandbox_path() accepts state dirs reached through symlinks
    return os.path.realpath(os.path.abspath(os.path.expanduser(home)))

def get_home_path(path: str = "", sandbox=True):
    """get path relative to the home directory. returns the home path if no path is specified."""
    home = get_home()

    if not path:
        return home

    if os.path.isabs(path):
        return path

    return sandbox_path(home, path) if sandbox else os.path.join(home, path)

def get_module_deps_path(package_name: str, module_name: str):
    """writable directory holding runtime-installed dependencies for a module/channel"""
    return get_home_path(os.path.join("module_deps", package_name, module_name))

LEGACY_STATE_ENTRIES = (
    "config.yml",
    "data",
    "user_modules",
    "user_channels",
    "skills",
    "user_webui_themes",
    "data_backups",
)

def migrate_legacy_state():
    """move state left in the install dir by pre-home versions of the app into the home directory"""
    home = get_home()
    root = get_path()
    entries = list(LEGACY_STATE_ENTRIES)

    # a custom data folder from the legacy config is migrated too, on the first run only
    config_file = os.path.join(root, "config.yml")
    legacy_config_still_live = os.path.exists(config_file) and not os.path.exists(os.path.join(home, "config.yml"))

    if legacy_config_still_live:
        try:
            import yaml
            with open(config_file, "r", encoding="utf-8") as f:
                folder = (yaml.safe_load(f) or {}).get("core", {}).get("data_folder")
        except Exception:
            folder = None

        usable_name = isinstance(folder, str) and folder
        not_already_listed = folder not in entries
        if usable_name and not_already_listed:
            entries.append(folder)

    for name in entries:
        src = os.path.normpath(os.path.join(root, name))
        dst = os.path.join(home, name)

        # protect against path traversal
        outside_install_dir = not src.startswith(root + os.sep)
        missing_source = not os.path.exists(src)
        already_migrated = os.path.exists(dst)

        if outside_install_dir or missing_source or already_migrated:
            continue

        # back up first, verify the backup, abort if backing up fails for ANY reason
        backup_root = "~/openlumara_legacy_backups" if sys.platform == "win32" else "~/.openlumara_legacy_backups"
        backup_dir = os.path.abspath(os.path.expanduser(backup_root))
        backup_path = os.path.join(backup_dir, name)

        try:
            os.makedirs(backup_dir, exist_ok=True)

            # delete from the backup if exists
            if os.path.isdir(backup_path):
                shutil.rmtree(backup_path)
            elif os.path.exists(backup_path):
                os.remove(backup_path)

            # then copy it over
            if os.path.isdir(src):
                shutil.copytree(src, backup_path)
            else:
                shutil.copy2(src, backup_path)

            if not os.path.exists(backup_path):
                raise Exception("Backup file not created")
            log("core", f"backed up {src} to {backup_path}")
        except Exception as e:
            # never leave a half-written backup behind
            if os.path.isdir(backup_path):
                shutil.rmtree(backup_path, ignore_errors=True)
            elif os.path.exists(backup_path):
                os.remove(backup_path)

            log("core", f"FATAL ERROR: could not back up {src} before migration. Aborting: {core.detail_error(e)}")
            sys.exit(1)

        try:
            shutil.move(src, dst)
            if not os.path.exists(dst):
                raise Exception(f"moving the backup to the home directory failed! check '{src}' and '{dst}'")

            log("core", f"moved {src} to {dst}")
        except Exception as e:
            # never leave a half-moved destination behind, or the next run would skip it
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            elif os.path.exists(dst):
                os.remove(dst)

            # if the move consumed the source, restore it from the verified backup
            if not os.path.exists(src):
                try:
                    if os.path.isdir(backup_path):
                        shutil.copytree(backup_path, src)
                    else:
                        shutil.copy2(backup_path, src)
                    log("core", f"restored {src} from backup after failed move")
                except Exception as restore_error:
                    log("core", f"FATAL ERROR: failed to move {src} and could not restore it. Backup kept at {backup_path}: {core.detail_error(restore_error)}")
                    sys.exit(1)
            log("core", f"could not move {src} to {dst}: {e}")

def get_data_path(subpath=None):
    """get path to the data directory. contains all persistent data used by the framework"""

    data_path = core.config.get("core", {}).get("data_folder", "data")

    # if it's a relative path, resolve it from the home directory
    if not os.path.isabs(data_path):
        data_path = core.get_home_path(data_path)

    # create it if it doesn't exist
    if not os.path.exists(data_path):
        os.makedirs(data_path, exist_ok=True)

    return sandbox_path(data_path, subpath) if subpath else data_path

def remove_duplicates(lst: list):
    # removes duplicates from a list

    new_lst = []
    for item in lst:
        if item not in new_lst:
            new_lst.append(item)
    return new_lst

def validate_path_string(path: str) -> str:
    """
    validates a path string for traversal and encoding attacks.
    """
    # Strip path separators
    path = path.strip(os.path.sep)

    # Handle URL encoding (check for double/triple encoding)
    decoded = path
    for _ in range(3):
        decoded = urllib.parse.unquote(decoded)

    # normalize slashes after decoding to prevent windows join bypasses
    decoded = decoded.replace("\\", os.sep).replace("/", os.sep)
    # strip again in case unquote introduced new separators
    decoded = decoded.strip(os.path.sep)

    # Check for traversal and null bytes
    if ".." in decoded or "\x00" in decoded:
        raise ValueError(f"Path traversal is not allowed ({path})")

    return decoded

def sandbox_path(base_path: str, requested_path: str = None) -> str:
    """
    protects against path traversal attacks and the like
    """
    path = requested_path
    if not requested_path:
        # the base path is basically always the sandbox path, so um, yeah, no need to filter that
        return base_path

    # we dont use os.path.normpath here because it resolves '..' and allows path traversal
    # so we do the cross-platform stuff manually instead....
    # using a simple string replacement :(
    base_path = base_path.replace("\\", os.path.sep)
    base_path = base_path.replace("/", os.path.sep)
    
    path = requested_path.replace("\\", os.path.sep)
    path = path.replace("/", os.path.sep)

    # remove path separator at the beginning and end
    path = path.strip(os.path.sep)

    # remove the base path from it in case the AI/user inserts it
    prefix = base_path + os.sep
    if path.startswith(prefix):
        path = path[len(prefix):]
    elif path == base_path:
        path = ""

    decoded = validate_path_string(path)

    # block symlink paths
    if hasattr(os, 'O_NOFOLLOW'):
        # check if any component is a symlink
        parts = decoded.split(os.path.sep)
        for i, part in enumerate(parts):
            if i == 0:
                continue  # Skip root
            test_path = os.path.join(base_path, *parts[:i])
            if os.path.islink(test_path):
                raise ValueError("Symlinks are not allowed in the path")

    if not path:
        return base_path

    # more path traversal protection
    path_in_base = os.path.join(base_path, os.path.normpath(decoded))
    
    try:
        real_path = os.path.realpath(path_in_base)
    except (OSError, ValueError):
        raise ValueError(f"Invalid path: {requested_path}")

    if os.path.islink(path_in_base):
        raise ValueError("Symlinks are not allowed in the requested path")

    base_prefix = base_path + os.sep

    if sys.platform == "win32":
        check_path = real_path.lower()
        check_prefix = base_prefix.lower()
        check_base = base_path.lower()
    else:
        check_path = real_path
        check_prefix = base_prefix
        check_base = base_path

    if check_path.startswith(check_prefix) or check_path == check_base:
        return real_path
    else:
        raise ValueError("Access denied: target path is outside sandbox")

# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara status:reviewed
# ROSE22: based on a report submitted to me by @wishieshard. i've vetted and tested this.
def sandbox_open(base_path: str, requested_path: str, flags: int, mode: int = 0o666):
    """
    Atomic, symlink-proof open inside a sandbox. Fixes TOCTOU across the harness.

    Returns an open file descriptor; the caller owns it (wrap in os.fdopen or
    close it)
    """
    sep = os.path.sep
    base_path = base_path.replace("\\", sep).replace("/", sep).rstrip(sep)

    path = requested_path.replace("\\", sep).replace("/", sep)

    # in case the caller included the sandbox folder name itself in the path
    base_name = os.path.basename(base_path)
    if path == base_name:
        path = ""
    elif path.startswith(base_name + sep):
        path = path[len(base_name) + 1:]

    # rejects traversal (..), null bytes, url-encoded variants
    decoded = validate_path_string(path)

    no_dirfd = not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY")

    if no_dirfd:
        # best effort on exotic platforms: old string validation + final-component guard
        target = sandbox_path(base_path, decoded)
        return os.open(target, flags | getattr(os, "O_NOFOLLOW", 0), mode)

    try:
        # opening the base follows symlinks on purpose (operator-configured root)
        fd = os.open(base_path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as e:
        raise ValueError(f"Invalid sandbox base: {base_path} ({e.strerror})")

    try:
        if not decoded:
            # the generic except below closes fd for us
            raise ValueError("A file path is required, the sandbox base itself cannot be opened")

        parts = [p for p in decoded.split(sep) if p not in ("", ".")]
        if not parts:
            # decoded was something empty-ish like "." after normalization
            os.close(fd)
            raise ValueError("A file path is required, the sandbox base itself cannot be opened")
        for part in parts[:-1]:
            # descend one real directory at a time: O_NOFOLLOW means a symlink
            # component fails here instead of redirecting the rest of the walk
            try:
                sub = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError as e:
                if e.errno == errno.ELOOP:
                    raise ValueError(f"Symlinks are not allowed in the path: {part}")
                raise
            os.close(fd)
            fd = sub

        try:
            result = os.open(parts[-1], flags | os.O_NOFOLLOW, mode, dir_fd=fd)
        except OSError as e:
            if e.errno == errno.ELOOP:
                raise ValueError("Symlinks are not allowed in the requested path")
            raise
    except NotImplementedError:
        # platform claims the attrs but not openat(): fall back like above
        os.close(fd)
        target = sandbox_path(base_path, decoded)
        return os.open(target, flags | getattr(os, "O_NOFOLLOW", 0), mode)
    except Exception:
        os.close(fd)
        raise

    os.close(fd)
    return result

# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara status:reviewed
# ROSE22: based on a report submitted to me by @wishieshard. i've vetted and tested this.
def sandbox_listdir(base_path: str, requested_path: str = "") -> list:
    """
    Symlink-proof os.listdir. Fixes TOCTOU vulns just like sandbox_open
    """
    sep = os.path.sep
    base_path = base_path.replace("\\", sep).replace("/", sep).rstrip(sep)

    path = requested_path.replace("\\", sep).replace("/", sep)

    # in case the caller included the sandbox folder name itself in the path
    base_name = os.path.basename(base_path)
    if path == base_name:
        path = ""
    elif path.startswith(base_name + sep):
        path = path[len(base_name) + 1:]

    # rejects traversal (..), null bytes, url-encoded variants
    decoded = validate_path_string(path)

    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        return os.listdir(sandbox_path(base_path, decoded))

    try:
        # opening the base follows symlinks on purpose (operator-configured root)
        fd = os.open(base_path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as e:
        raise ValueError(f"Invalid sandbox base: {base_path} ({e.strerror})")

    try:
        parts = [p for p in decoded.split(sep) if p not in ("", ".")] if decoded else []
        if parts:
            for part in parts[:-1]:
                # descend one real directory at a time (same trick as sandbox_open)
                try:
                    sub = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except OSError as e:
                    if e.errno == errno.ELOOP:
                        raise ValueError(f"Symlinks are not allowed in the path: {part}")
                    raise
                os.close(fd)
                fd = sub

            # final component must also be a real directory, not a symlink
            try:
                sub = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError as e:
                if e.errno == errno.ELOOP:
                    raise ValueError("Symlinks are not allowed in the requested path")
                raise
            os.close(fd)
            fd = sub

        entries = os.listdir(fd)
    except NotImplementedError:
        # platform claims the attrs but not openat(): fall back like above
        os.close(fd)
        return os.listdir(sandbox_path(base_path, decoded))
    except Exception:
        os.close(fd)
        raise

    os.close(fd)
    return entries
