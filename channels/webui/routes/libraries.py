"""
Content install API routes: stage a git repo for review, commit a staged
install, update git-installed modules/channels in place, uninstall, and
the installed-content listing that feeds the settings panels.
"""

import fastapi

import core

import channels.webui.utils as utils


def get_module_manager(channel):
    return channel.manager.module_manager


def register(app, channel):
    # ----------------------------
    # content installs (one repo per module/channel, packs for skills/themes)
    # ----------------------------
    @app.get("/api/libraries/status")
    async def libraries_status():
        """every content entry installed on disk: modules, channels, skills and themes"""
        mm = get_module_manager(channel)
        return utils.api_result({"modules": mm.list_installed()})

    @app.post("/api/libraries/stage")
    async def libraries_stage(request: fastapi.Request):
        """clones a repo into the staging area so its code can be reviewed before anything is installed"""
        data = await request.json()
        url = str(data.get("url") or "").strip()
        progress_key = str(data.get("progress_key") or "").strip() or None

        mm = get_module_manager(channel)
        token, info = await mm.stage_repo(url, branch=data.get("branch"), progress_key=progress_key)
        if token is None:
            return utils.api_result(info, success=False)

        return utils.api_result(dict(info, token=token))

    @app.post("/api/libraries/cancel")
    async def libraries_cancel(request: fastapi.Request):
        """terminate the in-flight clone started by /stage under this key"""
        data = await request.json()
        key = str(data.get("key") or "").strip()

        if not get_module_manager(channel).cancel_clone(key):
            return utils.api_result("that clone is no longer running", success=False)

        return utils.api_result(None)

    # live clone percentage for the stage request currently in flight
    @app.get("/api/libraries/progress")
    async def libraries_progress(request: fastapi.Request):
        """percentage of the clone running under this progress_key; data is null once it's done"""
        key = (request.query_params.get("key") or "").strip()
        return utils.api_result(get_module_manager(channel).clone_progress(key))

    # source viewer for the pre-install code review modal (reads the staging copy)
    @app.get("/api/libraries/source")
    async def libraries_source(request: fastapi.Request):
        """a staged repo's file list plus the contents of one file, with review hints"""
        token = (request.query_params.get("token") or "").strip()
        file_rel = (request.query_params.get("file") or "").strip()

        mm = get_module_manager(channel)
        review = mm.stage_review(token, file_rel)
        if review is None:
            return utils.api_result("staged repo not found - stage it again", success=False)

        return utils.api_result(review)

    @app.post("/api/libraries/install")
    async def libraries_install(request: fastapi.Request):
        """commits a reviewed staging folder and installs dependencies for module/channel entries"""
        data = await request.json()
        token = (data.get("token") or "").strip()

        mm = get_module_manager(channel)
        success, result, kind = mm.commit_stage(token)
        if not success:
            return utils.api_result(result.get("message", "install failed"), success=False)

        if kind in ("module", "channel"):
            pkg = "user_channels" if kind == "channel" else "user_modules"
            for name in result.get("installed", []):
                try:
                    await core.modules.install_module_deps(__import__(pkg), name, channel.manager)
                except Exception as e:
                    channel.log("libraries", f"dependency install failed for {name}: {core.detail_error(e)}")

        return utils.api_result({
            "kind": kind,
            "installed": result.get("installed", []),
            "skipped": result.get("skipped", []),
            "restart_required": kind in ("module", "channel"),
            "note": {
                "theme": "Pick it in Settings -> Appearance after a page reload.",
                "skill": "Run /skills reload to load it.",
            }.get(kind, ""),
        }, success=True)

    @app.post("/api/libraries/update")
    async def libraries_update(request: fastapi.Request):
        """git pulls an installed module/channel repo back up to date, in place"""
        data = await request.json()
        name = (data.get("name") or "").strip()

        mm = get_module_manager(channel)
        success, message, kind, changed = await mm.update_entry(name)
        if not success:
            return utils.api_result(message, success=False)

        if changed and kind in ("module", "channel"):
            pkg = "user_channels" if kind == "channel" else "user_modules"
            try:
                await core.modules.install_module_deps(__import__(pkg), name, channel.manager)
            except Exception as e:
                channel.log("libraries", f"dependency install failed for {name}: {core.detail_error(e)}")

        return utils.api_result({
            "kind": kind,
            "up_to_date": not changed,
            "restart_required": changed,
            "message": message,
        }, success=True)

    @app.post("/api/libraries/uninstall")
    async def libraries_uninstall(request: fastapi.Request):
        """Removes an installed user module/channel/skill/theme and cleans up dependencies nothing else needs anymore"""
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
