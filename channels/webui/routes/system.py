"""
System API routes: misc data, context size, logs, restart and updates.
"""

import asyncio
import os
import sys

import core

import channels.webui.utils as utils

def register(app, channel):
    # ----------------------------
    # System.. stuff
    # ----------------------------
    # -- GET
    @app.get("/api/system/data")
    async def get_data():
        """returns any relevant data for the webUI to use"""
        data = {
            "max_context": core.config.get("api", "max_context")
        }

        return utils.api_result(data)

    @app.get("/api/system/context_size")
    async def get_context_size():
        """returns a detailed breakdown of the current context window usage"""
        try:
            size = await channel.context.get_size()
        except Exception as e:
            return utils.api_result(core.detail_error(e), success=False)

        threshold = core.config.get("model", "context_compression_threshold") or 0
        size["compression_threshold"] = round(float(threshold) * 100, 1)
        size["auto_compress"] = bool(core.config.get("model", "automatically_compress_context"))

        return utils.api_result(size)

    @app.get("/api/system/logs")
    async def get_logs():
        return utils.api_result(channel.logs)

    @app.get("/api/command_prefix")
    async def get_command_prefix():
        return utils.api_result(core.config.get("core", "cmd_prefix"))

    @app.get("/api/commands")
    async def get_commands():
        return utils.api_result(core.commands.get_commands(channel.manager.modules))

    # ----------------------------
    # ----------------------------
    async def _run_git(*args, timeout=90):
        """runs git in the repo root; returns (returncode, stdout, stderr)"""
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=os.getcwd(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return -1, "", "timed out"
        return proc.returncode, out.decode(errors="replace").strip(), err.decode(errors="replace").strip()

    @app.get("/api/system/update_check")
    async def update_check():
        """checks the git remote for updates: fetches, then compares HEAD to the upstream ref"""
        data = {
            "is_repo": False, "branch": None, "commit": None,
            "remote_commit": None, "behind": 0, "ahead": 0,
            "update_available": False, "note": None,
        }

        try:
            rc, _, _ = await _run_git("rev-parse", "--is-inside-work-tree")
        except FileNotFoundError:
            return utils.api_result("git is not installed on this system", success=False)

        if rc != 0:
            data["note"] = "This OpenLumara install is not a git repository, so it can't update itself."
            return utils.api_result(data)

        data["is_repo"] = True

        rc, _, _ = await _run_git("fetch", "origin")
        fetch_failed = rc != 0

        _, data["branch"], _ = await _run_git("rev-parse", "--abbrev-ref", "HEAD")
        _, data["commit"], _ = await _run_git("rev-parse", "--short", "HEAD")

        rc, _, _ = await _run_git("rev-parse", "--abbrev-ref", "@{u}")
        if rc != 0:
            data["note"] = "The current branch has no upstream configured."
            return utils.api_result(data)

        rc, remote, _ = await _run_git("rev-parse", "--short", "@{u}")
        if rc != 0:
            data["note"] = "Could not resolve the upstream ref."
            return utils.api_result(data)
        data["remote_commit"] = remote

        _, behind, _ = await _run_git("rev-list", "--count", "HEAD..@{u}")
        _, ahead, _ = await _run_git("rev-list", "--count", "@{u}..HEAD")
        data["behind"] = int(behind) if behind.isdigit() else 0
        data["ahead"] = int(ahead) if ahead.isdigit() else 0

        if fetch_failed:
            data["note"] = "git fetch failed: the comparison below may be stale."
        else:
            data["update_available"] = data["commit"] != data["remote_commit"]

        return utils.api_result(data)

    async def _check_entry_git(git, folder):
        """fetch + compare one cloned repo against its upstream; returns a status dict"""
        st = {
            "commit": None, "remote_commit": None, "behind": 0,
            "update_available": False, "note": None,
        }

        rc, _, _ = await channel.manager.module_manager._run_git(git, ["-C", folder, "fetch", "origin"])
        fetch_failed = rc != 0

        rc, head, _ = await channel.manager.module_manager._run_git(git, ["-C", folder, "rev-parse", "--short", "HEAD"])
        if rc != 0:
            st["note"] = "Could not read this repo's HEAD."
            return st
        st["commit"] = head

        rc, remote, _ = await channel.manager.module_manager._run_git(git, ["-C", folder, "rev-parse", "--short", "@{u}"])
        if rc != 0:
            st["note"] = "No upstream branch configured."
            return st
        st["remote_commit"] = remote

        _, behind, _ = await channel.manager.module_manager._run_git(git, ["-C", folder, "rev-list", "--count", "HEAD..@{u}"])
        st["behind"] = int(behind) if behind.isdigit() else 0

        if fetch_failed:
            st["note"] = "git fetch failed; comparison may be stale."
        else:
            st["update_available"] = st["commit"] != st["remote_commit"]

        return st

    @app.get("/api/system/entry_updates")
    async def entry_updates():
        """git-update status for every installed user module/channel repo, checked in parallel"""
        mm = channel.manager.module_manager
        git = mm._find_git()

        entries = []
        for item in mm.list_installed():
            if item["type"] not in ("module", "channel") or not item.get("git"):
                continue

            entry = {
                "name": item["name"],
                "type": item["type"],
                "library": item.get("library") or "",
            }

            if not git:
                entry.update({"update_available": False, "note": "git executable not found"})
                entries.append(entry)
                continue

            folder, _ = mm._git_dir_of(item["name"])
            if not folder:
                continue

            entry.update(await _check_entry_git(git, folder))
            entries.append(entry)

        return utils.api_result(entries)

    @app.post("/api/system/entry_update")
    async def entry_update(request):
        """git pulls one installed module/channel repo up to date, in place (same path as the library panels)"""
        data = await request.json()
        name = str(data.get("name") or "").strip()
        if not name:
            return utils.api_result("no entry name given", success=False)

        mm = channel.manager.module_manager
        try:
            success, message, kind, changed = await mm.update_entry(name)
        except Exception as e:
            return utils.api_result(core.detail_error(e), success=False)

        if not success:
            return utils.api_result(message, success=False)

        if changed and kind in ("module", "channel"):
            pkg = "user_channels" if kind == "channel" else "user_modules"
            try:
                await core.modules.install_module_deps(__import__(pkg), name, channel.manager)
            except Exception as e:
                channel.log("webui", f"dependency install failed for {name}: {core.detail_error(e)}")

        return utils.api_result({
            "kind": kind,
            "up_to_date": not changed,
            "restart_required": changed,
            "message": message,
        })

    update_lock = asyncio.Lock()

    @app.post("/api/system/update")
    async def trigger_update():
        """runs the update script (same as the updater module's /update command), then hard-restarts"""
        if update_lock.locked():
            return utils.api_result("An update is already running.", success=False)

        async with update_lock:
            if sys.platform == "win32":
                update_cmd = ["update.bat"]
            else:
                update_cmd = ["sh", "update.sh"]

            proc = await asyncio.create_subprocess_exec(
                *update_cmd,
                cwd=os.getcwd(),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )
            out, err = await proc.communicate()

            output = out.decode(errors="replace")
            if err:
                output += f"\nErrors:\n{err.decode(errors='replace')}"

            channel.log("webui", f"update finished (exit {proc.returncode}):\n{output}")
            await channel.manager.restart(hard=True)

        return utils.api_result(output)

    @app.post("/api/system/update_all")
    async def update_all():
        """pulls every installed module/channel repo, then OpenLumara itself (which restarts); restarts once if only entries changed"""
        if update_lock.locked():
            return utils.api_result("An update is already running.", success=False)

        core_res = await update_check()
        core_available = bool(core_res.get("success") and (core_res.get("data") or {}).get("update_available"))

        mm = channel.manager.module_manager
        updated, failed = [], []
        entry_changed = False
        for item in mm.list_installed():
            if item["type"] not in ("module", "channel") or not item.get("git"):
                continue

            name = item["name"]
            try:
                success, message, kind, changed = await mm.update_entry(name)
            except Exception as e:
                failed.append(f"{name}: {core.detail_error(e)}")
                continue

            if not success:
                failed.append(f"{name}: {message}")
                continue

            if changed:
                updated.append(name)
                entry_changed = True
                pkg = "user_channels" if kind == "channel" else "user_modules"
                try:
                    await core.modules.install_module_deps(__import__(pkg), name, channel.manager)
                except Exception as e:
                    channel.log("webui", f"dependency install failed for {name}: {core.detail_error(e)}")

        channel.log("webui", f"update all: updated {updated or 'nothing'}"
                             f"{'; failed: ' + '; '.join(failed) if failed else ''}"
                             f"; core {'updating' if core_available else 'up to date'}")

        if core_available:
            return await trigger_update()

        if entry_changed:
            async with update_lock:
                await channel.manager.restart(hard=True)

        return utils.api_result({"updated": updated, "failed": failed})

    # -- POST
    @app.post("/api/system/restart")
    async def restart_server():
        await channel.manager.restart()
