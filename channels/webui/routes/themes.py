"""
Theme-related API routes

themes come from two places: the WebUI's bundled folder (built-ins),
and the configured user themes folder
"""

import os
import json

import fastapi

import core

import channels.webui.utils as utils

def themes_dirs(channel):
    return [
        core.get_home_path("user_webui_themes", sandbox=False),
        os.path.join(channel.path, "themes")
    ]

def register(app, channel):
    # ----------------------------
    # Theme API endpoints
    # ----------------------------
    @app.get("/api/themes")
    async def get_themes():
        """Returns a list of available theme families with their supported modes (dark/light)"""
        families = {}

        # built-ins first, user themes override same-name families afterwards
        for themes_dir in reversed(themes_dirs(channel)):
            if not os.path.isdir(themes_dir):
                continue
                
            for f in os.listdir(themes_dir):
                if f.endswith('.json') and f != 'base.json':
                    family_name = f[:-5]
                    filepath = os.path.join(themes_dir, f)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as fh:
                            theme_data = json.load(fh)
                            families[family_name] = {
                                "name": family_name,
                                "dark": "dark" in theme_data,
                                "light": "light" in theme_data
                            }
                    except Exception as e:
                        channel.log(channel.name, f"failed to read theme {filepath}: {e}")

        theme_list = sorted(families.values(), key=lambda x: x["name"])
        return theme_list

    @app.get("/api/themes/{family_name}")
    async def get_theme(family_name: str):
        """Returns full theme data for a specific family"""
        if family_name != os.path.basename(family_name) or ".." in family_name:
            return utils.api_result(f"Theme family '{family_name}' not found", success=False)

        filepath = None
        for themes_dir in themes_dirs(channel):
            candidate = os.path.join(themes_dir, f"{family_name}.json")
            if os.path.isfile(candidate):
                filepath = candidate
                break

        if not filepath:
            return utils.api_result(f"Theme family '{family_name}' not found", success=False)

        try:
            with open(filepath, 'r', encoding='utf-8') as fh:
                theme_data = json.load(fh)
            return theme_data
        except Exception as e:
            channel.log(channel.name, f"failed to load theme {filepath}: {e}")
            return utils.api_result(f"Failed to load theme: {str(e)}", success=False)

    # serve .css file sitting next to a theme JSON
    @app.get("/themes/{file_name}")
    async def theme_sidecar_css(file_name: str):
        if not file_name.endswith(".css"):
            raise fastapi.HTTPException(status_code=404, detail="Only CSS files are served")
            
        for themes_dir in themes_dirs(channel):
            themes_dir = os.path.realpath(themes_dir)
            full_path = os.path.realpath(os.path.join(themes_dir, file_name))
            if full_path.startswith(themes_dir + os.sep) and os.path.isfile(full_path):
                return fastapi.responses.FileResponse(full_path, media_type="text/css")
            
        raise fastapi.HTTPException(status_code=404, detail="Theme CSS not found")
