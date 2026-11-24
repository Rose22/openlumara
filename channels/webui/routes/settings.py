"""API routes that affect settings/config"""

import copy

import fastapi

import core

import channels.webui.utils as utils
import channels.webui.settings_structure as settings_structure

def register(app, channel):
    # --- Settings
    # -- GET
    @app.get("/api/settings/load")
    async def settings_load():
        """Returns the complete, render-ready settings structure (categories, field types, schemas and current values merged)"""
        module_info, core_sections = settings_structure.get_module_info()
        # the Your Skills tab only makes sense while the skills module is loaded
        skills_enabled = "skills" in channel.manager.modules
        structure = settings_structure.build_settings_structure(core.config.config, module_info, core_sections, skills_enabled=skills_enabled)

        return utils.api_result({
            "categories": structure,
            "show_unsafe_settings": bool(channel.config.get("show_unsafe_settings"))
        })

    @app.get("/api/check_connection")
    async def check_connection():
        """returns True if the backend is connected to the AI API, else False"""
        if channel.manager.API.connected:
            return utils.api_result(True, success=True)
        else:
            return utils.api_result("not connected", success=False)

    @app.get("/api/models")
    async def models_get():
        """Returns a list of all available AI models"""
        try:
            result = await channel.manager.API.list_models()
        except core.api.APIError as e:
            return utils.api_result(str(e), success=False)

        return utils.api_result(result)

    @app.post("/api/settings/field")
    async def settings_field_set(request: fastapi.Request):
        """Sets a single core config field by key path, e.g. {"path": ["model", "enable_thinking"], "value": false}.
        The path is validated against the core settings schema, so only real, known fields can be written."""
        data = await request.json()
        keys = data.get("path")
        value = data.get("value")

        if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k for k in keys):
            return utils.api_result("path must be a non-empty list of strings", success=False)

        node = core.config.core_settings_schema
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return utils.api_result(f"unknown setting: {'.'.join(keys)}", success=False)
            node = node[key]

        if not isinstance(node, dict) or "default" not in node:
            return utils.api_result(f"{'.'.join(keys)} is not a setting field", success=False)

        if node.get("unsafe") and not core.config.get("channels", "settings", "webui", "show_unsafe_settings", default=False):
            return utils.api_result(f"{'.'.join(keys)} is unsafe and unsafe settings are hidden", success=False)

        default = node["default"]
        if isinstance(default, bool) != isinstance(value, bool) or isinstance(default, (int, float)) and not isinstance(default, bool) and not isinstance(value, (int, float)):
            return utils.api_result(f"value type does not match {'.'.join(keys)}", success=False)

        core.config.ConfigManager(core.config.config, base_path=keys[:-1]).set(keys[-1], value)
        return utils.api_result({"path": keys, "value": value}, success=True)

    @app.post("/api/model/set")
    async def model_set(request: fastapi.Request):
        """Switches the active model to the given name"""
        data = await request.json()
        name = (data.get("name") or "").strip()

        if not name:
            return utils.api_result("Model name cannot be empty", success=False)

        channel.manager.API.set_model(name)

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
        channel.context.invalidate_size_cache()
        await channel.websocket_manager.push_context_update()
        return utils.api_result({"name": name}, success=True)

    # -- POST
    @app.post("/api/settings/save")
    async def settings_save(request: fastapi.Request):
        """Saves the (possibly edited) settings structure back to the backend. Accepts exactly what /api/settings/load returned, flattens it server-side and writes it to the config. Returns requires_restart/requires_reconnect if needed"""
        data = await request.json()

        changed_modules = list(data.get("changed_modules", []))

        # the frontend sends the category tree it got from settings/load,
        # with edited values, rebuild the raw config dict from it
        flattened = settings_structure.flatten_categories(data.get("categories", {}))
        new_webui = ((flattened.get("channels") or {}).get("settings") or {}).get("webui") or {}

        if new_webui.get("require_login"):
            blank = [f for f in ("username", "password") if not (new_webui.get(f) or "").strip()]
            if blank:
                if len(blank) == 2:
                    detail = "both username and password are still blank. Please fill in both fields"
                else:
                    detail = f"{blank[0]} is still blank. Please fill it in"
                return utils.api_result(
                    f"Logins are enabled but {detail}, or turn logins off.",
                    success=False,
                )

        new_mode = new_webui.get("network_mode", "local")
        if new_mode in ("internet", "custom"):
            login_ok = (
                bool(new_webui.get("require_login"))
                and bool((new_webui.get("username") or "").strip())
                and bool(new_webui.get("password"))
            )
            if not login_ok:
                return utils.api_result(
                    f"network mode '{new_mode}' exposes the WebUI beyond this machine, so a login is required. "
                    "Please enable 'Require login' and fill in a username and password, or switch the network mode back to local.",
                    success=False,
                )

        # snapshot the pre-save config so we can tell the frontend whether
        # the changes need a server restart or an API reconnect
        old_config = copy.deepcopy(dict(core.config.config))

        result = core.config.config.load(data=flattened)
        core.config.config.save()

        if not result:
            return utils.api_result(success=False)

        # require a restart if any modules/channels were toggled
        requires_restart = any(
            {k: (old_config.get(key) or {}).get(k) for k in ("enabled", "disabled")} !=
            {k: (flattened.get(key) or {}).get(k) for k in ("enabled", "disabled")}
            for key in settings_structure.MODULE_CATEGORY_KEYS
        )
        # and a reconnect if the API settings got changed
        requires_reconnect = (not requires_restart) and (
            old_config.get("api") != flattened.get("api")
        )

        # reload modules that had their settings changed
        if changed_modules:
            for module_name in changed_modules:
                try:
                    await channel.manager.reload_module(module_name)
                except Exception as e:
                    channel.log(channel.name, f"Error reloading module {module_name}: {core.detail_error(e)}")

        # reload all webui extensions
        channel.setup_ui_extensions()

        # if the webui's own settings changed, tell every connected client to refresh the page
        old_webui = (old_config.get("channels") or {}).get("settings" or {}).get("webui") or {}
        new_webui = (flattened.get("channels") or {}).get("settings" or {}).get("webui") or {}
        if old_webui != new_webui:
            await channel.websocket_manager.broadcast({"type": "refresh_page"})

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
        channel.context.invalidate_size_cache()
        await channel.websocket_manager.push_context_update()

        return utils.api_result({
            "requires_restart": requires_restart,
            "requires_reconnect": requires_reconnect,
        }, success=True)
    
    @app.post("/api/reconnect")
    async def reconnect():
        """Disconnects and then reconnects the API."""
        try:
            await channel.manager.API.reconnect()
        except core.api.APIError as e:
            return utils.api_result(str(e), success=False)

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
        channel.context.invalidate_size_cache()
        await channel.websocket_manager.push_context_update()

        return utils.api_result(success=True)
