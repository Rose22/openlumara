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
        structure = settings_structure.build_settings_structure(core.config.config, module_info, core_sections)

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

    @app.post("/api/model/set")
    async def model_set(request: fastapi.Request):
        """Switches the active model to the given name"""
        data = await request.json()
        name = (data.get("name") or "").strip()

        if not name:
            return utils.api_result("Model name cannot be empty", success=False)

        channel.manager.API.set_model(name)
        
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

        await channel.websocket_manager.push_context_update()

        return utils.api_result(success=True)
