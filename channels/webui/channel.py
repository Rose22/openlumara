"""
OpenLumara WebUI - manual rewrite

This is daunting, but i'm rewriting the entire WebUI from the ground up, manually, with minimal AI-generated code, due to high amount of unpredictable bugs in the previous version, and sheer difficulty of maintaining it

The plan is to use FastAPI for the backend again, but manually written, and alpine.js for the frontend, since it's nice and lightweight and not React.

Let's get this WebUI up to the standards of the rest of openlumara, since it's become basically the primary way everyone uses it..

~ Rose22
"""

# openlumara core
import core

# system
import os
import copy
import hashlib
import json
import asyncio
import importlib
import calendar
import datetime
import re
import time
import ast
import html as html_lib
import urllib.parse

# webui stuff
import fastapi, fastapi.templating, fastapi.staticfiles
import starlette, starlette.middleware.sessions
import uvicorn
import jinja2
import markupsafe
import base64

# security libraries
import secrets

# --------------------
# Channel class
# --------------------
class Webui(core.channel.Channel):
    """A full-featured, modern webUI for OpenLumara, providing you with a privacy-friendly option that doesn't depend on any external chat providers"""
    version = 2.0

    dependencies = [
        "fastapi",
        "starlette>=1.0.1",
        "itsdangerous",
        "websockets",
        "jinja2",
        "uvicorn",
        "python-multipart"
    ]

    # these settings are taken straight from the previous webUI,
    # and currently, many of the settings don't do anything yet
    # but i plan to support these of course
    settings = {
        "network_mode": {
            "type": "select",
            "options": {
                "local": "Allows only the device OpenLumara is running on to access the WebUI (sets hostname to `localhost`)",
                "internet": "Allows any device to access the WebUI (sets hostname to `0.0.0.0`)",
                "custom": "Use the custom hostname defined below"
            },
            "default": "local"
        },
        "custom_host": {
            "default": None,
            "depends": {"network_mode": "custom"}
        },
        "port": {
            "description": "What port to run the WebUI on. Set this to 80 to be able to access it like a normal website, and anything else to access it on that port (for example http://yourdomain.org:3000)",
            "default": 3000
        },
        "enable_chat_header": {
            "description": "Whether to enable the header at the top of a chat. Disabling this removes access to all graphical controls, and strips the interface down to a very basic chat. You might want this for public instances!",
            "default": True
        },
        "enable_title": {
            "default": True,
            "description": "Whether to show a fancy title in the header",
            "depends": "enable_chat_header"
        },
        "title": {
            "default": "OpenLumara",
            "depends": {"enable_chat_header": True, "enable_title": True}
        },
        "enable_model_switcher": {
            "description": "Whether to show a model dropdown in the header, so you can quickly switch models without opening the settings. Disabled on mobile due to lack of space.",
            "default": True,
            "depends": "enable_chat_header",
        },
        "enable_streaming_state_display": {
            "description": "Whether to show an indicator in the header that tells you what the AI is currently doing. Very useful! Disabled on mobile due to lack of space.",
            "default": False,
            "depends": "enable_chat_header",
        },
        "enable_chain_expansion": {
            "description": "Whether the processing chain can be expanded to view the AI's thoughts and intermediate steps. When disabled, it stays locked in its collapsed state (showing only 'Processing..'/'Thinking..' labels), so you always see that the AI is busy without being able to peek inside.",
            "default": True
        },
        "enable_context_pill": {
            "description": "Whether to show the context usage pill next to the message input.",
            "default": True
        },
        "enable_file_upload": {
            "description": "Whether to allow uploading files and pasting images into the chat",
            "default": True
        },
        "show_welcome_screen": {
            "description": "Whether to show the welcome panel in empty chats",
            "default": True
        },
        "enable_sidebar": {
            "description": "Whether to enable the sidebar at the left of the screen. Without it, you can\'t switch chats the graphical way, but you can still use commands like `/chat`!",
            "default": True
        },
        "show_unsafe_settings": {
            "description": "Whether to show unsafe settings. This setting has to be manually toggled via `/config` or by editing the config file, because if you want access to the unsafe features, you hopefully know what you're doing!",
            "default": False,
            "unsafe": True
        },
        "enable_admin_settings": {
            "description": "Whether to allow changing server settings from the webui. If you turn this off, it hides the settings button and blocks all other ways the settings could be changed, including commands. So if you turn this off, *the only way you can turn it back on is by editing the config file*. Be careful!",
            "default": True
        },
        "require_login": {
            "description": "Whether to protect the WebUI with a username and password. **Highly recommended if your webui is exposed to the internet!!**",
            "default": False
        },
        "username": {
            "default": "admin",
            "depends": "require_login"
        },
        "password": {
            "default": "admin",
            "depends": "require_login"
        },
        "login_lifetime": {
            "description": "How many days to stay logged in for",
            "default": 30,
            "depends": "require_login"
        },
        "extra_allowed_origins": {
            "default": [],
            "description": "Extra origins allowed to open WebSockets to this webui. You NEED this when OpenLumara sits behind a reverse proxy or HTTPS tunnel (e.g. https://mybox:8443 fronting 127.0.0.1:3000): the browser sends that public URL as the Origin, which no longer matches the bound host/port, and every websocket gets rejected. Scheme-less entries like \"crystal-ai:8006\" match that host+port over any scheme. Exact matches only - no wildcards."
        }
    }

    def _origin_allowed(self, origin: str, host_header: str = "") -> bool:
        """-- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        True when an Origin header refers back to this same webui instance.
        localhost and 127.0.0.1 are treated as the same host. Used to reject
        cross-origin WebSocket handshakes, which is the only real defense
        against a malicious web page driving a localhost instance (WebSocket
        frames are not covered by SameSite cookies).

        host_header enables the wildcard-bind fix below; callers should pass
        the request's Host header when they have one."""
        try:
            parsed = urllib.parse.urlsplit(origin)
        except ValueError:
            return False
        origin_host = (parsed.hostname or "").lower()
        # strip the scheme-default port so http://host:80 matches host
        origin_port = parsed.port
        if origin_port and (
            (parsed.scheme == "http" and origin_port == 80)
            or (parsed.scheme == "https" and origin_port == 443)
        ):
            origin_port = None

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        # explicit allow list (extra_allowed_origins): the public origin of a
        # reverse proxy / tunnel will never match the bound host:port, so the
        # setting is the only way a proxied webui can pass this check.
        # entries with a scheme must match it exactly; scheme-less entries
        # match host+port over either scheme. exact matches only.
        for spec in (self.config.get("extra_allowed_origins") or []):
            if not isinstance(spec, str) or not spec.strip():
                continue
            spec = spec.strip().lower().rstrip("/")
            has_scheme = "://" in spec
            parsed_spec = urllib.parse.urlsplit(spec if has_scheme else "//" + spec)
            spec_host = (parsed_spec.hostname or "").lower()
            if spec_host == "localhost":
                spec_host = "127.0.0.1"
            if spec_host != origin_host:
                continue
            spec_port = parsed_spec.port
            if spec_port and (
                (parsed_spec.scheme == "http" and spec_port == 80)
                or (parsed_spec.scheme == "https" and spec_port == 443)
            ):
                spec_port = None
            if spec_port != origin_port:
                continue
            if has_scheme and parsed_spec.scheme != parsed.scheme:
                continue
            return True

        if self.host in ("0.0.0.0", "::"):
            if not host_header:
                return origin_port in (None, self.port)
            try:
                parsed_hdr = urllib.parse.urlsplit("//" + host_header.strip().lower())
            except ValueError:
                return False
            
            hdr_host = (parsed_hdr.hostname or "").lower()
            if hdr_host == "localhost":
                hdr_host = "127.0.0.1"
            return hdr_host == origin_host and parsed_hdr.port == origin_port

        server_host = (self.host or "").lower()
        if server_host == "localhost":
            server_host = "127.0.0.1"
        if origin_host == "localhost":
            origin_host = "127.0.0.1"
        if origin_host != server_host:
            return False
        return origin_port in (None, self.port)

    async def _verify_credentials(self, username: str, password: str) -> bool:
        """Verify credentials securely using timing-safe comparison."""
        correct_username = self.config.get("username")
        correct_password = self.config.get("password")

        if not secrets.compare_digest(username, correct_username):
            # Dummy comparison to prevent timing attacks
            secrets.compare_digest(password, correct_password)
            return False
        return secrets.compare_digest(password, correct_password)

    # -- AI GENERATED CODE (qwen/Qwen3.8-Flash-Next-Q4) :: 2026-10-03
    # webui extension system: modules ship UI by placing templates in
    # <module>/webui/templates/. the jinja loader becomes a ChoiceLoader where the
    # core webui templates always win, plus a PrefixLoader exposing each enabled
    # module's templates under "<module_name>/..". core templates call
    # `extension_slot("name")` for named regions, and the modal area auto-includes
    # everything under each module's templates/modals/ via `extension_modals()`.
    def _ui_extension_enabled(self, module):
        """special gate for optional module webui extensions.

        If a module declares enable_webui_extension, its configured value controls
        all webui extension loading/injection for that module: True proceeds,
        False disables templates, assets and /api/ext routes. If the config value
        is not persisted yet, fall back to the declared default. Modules without
        the setting keep legacy behavior.
        -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13)
        """
        enabled = module.config.get("enable_webui_extension")
        if enabled is None:
            setting = (getattr(module, "settings", None) or {}).get("enable_webui_extension", {})
            enabled = setting.get("default") if isinstance(setting, dict) else None
        if enabled is None:
            return True
        if isinstance(enabled, str):
            return enabled.strip().lower() not in ("false", "0", "no", "off", "")
        return bool(enabled)

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-14)
    def _ext_module_config(self, module):
        """settings of a module for use inside its shipped templates"""
        values = {}
        for name in (getattr(module, "settings", None) or {}):
            values[name] = module.config.get(name)
        return values

    def _ext_template_vars(self, template_name):
        """jinja vars for a prefixed extension template ('<module>/..'):
        the owning module's settings, exposed as `module_config`.
        an empty dict for templates."""
        module = self.manager.modules.get(template_name.split("/", 1)[0])
        return {"module_config": self._ext_module_config(module) if module else {}}

    def _ui_extension_dirs(self):
        """collect webui template folders from all enabled modules, as {module_name: path}"""
        dirs = {}
        for package_name in ("modules", "user_modules"):
            try:
                package = importlib.import_module(package_name)
            except ImportError:
                continue

            for module_name in core.config.get(package_name, "enabled", []):
                module = self.manager.modules.get(module_name)
                if module is None or not self._ui_extension_enabled(module):
                    continue

                for sub_path in getattr(package, "__path__", []):
                    candidate = os.path.join(sub_path, module_name, "webui", "templates")
                    if os.path.isdir(candidate):
                        dirs[module_name] = candidate
        return dirs

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-03)
    # phase 3 of the extension system: modules can ship static assets
    # (css/js/...) in <module>/webui/assets/, served under /ext-assets/.
    def _ui_asset_dirs(self):
        """collect webui asset folders from all enabled modules, as {module_name: path}"""
        dirs = {}
        for package_name in ("modules", "user_modules"):
            try:
                package = importlib.import_module(package_name)
            except ImportError:
                continue

            for module_name in core.config.get(package_name, "enabled", []):
                module = self.manager.modules.get(module_name)
                if module is None or not self._ui_extension_enabled(module):
                    continue

                for sub_path in getattr(package, "__path__", []):
                    candidate = os.path.join(sub_path, module_name, "webui", "assets")
                    if os.path.isdir(candidate):
                        dirs[module_name] = candidate
        return dirs

    def _ui_asset_urls(self, ext):
        """urls for css/js files shipped by enabled modules, as
        /ext-assets/<module>/<relpath> entries meant to be appended to
        the css_files/js_files template variables."""
        urls = []
        for module_name, assets_dir in sorted(self._ui_asset_dirs().items()):
            ext_dir = os.path.join(assets_dir, ext)
            if not os.path.isdir(ext_dir):
                continue
            for root, _sub, files in os.walk(ext_dir):
                for filename in sorted(files):
                    if not filename.endswith(f".{ext}"):
                        continue
                    rel = os.path.relpath(os.path.join(root, filename), assets_dir).replace(os.sep, "/")
                    urls.append(f"/ext-assets/{module_name}/{rel}")
        return urls

    def setup_ui_extensions(self):
        """(re)build the jinja loader so module-provided templates become available.
        called at startup and after settings saves (module reloads)."""
        dirs = self._ui_extension_dirs()

        loaders = [jinja2.FileSystemLoader(self.template_path)]
        if dirs:
            loaders.append(jinja2.PrefixLoader(
                {name: jinja2.FileSystemLoader(path) for name, path in dirs.items()},
                delimiter="/"
            ))

        env = self.templates.env
        env.loader = jinja2.ChoiceLoader(loaders)

        def _extension_templates(relative_path):
            """all module templates that mirror the given template path, sorted by module name.
            each is compiled once here, so a broken extension is skipped and logged
            instead of breaking the page."""
            found = []
            for module_name in sorted(dirs):
                template_name = f"{module_name}/{relative_path}"
                if not os.path.isfile(os.path.join(dirs[module_name], relative_path)):
                    continue
                try:
                    env.get_template(template_name)
                except Exception as e:
                    self.log("webui", f"skipping UI extension '{template_name}': {core.detail_error(e)}")
                    continue
                found.append(template_name)
            return found

        def extension_modals():
            """auto-discovers modal templates: every .html file directly in
            <module>/webui/templates/modals/ is included by the core modal area.
            index.html inside modals/ is skipped (legacy manual-hook file)."""
            found = []
            for module_name in sorted(dirs):
                modal_root = os.path.join(dirs[module_name], "modals")
                if not os.path.isdir(modal_root):
                    continue
                module = self.manager.modules.get(module_name)
                module_config = self._ext_module_config(module) if module else {}
                for filename in sorted(os.listdir(modal_root)):
                    filepath = os.path.join(modal_root, filename)
                    if not os.path.isfile(filepath):
                        continue
                    if not filename.endswith(".html") or filename == "index.html":
                        continue
                    rel = os.path.relpath(filepath, dirs[module_name]).replace(os.sep, "/")
                    template_name = f"{module_name}/{rel}"
                    try:
                        env.get_template(template_name)
                    except Exception as e:
                        self.log("webui", f"skipping UI modal '{template_name}': {core.detail_error(e)}")
                        continue
                    found.append({"template": template_name, "config": module_config})
            return found

        def extension_sidebars():
            """
            auto-discovers sidebar tab panels: every .html file directly in
            <module>/webui/templates/sidebars/ renders as its own tab in the
            core sidebar. a same-named .svg next to it becomes the tab icon
            (inlined raw, so it inherits currentColor and themes for free).
            the tab label is derived from the filename (underscores/hyphens
            become spaces, title-cased) - zero config, just drop files in.

			templates can access module config using var `module_config`
            """
            found = []
            for module_name in sorted(dirs):
                sidebar_root = os.path.join(dirs[module_name], "sidebars")
                if not os.path.isdir(sidebar_root):
                    continue
                module = self.manager.modules.get(module_name)
                module_config = self._ext_module_config(module) if module else {}
                for filename in sorted(os.listdir(sidebar_root)):
                    filepath = os.path.join(sidebar_root, filename)
                    if not os.path.isfile(filepath):
                        continue
                    if not filename.endswith(".html"):
                        continue
                    name = filename[:-5]
                    template_name = f"{module_name}/sidebars/{filename}"
                    try:
                        env.get_template(template_name)
                    except Exception as e:
                        self.log("webui", f"skipping UI sidebar '{template_name}': {core.detail_error(e)}")
                        continue
                    icon = markupsafe.Markup("")
                    icon_path = os.path.join(sidebar_root, f"{name}.svg")
                    if os.path.isfile(icon_path):
                        try:
                            with open(icon_path, encoding="utf-8") as f:
                                icon = markupsafe.Markup(f.read())
                        except Exception as e:
                            self.log("webui", f"skipping sidebar icon '{icon_path}': {core.detail_error(e)}")
                    label = name.replace("_", " ").replace("-", " ").title()
                    found.append({
                        "module": module_name,
                        "name": name,
                        "label": label,
                        "template": template_name,
                        "icon": icon,
                        "config": module_config,
                    })
            return found

        @jinja2.pass_context
        def extension_slot(ctx, slot_name, relative_path=None):
            """renders the macro `slot_name` from every module template mirroring the
            calling template's path (or the explicit one). lets a single module file
            fill multiple named regions of a core component:
            {% macro left() %}...{% endmacro %} -> {{ extension_slot("left") }}.
            the caller's context is passed to a macro as the `ctx` kwarg only if the
            macro declares it, so slots needing scoped data (turn/message in chat
            templates) declare `{% macro below_message(ctx) %}` and read
            `ctx['message']`. zero-arg macros are called plain, untouched.
            modules that don't define the slot are silently skipped.

            the owning module's settings are injected as `module_config`, so a
            slot template can gate its own markup with plain jinja:
            `{% if module_config.get("show_welcome_card", true) %}`.
            """
            relative_path = relative_path or ctx.name
            if not relative_path:
                return markupsafe.Markup("")
            parts = []
            for template_name in _extension_templates(relative_path):
                try:
                    template_vars = self._ext_template_vars(template_name)
                    macro = getattr(env.get_template(template_name).make_module(vars=template_vars), slot_name, None)
                    if macro is not None:
                        if "ctx" in getattr(macro, "arguments", ()):
                            parts.append(str(macro(ctx=ctx.get_all())))
                        else:
                            parts.append(str(macro()))
                except Exception as e:
                    self.log("webui", f"skipping extension slot '{slot_name}' in '{template_name}': {core.detail_error(e)}")
                    continue
            return markupsafe.Markup("\n".join(parts))

        env.globals["extension_modals"] = extension_modals
        env.globals["extension_sidebars"] = extension_sidebars
        env.globals["extension_slot"] = extension_slot
        env.cache.clear()

    async def on_ready(self):
        # paths
        self.path = core.get_path(os.path.join("channels", "webui"))
        self.template_path = os.path.join(self.path, "templates")
        self.assets_path = os.path.join(self.path, "assets")

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        self.session_secret_value = ""
        secret_file = core.get_data_path("webui_session_secret")
        try:
            if os.path.exists(secret_file):
                with open(secret_file, "r", encoding="utf-8") as f:
                    self.session_secret_value = f.read().strip()
        except OSError:
            self.session_secret_value = ""
        if not self.session_secret_value:
            legacy = str(self.config.get("session_secret") or "").strip()
            self.session_secret_value = legacy or secrets.token_urlsafe(48)
            try:
                fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(self.session_secret_value)
                self.log("webui", "session signing key stored in webui_session_secret (data folder, 0600)"
                         + (" - migrated from the old config value" if legacy else ""))
            except OSError:
                self.log("webui", "WARNING: could not persist the session key; all sessions will reset on restart")
        # the config must not keep a signing key, even an ignored one: drop
        # any leftover so it stops riding along in config dumps and saves.
        try:
            if self.config.get("session_secret"):
                self.config.pop("session_secret")
        except (AttributeError, TypeError):
            pass

        # fastapi-specific instances
        self.templates = fastapi.templating.Jinja2Templates(self.template_path)
        self.setup_ui_extensions()

        # aaand create it
        self.app = await create_fastapi(self)

        # determine network mode
        network_mode = self.config.get("network_mode")
        match network_mode:
            case "local":
                self.host = "127.0.0.1"
            case "internet":
                self.host = "0.0.0.0"
            case "custom":
                self.host = self.config.get("custom_host")
            case _:
                self.host = "127.0.0.1"

        self.port = self.config.get("port")
        self.url = f"http://{self.host}:{self.port}"

        # stores logs from channel.log()
        self.logs = []

        self.username = self.config.get("username", "admin")
        self.password = self.config.get("password", "admin")
        self.login_attempts = {}

        # initialize the websocket manager
        self.websocket_manager = WebSocketManager(self)

    async def run(self):
        self.log("webui", f"Starting WebUI on {self.url}")

        # serve the app using uvicorn
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,

            # this makes it work in situations where https and http content are served mixed
            proxy_headers=True,
            forwarded_allow_ips = "127.0.0.1",

            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
            # keep the protocol-level ping (defends against silently-dead TCP:
            # sleep/resume, wifi switches, tunnels) but widen the pong deadline
            # from the 20s default: on a box busy serving local models the
            # event loop can answer a pong late WITHOUT anything being wrong,
            # and uvicorn would tear healthy websockets down as code 1006.
            ws_ping_interval=20,
            ws_ping_timeout=90,

            # only log critical http errors
            log_level="error"
        )
        self.server = uvicorn.Server(config)

        await self.server.serve()

    async def on_push(self, message):
        await self.websocket_manager.broadcast({
            "type": "push",
            "content": message
        })

    async def on_stream(self, stream):
        user_message_confirmed = False
        index = getattr(self, "_ws_stream_index", -1)

        async for partial in self.turncollector.group_stream(stream):
            payload = serialize_for_json(partial)

            if partial.get("type") == "token":
                token = partial.get("content")
                token_type = token.get("type")
                match token_type:
                    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
                    # the backend derives the stream state from the token
                    # stream itself and broadcasts stream_state transitions.
                    # the frontend used to run this state machine off raw
                    # tokens; now it only mirrors what we announce.
                    case "user_message":
                        await self.websocket_manager.set_stream_state("message_sending")
                        try:
                            user_msg_payload = token.copy()
                            user_msg_payload['index'] = index
                            await self.websocket_manager.broadcast({
                                "type": "user_message_added",
                                "message": user_msg_payload,
                            })
                        except Exception as e:
                            self.log(self.name, f"error sending user message: {core.detail_error(e)}")
                            return
                    case "error":
                        # an error ends the turn: go straight back to idle
                        await self.websocket_manager.set_stream_state("idle")

                        await self.websocket_manager.broadcast({
                            "type": "user_message_confirmed",
                            "index": index
                        })

                        # pass the raw token on so this case can be handled seperately
                        await self.websocket_manager.broadcast({
                            "type": "token",
                            "content": token
                        })

                        # force a chat reload so that it shows up (core/channel takes care of adding it to context)
                        await self.websocket_manager.broadcast({
                            "type": "sync"
                        })
                        return
                    case _:
                        if not user_message_confirmed:
                            user_message_confirmed = True
                            await self.websocket_manager.broadcast({
                                "type": "user_message_confirmed",
                                "index": index
                            })
                            await self.websocket_manager.set_stream_state("message_received")

                        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
                        # backend-side state machine for the token types that
                        # drive the UI's "what is the AI doing" indicator.
                        # set_stream_state is deduped, so hitting it on every
                        # streamed token costs nothing beyond the transition.
                        match token_type:
                            case "prompt_progress":
                                # prompt eval between tool rounds: keep the
                                # processing_tools state if it's been set
                                # (matches the old frontend's behavior)
                                if self.websocket_manager.stream_state != "processing_tools":
                                    await self.websocket_manager.set_stream_state("processing")
                            case "model_load_progress":
                                await self.websocket_manager.set_stream_state("processing")
                            case "tool":
                                await self.websocket_manager.set_stream_state("processing_tools")
                            case "tool_call_delta":
                                await self.websocket_manager.set_stream_state("calling_tools")
                            case "tool_calls":
                                await self.websocket_manager.set_stream_state("calling_tools")

                        await self.websocket_manager.broadcast({
                            "type": "token",
                            "content": token
                        })

            elif partial.get("type") == "turn":
                # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
                # the turncollector groups tokens into typed segments; the
                # live segment type is what the UI shows (thinking/streaming)
                segment_type = (payload.get("content") or {}).get("type")
                if segment_type == "reasoning":
                    await self.websocket_manager.set_stream_state("thinking")
                elif segment_type == "content":
                    await self.websocket_manager.set_stream_state("streaming")

                # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
                # buffer the snapshot for mid-stream reconnect replay.
                # payload is a fresh serialize_for_json copy every pass, so
                # the buffered object is a true point-in-time snapshot and
                # never aliases the collector's mutating live segment.
                self.websocket_manager.record_turn_segment(payload.get("content"))

                await self.websocket_manager.broadcast({
                    "type": "turn_stream",
                    "turn": payload.get("content")
                })

    def on_log(self, category, message):
        if not hasattr(self, 'websocket_manager'):
            # not initialized yet
            return False

        # Store log in buffer for history
        self.logs.append({"category": category, "message": message})
        
        # Broadcast log messages to all connected webui clients
        # Since on_log is sync but manager.broadcast is async, we schedule it as a task
        log_message = {
            "type": "log",
            "category": category,
            "message": message
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.websocket_manager.broadcast(log_message))
        except RuntimeError:
            # No event loop running - create one for this task
            asyncio.ensure_future(self.websocket_manager.broadcast(log_message))

    async def on_shutdown(self):
        # broadcast first so clients know we're going away
        await self.websocket_manager.broadcast({"type": "shutdown"})
        
        # then properly stop uvicorn
        # this is a flag exposed by uvicorn itself, which causes it to start gracefully shutting down when set
        self.server.should_exit = True

        # wait for uvicorn to actually finish shutting down
        try:
            await asyncio.wait_for(self.server.shutdown(), timeout=5.0)
        except (AttributeError, asyncio.TimeoutError):
            # fallback: just give it a moment to release the socket
            await asyncio.sleep(0.5)

# -------------------
# Helper Functions
# -------------------
def serialize_for_json(obj):
    """Recursively converts non-serializable objects into plain dicts/lists."""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(x) for x in obj]
    elif hasattr(obj, 'to_dict'):
        return serialize_for_json(obj.to_dict())
    elif hasattr(obj, '__dict__'):
        return serialize_for_json(obj.__dict__)
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)

def get_recursive_assets(assets_path, ext, skip: list = []):
    """Recursively list asset files with paths relative to server root."""
    files = []
    
    for root, dirs, filenames in os.walk(assets_path):
        # Skip files and directories marked for skipping
        filenames[:] = [f for f in filenames if os.path.basename(f) not in skip]
        dirs[:] = [d for d in dirs if d not in skip]
        
        for filename in filenames:
            if filename.endswith(f".{ext}"):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, assets_path)
                files.append(rel_path)
    
    return sorted(files)

def inject_indexes_into_messages(lst: list):
    """speaks for itself lol"""
    return [{**dickt, 'index': index} for index, dickt in enumerate(lst)]

def inject_indexes_into_chat(chat):
    """injects indexes into a chat's messages"""
    # copy it so we dont mutate it when injecting indexes
    chat_copy = dict(chat)

    # insert indexes into the messages array
    # so that the UI can track them for things like
    # editing messages, regenerating, deleting, etc
    chat_copy["messages"] = inject_indexes_into_messages(chat["messages"])

    return chat_copy

# -------------------
# Settings Structure (backend-side)
# -------------------
# -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
# ported from the webui frontend's processors/settings_structure.js and
# settings_flatten.js. the backend now returns a ready-to-render category
# tree from /api/settings/load and accepts that same (edited) tree on
# /api/settings/save, flattening it back into raw config server-side.
# the frontend never merges schemas or reassembles nested config again.

# special keys that render with a bespoke widget instead of a generic field
SPECIAL_FIELD_TYPES = {
    "model.name": "model_select",
    "api.url": "api_url",
    "api.key": "api_key",
    "model.reasoning_effort": "reasoning_effort_slider",
}

MODULE_CATEGORY_KEYS = ("modules", "user_modules", "channels", "user_channels")


def format_label(key):
    if not isinstance(key, str):
        return key
    spaced = key.replace("_", " ")
    return re.sub(r"\b\w", lambda m: m.group(0).upper(), spaced)


def is_toggle_list(data):
    return (
        isinstance(data, dict)
        and isinstance(data.get("enabled"), list)
        and isinstance(data.get("disabled"), list)
    )


def detect_field_type(value, key=""):
    if key in SPECIAL_FIELD_TYPES:
        return SPECIAL_FIELD_TYPES[key]
    if value is None:
        return "text"
    elif isinstance(value, bool):
        return "boolean"
    elif isinstance(value, (int, float)) and not key.lower().endswith("id"):
        return "number"
    elif isinstance(value, list):
        return "array"
    elif isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://"):
            return "url"
        elif "\n" in value:
            return "textarea"
        else:
            return "text"
    return "text"


def build_field_settings(obj, schema, prefix=""):
    if not obj or not isinstance(obj, dict):
        return {}

    settings = {}

    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        field_schema = schema.get(key) or {}
        if not isinstance(field_schema, dict):
            field_schema = {}

        has_schema_definition = any(
            k in field_schema for k in ("type", "default", "description")
        )

        if has_schema_definition:
            # schema defines the field - use schema for metadata, value for current value
            schema_value = field_schema["default"] if "default" in field_schema else value
            raw_type = field_schema.get("type")
            if raw_type == "long_text":
                field_type = "textarea"
            elif raw_type is not None:
                field_type = raw_type
            else:
                field_type = detect_field_type(schema_value, full_key)

            settings[key] = {
                "title": format_label(key),
                "type": field_type,
                "description": field_schema.get("description") or None,
                "unsafe": field_schema.get("unsafe", False),
                "value": value,
                "options": field_schema.get("options") or None,
                "min": field_schema.get("min"),
                "max": field_schema.get("max"),
                "step": field_schema.get("step"),
                "depends": field_schema.get("depends") or None,
            }
        elif isinstance(value, dict) and not is_toggle_list(value):
            # nested object without schema definition - recurse
            settings[key] = {
                "type": "object",
                "title": format_label(key),
                "description": field_schema.get("description") or None,
                "depends": field_schema.get("depends") or None,
                "settings": build_field_settings(value, field_schema, full_key),
            }
        elif is_toggle_list(value):
            settings[key] = {
                "type": "toggle_list",
                "title": format_label(key),
                "description": field_schema.get("description") or None,
                "value": value,
            }
        elif isinstance(value, list):
            settings[key] = {
                "type": "array",
                "title": format_label(key),
                "description": field_schema.get("description") or None,
                "value": value,
            }
        else:
            # primitive value without schema definition
            settings[key] = {
                "title": format_label(key),
                "type": detect_field_type(value, full_key),
                "description": field_schema.get("description") or None,
                "unsafe": field_schema.get("unsafe", False),
                "depends": field_schema.get("depends") or None,
                "value": value,
                "options": field_schema.get("options") or None,
                "min": field_schema.get("min"),
                "max": field_schema.get("max"),
                "step": field_schema.get("step"),
            }

    return settings


def build_settings_structure(original_data, module_info, core_sections):
    categories = {}
    order = 0

    categories["appearance"] = {
        "title": "Appearance",
        "description": "Theme and interface customization",
        "order": order,
        "isThemeCategory": True,
    }
    order += 1
    categories["audio"] = {
        "title": "Audio",
        "description": "Audio settings",
        "order": order,
        "isThemeCategory": True,
    }
    categories["system_prompt"] = {
        "title": "System Prompt",
        "description": "See the current system prompt",
        "order": 100,
        "isThemeCategory": True,
    }
    categories["system_logs"] = {
        "title": "System Logs",
        "description": "Peek into the great unknown",
        "order": 999,
        "isThemeCategory": True,
    }

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
    # explicit display priority for the module/channel sections, so the
    # sidebar groups as: appearance, audio, core config sections, channels,
    # modules | get modules, user channels, user modules | info-only tabs.
    # the 10+ base keeps these clear of the sequentially ordered sections.
    section_order = {
        "channels": 10,
        "modules": 11,
        "user_channels": 13,
        "user_modules": 14,
    }
    module_library_order = 12

    for top_key, top_value in original_data.items():
        if top_key.lower() in ("theme", "theme_mode"):
            continue

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
        # special tab: browse, install, update and uninstall modules coming
        # from the git repos in core.module_libraries (see core/module_manager.py).
        # sits in its own slot between Modules and User Channels; the sidebar
        # draws a divider above it.
        if top_key == "channels" and "module_library" not in categories:
            categories["module_library"] = {
                "title": "Get Modules",
                "description": "Install modules from external libraries",
                "order": module_library_order,
                "isThemeCategory": True,
            }

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
        # display names for the user folders (where Get Modules installs to);
        # the config keys and folders themselves stay user_modules/user_channels
        section_titles = {
            "user_channels": "Installed Channels",
            "user_modules": "Installed Modules",
        }

        display_title = section_titles.get(top_key, format_label(top_key))
        category = {
            "title": display_title,
            "description": f"Configure {display_title.lower()}",
            "order": section_order.get(top_key, order),
        }
        order += 1

        if top_key in MODULE_CATEGORY_KEYS:
            category["isModuleCategory"] = True
            category["enabled"] = (top_value or {}).get("enabled") or []
            category["disabled"] = (top_value or {}).get("disabled") or []

            descriptions = {}
            unsafe_modules = {}
            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
            # module_name -> declared category, so the frontend can group the list
            module_categories = {}
            for item_name, info in module_info.items():
                if info.get("description"):
                    descriptions[item_name] = info["description"]
                if info.get("unsafe"):
                    unsafe_modules[item_name] = True
                if info.get("category"):
                    module_categories[item_name] = info["category"]
            category["descriptions"] = descriptions
            category["unsafeModules"] = unsafe_modules
            category["moduleCategories"] = module_categories

            category["settings"] = {}
            top_settings = (top_value or {}).get("settings")
            if isinstance(top_settings, dict):
                for item_name, item_settings in top_settings.items():
                    if not item_settings:
                        continue
                    item_info = module_info.get(item_name) or {}
                    item_schema = item_info.get("settings_schema") or {}
                    category["settings"][item_name] = {
                        "title": format_label(item_name),
                        "description": item_info.get("description") or "",
                        "unsafe": item_info.get("unsafe", False),
                        "value": build_field_settings(item_settings, item_schema, item_name),
                    }
        else:
            # core config sections (api, model, core, etc.), schema from core_sections
            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
            section_schema = (core_sections.get(top_key) or {}).get("settings_schema") or {}
            if isinstance(top_value, dict) and top_value:
                category["settings"] = build_field_settings(top_value, section_schema, top_key)
            else:
                category["settings"] = {}

        categories[top_key] = category

    # safety net: if the channels section was absent from the config,
    # the tab still shows up (appended at the end of the regular sections)
    if "module_library" not in categories:
        categories["module_library"] = {
            "title": "Get Modules",
            "description": "Install modules from external libraries",
            "order": module_library_order,
            "isThemeCategory": True,
        }

    return categories


def flatten_field_settings(settings):
    """reduces a (possibly edited) field tree back to plain key -> value config"""
    result = {}
    for key, setting in settings.items():
        if not isinstance(setting, dict):
            continue
        if setting.get("type") == "object" and setting.get("settings"):
            result[key] = flatten_field_settings(setting["settings"])
        else:
            result[key] = setting.get("value")
    return result


def flatten_categories(categories):
    """inverse of build_settings_structure: category tree -> raw config dict"""
    result = {}

    for cat_key, category in categories.items():
        if not isinstance(category, dict):
            continue

        has_settings = bool(category.get("settings"))
        has_enabled = "enabled" in category
        has_disabled = "disabled" in category
        if not has_settings and not has_enabled and not has_disabled:
            continue

        if category.get("isModuleCategory"):
            entry = {}
            if has_enabled:
                entry["enabled"] = category["enabled"]
            if has_disabled:
                entry["disabled"] = category["disabled"]
            if has_settings:
                module_settings = {}
                for name, module in category["settings"].items():
                    if isinstance(module, dict) and module.get("value"):
                        module_settings[name] = flatten_field_settings(module["value"])
                entry["settings"] = module_settings
            result[cat_key] = entry
        else:
            result[cat_key] = flatten_field_settings(category.get("settings") or {})

    return result


def get_module_info():
    """
    -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
    schemas (descriptions, settings schemas, etc) for all modules/channels and for
    the core config sections.

    These are returned as TWO separate namespaces. They used to share one dict,
    which meant a module named like a core config section (e.g. the `modules`
    module vs the `modules` config section) would clobber the section's entry -
    or, with the section loop running last, the section would clobber the
    module's entry, silently losing its category/description/settings schema.
    Returns (module_info, core_sections).
    """
    module_info = {}

    for module_name, module_data in core.config.get_module_structure().items():
        metadata = module_data.get("metadata", {})
        module_info[module_name] = {
            "description": metadata.get("doc", ""),
            "unsafe": metadata.get("unsafe", False),
            "category": metadata.get("category", ""),
            "settings_schema": module_data.get("settings", {}),
        }

    core_sections = {}

    for section_name, section_data in core.config.get_core_settings_structure().items():
        core_sections[section_name] = {
            "description": section_data.get("metadata", {}).get("doc", ""),
            "unsafe": section_data.get("metadata", {}).get("unsafe", False),
            "settings_schema": section_data.get("settings", {}),
        }

    return module_info, core_sections

# -------------------
# Chat List Projection & Search Highlighting
# -------------------
# -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
# list endpoints only ever render a handful of chat fields; sending whole
# chat dicts (with descriptions, prompt data, etc) was pure payload waste.
CHAT_LIST_FIELDS = (
    "id", "title", "category", "tags", "created", "updated",
    "messages_found", "message_snippets",
)


def project_chat(chat, extra_fields=()):
    projected = {key: chat.get(key) for key in CHAT_LIST_FIELDS if key in chat}
    for key in extra_fields:
        if key in chat:
            projected[key] = chat[key]
    return projected


def highlight_query(text, query):
    """html-escaped text with case-insensitive query matches wrapped in <strong>"""
    if text is None:
        return None
    escaped_text = html_lib.escape(str(text), quote=True)
    if not query:
        return escaped_text
    # -- AI GENERATED CODE (qwen/Qwen3.8-Flash-Next-Q4) :: (2026-10-02)
    # highlight the verbatim phrase plus each normalized query token as a
    # substring, mirroring what core.search's BM25 actually matches.
    # escape both sides identically before regexing, so queries containing
    # html-ish characters still match the escaped text
    candidates = [str(query).strip()] + core.search.normalize_words(query)
    pattern = "|".join(dict.fromkeys(
        re.escape(html_lib.escape(c, quote=True)) for c in candidates if c
    ))
    if not pattern:
        return escaped_text
    return re.sub(
        f"({pattern})",
        lambda m: '<strong class="search-highlight">' + m.group(1) + "</strong>",
        escaped_text,
        flags=re.IGNORECASE,
    )


def day_label_from_key(key, tz_offset_min=0):
    """human label for a day/week/month group key (see _group_key)"""
    if not key:
        return "Undated"
    if key.startswith("last-week"):
        return "Last Week"

    parts = key.split("-")
    try:
        year = int(parts[0])
        month = int(parts[1])
        day = int(parts[2]) if len(parts) > 2 else 1
        date = datetime.date(year, month, day)
    except (ValueError, IndexError):
        return "Undated"

    # month group keys are 'YYYY-MM': always show the year, month groups
    # can span years and 'September' alone gets ambiguous
    if len(parts) == 2:
        return f"{calendar.month_name[month]} {year}"

    today = (datetime.datetime.utcnow() - datetime.timedelta(minutes=tz_offset_min)).date()
    diff_days = (today - date).days

    if diff_days == 0:
        return "Today"
    if diff_days == 1:
        return "Yesterday"
    if 1 < diff_days < 7:
        return date.strftime("%A")
    if date.year == today.year:
        return f"{calendar.month_name[month]} {day}"
    return f"{calendar.month_name[month]} {day}, {year}"

# -------------------
# Shared Chat Operations
# -------------------
# -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
# one implementation per chat mutation, used by BOTH the REST routes and
# the websocket commands, so the two transports can never drift apart.
# every chat_switched broadcast uses 'id' for the chat id (that's what
# the frontend listens for - the old ws handlers sent 'chat_id', which
# silently fell through to a broken loadChat(undefined) round-trip).


async def op_chat_switch(channel, chat_id):
    """loads a chat, cancels any stream, notifies all clients"""
    ws_mgr = channel.websocket_manager
    if ws_mgr.active_stream_task and not ws_mgr.active_stream_task.done():
        ws_mgr.active_stream_task.cancel()

    try:
        success = await channel.context.chat.load(chat_id)
    except Exception as e:
        return False

    if success:
        ws_mgr.active_chat_id = chat_id
        await ws_mgr.broadcast({"type": "chat_switched", "id": chat_id})

    return True


async def op_chat_new(channel, category="general"):
    """creates a chat, switches to it, notifies all clients"""
    ws_mgr = channel.websocket_manager
    if ws_mgr.active_stream_task and not ws_mgr.active_stream_task.done():
        ws_mgr.active_stream_task.cancel()

    new_id = await channel.context.chat.new(category=category)
    ws_mgr.active_chat_id = new_id

    await ws_mgr.broadcast({"type": "chat_switched", "id": new_id})
    return new_id


async def op_chat_delete(channel, chat_id):
    """deletes a chat and points all clients at whatever is loaded now"""
    await channel.context.chat.delete(chat_id)
    await channel.websocket_manager.broadcast({
        "type": "chat_switched",
        "id": channel.context.chat.get("id"),
    })


# -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
# single source of truth for category name validation. returns
# (error, normalized_name).
def validate_category_format(name):
    name = (name or "").strip()

    if not name:
        return "category name cannot be empty", None
    if ":" in name:
        return "':' is reserved for subcategories", None

    return None, name


def validate_category_name(name, chat_store):
    """format validation + duplicate check, for explicitly creating a
    new category. returns (error, normalized_name)."""
    error, name = validate_category_format(name)
    if error:
        return error, None

    existing = [
        (chat.get("category") or "general")
        for chat in chat_store.data
    ]
    if name in existing:
        return f"'{name}' already exists", None

    return None, name


async def op_chat_rename(channel, title, chat_id=None):
    """renames a chat (current chat when no id given), saves, notifies"""
    chat_store = channel.context.chat

    if chat_id:
        index = chat_store._find_index(chat_id)
        if index is None:
            return False
        await chat_store.set("title", title, index=index)
        tags = chat_store.data[index].get("tags") or []
    else:
        await chat_store.set("title", title)
        tags = chat_store.get("tags") or []

    chat_store.data.save()

    await channel.websocket_manager.broadcast({
        "type": "chat_metadata_updated",
        "title": title,
        "tags": tags,
    })
    return True

# -------------------
# FastAPI creator (contains routes and so on)
# -------------------

# -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
# endpoints blocked entirely when enable_admin_settings is off.
# /api/system/data is deliberately NOT here: the context pill reads
# max_context from it, and it's read-only.
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
    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
    # module library management follows the same admin lockdown
    "/api/libraries/status",
    "/api/libraries/sync",
    "/api/libraries/install",
    "/api/libraries/update",
    "/api/libraries/uninstall",
    "/api/libraries/source",
]

# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
# static hints for the pre-install code review modal. the entry file is only
# parsed with ast - nothing from the library is imported or executed here.
_REVIEW_IMPORT_FLAGS = {
    "subprocess": "imports subprocess - can run shell commands",
    "ctypes": "imports ctypes - can call native code",
    "socket": "imports socket - can open raw network connections",
}

def library_review_flags(entry_path):
    """returns (flags, warnings) for a library module's entry file:
    flags = places the user should look (dependencies, on_install, on_ready),
    warnings = anything that smells like shell/exec/network access."""
    flags = []
    warnings = []
    try:
        with open(entry_path, "r", encoding="utf-8", errors="replace") as f:
            tree = ast.parse(f.read())
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

def api_result(obj = None, success: bool = True):
    if obj is None:
        result = {}
    else:
        result = obj

    return {"data": result, "success": success}

# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
def trusted_client_ip(conn):
    """rate-limit identity for a fastapi Request or WebSocket.

    Behind a reverse proxy the socket peer is always 127.0.0.1, so every
    visitor would share one login rate-limit bucket: one crank could lock
    the real user out for 15 minutes (and per-user limiting would not exist).
    X-Forwarded-For is therefore honored ONLY when the socket peer is
    loopback: the webui binds to 127.0.0.1, so a connection either arrives
    from the local proxy (whose XFF is trustworthy) or from a local process,
    which is already inside the machine's trust boundary. A remote attacker
    cannot reach this socket without the proxy, so the header can never be
    used to forge a rate-limit identity across the network boundary.
    """
    peer = conn.client.host if conn.client else "unknown"
    if peer in ("127.0.0.1", "::1"):
        forwarded = conn.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    return peer

async def create_fastapi(channel):
    app = fastapi.FastAPI()

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-09)
    # cross-origin isolation: COOP + COEP on every response
    @app.middleware("http")
    async def coi_middleware(request: fastapi.Request, call_next):
        response = await call_next(request)
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
        return response

    # add authorization, cookies, and so on (middleware)
    # auth middleware for all routes
    @app.middleware("http")
    async def auth_middleware(request: fastapi.Request, call_next):
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # admin lockdown: when enable_admin_settings is off, every
        # settings-related endpoint is blocked outright, regardless of
        # whether login is enabled.
        if not channel.config.get("enable_admin_settings", True):
            if request.url.path in ADMIN_ONLY_ENDPOINTS:
                return fastapi.responses.JSONResponse(
                    status_code=403,
                    content={"data": "Admin settings are disabled", "success": False}
                )

        # Skip auth check if login isn't required
        if not channel.config.get("require_login", False):
            return await call_next(request)
        
        # Skip auth for login page and assets
        if request.url.path in ["/login", "/logout"] or str(request.url.path).startswith("/assets/"):
            return await call_next(request)
        
        # Check session for API and other routes
        if not request.session.get("authenticated", False):
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

    session_lifetime_days = channel.config.get("login_lifetime")
    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara
    signing_key = getattr(channel, "session_secret_value", "") or secrets.token_urlsafe(48)
    cookie_name = "session_" + hashlib.sha256(signing_key.encode()).hexdigest()[:12]
    channel.session_cookie_name = cookie_name
    app.add_middleware(
        starlette.middleware.sessions.SessionMiddleware,
        session_cookie=cookie_name,
        secret_key=signing_key,
        max_age=session_lifetime_days * 86400,
        # CSRF hardening: the session cookie is never sent on cross-site
        # requests (a malicious page can no longer ride an active session)
        same_site="strict"
    )

    # serve asset files (formerly /static) using fastAPI's mount()
    app.mount("/assets", fastapi.staticfiles.StaticFiles(directory=channel.assets_path), name="assets")

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-03)
    # serve module-provided assets (<module>/webui/assets/) under /ext-assets/.
    # auth is already handled by the middleware (path isn't /assets/* or /login).
    @app.get("/ext-assets/{module_name}/{asset_path:path}")
    async def ext_module_assets(module_name: str, asset_path: str):
        module_dir = channel._ui_asset_dirs().get(module_name)
        if module_dir is None:
            raise fastapi.HTTPException(status_code=404, detail="Unknown module or no assets")
        module_root = os.path.realpath(module_dir)
        full_path = os.path.realpath(os.path.join(module_dir, asset_path))
        if not full_path.startswith(module_root + os.sep) or not os.path.isfile(full_path):
            raise fastapi.HTTPException(status_code=404, detail="Asset not found")
        return fastapi.responses.FileResponse(full_path)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-03)
    # phase 4 of the extension system: modules expose API endpoints via the
    # zero-dependency marker in channels/webui/api.py (@webui.route). the
    # lookup scans live module classes on every request, so module reloads
    # (enable/disable/edit) are picked up with no rebuild hook. routes are
    # exact-match against module-declared paths, so no traversal concerns.
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
                # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
                # security: routes explicitly marked admin_only=True are
                # blocked (403) while enable_admin_settings is off. the
                # meta.get default is True so hand-written _ui_route dicts
                # that predate the flag fail closed; the decorator itself
                # defaults to admin_only=False.
                if meta.get("admin_only", True) and not channel.config.get("enable_admin_settings", True):
                    return None, "admin-only"
                return getattr(module, attr_name), None
        if not route_exists:
            return None, "route not found"
        return None, f"route only accepts {'GET' if method != 'GET' else 'POST'}"

    @app.api_route("/api/ext/{module_name}/{route_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def ext_api(module_name: str, route_path: str, request: fastapi.Request):
        """forwards to a module handler marked with @webui.route. handlers
        take (body=None, query=None) and return raw data (wrapped in the
        standard api envelope) or the self.result() dict (unwrapped)."""
        handler, reason = _ui_api_lookup(module_name, route_path, request.method)
        if handler is None:
            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
            # "admin-only" (route blocked because enable_admin_settings is off)
            # gets a proper 403, everything else keeps 404/405 behavior.
            if reason == "admin-only":
                status = 403
            elif "accepts" in reason:
                status = 405
            else:
                status = 404
            return fastapi.responses.JSONResponse(api_result(reason, success=False), status_code=status)

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-04)
        # ext routes bypass send()/send_stream(), the only other caller of
        # _set_as_active_channel(); without this, modules reading self.channel
        # operate on whichever channel last handled a chat message instead of
        # the webui this request actually came from (cross-channel leaks).
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
            return api_result(core.detail_error(e), success=False)

        # unwrap the module-side self.result() convention into the api envelope
        if isinstance(outcome, dict) and "status" in outcome and "content" in outcome:
            return api_result(outcome["content"], outcome["status"] == "success")
        return api_result(outcome, True)

    # ------------------
    # Web pages
    # ------------------

    # main page
    @app.get("/")
    async def root(request: fastapi.Request):
        """The main page. This returns HTML, not JSON"""
        css_files = get_recursive_assets(os.path.join(channel.assets_path, "css"), "css", skip=["code-themes"])
        alpine_stores = os.listdir(os.path.join(channel.assets_path, "js", "stores"))
        js_utils = os.listdir(os.path.join(channel.assets_path, "js", "utils"))
        js_files = get_recursive_assets(os.path.join(channel.assets_path, "js"), "js", skip=["init.js", "stores", "libs", "utils"])

        return channel.templates.TemplateResponse(request, "index.html", {
            "version": channel.version,
            "config": channel.config,
            "css_files": css_files,
            "alpine_stores": alpine_stores,
            "js_utils": js_utils,
            "js_files": js_files,
            "ext_css_files": channel._ui_asset_urls("css"),
            "ext_js_files": channel._ui_asset_urls("js"),
            "login_enabled": channel.config.get("require_login"),
            "core_config": core.config
        })

    # ---- login
    # -- GET
    @app.get("/login")
    async def login_page(request: fastapi.Request):
        """Shows the login form."""
        if channel.config.get("require_login"):
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

        # rate limit the request
        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        # per-USER bucket: behind a local proxy the socket peer is always
        # loopback; trusted_client_ip() restores real attribution via XFF.
        client_ip = trusted_client_ip(request)
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
        return fastapi.responses.RedirectResponse(url="/login", status_code=303)

    # ------------------
    # API routes (/api)
    # ------------------

    # reminder to self: docstrings show up in the autogenerated API docs (/docs), so they are essential

    # --- chats
    # -- GET
    @app.get("/api/chat/load/{chat_id}")
    async def chat_load(chat_id: str, request: fastapi.Request):
        """Loads a specific chat by its id"""
        success = await op_chat_switch(channel, chat_id)
        if not success:
            return api_result("error while loading chat", success=False)

        chat = dict(channel.context.chat.get())
        chat["turn_history"] = await channel.group_history()
        chat["token_usage"] = await channel.context.get_total_tokens()
        return api_result(chat, success=True)

    @app.get("/api/chat/current")
    async def chat_get_current():
        """Gives you the currently loaded chat's data"""

        chat = dict(channel.context.chat.get())
        chat["turn_history"] = await channel.group_history()
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-21)
        # report the live, authoritative count instead of the raw metadata
        # field, so the context pill can never disagree with the popup
        chat["token_usage"] = await channel.context.get_total_tokens()
        return api_result(chat)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
    # the backend owns the stream state machine now; this lets clients
    # (or anything else) read the authoritative state on demand.
    @app.get("/api/stream/state")
    async def stream_state_get():
        """Returns the current stream state as tracked by the backend"""
        return api_result({"state": channel.websocket_manager.stream_state})

    @app.get("/api/chat/export")
    async def chat_export():
        """Gives you the chat history as a human-readable string, plus a safe filename, which you can save to a file or do whatever else with"""
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # filename sanitization moved here from the frontend: the backend
        # owns the title, so it owns turning it into a filename too.
        content = await channel.context.chat.export()
        title = channel.context.chat.get("title") or ""
        safe_title = re.sub(r'[\\/:*?"<>|]', "_", title).strip() or "chat-export"
        return api_result({"content": content, "filename": f"{safe_title}.txt"})

    @app.get("/api/chats")
    async def get_chats(request: fastapi.Request):
        """Returns a list of all chats, with pagination"""
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", 50))
        category = request.query_params.get("category", None)

        all_chats = channel.context.chat.get_all()
        if category:
            all_chats = [c for c in all_chats if c.get("category") == category]

        paginated = all_chats[offset:offset + limit]
        has_more = offset + limit < len(all_chats)

        return api_result({
            "messages": [project_chat(c) for c in paginated],
            "has_more": has_more
        }, success=True)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    # day-grouped chat listing for the sidebar's collapsible date
    # headers. 'updated' is naive UTC, so days are bucketed in the
    # browser's local day: the frontend sends its tz offset (JS
    # getTimezoneOffset, minutes behind UTC) and the backend shifts
    # before bucketing so headers and client-side grouping agree.
    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-26)
    # optional tag filter for the sidebar's tag panel: AND semantics, a
    # chat must carry every selected tag to survive the filter.
    def _chats_for_category(category, tags=None):
        all_chats = channel.context.chat.get_all()
        if category:
            all_chats = [c for c in all_chats if c.get("category") == category]

        if tags:
            all_chats = [
                c for c in all_chats
                if all(t in (c.get("tags") or []) for t in tags)
            ]

        return all_chats

    def _local_day(updated_str, tz_offset_min):
        # naive UTC isoformat -> local date string 'YYYY-MM-DD'
        if not updated_str:
            return ""

        try:
            dt = datetime.datetime.fromisoformat(updated_str)
        except ValueError:
            return ""

        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)

        dt = dt - datetime.timedelta(minutes=tz_offset_min)
        return dt.date().isoformat()

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    # sidebar grouping tiers (ISO weeks, Monday start):
    # - this week (Mon..today): one group per day ('YYYY-MM-DD')
    # - last week (Mon..Sun):   one group, key 'last-week-<monday>'
    # - older:                  one group per month ('YYYY-MM')
    # cutoffs are computed in the browser's local day (tz_offset
    # shifted) so they match the client's labels exactly.
    def _local_today(tz_offset_min):
        return (datetime.datetime.utcnow() - datetime.timedelta(minutes=tz_offset_min)).date()

    def _group_key(updated_str, tz_offset_min):
        day = _local_day(updated_str, tz_offset_min)
        if not day:
            return ""

        today = _local_today(tz_offset_min)
        this_monday = today - datetime.timedelta(days=today.weekday())
        last_monday = this_monday - datetime.timedelta(days=7)

        if day >= this_monday.isoformat():
            return day
        if day >= last_monday.isoformat():
            return f"last-week-{last_monday.isoformat()}"
        return day[:7]

    @app.get("/api/chats/days")
    async def get_chat_days(request: fastapi.Request):
        """Returns the day/last-week/month groups that have chats, newest first, with counts"""
        category = request.query_params.get("category", None)
        tz_offset = int(request.query_params.get("tz_offset", 0))
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-26)
        # repeated 'tags' query params narrow the listing (AND semantics)
        tags = request.query_params.getlist("tags")

        # max local day per group key: mixed-format keys ('YYYY-MM-DD',
        # 'last-week-...', 'YYYY-MM') can't be string-sorted against each
        # other, so groups are ordered by their newest member instead
        counts = {}
        newest = {}
        for chat in _chats_for_category(category, tags):
            updated = chat.get("updated", "")
            key = _group_key(updated, tz_offset)
            day = _local_day(updated, tz_offset)
            counts[key] = counts.get(key, 0) + 1
            if day > newest.get(key, ""):
                newest[key] = day

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # labels are computed server-side now: the frontend used to mirror
        # the grouping/labeling rules in format.js, kept in sync by prayer
        groups = [
            {"key": k, "count": c, "label": day_label_from_key(k, tz_offset)}
            for k, c in counts.items()
        ]
        groups.sort(key=lambda entry: newest.get(entry["key"], ""), reverse=True)

        return api_result(groups, success=True)

    @app.get("/api/chats/day")
    async def get_chats_for_day(request: fastapi.Request):
        """Returns the chats of one day/month group, newest first, paginated"""
        day = request.query_params.get("day", "")
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", 50))
        category = request.query_params.get("category", None)
        tz_offset = int(request.query_params.get("tz_offset", 0))
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-26)
        # repeated 'tags' query params narrow the listing (AND semantics)
        tags = request.query_params.getlist("tags")

        day_chats = [
            c for c in _chats_for_category(category, tags)
            if _group_key(c.get("updated", ""), tz_offset) == day
        ]

        paginated = day_chats[offset:offset + limit]
        has_more = offset + limit < len(day_chats)

        return api_result({
            "messages": [project_chat(c) for c in paginated],
            "has_more": has_more,
            "count": len(day_chats)
        }, success=True)

    @app.get("/api/chats/categories")
    async def get_chat_categories():
        """Returns a list of all existing chat categories, sorted with 'general' pinned to the top"""
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # ordering moved here from the frontend's dropdownCategories()
        categories = [c or "general" for c in channel.context.chat.get_categories()]
        categories = sorted(set(categories))
        if "general" in categories:
            categories.remove("general")
            categories.insert(0, "general")
        return api_result(categories, True)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    # per-category chat counts for the manage-categories modal. the
    # frontend used to fetch every single chat (limit=100000) just to
    # count them itself.
    @app.get("/api/chats/categories/count")
    async def get_chat_category_counts():
        """Returns how many chats live in each category"""
        counts = {}
        for chat in channel.context.chat.data:
            cat = chat.get("category") or "general"
            counts[cat] = counts.get(cat, 0) + 1
        return api_result(counts, True)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-26)
    # all tags in use, optionally scoped to a category (the sidebar's
    # tag filter panel only offers tags relevant to the open category).
    @app.get("/api/chats/tags")
    async def get_chat_tags(request: fastapi.Request):
        """Returns the sorted list of tags used by chats"""
        category = request.query_params.get("category", None)

        tags = set()
        for chat in _chats_for_category(category):
            for tag in (chat.get("tags") or []):
                if tag:
                    tags.add(tag)

        return api_result(sorted(tags), success=True)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    # explicitly create a category: validation happens here, then a fresh
    # chat is created inside it (a category exists once a chat uses it).
    @app.post("/api/chats/categories/create")
    async def create_chat_category(request: fastapi.Request):
        """Validates a category name and creates a new chat inside it"""
        data = await request.json()
        name = data.get("name") or ""

        error, name = validate_category_name(name, channel.context.chat)
        if error:
            return api_result(error, success=False)

        new_id = await op_chat_new(channel, category=name)
        return api_result({"id": new_id}, True)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
    # deleting a category = moving all of its chats to 'general'.
    # the category field is set to 'general' explicitly rather than
    # blanked: a blank category would make those chats invisible to the
    # sidebar's category filter (which matches with ==).
    @app.post("/api/chats/categories/delete")
    async def delete_chat_category(request: fastapi.Request):
        """Moves every chat in the given category to 'general', removing the category"""
        data = await request.json()
        name = (data.get("name") or "").strip()

        if not name or name == "general":
            return api_result("'general' cannot be deleted", False)

        chat_store = channel.context.chat

        moved = 0
        for chat in chat_store.data:
            if chat.get("category") == name:
                chat["category"] = "general"
                moved += 1

        if moved:
            chat_store.data.save()

        return api_result({"moved": moved}, True)

    @app.post("/api/chats/search")
    async def search_chats(request: fastapi.Request):
        """Searches across all chats for messages matching a query"""
        data = await request.json()
        query = data.get("query", "").strip()
        search_in_content = data.get("search_in_content", True)
        category = data.get("category")
        # the browser's tz offset (minutes behind UTC), used to bucket
        # results into the same local day groups as the sidebar
        tz_offset = int(data.get("tz_offset") or 0)

        if not query:
            return api_result([])

        results = await channel.context.chat.search(query, search_in_content=search_in_content)

        # filter by category if provided
        if category and category != 'general':
            results = [r for r in results if r.get('category') == category]
        elif category == 'general':
            results = [r for r in results if not r.get('category') or r.get('category') == 'general']

        # respect the sidebar's active tag filter (AND semantics)
        tags = data.get("tags") or []
        if tags:
            results = [r for r in results if all(t in (r.get("tags") or []) for t in tags)]

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # pure updated-descending sort (the core's title-match priority
        # would scramble the sidebar's day groups). each result is slimmed
        # down and gains pre-highlighted title/snippets plus its day group
        # key + label, so the frontend renders without deriving anything.
        # -- AI GENERATED CODE (qwen/Qwen3.8-Flash-Next-Q4) :: (2026-10-02)
        # sort=relevance (global modal) keeps the BM25 ranking; the sidebar
        # still wants newest-first so its day groups stay coherent.
        if (data.get("sort") or "updated") != "relevance":
            results.sort(key=lambda r: r.get("updated") or "", reverse=True)

        projected = []
        for chat in results:
            group = _group_key(chat.get("updated", ""), tz_offset)
            entry = project_chat(chat, extra_fields=("title_match",))
            entry["group_key"] = group or "undated"
            entry["group_label"] = day_label_from_key(group, tz_offset)
            entry["title_highlighted"] = highlight_query(chat.get("title") or "", query)
            entry["snippets_highlighted"] = [
                highlight_query(snippet, query)
                for snippet in (chat.get("message_snippets") or [])
            ]
            projected.append(entry)

        return api_result(projected)

    @app.get("/api/chat/prompt")
    async def get_prompt():
        sysprompt = await channel.context.get(system_prompt=True, end_prompt=False, history=False)
        if isinstance(sysprompt, core.api.APIError):
            return api_result(sysprompt, success=False)

        return api_result(sysprompt[-1].get("content"))

    # -- POST
    @app.post("/api/chat/new")
    async def chat_new(request: fastapi.Request):
        """Creates a new chat"""
        # optional json body with a category, so the webui can create
        # the chat inside the currently selected category.
        category = "general"
        try:
            data = await request.json()
            category = (data.get("category") or "general").strip() or "general"
        except Exception:
            pass

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01) status:reviewed
        if category != "general":
            error, category = validate_category_format(category)
            if error:
                return api_result(error, success=False)

        new_id = await op_chat_new(channel, category=category)
        return api_result({"id": new_id})

    @app.post("/api/chat/rename/{chat_id}")
    async def chat_rename(chat_id: str, request: fastapi.Request):
        """Renames a chat by its ID"""
        try:
            data = await request.json()
            new_title = data.get('title', '').strip()
            if not new_title:
                return api_result("Title cannot be empty", success=False)

            renamed = await op_chat_rename(channel, new_title, chat_id=chat_id)
            if not renamed:
                return api_result("Chat not found", success=False)

            return api_result(success=True)
        except Exception as e:
            return api_result(str(e), success=False)

    @app.post("/api/chat/delete/{chat_id}")
    async def chat_delete(chat_id: str):
        """Deletes a chat by its ID"""
        await op_chat_delete(channel, chat_id)
        return api_result(success=True)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
    # move a chat to a different category. chat.set() mutates the index
    # without saving (rename gets away with it via later saves), so the
    # save is called explicitly here.
    @app.post("/api/chat/set-category/{chat_id}")
    async def chat_set_category(chat_id: str, request: fastapi.Request):
        """Changes the category of a chat by its ID"""
        try:
            data = await request.json()
            category = (data.get('category') or '').strip()
            if not category:
                return api_result("Category cannot be empty", success=False)

            index = channel.context.chat._find_index(chat_id)
            if index is None:
                return api_result("Chat not found", success=False)

            await channel.context.chat.set("category", category, index=index)
            channel.context.chat.data.save()

            return api_result(success=True)
        except Exception as e:
            return api_result(str(e), success=False)

    # --- Settings
    # -- GET
    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    # the config + module schemas are merged into a ready-to-render
    # category tree here, instead of shipping both to the frontend and
    # letting processors/settings_structure.js stitch them together.
    # /api/settings/get_module_info is gone along with that processor.
    @app.get("/api/settings/load")
    async def settings_load():
        """Returns the complete, render-ready settings structure (categories, field types, schemas and current values merged)"""
        module_info, core_sections = get_module_info()
        structure = build_settings_structure(core.config.config, module_info, core_sections)

        return api_result({
            "categories": structure,
            "show_unsafe_settings": bool(channel.config.get("show_unsafe_settings"))
        })

    @app.get("/api/check_connection")
    async def check_connection():
        """returns True if the backend is connected to the AI API, else False"""
        if channel.manager.API.connected:
            return api_result(True, success=True)
        else:
            return api_result("not connected", success=False)

    @app.get("/api/models")
    async def models_get():
        """Returns a list of all available AI models"""
        result = await channel.manager.API.list_models()
        if isinstance(result, core.api.APIError):
            return api_result(str(result), success=False)

        return api_result(result)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    # quick model switch from the header dropdown. set_model() writes to
    # config and saves it; requests read model.name fresh every time, so
    # no reconnect is needed.
    @app.post("/api/model/set")
    async def model_set(request: fastapi.Request):
        """Switches the active model to the given name"""
        data = await request.json()
        name = (data.get("name") or "").strip()

        if not name:
            return api_result("Model name cannot be empty", success=False)

        channel.manager.API.set_model(name)
        return api_result({"name": name}, success=True)

    # -- POST
    @app.post("/api/settings/save")
    async def settings_save(request: fastapi.Request):
        """Saves the (possibly edited) settings structure back to the backend. Accepts exactly what /api/settings/load returned, flattens it server-side and writes it to the config. Returns requires_restart/requires_reconnect so the frontend never has to diff config itself"""
        data = await request.json()

        changed_modules = list(data.get("changed_modules", []))

        # the frontend sends the category tree it got from settings/load,
        # with edited values; rebuild the raw config dict from it
        flattened = flatten_categories(data.get("categories", {}))

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # snapshot the pre-save config so we can tell the frontend whether
        # the changes need a server restart (module/channel lists) or an
        # API reconnect (api section); that decision used to be made
        # client-side with four JSON.stringify diffs
        old_config = copy.deepcopy(dict(core.config.config))


        result = core.config.config.load(data=flattened)
        core.config.config.save()

        if not result:
            return api_result(success=False)

        requires_restart = any(
            {k: (old_config.get(key) or {}).get(k) for k in ("enabled", "disabled")} !=
            {k: (flattened.get(key) or {}).get(k) for k in ("enabled", "disabled")}
            for key in MODULE_CATEGORY_KEYS
        )
        requires_reconnect = (not requires_restart) and (
            old_config.get("api") != flattened.get("api")
        )

        # Reload modules that had their settings changed
        if changed_modules:
            for module_name in changed_modules:
                try:
                    await channel.manager.reload_module(module_name)
                except Exception as e:
                    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                    # bugfix: referenced `self` outside of a class context,
                    # which turned any module reload error into a NameError
                    channel.log(channel.name, f"Error reloading module {module_name}: {core.detail_error(e)}")

        # -- AI GENERATED CODE (qwen/Qwen3.8-Flash-Next-Q4) :: 2026-10-03
        # rebuild the UI extension loader: modules may have gained or lost
        # their webui/templates folder, and cached templates must be dropped
        channel.setup_ui_extensions()

        return api_result({
            "requires_restart": requires_restart,
            "requires_reconnect": requires_reconnect,
        }, success=True)
    
    @app.post("/api/reconnect")
    async def reconnect():
        """Disconnects and then reconnects the API."""
        result = await channel.manager.API.reconnect()
        if isinstance(result, core.api.APIError):
            return api_result(str(result), success=False)

        return api_result(success=True)

    # ----------------------------
    # Module Library (external module repos)
    # ----------------------------
    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-12)
    # thin HTTP layer over core.module_manager.ModuleManager; the instance
    # itself is owned by the manager (manager.module_manager), so every
    # channel and module shares the same one.
    def get_module_manager():
        return channel.manager.module_manager

    @app.get("/api/libraries/status")
    async def libraries_status():
        """Returns the configured library repos, the cloned libraries, and every installable module found in them"""
        mm = get_module_manager()
        return api_result({
            "repos": mm.list_repos(),
            "libraries": list(mm.list_libraries().keys()),
            "modules": mm.list_available(),
        })

    @app.post("/api/libraries/sync")
    async def libraries_sync():
        """Clones/updates every repo in core.module_libraries, then returns the refreshed module list"""
        mm = get_module_manager()
        if not mm.list_repos():
            return api_result("No module libraries configured. Add github repo urls under Core settings first.", success=False)

        synced = await mm.load()
        return api_result({"synced": bool(synced), "modules": mm.list_available()}, success=True)

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
    # source viewer for the pre-install code review modal. read-only, and
    # hard-restricted to .py files inside the cloned module's own folder:
    # the requested file must appear in the server-generated file list, so
    # traversal through this endpoint is not possible.
    @app.get("/api/libraries/source")
    async def libraries_source(request: fastapi.Request):
        """returns a library module's source code plus review hints"""
        library = (request.query_params.get("library") or "").strip()
        name = (request.query_params.get("name") or "").strip()
        file_rel = (request.query_params.get("file") or "").strip()

        mm = get_module_manager()
        lib_path = mm.list_libraries().get(library)
        if not lib_path:
            return api_result("library not found", success=False)
        source, kind = mm._find_source(lib_path, name)
        if not source:
            return api_result("module not found in this library", success=False)

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara
        # kind-aware source view: skills (SKILL.md + extras) and themes (flat
        # json + optional css sidecar) are reviewable too, not just .py modules.
        source_root = os.path.realpath(source)
        REVIEW_TEXT_EXTS = (".py", ".json", ".md", ".txt", ".yaml", ".yml", ".css", ".js", ".html")

        if kind == "theme":
            files = [f for f in (f"{name}.json", f"{name}.css")
                     if os.path.isfile(os.path.join(source_root, f))]
            entry = f"{name}.json"
        else:
            files = []
            for dirpath, dirnames, filenames in os.walk(source_root):
                dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
                for fname in filenames:
                    if fname.endswith(REVIEW_TEXT_EXTS):
                        rel = os.path.relpath(os.path.join(dirpath, fname), source_root)
                        files.append(rel.replace(os.sep, "/"))
            files.sort()
            entry = "module.py" if kind == "module" else "channel.py" if kind == "channel" else "SKILL.md"

        wanted = file_rel if file_rel in files else entry
        full = os.path.realpath(os.path.join(source_root, wanted))
        if not full.startswith(source_root + os.sep) or not os.path.isfile(full):
            return api_result("file is not part of this module", success=False)

        max_chars = 500_000
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                code = f.read(max_chars)
        except Exception as e:
            return api_result(core.detail_error(e), success=False)

        # shell/exec smell checks only apply to runnable python entries
        if kind in ("module", "channel"):
            flags, warnings = library_review_flags(os.path.join(source_root, entry))
        else:
            flags, warnings = [], []

        return api_result({
            "library": library,
            "name": name,
            "kind": kind,
            "file": wanted,
            "files": files,
            "code": code,
            "truncated": len(code) >= max_chars,
            "flags": flags,
            "warnings": warnings
        })

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara
    # install/update/uninstall are kind-aware: mm returns (success, message, kind).
    # modules -> user_modules, channels -> user_channels, skills -> skills/,
    # themes -> user_webui_themes/. Only module/channel have pip dependencies
    # or need a restart.
    @app.post("/api/libraries/install")
    async def libraries_install(request: fastapi.Request):
        """Installs a module/channel/skill/theme from a library and installs its dependencies"""
        data = await request.json()
        library = (data.get("library") or "").strip()
        name = (data.get("name") or "").strip()

        mm = get_module_manager()
        success, message, kind = mm.install(library, name)
        if not success:
            return api_result(message, success=False)

        if kind in ("module", "channel"):
            pkg = "user_channels" if kind == "channel" else "user_modules"
            try:
                await core.modules.install_module_deps(__import__(pkg), name, channel.manager)
            except Exception as e:
                channel.log("libraries", f"dependency install failed for {name}: {core.detail_error(e)}")

        return api_result({
            "kind": kind,
            "restart_required": kind in ("module", "channel"),
            "message": message,
            "note": {
                "theme": "Pick it in Settings -> Appearance after a page reload.",
                "skill": "Run /skills reload to load it.",
            }.get(kind, ""),
        }, success=True)

    @app.post("/api/libraries/update")
    async def libraries_update(request: fastapi.Request):
        """Re-syncs a library and overwrites an installed entry with the newest version from it"""
        data = await request.json()
        library = (data.get("library") or "").strip()
        name = (data.get("name") or "").strip()

        mm = get_module_manager()
        success, message, kind = await mm.update(library, name)
        if not success:
            return api_result(message, success=False)

        if kind in ("module", "channel"):
            pkg = "user_channels" if kind == "channel" else "user_modules"
            try:
                await core.modules.install_module_deps(__import__(pkg), name, channel.manager)
            except Exception as e:
                channel.log("libraries", f"dependency install failed for {name}: {core.detail_error(e)}")

        return api_result({
            "kind": kind,
            "restart_required": kind in ("module", "channel"),
            "message": message,
            "note": {
                "theme": "Pick it in Settings -> Appearance after a page reload.",
                "skill": "Run /skills reload to load it.",
            }.get(kind, ""),
        }, success=True)

    @app.post("/api/libraries/uninstall")
    async def libraries_uninstall(request: fastapi.Request):
        """Removes an installed user module/channel and cleans up dependencies nothing else needs anymore"""
        data = await request.json()
        name = (data.get("name") or "").strip()

        mm = get_module_manager()

        # run the on_uninstall hook and dependency cleanup while the files still exist
        for kind in ("user_modules", "user_channels"):
            try:
                await core.modules.uninstall_module_deps(__import__(kind), name, channel.manager)
            except Exception as e:
                channel.log("libraries", f"dependency cleanup failed for {name}: {core.detail_error(e)}")

        success, message, kind = mm.uninstall(name)
        if not success:
            return api_result(message, success=False)

        return api_result({
            "kind": kind,
            "restart_required": kind in ("module", "channel"),
            "message": message,
            "note": "Run /skills reload to apply." if kind == "skill" else "",
        }, success=True)

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

        return api_result(data)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
    # serves the context breakdown (from channel.context.get_size()) for the webui context ring popup.
    @app.get("/api/system/context_size")
    async def get_context_size():
        """returns a detailed breakdown of the current context window usage"""
        try:
            size = await channel.context.get_size()
        except Exception as e:
            return api_result(core.detail_error(e), success=False)

        # -- AI GENERATED CODE (qwen3.8-flash-next-q4) :: 2026-09-22 02:50
        # expose the compression threshold (stored as a 0-1 ratio) as a
        # percentage so the popup can draw a marker line in the stacked bar
        threshold = core.config.get("model", "context_compression_threshold") or 0
        size["compression_threshold"] = round(float(threshold) * 100, 1)
        size["auto_compress"] = bool(core.config.get("model", "automatically_compress_context"))

        return api_result(size)

    @app.get("/api/system/logs")
    async def get_logs():
        return api_result(channel.logs)

    # -- POST
    @app.post("/api/system/restart")
    async def restart_server():
        await channel.manager.restart()

    # ----------------------------
    # Theme API endpoints
    # ----------------------------
    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara
    # themes now come from two places: the WebUI's bundled folder (built-ins)
    # and the root-level user_webui_themes/ folder (user themes, including ones
    # installed from module libraries). The user folder wins on name collisions.
    def user_themes_dir():
        return core.get_path("user_webui_themes", sandbox=False)

    def builtin_themes_dir():
        return os.path.join(channel.path, "themes")

    def themes_dirs():
        return [user_themes_dir(), builtin_themes_dir()]

    @app.get("/api/themes")
    async def get_themes():
        """Returns a list of available theme families with their supported modes (dark/light)"""
        families = {}

        # built-ins first, user themes override same-name families afterwards
        for themes_dir in reversed(themes_dirs()):
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
            return api_result(f"Theme family '{family_name}' not found", success=False)

        filepath = None
        for themes_dir in themes_dirs():
            candidate = os.path.join(themes_dir, f"{family_name}.json")
            if os.path.isfile(candidate):
                filepath = candidate
                break

        if not filepath:
            return api_result(f"Theme family '{family_name}' not found", success=False)

        try:
            with open(filepath, 'r', encoding='utf-8') as fh:
                theme_data = json.load(fh)
            return theme_data
        except Exception as e:
            channel.log(channel.name, f"failed to load theme {filepath}: {e}")
            return api_result(f"Failed to load theme: {str(e)}", success=False)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-04)
    # serve theme sidecar CSS: a .css file sitting next to a theme JSON with
    # the same name is auto-loaded by theming.js when that theme is active.
    # only .css files are served (no JS), and only from the themes dirs
    # (user themes first, then the WebUI built-ins).
    @app.get("/themes/{file_name}")
    async def theme_sidecar_css(file_name: str):
        if not file_name.endswith(".css"):
            raise fastapi.HTTPException(status_code=404, detail="Only CSS files are served")
        for themes_dir in themes_dirs():
            themes_dir = os.path.realpath(themes_dir)
            full_path = os.path.realpath(os.path.join(themes_dir, file_name))
            if full_path.startswith(themes_dir + os.sep) and os.path.isfile(full_path):
                return fastapi.responses.FileResponse(full_path, media_type="text/css")
        raise fastapi.HTTPException(status_code=404, detail="Theme CSS not found")

    def generate_cache_version():
        # generate an sw.js cache version based on this file's last modified time
        # because bumping sw.js's version manually each time i update the webui
        # is a total pain and i don't want to deal with it

        webui_folder = core.get_path("channels/webui")

        # Get the latest modification time among all files in the folder
        latest_mtime = os.path.getmtime(__file__)  # fallback to this file

        for root, dirs, files in os.walk(webui_folder):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime > latest_mtime:
                        latest_mtime = file_mtime
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    pass

        return f"v{int(latest_mtime)}"

    @app.get('/sw.js')
    async def service_worker():
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # bugfix: scanned channels/webui/static/, which hasn't existed
        # since the rewrite, so the precache list was always empty.
        # assets live in assets/ now (and keep their /assets/ url prefix).
        base_path = core.get_path("channels/webui")
        assets_base = os.path.join(base_path, 'assets')

        files_to_cache = []
        for subdir in ['js', 'css']:
            dir_path = os.path.join(assets_base, subdir)
            if os.path.isdir(dir_path):
                for root, _, files in os.walk(dir_path):
                    for filename in files:
                        full_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(full_path, assets_base)
                        files_to_cache.append('/assets/' + rel_path.replace(os.sep, "/"))
        files_to_cache.sort()

        sw_template_path = os.path.join(base_path, 'sw.js')
        with open(sw_template_path) as f:
            sw_code = f.read()

        version = generate_cache_version()

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
        # inject the precache list as a JSON string (sw.js wraps
        # {{FILE_LIST}} in quotes and JSON.parses it): keeps the template
        # itself valid JS. json.dumps escapes double/single quotes, so the
        # surrounding single-quoted literal can never be broken out of.
        sw_code = sw_code.replace('{{VERSION}}', version)
        sw_code = sw_code.replace('{{FILE_LIST}}', json.dumps(files_to_cache).replace("'", "\\'"))

        return fastapi.Response(
            content=sw_code,
            media_type='application/javascript',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
            }
        )

    @app.get('/manifest.json')
    async def manifest():
        """Serve the PWA manifest."""
        with open(os.path.join(channel.path, "manifest.json")) as f:
            manifest_data = json.loads(f.read())
        return manifest_data

    @app.get('/icon-192.png')
    async def icon_192():
        """Serve the 192x192 icon for PWA."""
        return fastapi.responses.FileResponse(os.path.join(channel.path, "icon-192.png"))

    @app.get('/icon-512.png')
    async def icon_512():
        """Serve the 512x512 icon for PWA."""
        return fastapi.responses.FileResponse(os.path.join(channel.path, "icon-512.png"))

    @app.get('/favicon.ico')
    async def favicon():
        """Serve the favicon for the web interface."""
        return fastapi.responses.FileResponse(os.path.join(channel.path, "favicon.ico"))

    # ------------------
    # WebSocket endpoint
    # ------------------
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: fastapi.WebSocket):
        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        # security: origin check. browsers always send Origin on WebSocket
        # handshakes; a foreign origin means a malicious page is trying to
        # drive this instance (CSRF-style). non-browser clients send no
        # Origin and stay allowed.
        ws_origin = websocket.headers.get("origin")
        if ws_origin and channel._origin_allowed(ws_origin, host_header=websocket.headers.get("host") or "") is False:
            channel.log(channel.name, f"websocket handshake rejected: foreign origin '{ws_origin}' (expected host '{channel.host}', port {channel.port}) - if this webui runs behind a proxy/tunnel, add that origin to the 'extra_allowed_origins' setting")
            await websocket.close(code=4003, reason="Foreign origin")
            return

        # WebSocket auth check
        if channel.config.get("require_login", False):
            # security: previously any non-empty cookie passed this check,
            # which made forging access trivial. verify the actual signed
            # session instead (starlette's SessionMiddleware runs for
            # websocket handshakes too and unsigns it into scope["session"]).
            ws_session = websocket.scope.get("session") or {}
            if not ws_session.get("authenticated", False):
                # check if rate limited
                # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
                client_ip = trusted_client_ip(websocket)
                now = time.time()

                if client_ip in channel.login_attempts:
                    channel.login_attempts[client_ip] = [
                        t for t in channel.login_attempts[client_ip] if now - t < 900
                    ]
                    if len(channel.login_attempts[client_ip]) >= 5:
                        channel.log(channel.name, f"websocket handshake rejected: rate limited ({client_ip})")
                        await websocket.close(code=4001, reason="Rate limited")
                        return

                channel.log(channel.name, f"websocket handshake rejected: session not authenticated (cookie_present={getattr(channel, 'session_cookie_name', 'session') in websocket.cookies}, client={client_ip})")
                await websocket.close(code=4001, reason="Unauthorized")
                return

        ws_mgr = channel.websocket_manager
        await ws_mgr.connect(websocket)

        try:
            while True:
                data_text = await websocket.receive_text()

                try:
                    data = json.loads(data_text)
                    msg_type = data.get("type")

                    match msg_type:
                        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
                        # app-level heartbeat: an in-band frame every ~25s
                        # keeps idle-socket reapers (reverse proxies, tunnels)
                        # off the connection no matter what the protocol-level
                        # pings are doing, and proves liveness end to end
                        # (through proxies that mangle ws control frames).
                        case "ping":
                            await websocket.send_json({"type": "pong"})
                        case "stop":
                            if channel:
                                await channel.manager.API.cancel()
                        case "reload_messages":
                            await ws_mgr.broadcast({
                                "type": "sync"
                            })
                        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                        # these handlers now call the same shared ops as the
                        # REST routes (rename persists again, broadcasts use
                        # 'id' like the frontend expects)
                        case "rename":
                            new_title = data.get("title")
                            if channel and new_title:
                                await op_chat_rename(channel, new_title)
                        case "switch_chat":
                            new_chat_id = data.get("chat_id")
                            if new_chat_id:
                                success = await op_chat_switch(channel, new_chat_id)
                                if not success:
                                    await ws_mgr.broadcast({"type": "error", "content": "Failed to load chat"})
                        case "new_chat":
                            await op_chat_new(channel)
                        case "chat_delete":
                            chat_id = data.get("chat_id")
                            if not chat_id:
                                return False

                            await op_chat_delete(channel, chat_id)
                        case "user_message":
                            text = data.get("content")
                            files_data = data.get("files")

                            # bugfix: referenced undefined `files` here
                            if not text and not files_data:
                                break

                            files_dict = None
                            if files_data:
                                # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                                # enforce enable_file_upload server-side too:
                                # hiding the button is only cosmetic otherwise
                                if not channel.config.get("enable_file_upload", True):
                                    await ws_mgr.broadcast({
                                        "type": "error",
                                        "error": "File uploads are disabled"
                                    })
                                    continue

                                files_dict = {
                                    f["name"]: base64.b64decode(f["data"])
                                    for f in files_data
                                }

                            chat_id = channel.context.chat.get("id") or "default"
                            await ws_mgr.start_stream(channel, chat_id, message=text, files=files_dict)
                        case "message_edit":
                            index = data.get("index")
                            if index < 0:
                                return False

                            message = await channel.context.chat.messages.get(index)
                            message["content"] = data.get("content")
                            await channel.context.chat.messages.edit(index, message)

                            await ws_mgr.broadcast({
                                "type": "sync"
                            })
                        case "message_delete":
                            index = data.get("index")
                            if index < 0:
                                return False

                            await channel.context.chat.messages.delete_from(index)
                            await ws_mgr.broadcast({
                                "type": "sync"
                            })
                        case "message_regenerate":
                            index = data.get("index")

                            if index is not None and channel:
                                last_user_message_index = await channel.context.chat.messages.get_last_message_with_role("user", cutoff_index=index)

                                if last_user_message_index == -1:
                                    await ws_mgr.broadcast({
                                        "type": "error",
                                        "error": "Could not regenerate message (no preceding user message found)"
                                    })
                                    return

                                user_message = await channel.context.chat.messages.get(last_user_message_index)

                                # delete_from deletes all messages AFTER the target, so we need to do index-1
                                # max(0, index) clamps it so that it never goes below 0
                                await channel.context.chat.messages.delete_from(max(0, last_user_message_index))

                                await ws_mgr.broadcast({"type": "sync"})
                                await ws_mgr.start_stream(channel, channel.context.chat.get("id"), user_message.get("content"))
                        case _:
                            channel.log(channel.name, f"Unknown websocket command received: {msg_type}")

                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    channel.log(channel.name, f"WebSocket command error: {core.detail_error(e)}")

        except fastapi.WebSocketDisconnect as e:
            ws_mgr.disconnect(websocket)
        except Exception as e:
            channel.log(channel.name, f"WebSocket error: {core.detail_error(e)}")
            ws_mgr.disconnect(websocket)

    return app

# -------------------
# Websocket Manager
# -------------------
class WebSocketManager:
    def __init__(self, channel):
        self.channel = channel

        self.active_connections = []

        self.active_stream_task = None
        self.webui_ready = False

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
        # the backend is now the single source of truth for stream state.
        # the frontend used to infer it from ~10 different websocket events,
        # which drifted whenever a client missed a message or reconnected
        # mid-stream. states: idle, message_sending, message_received,
        # processing, thinking, streaming, calling_tools, processing_tools
        self.stream_state = "idle"

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
        # live-turn segment buffer: the latest snapshot of every segment the
        # turncollector has emitted for the in-progress stream, in order.
        # a websocket that connects mid-stream (page reload) gets a replay,
        # so the frontend can rebuild the entire live turn instead of only
        # seeing segments streamed from now on. entries are serialized
        # snapshots (fresh objects per broadcast), replaced in place while
        # the same segment keeps growing.
        self.turn_segments = []

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
    def record_turn_segment(self, segment: dict):
        """track the newest snapshot of the streaming turn's segments.
        mirrors the frontend's segment-identity rule: same type and same
        tool_call_id = the same segment growing, otherwise a new one."""
        if self.turn_segments:
            last = self.turn_segments[-1]
            if (last.get("type") == segment.get("type")
                    and last.get("tool_call_id") == segment.get("tool_call_id")):
                self.turn_segments[-1] = segment
                return
        self.turn_segments.append(segment)

    async def set_stream_state(self, state: str):
        """update the authoritative stream state and notify all clients.
        deduped, so high-frequency token paths can set it every token for free."""
        if state == self.stream_state:
            return
        self.stream_state = state

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
        # the segment buffer only ever belongs to the in-progress stream:
        # wipe it when a new stream starts and when one finishes.
        if state in ("message_sending", "idle"):
            self.turn_segments = []

        await self.broadcast({"type": "stream_state", "state": state})

    async def connect(self, websocket: fastapi.WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        current_chat_id = self.channel.context.chat.get("id")

        if current_chat_id:
            await websocket.send_json({
                "type": "ready"
            })

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
        # push the current stream state to the freshly connected client, so
        # a page reload or reconnect mid-stream lands in the right state
        # instead of assuming idle
        await websocket.send_json({
            "type": "stream_state",
            "state": self.stream_state
        })

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara
        # mid-stream reconnect: replay the segments the in-progress stream
        # has emitted so far, so a page reload resumes the live turn where
        # it left off (all of it, not just whatever streams in next). the
        # frontend's turn_stream handler rebuilds the turn from these exactly
        # like it would have watched them live, because each snapshot is
        # fully accumulated for its segment.
        if self.stream_state != "idle" and self.turn_segments:
            for segment in self.turn_segments:
                await websocket.send_json({
                    "type": "turn_stream",
                    "turn": segment
                })

        asyncio.create_task(self.queue_ready_signal())

    def disconnect(self, websocket: fastapi.WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def queue_ready_signal(self):
        while not self.webui_ready:
            await asyncio.sleep(0.1)
        await self.broadcast({"type": "ready"})

    def send_ready_signal(self):
        self.webui_ready = True

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                if connection.client_state == starlette.websockets.WebSocketState.CONNECTED:
                    await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def _stream_task(self, message: str, index, files: list = None):
        self.channel._ws_stream_index = index

        try:
            await self.channel.push_stream(
                self.channel.send_stream(
                    message=message,
                    files=files,
                    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                    # admin commands are now gated by enable_admin_settings
                    # (the old allow_admin_commands toggle was merged into it)
                    commands_authorized=self.channel.config.get("enable_admin_settings", True)
                )
            )
        finally:
            # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
            # always finalize the stream, no matter what: the state returns
            # to idle here (also on cancellation), so clients can never get
            # stuck in a streaming state. broadcast first, state second:
            # stream_complete does UI handoff work that still reads the state.
            await self.broadcast({
                "type": "stream_complete"
            })
            await self.set_stream_state("idle")

    async def start_stream(self, channel, chat_id: str, message: str, files: list = None):
        if self.active_stream_task and not self.active_stream_task.done():
            self.active_stream_task.cancel()

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-12)
        # a new stream begins: the backend announces it right away, so every
        # connected client (not just the one that sent the message) shows
        # the typing indicator immediately
        await self.set_stream_state("message_sending")

        next_index = len(await channel.context.chat.messages.get())

        try:
            self.active_stream_task = asyncio.create_task(self._stream_task(message, next_index, files=files))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            channel.log(channel.name, f"Background stream error: {core.detail_error(e)}")

