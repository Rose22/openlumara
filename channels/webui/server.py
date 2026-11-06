"""
FastAPI creator: middleware, sessions, asset mounts and the module extension API
"""
import os
import hashlib

import fastapi
import fastapi.staticfiles
import starlette.middleware.sessions

import core

import channels.webui.utils as utils
import channels.webui.routes.pages as pages_routes
import channels.webui.routes.chats as chats_routes
import channels.webui.routes.settings as settings_routes
import channels.webui.routes.libraries as libraries_routes
import channels.webui.routes.system as system_routes
import channels.webui.routes.themes as themes_routes
import channels.webui.routes.pwa as pwa_routes
import channels.webui.routes.ws as ws_routes

# endpoints that are blocked when enable_admin_settings is off.
ADMIN_ONLY_ENDPOINTS = [
    "/api/settings/load",
    "/api/settings/save",
    "/api/check_connection",
    "/api/models",
    "/api/model/set",
    "/api/reconnect",
    "/api/chat/prompt",
    "/api/system/logs",
    "/api/system/restart",
    "/api/system/context_size",
    
    "/api/libraries/status",
    "/api/libraries/sync",
    "/api/libraries/install",
    "/api/libraries/update",
    "/api/libraries/uninstall",
    "/api/libraries/source",
]

async def create_fastapi(channel):
    app = fastapi.FastAPI()

    # cross-origin isolation
    @app.middleware("http")
    async def coi_middleware(request: fastapi.Request, call_next):
        response = await call_next(request)
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
        return response

    # add authorization, cookies, and so on (middleware)
    @app.middleware("http")
    async def auth_middleware(request: fastapi.Request, call_next):
        # we use a custom header to protect against leaking data using simple GET requests coming from injected HTML
        # for example <img src="http://localhost:3005/api/settings/load">
        if request.url.path.startswith("/api") and request.headers.get("x-openlumara") != "1":
            return fastapi.responses.JSONResponse(
                status_code=403,
                content={"data": "Missing request header", "success": False}
            )

        if not channel.config.get("enable_admin_settings", True):
            if request.url.path in ADMIN_ONLY_ENDPOINTS:
                return fastapi.responses.JSONResponse(
                    status_code=403,
                    content={"data": "Admin settings are disabled", "success": False}
                )

        # Skip auth check if login isn't required. Note that login is only
        # ENFORCEABLE when both credentials are actually set (auth_enforced):
        # with empty credentials nobody can log in, so nobody gets locked out.
        if not channel.auth_enforced:
            return await call_next(request)
        
        # Skip auth for login page and assets
        if request.url.path in ["/login", "/logout"] or str(request.url.path).startswith("/assets/"):
            return await call_next(request)
        
        # Check session for API and other routes.
        # -- AI GENERATED CODE (Qwen3-Coder Next) :: (11-06-2026) harness:openlumara
        # A session only stays valid while its credential fingerprint matches
        # the configured username/password: changing credentials instantly
        # revokes every previously issued session, everywhere, no restart.
        if (
            not request.session.get("authenticated", False)
            or request.session.get("creds_fp") != channel.credentials_fingerprint
        ):
            # For API requests, return 401
            if str(request.url.path).startswith("/api"):
                return fastapi.responses.JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized"}
                )
            # For web routes, redirect to login
            if request.url.path != "/login":
                return fastapi.responses.RedirectResponse(url="/login", status_code=303)
        
        return await call_next(request)

    # SECOORITYYYYYY SOMEONE TUGGED ON MY HAAIIIIIRRR
    session_lifetime_days = channel.config.get("login_lifetime") or 30
    signing_key = channel.session_secret_value
    cookie_name = "session_" + hashlib.sha256(signing_key.encode()).hexdigest()[:12]
    channel.session_cookie_name = cookie_name
    app.add_middleware(
        starlette.middleware.sessions.SessionMiddleware,
        session_cookie=cookie_name,
        secret_key=signing_key,
        max_age=session_lifetime_days * 86400,
        # CSRF hardening
        same_site="strict"
    )

    # -- AI GENERATED CODE (Qwen3-Coder Next) :: (11-06-2026) harness:openlumara
    # Auto-Secure cookie flag: when the request arrived over https (uvicorn
    # rewrites the scheme from X-Forwarded-Proto for proxies listed in
    # forwarded_allow_ips), append Secure to any Set-Cookie on the way out.
    # Plain http localhost keeps working without any extra setting.
    # This middleware must be registered AFTER SessionMiddleware so that it
    # runs outside it and sees the session cookie being set.
    @app.middleware("http")
    async def secure_cookie_middleware(request: fastapi.Request, call_next):
        response = await call_next(request)
        if request.url.scheme == "https":
            cookies = response.headers.getlist("set-cookie")
            if cookies:
                updated = []
                for cookie in cookies:
                    attrs = [a.strip().lower() for a in cookie.split(";")]
                    if "secure" not in attrs:
                        cookie += "; Secure"
                    updated.append(cookie)
                del response.headers["set-cookie"]
                for cookie in updated:
                    response.headers.append("set-cookie", cookie)
        return response

    # serve asset files (formerly /static) using fastAPI's mount()
    app.mount("/assets", fastapi.staticfiles.StaticFiles(directory=channel.assets_path), name="assets")

    # serve module-provided assets (<module>/webui/assets/) under /ext-assets/.
    @app.get("/ext-assets/{module_name}/{asset_path:path}")
    async def ext_module_assets(module_name: str, asset_path: str):
        module = channel.manager.modules.get(module_name)
        if module is not None and channel._ui_extension_enabled(module):
            mounts = getattr(module, "asset_mounts", None) or {}
            norm = str(asset_path).replace("\\", "/").lstrip("/")
            for prefix, root in mounts.items():
                prefix = str(prefix).strip("/").lower()
                root = os.path.expanduser(str(root)) if root else ""
                if not prefix or not root or not os.path.isdir(root):
                    continue
                if norm == prefix or norm.startswith(prefix + "/"):
                    rel = norm[len(prefix):].lstrip("/")
                    root_real = os.path.realpath(root)
                    full_path = os.path.realpath(os.path.join(root, rel))
                    if not full_path.startswith(root_real + os.sep) or not os.path.isfile(full_path):
                        raise fastapi.HTTPException(status_code=404, detail="Asset not found")
                    return fastapi.responses.FileResponse(full_path)

        # default: <module>/webui/assets/
        module_dir = channel._ui_asset_dirs().get(module_name)
        if module_dir is None:
            raise fastapi.HTTPException(status_code=404, detail="Unknown module or no assets")

        module_root = os.path.realpath(module_dir)
        full_path = os.path.realpath(os.path.join(module_dir, asset_path))

        if not full_path.startswith(module_root + os.sep) or not os.path.isfile(full_path):
            raise fastapi.HTTPException(status_code=404, detail="Asset not found")

        return fastapi.responses.FileResponse(full_path)

    def _ui_api_lookup(module_name, route_path, method):
        """resolve /api/ext/<module>/<path> to a bound handler.
        returns (handler, None) on success or (None, reason) on miss."""
        module = channel.manager.modules.get(module_name)
        if module is None:
            return None, "unknown module"
        
        if not channel._ui_extension_enabled(module):
            return None, "webui extension disabled"
        
        wanted_path = str(route_path).strip("/").lower()
        route_exists = False
        for klass in type(module).__mro__:
            for attr_name, attr in vars(klass).items():
                meta = getattr(attr, "_ui_route", None)
                if not meta or meta["path"] != wanted_path:
                    continue
                route_exists = True
                if meta["method"] != method:
                    continue

                if meta.get("admin_only", True) and not channel.config.get("enable_admin_settings", True):
                    return None, "admin-only"
                return getattr(module, attr_name), None
            
        if not route_exists:
            return None, "route not found"
        return None, f"route only accepts {'GET' if method != 'GET' else 'POST'}"

    @app.api_route("/api/ext/{module_name}/{route_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def ext_api(module_name: str, route_path: str, request: fastapi.Request):
        """forwards to a module handler marked with the @webui.route decorator"""
        handler, reason = _ui_api_lookup(module_name, route_path, request.method)
        if handler is None:
            if reason == "admin-only":
                status = 403
            elif "accepts" in reason:
                status = 405
            else:
                status = 404
            return fastapi.responses.JSONResponse(utils.api_result(reason, success=False), status_code=status)

        await channel._set_as_active_channel()

        body = None
        if request.method != "GET":
            try:
                body = await request.json()
            except Exception:
                body = None

        try:
            outcome = await handler(body=body, query=dict(request.query_params))
        except Exception as e:
            channel.log("webui", f"ext api error {module_name}/{route_path}: {core.detail_error(e)}")
            return utils.api_result(core.detail_error(e), success=False)

        # unwrap the module-side self.result() convention into the api envelope
        if isinstance(outcome, dict) and "status" in outcome and "content" in outcome:
            return utils.api_result(outcome["content"], outcome["status"] == "success")
        return utils.api_result(outcome, True)

    # register every route group on the app
    pages_routes.register(app, channel)
    chats_routes.register(app, channel)
    settings_routes.register(app, channel)
    libraries_routes.register(app, channel)
    system_routes.register(app, channel)
    themes_routes.register(app, channel)
    pwa_routes.register(app, channel)
    ws_routes.register(app, channel)

    return app
