"""
Web pages like the main page, login and logout.
"""

import os
import time

import fastapi

import core

import channels.webui.utils as utils

def register(app, channel):
    # ------------------
    # Web pages
    # ------------------

    # main page
    @app.get("/")
    async def root(request: fastapi.Request):
        """The main page. This returns HTML, not JSON"""
        css_files = utils.get_recursive_assets(os.path.join(channel.assets_path, "css"), "css", skip=["code-themes"])
        alpine_stores = os.listdir(os.path.join(channel.assets_path, "js", "stores"))
        js_utils = os.listdir(os.path.join(channel.assets_path, "js", "utils"))
        js_files = utils.get_recursive_assets(os.path.join(channel.assets_path, "js"), "js", skip=["init.js", "stores", "libs", "utils", "fetch_gate.js"])

        return channel.templates.TemplateResponse(request, "index.html", {
            "version": channel.version,
            "config": channel.config,
            "css_files": css_files,
            "alpine_stores": alpine_stores,
            "js_utils": js_utils,
            "js_files": js_files,
            "ext_css_files": channel._ui_asset_urls("css"),
            "ext_js_files": channel._ui_asset_urls("js"),
            "login_enabled": channel.auth_enforced,
            "core_config": core.config
        })

    # ---- login
    # -- GET
    @app.get("/login")
    async def login_page(request: fastapi.Request):
        """Shows the login form."""
        if channel.auth_enforced:
            return channel.templates.TemplateResponse(request, "login.html", {
                "error": None,
                "ext_css_files": channel._ui_asset_urls("css"),
            })
        else:
            return fastapi.responses.RedirectResponse(url="/", status_code=303)

    # -- POST
    @app.post("/login")
    async def login_submit(request: fastapi.Request):
        """Handles login form submission."""

        # rate limit the request per IP
        client_ip = utils.trusted_client_ip(request)
        now = time.time()

        if client_ip in channel.login_attempts:
            # clean old attempts (older than 15 minutes)
            channel.login_attempts[client_ip] = [
                t for t in channel.login_attempts[client_ip] if now - t < 900
            ]

            if len(channel.login_attempts[client_ip]) >= 5:
                return fastapi.responses.JSONResponse(
                    status_code=429,
                    content={"error": "Too many attempts. Try again later."}
                )

        # and now check if the credentials match
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
        if await channel._verify_credentials(username, password):
            channel.login_attempts[client_ip] = []
            request.session["authenticated"] = True
            # -- AI GENERATED CODE (Qwen3-Coder Next) :: (11-06-2026) harness:openlumara
            # bind this session to the current credentials (see auth_middleware)
            request.session["creds_fp"] = channel.credentials_fingerprint

            return fastapi.responses.RedirectResponse(url="/", status_code=303)
        
        # on failure, record the login attempt
        if client_ip not in channel.login_attempts:
            channel.login_attempts[client_ip] = []
        channel.login_attempts[client_ip].append(now)
        
        return channel.templates.TemplateResponse(request, "login.html", {
            "error": "Invalid credentials",
            "ext_css_files": channel._ui_asset_urls("css"),
        })

    # ---- logout
    @app.get("/logout")
    async def logout(request: fastapi.Request):
        """Logs the user out by clearing their session."""
        request.session.pop("authenticated", None)
        request.session.pop("creds_fp", None)
        return fastapi.responses.RedirectResponse(url="/login", status_code=303)
