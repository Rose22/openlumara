# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-11-13) harness:openlumara status:reviewed
import os
import regex as re
import ast
import json
import time
import shutil
import asyncio
import uuid
import core

# staged installs (clones awaiting review/confirmation) live here, inside the data folder
STAGING_SUBFOLDER = "library_staging"

# abandoned staging folders (review opened but never confirmed) are swept after this
STAGING_TTL = 24 * 60 * 60

# theme families that are reserved and cannot be installed/uninstalled
RESERVED_THEMES = ("base",)

# static hints for the pre-install code review modal. staged code is only parsed with
# ast - nothing from a staged repo is ever imported or executed.
_REVIEW_IMPORT_FLAGS = {
    "subprocess": "imports subprocess - can run shell commands",
    "ctypes": "imports ctypes - can call native code",
    "socket": "imports socket - can open raw network connections",
}

def review_flags(source_code):
    """returns (flags, warnings) for staged module/channel source text:
    flags = places the user should look (dependencies, on_install, on_ready),
    warnings = anything that smells like shell/exec/network access."""
    flags = []
    warnings = []
    try:
        tree = ast.parse(source_code)
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

class ModuleManager:
    """
    installs and updates external content from git repos, staged first for review:

    - modules and channels: one git repo per entry (module.py / channel.py at the
      repo root). the repo is cloned into a staging folder, reviewed, then moved
      into user_modules/ or user_channels/: the clone IS the installed entry,
      its .git stays with it so updates pull in place.
    - skills and themes: pack repos. a skills pack has folders with SKILL.md at
      the repo root; a themes pack has <name>.json files there (with optional
      matching .css sidecars). their contents are copied into the skills and
      themes folders - no .git, no update tracking (re-install to refresh;
      names already installed are always skipped, never clobbered).
    """

    def __init__(self, manager=None):
        self.manager = manager
        # token of the most recent staged install (lets the slash command confirm
        # a staged repo without the webui's token handoff)
        self._last_stage = None

        # live progress of in-flight clones, keyed by the caller's progress_key
        # (the webui passes one so it can poll while the clone request is in
        # flight; slash-command staging leaves it unused)
        self._clone_progress = {}

        # the clone subprocesses themselves, under the same keys, so a clone
        # can be cancelled mid-download
        self._clone_procs = {}

    def log(self, msg):
        if self.manager:
            self.manager.log("modules", msg)
        else:
            core.log("modules", msg)

    def staging_root(self):
        """staging area for clones awaiting review/confirmation (inside the data folder)"""
        path = core.get_data_path(STAGING_SUBFOLDER)
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)

        return path

    def _sweep_staging(self):
        """remove staging folders left behind by abandoned reviews"""
        base = self.staging_root()
        cutoff = time.time() - STAGING_TTL
        for entry in os.listdir(base):
            path = os.path.join(base, entry)
            try:
                if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass

    def _staging_path(self, token):
        return core.sandbox_path(self.staging_root(), str(token))

    def repo_name(self, url):
        """derive a safe local folder name from a git url"""
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]

        name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
        if not name or name.strip(".") == "":
            # sanitize dot-only names (e.g. '..', '...')
            name = "repo"
        return name

    def _find_git(self):
        git = shutil.which("git")
        if not git:
            self.log("git executable not found - cannot install from repos")

        return git

    async def _run_git(self, git, args):
        """run a git command without blocking the event loop. returns (returncode, stdout, stderr)"""
        proc = await asyncio.create_subprocess_exec(
            git, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        return proc.returncode, stdout.decode("utf-8", "replace").strip(), stderr.decode("utf-8", "replace").strip()

    def clone_progress(self, key):
        """live {percent, text} of an in-flight clone, or None when not cloning"""
        if not key:
            return None
        return self._clone_progress.get(key)

    def _clone_line(self, key, line):
        """map one `git clone --progress` stderr line onto the progress record"""
        rec = self._clone_progress.get(key)
        if not rec:
            return

        match = re.search(r"Receiving objects:\s+(\d+)%", line)
        if match:
            rec["percent"] = 10 + int(match.group(1)) * 80 // 100
            rec["text"] = "receiving objects"
            return

        match = re.search(r"Resolving deltas:\s+(\d+)%", line)
        if match:
            rec["percent"] = 90 + int(match.group(1)) * 8 // 100
            rec["text"] = "resolving deltas"
            return

        if "Compressing objects" in line or "Enumerating objects" in line:
            rec["percent"] = max(rec["percent"], 5)
            rec["text"] = "asking the remote"
        elif "Checking out" in line:
            rec["percent"] = max(rec["percent"], 96)
            rec["text"] = "checking out files"

    async def _run_clone(self, git, args, progress_key=None):
        """
        git clone with --progress forced, parsing the percentages from stderr.
        while it runs, a {percent, text} record lives under progress_key so the
        webui can poll it while the request that started the clone is still in
        flight. returns (returncode, last stderr lines, cancelled).
        """
        if progress_key:
            self._clone_progress[progress_key] = {"percent": 2, "text": "connecting.."}

        try:
            proc = await asyncio.create_subprocess_exec(
                git, *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            if progress_key:
                self._clone_procs[progress_key] = proc

            buf = b""
            tail = []
            while True:
                chunk = await proc.stderr.read(256)
                if not chunk:
                    break

                # git paints its progress with carriage returns: split on both
                buf += chunk
                parts = re.split(rb"[\r\n]", buf)
                buf = parts.pop()
                for raw in parts:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    tail.append(line)
                    del tail[:-4]
                    if progress_key:
                        self._clone_line(progress_key, line)

            await proc.stdout.read()
            code = await proc.wait()
            rec = self._clone_progress.get(progress_key) if progress_key else None
            return code, "\n".join(tail), bool(rec and rec.get("cancelled"))
        finally:
            if progress_key:
                self._clone_progress.pop(progress_key, None)
                self._clone_procs.pop(progress_key, None)

    def cancel_clone(self, key):
        """terminate the clone running under this key. returns False when
        there is no such clone (anymore)."""
        if not key:
            return False
        proc = self._clone_procs.get(key)
        if not proc or proc.returncode is not None:
            return False

        rec = self._clone_progress.get(key)
        if rec:
            rec["cancelled"] = True
            rec["text"] = "cancelled"

        try:
            proc.terminate()
        except ProcessLookupError:
            pass

        self.log("clone cancelled")
        return True

    # ----------------------------
    # local (install destination) folders
    # ----------------------------
    def skills_root(self):
        """the folder the skills module reads skills from (core setting: skills -> folder, default 'skills')"""
        folder = core.config.get("skills", "folder", default="skills")
        if not isinstance(folder, str) or not folder.strip():
            folder = "skills"

        return core.get_path(folder.strip(), sandbox=False)

    def themes_root(self):
        """the folder user/installed themes live in (WebUI built-in themes are separate)"""
        return core.get_path("user_webui_themes", sandbox=False)

    def builtin_themes_root(self):
        """the WebUI's own bundled themes folder"""
        return core.get_path("channels/webui/themes", sandbox=False)

    def _local_target(self, kind, name):
        """
        the path an installed entry of this kind lives at (folders for folder kinds, the themes dir for themes).
        names are sandboxed into their destination folder: raises ValueError on anything
        that would land outside it.
        """
        if kind == "module":
            return core.sandbox_path(core.get_path("user_modules", sandbox=False), name)
        if kind == "channel":
            return core.sandbox_path(core.get_path("user_channels", sandbox=False), name)
        if kind == "skill":
            return core.sandbox_path(self.skills_root(), name)
        if kind == "theme":
            return core.sandbox_path(self.themes_root(), f"{name}.json")
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
    # staging: clone first, review, then commit
    # nothing from a repo touches the install folders (or gets executed)
    # until the user has had the code in front of them and confirmed.
    # ----------------------------
    def _repo_root_entries(self, folder):
        """(dirs, files) at a staged repo's root; hidden files and __pycache__ excluded"""
        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            return [], []

        dirs = [e for e in entries
                if os.path.isdir(os.path.join(folder, e)) and not e.startswith((".", "_")) and e != "__pycache__"]
        files = [e for e in entries
                 if os.path.isfile(os.path.join(folder, e)) and not e.startswith((".", "_"))]
        return dirs, files

    def _stage_skill_dirs(self, folder):
        """root folders of a staged repo that are skills (contain a SKILL.md)"""
        dirs, _ = self._repo_root_entries(folder)
        return [d for d in dirs if os.path.isfile(os.path.join(folder, d, "SKILL.md"))]

    def _stage_theme_names(self, folder):
        """root json files of a staged repo that are themes (reserved families excluded)"""
        _, files = self._repo_root_entries(folder)
        return [f[:-5] for f in files if f.endswith(".json") and f[:-5] not in RESERVED_THEMES]

    def _classify_staged(self, folder):
        """what kind of content repo is this, judging by its root layout"""
        if os.path.isfile(os.path.join(folder, "module.py")):
            return "module"
        if os.path.isfile(os.path.join(folder, "channel.py")):
            return "channel"
        if self._stage_skill_dirs(folder):
            return "skill"
        if self._stage_theme_names(folder):
            return "theme"
        return None

    async def stage_repo(self, url, branch=None, progress_key=None):
        """
        phase 1 of installing: clone the repo (full history) into the staging area
        and classify it. nothing is installed or executed yet.
        progress_key is optional: when given, the clone's live percentage is
        exposed through clone_progress() until it finishes.
        returns (token, info) on success, (None, error_message) on failure.
        info: {kind, name, url, entries, skipped} - entries are the things this repo
        would install, skipped the ones already present that will be left alone.
        """
        url = str(url or "").strip()
        if "://" not in url and not url.startswith("git@"):
            return None, "that doesn't look like a git url - expected http(s):// or git@..."

        git = self._find_git()
        if not git:
            return None, "git executable not found - cannot install from repos"

        self._sweep_staging()
        name = self.repo_name(url)
        token = name + "_" + uuid.uuid4().hex[:8]
        staging = self._staging_path(token)

        clone_args = ["clone", "--progress"]
        if branch and str(branch).strip():
            clone_args += ["--branch", str(branch).strip()]
        clone_args += [url, staging]

        code, err, cancelled = await self._run_clone(git, clone_args, progress_key or None)
        if cancelled:
            shutil.rmtree(staging, ignore_errors=True)
            return None, "clone cancelled"
        if code != 0:
            shutil.rmtree(staging, ignore_errors=True)
            return None, f"failed to clone '{url}': {err}"

        kind = self._classify_staged(staging)
        if not kind:
            shutil.rmtree(staging, ignore_errors=True)
            return None, ("this repo doesn't look like openlumara content: expected module.py or "
                          "channel.py at the root (module/channel repo), folders with SKILL.md "
                          "(skills pack) or .json theme files (themes pack)")

        if kind in ("module", "channel"):
            entries = [name]
            skipped = [name] if name in self._installed_names(kind) else []
        elif kind == "skill":
            entries = self._stage_skill_dirs(staging)
            skipped = [e for e in entries if os.path.isdir(core.sandbox_path(self.skills_root(), e))]
            entries = [e for e in entries if e not in skipped]
        else:
            entries = self._stage_theme_names(staging)
            installed_themes = self._installed_names("theme")
            skipped = [e for e in entries if e in installed_themes]
            entries = [e for e in entries if e not in skipped]

        # remember the context inside the staging folder so later calls need only the token
        meta = {"kind": kind, "name": name, "url": url, "entries": entries, "skipped": skipped}
        try:
            with open(os.path.join(staging, ".lumara_stage.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f)
        except OSError:
            shutil.rmtree(staging, ignore_errors=True)
            return None, "could not write staging metadata - disk full?"

        self._last_stage = token
        self.log(f"staged {kind} repo from {url}")
        return token, meta

    def _stage_meta(self, token):
        """the metadata a staged folder carries; None for unknown/unreadable tokens"""
        try:
            staging = self._staging_path(token)
        except ValueError:
            return None

        if not os.path.isdir(staging):
            return None

        try:
            with open(os.path.join(staging, ".lumara_stage.json"), "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            return None

        if not isinstance(meta, dict) or "kind" not in meta:
            return None
        return meta

    def stage_review(self, token, file_rel=""):
        """
        code-review payload for a staged repo: the full file list plus the contents
        of one file (its entry file by default). module/channel entry files get
        ast-based flags and warnings. returns None for unknown tokens.
        """
        meta = self._stage_meta(token)
        if not meta:
            return None

        staging = self._staging_path(token)
        REVIEW_TEXT_EXTS = (".py", ".json", ".md", ".txt", ".yaml", ".yml", ".css", ".js", ".html")

        files = []
        for dirpath, dirnames, filenames in os.walk(staging):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
            for fname in filenames:
                if fname.startswith(".") or not fname.endswith(REVIEW_TEXT_EXTS):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fname), staging)
                files.append(rel.replace(os.sep, "/"))
        files.sort()

        kind = meta["kind"]
        if kind == "module":
            entry = "module.py"
        elif kind == "channel":
            entry = "channel.py"
        else:
            first_skill = f"{meta['entries'][0]}/SKILL.md" if meta.get("entries") else ""
            entry = first_skill if first_skill in files else (files[0] if files else "")

        wanted = file_rel if file_rel in files else entry
        code = ""
        truncated = False
        if wanted:
            full = os.path.realpath(os.path.join(staging, wanted))
            if not full.startswith(os.path.realpath(staging) + os.sep) or not os.path.isfile(full):
                return None
            max_chars = 500_000
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    code = f.read(max_chars)
                truncated = len(code) >= max_chars
            except OSError:
                code = ""

        if kind in ("module", "channel"):
            entry_file = "module.py" if kind == "module" else "channel.py"
            try:
                with open(os.path.join(staging, entry_file), "r", encoding="utf-8", errors="replace") as f:
                    flags, warnings = review_flags(f.read())
            except OSError:
                flags, warnings = [], []
        else:
            flags, warnings = [], []

        result = dict(meta)
        result.update({"token": token, "file": wanted, "files": files,
                       "code": code, "truncated": truncated,
                       "flags": flags, "warnings": warnings})
        return result

    def _auto_enable(self, kind, name):
        """newly installed modules/channels switch themselves on right away
        (the manager still only loads them on the next boot, so a restart is
        what actually brings them to life)."""
        section = "user_modules" if kind == "module" else "user_channels"
        section_config = core.config.config[section]

        enabled = section_config.setdefault("enabled", [])
        if name not in enabled:
            enabled.append(name)
        if name in section_config.get("disabled", []):
            section_config["disabled"].remove(name)

        core.config.config.save()

    def commit_stage(self, token):
        """
        phase 2: put a reviewed staging folder into place.
        module/channel clones are MOVED in whole (history included, .git and all);
        skills/themes pack contents are COPIED out into their folders (names that
        already exist are skipped) and staging is always removed afterwards.
        returns (success, result, kind) with result = {message} on failure and
        {target, installed, skipped} on success.
        """
        meta = self._stage_meta(token)
        if not meta:
            return False, {"message": "staged repo not found - stage it again"}, None

        staging = self._staging_path(token)
        kind, name = meta["kind"], meta.get("name", "")

        try:
            if kind in ("module", "channel"):
                if name in self._installed_names(kind):
                    return False, {"message": f"'{name}' is already installed"}, kind

                target_root = dict(self._direct_kinds())[kind]
                target = core.sandbox_path(target_root, name)
                if os.path.exists(target):
                    return False, {"message": f"'{name}' is already installed at {target}"}, kind

                meta_file = os.path.join(staging, ".lumara_stage.json")
                if os.path.isfile(meta_file):
                    os.remove(meta_file)

                shutil.move(staging, target)
                self._auto_enable(kind, name)
                self.log(f"installed {kind} '{name}' from {meta['url']} (enabled)")
                return True, {"target": target, "installed": [name], "skipped": []}, kind

            installed, skipped = [], []
            if kind == "skill":
                root = self.skills_root()
                os.makedirs(root, exist_ok=True)
                for skill_name in self._stage_skill_dirs(staging):
                    dest = core.sandbox_path(root, skill_name)
                    if os.path.exists(dest):
                        skipped.append(skill_name)
                        continue
                    shutil.copytree(os.path.join(staging, skill_name), dest,
                                    ignore=shutil.ignore_patterns(".git", "__pycache__"))
                    installed.append(skill_name)
            else:
                root = self.themes_root()
                os.makedirs(root, exist_ok=True)
                for theme_name in self._stage_theme_names(staging):
                    json_dest = core.sandbox_path(root, f"{theme_name}.json")
                    css_dest = core.sandbox_path(root, f"{theme_name}.css")
                    if os.path.isfile(json_dest) or os.path.isfile(css_dest):
                        skipped.append(theme_name)
                        continue
                    shutil.copyfile(core.sandbox_path(staging, f"{theme_name}.json"), json_dest)
                    sidecar = os.path.join(staging, f"{theme_name}.css")
                    if os.path.isfile(sidecar):
                        shutil.copyfile(sidecar, css_dest)
                    installed.append(theme_name)
        except ValueError as e:
            return False, {"message": str(e)}, kind
        except Exception as e:
            return False, {"message": f"failed to install from '{meta['url']}': {core.detail_error(e)}"}, kind
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        note = f", skipped {len(skipped)} already installed" if skipped else ""
        self.log(f"installed {len(installed)} {kind}(s) from {meta['url']}{note}")
        return True, {"target": self.skills_root() if kind == "skill" else self.themes_root(),
                      "installed": installed, "skipped": skipped}, kind

    # ----------------------------
    # installed content: one git repo per module/channel,
    # packs' contents loose in skills/ and user_webui_themes/
    # ----------------------------
    def _direct_kinds(self):
        """(kind, destination folder) pairs for one-repo-per-module entries"""
        return (
            ("module", core.get_path("user_modules", sandbox=False)),
            ("channel", core.get_path("user_channels", sandbox=False)),
        )

    def _git_dir_of(self, name):
        """(folder, kind) if an installed module/channel folder is a git clone, else (None, None)"""
        for kind, root in self._direct_kinds():
            try:
                target = core.sandbox_path(root, name)
            except ValueError:
                return None, None

            if os.path.isdir(target) and os.path.isdir(os.path.join(target, ".git")):
                return target, kind

        return None, None

    async def update_entry(self, name):
        """
        bring an installed module/channel git folder up to date with `git pull --ff-only`.
        never merges on top of local edits: if the user changed something or the
        histories diverged, git refuses and that error is reported as-is.
        returns (success, message, kind, changed).
        """
        if not name or name.strip() == ".":
            return False, "that is not a valid module name", None, False

        target, kind = self._git_dir_of(name)
        if not target:
            return False, f"'{name}' is not installed as a git repo - install it from a repo url first", None, False

        git = self._find_git()
        if not git:
            return False, "git executable not found", kind, False

        _, before, _ = await self._run_git(git, ["-C", target, "rev-parse", "HEAD"])

        code, out, err = await self._run_git(git, ["-C", target, "pull", "--ff-only"])
        if code != 0:
            return False, f"failed to update '{name}': {err or out}", kind, False

        _, after, _ = await self._run_git(git, ["-C", target, "rev-parse", "HEAD"])
        if before and before == after:
            return True, f"'{name}' is already up to date", kind, False

        self.log(f"updated {kind} '{name}' to commit {after[:8]}")
        return True, f"updated '{name}' to commit {after[:8]}", kind, True

    def _remote_url(self, folder):
        """the origin url of a git clone, read straight from .git/config (no subprocess)"""
        try:
            with open(os.path.join(folder, ".git", "config"), "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            return ""

        in_origin = False
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("["):
                in_origin = line.replace(" ", "").lower() == '[remote"origin"]'
            elif in_origin and line.startswith("url"):
                _, _, url = line.partition("=")
                return url.strip()

        return ""

    def list_installed(self):
        """
        discover all installed content from disk:
        - user_modules/<name>/module.py and user_channels/<name>/channel.py:
          git clones carry their source url (and can be updated in place)
        - skills/<name>/SKILL.md and user_webui_themes/<name>.json: pack
          contents, loose files with no source to track
        """
        entries = []
        for kind, root in self._direct_kinds():
            if not os.path.isdir(root):
                continue

            entry_file = "module.py" if kind == "module" else "channel.py"
            for name in sorted(os.listdir(root)):
                folder = os.path.join(root, name)
                if name.startswith(("_", ".")) or not os.path.isdir(folder):
                    continue

                entry_path = os.path.join(folder, entry_file)
                if not os.path.isfile(entry_path):
                    continue

                entries.append({
                    "library": self._remote_url(folder),
                    "name": name,
                    "type": kind,
                    "doc": self._extract_module_docstring(entry_path),
                    "installed": True,
                    "git": os.path.isdir(os.path.join(folder, ".git")),
                })

        skills_root = self.skills_root()
        if os.path.isdir(skills_root):
            for name in sorted(os.listdir(skills_root)):
                if name.startswith(("_", ".")):
                    continue

                skill_file = os.path.join(skills_root, name, "SKILL.md")
                if os.path.isfile(skill_file):
                    entries.append({
                        "library": "",
                        "name": name,
                        "type": "skill",
                        "doc": self._extract_skill_doc(skill_file),
                        "installed": True,
                        "git": False,
                    })

        themes_root = self.themes_root()
        if os.path.isdir(themes_root):
            for fname in sorted(os.listdir(themes_root)):
                if fname.startswith(("_", ".")) or not fname.endswith(".json"):
                    continue

                name = fname[:-5]
                if name in RESERVED_THEMES:
                    continue

                entries.append({
                    "library": "",
                    "name": name,
                    "type": "theme",
                    "doc": "",
                    "installed": True,
                    "git": False,
                })

        return entries

    def uninstall(self, module_name):
        """
        remove an installed user module/channel/skill/theme. returns (success, message, kind).
        only user-installed copies are ever removed: bundled built-ins stay untouched.
        names are sandboxed: anything that would escape its destination folder is refused.
        """
        # '.' and empty resolve to the destination folder itself -> never a valid module name
        if not module_name or module_name.strip() == ".":
            return False, "that is not a valid module name", None

        try:
            for kind in ("module", "channel", "skill"):
                target = self._local_target(kind, module_name)
                if os.path.isdir(target):
                    shutil.rmtree(target)
                    self.log(f"removed {kind} '{module_name}' from {os.path.dirname(target)}")
                    return True, target, kind

            # themes: flat files in the user themes folder (never the WebUI's built-ins)
            themes_root = self.themes_root()
            theme_json = core.sandbox_path(themes_root, f"{module_name}.json")
            theme_css = core.sandbox_path(themes_root, f"{module_name}.css")
            if os.path.isfile(theme_json) or os.path.isfile(theme_css):
                for path in (theme_json, theme_css):
                    if os.path.isfile(path):
                        os.remove(path)
                self.log(f"removed theme '{module_name}' from {themes_root}")
                return True, theme_json, "theme"
        except ValueError as e:
            return False, str(e), None

        return False, f"'{module_name}' is not installed as a user module/channel/skill/theme", None
