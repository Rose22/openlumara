"""
System API routes: misc data, context size, logs and restart.
"""

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

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-11-23) harness:openlumara
    # slash-command autocomplete (ported from the old webui): the frontend
    # needs the configured prefix plus the full command list, so it can show
    # suggestions while the user types. not admin-only: any chat user can
    # run these commands anyway.
    @app.get("/api/command_prefix")
    async def get_command_prefix():
        return utils.api_result(core.config.get("core", "cmd_prefix"))

    @app.get("/api/commands")
    async def get_commands():
        return utils.api_result(core.commands.get_commands(channel.manager.modules))

    # -- POST
    @app.post("/api/system/restart")
    async def restart_server():
        await channel.manager.restart()
