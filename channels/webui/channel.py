"""
OpenLumara WebUI

A full-featured, stable, cross-device webui with PWA support,
meant to be the default UI with which to interface with OpenLumara

This is as much a note to myself as to any AI's that touch this:
---
Anything implemented in the WebUI must always be implemented in the core,
every channel must be inter-compatible,
the framework must never end up in a state where you can do something in the webui
that you can't do in other channels.

Everything across OpenLumara must always be doable across every channel,
by implementing stuff into the core rather than clientside.
---
"""

# openlumara core
import core

# system
import os
import asyncio
import urllib.parse

# security libraries
import secrets

# webui stuff
import fastapi
import fastapi.templating
import uvicorn

# sibling modules this channel is assembled from
import channels.webui.utils as utils
import channels.webui.ws_manager as ws_manager
import channels.webui.server as webui_server
import channels.webui.ui_extensions as ui_extensions

# --------------------
# Channel class
# --------------------
class Webui(core.channel.Channel, ui_extensions.UiExtensionsMixin):
    """A full-featured, modern webUI for OpenLumara, providing you with a privacy-friendly option that doesn't depend on any external chat providers"""
    version = 2.0

    # stream index registered by the ws stream-start handler; -1 = none
    _ws_stream_index = -1

    dependencies = [
        "fastapi==0.162.0",
        "starlette==1.10.0",
        "itsdangerous==2.2.0",
        "websockets==17.3",
        "jinja2==3.1.6",
        "uvicorn==0.54.0",
        "python-multipart==0.0.32",
        "markupsafe==3.0.4"
    ]

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
            "description": "Whether the processing chain can be expanded to view the AI's thoughts and intermediate steps. When disabled, it stays locked in its collapsed state (showing only 'Processing..'/'Thinking..' labels), so you always see that the AI is busy without being able to peek inside. Very useful for public instances!",
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
        """
        True when an Origin header refers back to this same webui instance.
        localhost and 127.0.0.1 are treated as the same host. Used to reject
        cross-origin WebSocket handshakes
        """
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

        # allow extra allowed origins, for if you use a custom domain name
        # otherwise, the websocket will refuse the connection
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

    async def on_system_prompt(self):
        return """
WebUI layout:
- Sidebar: chat search box, tag filter button, chat list grouped by date modified, new chat button
- Chat window:
    - header: title | blank space | model dropdown | settings button (gear icon, opens settings dialog) | chat history export button (download icon) | clear chat button (trashcan icon)
    - messages area, contains current chat's messages
    - input bar: upload button | input field | send/stop button

The WebUI has support for an extra feature:
- You can render HTML and SVG's directly in the user's browser by outputting the code without fencing it in ```code blocks```
""".strip()

    async def on_ready(self):
        # ---- security stuff
        self.session_secret_value = ""
        secret_file = core.get_data_path("webui_session_secret")
        try:
            if os.path.exists(secret_file):
                with open(secret_file, "r", encoding="utf-8") as f:
                    self.session_secret_value = f.read().strip()
        except OSError:
            self.session_secret_value = ""
            
        if not self.session_secret_value:
            self.session_secret_value = secrets.token_urlsafe(48)
            try:
                fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(self.session_secret_value)
                self.log("webui", "session signing key stored in webui_session_secret (data folder, 0600)")
            except OSError:
                self.log("webui", "WARNING: could not persist the session key; all sessions will reset on restart")
                
        # ----------------------
        
        # paths
        self.path = core.get_path(os.path.join("channels", "webui"))
        self.template_path = os.path.join(self.path, "templates")
        self.assets_path = os.path.join(self.path, "assets")
                
        # fastapi-specific instances
        self.templates = fastapi.templating.Jinja2Templates(self.template_path)
        self.setup_ui_extensions()

        # aaand create it
        self.app = await webui_server.create_fastapi(self)

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
        self.websocket_manager = ws_manager.WebSocketManager(self)

        # shell-style input history, persisted server-side
        self.input_history = core.storage.StorageList(
            name="webui_input_history",
            type="json",
            manager=self
        )

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

            ws_ping_interval=20,
            ws_ping_timeout=90,

            # only log critical http errors
            log_level="error"
        )
        self.server = uvicorn.Server(config)

        await self.server.serve()

    async def on_push(self, message):
        if isinstance(message, dict) and message.get("role") == "user":
            return

        await self.websocket_manager.broadcast({
            "type": "push",
            "content": message
        })

    async def on_stream(self, stream):
        user_message_confirmed = False
        index = self._ws_stream_index

        restart_grouping = False

        async def grouped_events():
            nonlocal restart_grouping
            while True:
                restart_grouping = False
                grouped = self.turncollector.group_stream(stream)
                async for event in grouped:
                    yield event
                    if restart_grouping:
                        break
                await grouped.aclose()
                if not restart_grouping:
                    return

        async for event in grouped_events():
            payload = utils.serialize_for_json(event)

            if event.get("type") == "token":
                token = event.get("content")
                token_type = token.get("type")
                match token_type:
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
                    case "queue_flushed":
                        await self.websocket_manager.broadcast({
                            "type": "queue_flushed",
                            "messages": token.get("content") or [],
                            "end_of_chain": bool(token.get("end_of_chain", False))
                        })

                        if token.get("end_of_chain"):
                            restart_grouping = True
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

                        # track stream state backend-side based on tokens
                        push_context_size = False
                        match token_type:
                            case "reasoning":
                                await self.websocket_manager.set_stream_state("thinking")
                            case "content":
                                await self.websocket_manager.set_stream_state("streaming")
                            case "prompt_progress":
                                # prompt eval between tool rounds
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
                            case "token_usage":
                                push_context_size = True

                        await self.websocket_manager.broadcast({
                            "type": "token",
                            "content": token
                        })

                        if push_context_size:
                            try:
                                size = utils.serialize_for_json(await self.context.get_size())
                                await self.websocket_manager.broadcast({
                                    "type": "context_size",
                                    "content": size,
                                })
                            except Exception as e:
                                self.log(self.name, f"error sending context size: {core.detail_error(e)}")

            elif event.get("type") == "step":
                step = payload.get("content")
                if step is None:
                    continue

                self.websocket_manager.record_step_snapshot(step)

                await self.websocket_manager.broadcast({
                    "type": "turn_step",
                    "step": step
                })

            elif event.get("type") == "final":
                messages = payload.get("content") or []
                self.websocket_manager.record_final_snapshot(messages)

                await self.websocket_manager.broadcast({
                    "type": "turn_final",
                    "messages": messages
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
