"""
Module Library API routes (external module repos): status, sync, the
pre-install code-review source viewer, install/update/uninstall.
"""

import os
import ast

import fastapi

import core

import channels.webui.utils as utils

# static hints for the pre-install code review modal. the entry file is only parsed with ast.
# nothing from the library is imported or executed here.
_REVIEW_IMPORT_FLAGS = {
    "subprocess": "imports subprocess - can run shell commands",
    "ctypes": "imports ctypes - can call native code",
    "socket": "imports socket - can open raw network connections",
}

def library_review_flags(entry_path):
    """returns (flags, warnings) for a library module's entry file:
    flags = places the user should look (dependencies, on_install, on_ready),
    warnings = anything that smells like shell/exec/network access."""
    flags = []
    warnings = []
    try:
        with open(entry_path, "r", encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read())
    except Exception:
        return flags, warnings

    warned = set()
    def warn(text):
        if text not in warned:
            warned.add(text)
            warnings.append(text)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "dependencies":
                    flags.append({"name": "dependencies", "line": node.lineno, "kind": "info",
                                  "desc": "pip packages - auto-installed when you install this module"})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "on_install":
                flags.append({"name": "on_install", "line": node.lineno, "kind": "warn",
                              "desc": "runs code the moment this module is installed"})
            elif node.name == "on_ready":
                flags.append({"name": "on_ready", "line": node.lineno, "kind": "warn",
                              "desc": "runs code every time the server starts"})
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = str(alias.name).split(".")[0]
                if top in _REVIEW_IMPORT_FLAGS:
                    warn(_REVIEW_IMPORT_FLAGS[top])
        elif isinstance(node, ast.ImportFrom):
            top = str(node.module or "").split(".")[0]
            if top in _REVIEW_IMPORT_FLAGS:
                warn(_REVIEW_IMPORT_FLAGS[top])
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in ("eval", "exec", "compile", "__import__"):
                warn(f"calls {fn.id}() - can run dynamically generated code")
            elif isinstance(fn, ast.Attribute) and fn.attr in ("system", "popen", "execv", "execve", "spawnl", "spawnv"):
                warn(f"calls os.{fn.attr}() - can run shell commands")

    flags.sort(key=lambda flag: flag["line"])
    return flags, warnings

def get_module_manager(channel):
    return channel.manager.module_manager

def register(app, channel):
    # ----------------------------
    # Module Library (external module repos)
    # ----------------------------
    @app.get("/api/libraries/status")
    async def libraries_status():
        """Returns the configured library repos, the cloned libraries, and every installable module found in them"""
        mm = get_module_manager(channel)
        return utils.api_result({
            "repos": mm.list_repos(),
            "libraries": list(mm.list_libraries().keys()),
            "modules": mm.list_available(),
        })

    @app.post("/api/libraries/sync")
    async def libraries_sync():
        """Clones/updates every repo in core.module_libraries, then returns the refreshed module list"""
        mm = get_module_manager(channel)
        if not mm.list_repos():
            return utils.api_result("No module libraries configured. Add github repo urls under Core settings first.", success=False)

        synced = await mm.load()
        return utils.api_result({"synced": bool(synced), "modules": mm.list_available()}, success=True)

    # source viewer for the pre-install code review modal
    @app.get("/api/libraries/source")
    async def libraries_source(request: fastapi.Request):
        """returns a library module's source code plus review hints"""
        library = (request.query_params.get("library") or "").strip()
        name = (request.query_params.get("name") or "").strip()
        file_rel = (request.query_params.get("file") or "").strip()

        mm = get_module_manager(channel)
        lib_path = mm.list_libraries().get(library)
        if not lib_path:
            return utils.api_result("library not found", success=False)
        
        source, kind = mm._find_source(lib_path, name)
        if not source:
            return utils.api_result("module not found in this library", success=False)

        source_root = os.path.realpath(source)
        REVIEW_TEXT_EXTS = (".py", ".json", ".md", ".txt", ".yaml", ".yml", ".css", ".js", ".html")

        if kind == "theme":
            files = [f for f in (f"{name}.json", f"{name}.css")
                     if os.path.isfile(os.path.join(source_root, f))]
            entry = f"{name}.json"
        else:
            files = []
            for dirpath, dirnames, filenames in os.walk(source_root):
                dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
                for fname in filenames:
                    if fname.endswith(REVIEW_TEXT_EXTS):
                        rel = os.path.relpath(os.path.join(dirpath, fname), source_root)
                        files.append(rel.replace(os.sep, "/"))
            files.sort()
            entry = "module.py" if kind == "module" else "channel.py" if kind == "channel" else "SKILL.md"

        wanted = file_rel if file_rel in files else entry
        full = os.path.realpath(os.path.join(source_root, wanted))
        if not full.startswith(source_root + os.sep) or not os.path.isfile(full):
            return utils.api_result("file is not part of this module", success=False)

        max_chars = 500_000
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                code = f.read(max_chars)
        except Exception as e:
            return utils.api_result(core.detail_error(e), success=False)

        # shell/exec smell checks only apply to runnable python entries
        if kind in ("module", "channel"):
            flags, warnings = library_review_flags(os.path.join(source_root, entry))
        else:
            flags, warnings = [], []

        return utils.api_result({
            "library": library,
            "name": name,
            "kind": kind,
            "file": wanted,
            "files": files,
            "code": code,
            "truncated": len(code) >= max_chars,
            "flags": flags,
            "warnings": warnings
        })

    @app.post("/api/libraries/install")
    async def libraries_install(request: fastapi.Request):
        """Installs a module/channel/skill/theme from a library and installs its dependencies"""
        data = await request.json()
        library = (data.get("library") or "").strip()
        name = (data.get("name") or "").strip()

        mm = get_module_manager(channel)
        success, message, kind = mm.install(library, name)
        if not success:
            return utils.api_result(message, success=False)

        if kind in ("module", "channel"):
            pkg = "user_channels" if kind == "channel" else "user_modules"
            try:
                await core.modules.install_module_deps(__import__(pkg), name, channel.manager)
            except Exception as e:
                channel.log("libraries", f"dependency install failed for {name}: {core.detail_error(e)}")

        return utils.api_result({
            "kind": kind,
            "restart_required": kind in ("module", "channel"),
            "message": message,
            "note": {
                "theme": "Pick it in Settings -> Appearance after a page reload.",
                "skill": "Run /skills reload to load it.",
            }.get(kind, ""),
        }, success=True)

    @app.post("/api/libraries/update")
    async def libraries_update(request: fastapi.Request):
        """Re-syncs a library and overwrites an installed entry with the newest version from it"""
        data = await request.json()
        library = (data.get("library") or "").strip()
        name = (data.get("name") or "").strip()

        mm = get_module_manager(channel)
        success, message, kind = await mm.update(library, name)
        if not success:
            return utils.api_result(message, success=False)

        if kind in ("module", "channel"):
            pkg = "user_channels" if kind == "channel" else "user_modules"
            try:
                await core.modules.install_module_deps(__import__(pkg), name, channel.manager)
            except Exception as e:
                channel.log("libraries", f"dependency install failed for {name}: {core.detail_error(e)}")

        return utils.api_result({
            "kind": kind,
            "restart_required": kind in ("module", "channel"),
            "message": message,
            "note": {
                "theme": "Pick it in Settings -> Appearance after a page reload.",
                "skill": "Run /skills reload to load it.",
            }.get(kind, ""),
        }, success=True)

    @app.post("/api/libraries/uninstall")
    async def libraries_uninstall(request: fastapi.Request):
        # -- AI GENERATED CODE (glm-5.3-flash) :: 2026-10-31 12:03 harness:omp
        """Removes an installed user module/channel and its runtime dependencies"""
        data = await request.json()
        name = (data.get("name") or "").strip()

        mm = get_module_manager(channel)

        # run the on_uninstall hook and dependency cleanup while the files still exist
        for kind in ("user_modules", "user_channels"):
            try:
                await core.modules.uninstall_module_deps(__import__(kind), name, channel.manager)
            except Exception as e:
                channel.log("libraries", f"dependency cleanup failed for {name}: {core.detail_error(e)}")

        success, message, kind = mm.uninstall(name)
        if not success:
            return utils.api_result(message, success=False)

        return utils.api_result({
            "kind": kind,
            "restart_required": kind in ("module", "channel"),
            "message": message,
            "note": "Run /skills reload to apply." if kind == "skill" else "",
        }, success=True)
