# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara status:reviewed
import os
import regex as re
import ast
import shutil
import asyncio
import core

# cloned library repos live here (inside the data folder)
LIBRARY_SUBFOLDER = "content_libraries"

# Every installable kind and how it must be laid out inside a library repo.
# A library repo must mirror openlumara's own folder layout:
#
#   modules/<name>/module.py    -> module   (installed into user_modules/)
#   channels/<name>/channel.py  -> channel  (installed into user_channels/)
#   skills/<name>/SKILL.md      -> skill    (installed into the skills folder)
#   themes/<name>.json          -> theme    (installed into user_webui_themes/;
#                                            an optional themes/<name>.css sidecar travels with it)
#
# entries are ONLY picked up from these folders: a module lying around at the
# repo root or in a random folder is ignored.
KINDS = {
    "module":  {"folder": "modules",  "entry": "module.py"},
    "channel": {"folder": "channels", "entry": "channel.py"},
    "skill":   {"folder": "skills",   "entry": "SKILL.md"},
    "theme":   {"folder": "themes",   "entry": "{name}.json"},
}

# theme families that are reserved and cannot be installed/uninstalled
RESERVED_THEMES = ("base",)

class ModuleManager:
    """
    manages external module libraries: git repos listed in the core setting
    `module_libraries`. repos are shallow-cloned into the data folder and can
    then be browsed (list_available) and installed:

    modules -> user_modules, channels -> user_channels, skills -> skills/,
    themes -> user_webui_themes/ (the folder the WebUI reads user themes from).
    """

    def __init__(self, manager=None):
        self.manager = manager

    def log(self, msg):
        if self.manager:
            self.manager.log("modules", msg)
        else:
            core.log("modules", msg)

    def library_folder(self):
        path = core.get_data_path(LIBRARY_SUBFOLDER)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

        return path
    def repo_name(self, url):
        """derive a safe local folder name from a git url"""
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]

        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        return name or "repo"

    def list_repos(self):
        repos = core.config.get("core", "module_libraries")
        return [r.strip() for r in repos if isinstance(r, str) and r.strip()]

    def _find_git(self):
        git = shutil.which("git")
        if not git:
            self.log("git executable not found - module libraries cannot be synced")

        return git

    async def _run_git(self, git, args):
        """run a git command without blocking the event loop. returns (returncode, stderr)"""
        proc = await asyncio.create_subprocess_exec(
            git, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        return proc.returncode, stderr.decode("utf-8", "replace").strip()

    async def sync_repo(self, url):
        """clone a library repo, or update it if already cloned. returns the local path, or None on failure."""
        git = self._find_git()
        if not git:
            return None

        url = url.strip()
        dest = os.path.join(self.library_folder(), self.repo_name(url))

        if os.path.isdir(os.path.join(dest, ".git")):
            code, err = await self._run_git(git, ["-C", dest, "fetch", "--depth", "1", "origin"])
            if code != 0:
                self.log(f"failed to fetch {url}: {err} - using existing copy")
                return dest

            code, err = await self._run_git(git, ["-C", dest, "reset", "--hard", "origin/HEAD"])
            if code != 0:
                # origin/HEAD can be missing on some clones; fall back to tracked branch
                code, err = await self._run_git(git, ["-C", dest, "reset", "--hard", "@{u}"])
                if code != 0:
                    self.log(f"failed to update {url}: {err} - using existing copy")

            return dest

        code, err = await self._run_git(git, ["clone", "--depth", "1", url, dest])
        if code != 0:
            self.log(f"failed to clone {url}: {err}")
            return None

        self.log(f"cloned module library {url}")
        return dest

    async def load(self):
        """sync all module libraries defined in core.module_libraries. returns True if at least one synced."""
        repos = self.list_repos()
        if not repos:
            return False

        synced = 0
        for repo in repos:
            if await self.sync_repo(repo):
                synced += 1

        return synced > 0

    def list_libraries(self):
        """list locally cloned libraries as {name: path}"""
        base = self.library_folder()
        libs = {}
        for entry in sorted(os.listdir(base)):
            path = os.path.join(base, entry)
            if os.path.isdir(path) and os.path.isdir(os.path.join(path, ".git")):
                libs[entry] = path

        return libs

    # ----------------------------
    # local (install destination) folders
    # ----------------------------
    def skills_root(self):
        """the folder the skills module reads skills from (core setting: skills -> folder, default 'skills')"""
        folder = core.config.get("skills", "folder", default="skills")
        if not isinstance(folder, str) or not folder.strip():
            folder = "skills"

        return core.get_home_path(folder.strip(), sandbox=False)

    def themes_root(self):
        """the folder user/installed themes live in (WebUI built-in themes are separate)"""
        return core.get_home_path("user_webui_themes", sandbox=False)

    def builtin_themes_root(self):
        """the WebUI's own bundled themes folder"""
        return core.get_path("channels/webui/themes", sandbox=False)

    def _local_target(self, kind, name):
        """the path an installed entry of this kind lives at (folders for folder kinds, the themes dir for themes)"""
        if kind == "module":
            return os.path.join(core.get_home_path("user_modules", sandbox=False), name)
        if kind == "channel":
            return os.path.join(core.get_home_path("user_channels", sandbox=False), name)
        if kind == "skill":
            return os.path.join(self.skills_root(), name)
        if kind == "theme":
            return os.path.join(self.themes_root(), f"{name}.json")
        return None

    def _installed_names(self, kind):
        """names already present locally for a kind (user-installed AND bundled built-ins)"""
        names = set()

        if kind in ("module", "channel"):
            packages = ("modules", "user_modules") if kind == "module" else ("channels", "user_channels")
            for pkg_name in packages:
                try:
                    names.update(core.modules.discover_module_names(__import__(pkg_name)))
                except ImportError:
                    pass

        elif kind == "skill":
            root = self.skills_root()
            if os.path.isdir(root):
                for entry in os.listdir(root):
                    if entry.startswith(("_", ".")):
                        continue
                    if os.path.isfile(os.path.join(root, entry, "SKILL.md")):
                        names.add(entry)

        elif kind == "theme":
            for root in (self.builtin_themes_root(), self.themes_root()):
                if not os.path.isdir(root):
                    continue
                for entry in os.listdir(root):
                    if entry.startswith(("_", ".")) or not entry.endswith(".json"):
                        continue
                    name = entry[:-5]
                    if name not in RESERVED_THEMES:
                        names.add(name)

        return names

    # ----------------------------
    # doc extraction (no imports of the scanned code)
    # ----------------------------
    def _extract_module_docstring(self, module_file):
        """grab the first line of the module class docstring without importing anything"""
        try:
            with open(module_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
        except Exception:
            return ""

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node)
                if doc:
                    return doc.strip().split("\n")[0]

        return ""

    def _extract_skill_doc(self, skill_file):
        """first line of a SKILL.md: the frontmatter description if present, else the first text line"""
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                lines = f.read().split("\n")
        except Exception:
            return ""

        if lines and lines[0].strip() == "---":
            for line in lines[1:40]:
                stripped = line.strip()
                if stripped == "---":
                    break
                if stripped.lower().startswith("description:"):
                    value = stripped[len("description:"):].strip().strip("\"'")
                    if value:
                        return value

        for line in lines:
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                return stripped

        return ""

    # ----------------------------
    # browsing
    # ----------------------------
    def _scan_library(self, lib_path, library_name, installed_cache, available):
        """collect installables from one cloned library, honoring the required folder layout"""
        for kind, spec in KINDS.items():
            scan_root = os.path.join(lib_path, spec["folder"])
            if not os.path.isdir(scan_root):
                continue

            if kind not in installed_cache:
                installed_cache[kind] = self._installed_names(kind)
            installed = installed_cache[kind]

            if kind == "theme":
                # themes are flat files: themes/<name>.json (+ optional themes/<name>.css)
                for entry in sorted(os.listdir(scan_root)):
                    if entry.startswith(("_", ".")) or not entry.endswith(".json"):
                        continue

                    name = entry[:-5]
                    if name in RESERVED_THEMES:
                        continue

                    available.append({
                        "library": library_name,
                        "name": name,
                        "type": kind,
                        "doc": "",
                        "installed": name in installed,
                    })
                continue

            entry_file = spec["entry"]
            for entry in sorted(os.listdir(scan_root)):
                mod_dir = os.path.join(scan_root, entry)

                if not os.path.isdir(mod_dir) or entry.startswith(("_", ".")):
                    continue

                entry_path = os.path.join(mod_dir, entry_file)
                if not os.path.isfile(entry_path):
                    continue

                if kind == "skill":
                    doc = self._extract_skill_doc(entry_path)
                else:
                    doc = self._extract_module_docstring(entry_path)

                available.append({
                    "library": library_name,
                    "name": entry,
                    "type": kind,
                    "doc": doc,
                    "installed": entry in installed,
                })

    def list_available(self):
        """
        scan cloned libraries for installable modules, channels, skills and themes.
        a library must use openlumara's folder layout: modules/, channels/, skills/
        and themes/; entries outside those folders are ignored.
        returns list of dicts: {library, name, type, doc, installed}
        """
        available = []
        installed_cache = {}
        for lib_name, lib_path in self.list_libraries().items():
            self._scan_library(lib_path, lib_name, installed_cache, available)

        return available

    # ----------------------------
    # locating / copying entries
    # ----------------------------
    def _find_source(self, lib_path, module_name):
        """
        locate an installable inside a cloned library, respecting the required layout.
        returns (source, kind); for folder kinds source is the entry's folder, for
        themes it is the library's themes folder (flat files). (None, None) if absent.
        """
        for kind, spec in KINDS.items():
            root = os.path.join(lib_path, spec["folder"])

            if kind == "theme":
                if module_name in RESERVED_THEMES:
                    continue
                candidate = os.path.join(root, f"{module_name}.json")
                if os.path.isfile(candidate):
                    return root, kind
            else:
                candidate = os.path.join(root, module_name, spec["entry"])
                if os.path.isfile(candidate):
                    return os.path.dirname(candidate), kind

        return None, None

    def _copy_entry(self, source, kind, name, overwrite):
        """copy one entry from a library clone into its local folder. returns the local path."""
        if kind == "theme":
            target_root = self.themes_root()
            if not os.path.exists(target_root):
                os.makedirs(target_root, exist_ok=True)

            shutil.copyfile(os.path.join(source, f"{name}.json"), os.path.join(target_root, f"{name}.json"))

            sidecar = os.path.join(source, f"{name}.css")
            if os.path.isfile(sidecar):
                shutil.copyfile(sidecar, os.path.join(target_root, f"{name}.css"))

            return os.path.join(target_root, f"{name}.json")

        target = self._local_target(kind, name)
        if os.path.exists(target) and not overwrite:
            raise FileExistsError(target)

        shutil.copytree(source, target, dirs_exist_ok=overwrite, ignore=shutil.ignore_patterns("__pycache__", ".git"))
        return target

    def install(self, library, module_name):
        """
        copy a module/channel/skill/theme from a cloned library into its local folder.
        returns (success, message, kind). dependency installation is left to the caller
        via core.modules.install_module_deps(user_modules, name, manager) for module/channel kinds.
        """
        libs = self.list_libraries()
        lib_path = libs.get(library)
        if not lib_path:
            return False, f"library '{library}' not found - sync it first", None

        source, kind = self._find_source(lib_path, module_name)
        if not source:
            return False, f"'{module_name}' not found in library '{library}'", None

        if module_name in self._installed_names(kind):
            where = self._local_target(kind, module_name)
            return False, f"'{module_name}' is already installed ({where})", kind

        try:
            target = self._copy_entry(source, kind, module_name, overwrite=False)
        except FileExistsError:
            return False, f"'{module_name}' is already installed at {self._local_target(kind, module_name)}", kind
        except Exception as e:
            return False, f"failed to install '{module_name}': {core.detail_error(e)}", kind

        self.log(f"installed {kind} '{module_name}' from library '{library}'")
        return True, target, kind

    async def update(self, library, module_name):
        """
        re-sync a library repo and overwrite an installed entry with the latest
        version from it. returns (success, message, kind).
        """
        url = None
        for repo in self.list_repos():
            if self.repo_name(repo) == library:
                url = repo
                break
        if not url:
            return False, f"library '{library}' is not a configured repo - cannot update", None

        dest = await self.sync_repo(url)
        if not dest:
            return False, f"failed to update library '{library}'", None

        source, kind = self._find_source(dest, module_name)
        if not source:
            return False, f"'{module_name}' not found in library '{library}' anymore", None

        target = self._local_target(kind, module_name)
        if not os.path.exists(target):
            return False, f"'{module_name}' is not installed locally - use install instead", kind

        try:
            result = self._copy_entry(source, kind, module_name, overwrite=True)
        except Exception as e:
            return False, f"failed to update '{module_name}': {core.detail_error(e)}", kind

        self.log(f"updated {kind} '{module_name}' from library '{library}'")
        return True, result, kind

    def uninstall(self, module_name):
        """
        remove an installed user module/channel/skill/theme. returns (success, message, kind).
        only user-installed copies are ever removed: bundled built-ins stay untouched.
        """
        for kind in ("module", "channel", "skill"):
            target = self._local_target(kind, module_name)
            if os.path.isdir(target):
                shutil.rmtree(target)
                self.log(f"removed {kind} '{module_name}' from {os.path.dirname(target)}")
                return True, target, kind

        # themes: flat files in the user themes folder (never the WebUI's built-ins)
        themes_root = self.themes_root()
        theme_json = os.path.join(themes_root, f"{module_name}.json")
        theme_css = os.path.join(themes_root, f"{module_name}.css")
        if os.path.isfile(theme_json) or os.path.isfile(theme_css):
            for path in (theme_json, theme_css):
                if os.path.isfile(path):
                    os.remove(path)
            self.log(f"removed theme '{module_name}' from {themes_root}")
            return True, theme_json, "theme"

        return False, f"'{module_name}' is not installed as a user module/channel/skill/theme", None
