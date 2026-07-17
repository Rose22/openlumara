"""
OpenLumara WebUI - manual rewrite

This is daunting, but i'm rewriting the entire WebUI from the ground up, manually, with minimal AI-generated code, due to high amount of unpredictable bugs in the previous version, and sheer difficulty of maintaining it

The plan is to use FastAPI for the backend again, but manually written, and alpine.js for the frontend, since it's nice and lightweight and not React.

Let's get this WebUI up to the standards of the rest of openlumara, since it's become basically the primary way everyone uses it..

~ Rose22
"""

import os
import fastapi, fastapi.templating, fastapi.staticfiles
import uvicorn

import core

# --------------------
# Channel class
# --------------------
class WebuiRewrite(core.channel.Channel):
    """A full-featured, modern webUI for OpenLumara, providing you with a privacy-friendly option that doesn't depend on any external chat providers"""
    version = 2.0

    dependencies = [
        "fastapi",
        "starlette>=1.0.1",
        "jinja2",
        "uvicorn"
    ]

    # these settings are taken straight from the previous webUI,
    # and currently, many of the settings don't do anything yet
    # but i plan to support these of course
    settings = {
        "title": {
            "default": "OpenLumara",
            "description": "The title to show in the header, above the chat window"
        },
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
            "description": "If you want to use a custom hostname, set it here. If you don't know what that is, don't bother with this! Just use the network mode setting on either local or internet.",
            "default": None
        },
        "port": {
            "description": "What port to run the WebUI on. Set this to 80 to be able to access it like a normal website, and anything else to access it on that port (for example http://yourdomain.org:3000)",
            "default": 3000
        },
        "require_login": {
            "description": "Whether to protect the WebUI with a username and password. **Highly recommended if your webui is exposed to the internet!!**",
            "default": False
        },
        "username": "admin",
        "password": "admin",
        "debug_mode": {
            "description": "When enabled, this will show a ton of webui-related messages in the server console. Very useful for debugging webui related issues!",
            "default": False
        }
    }

    async def on_ready(self):
        debug = self.config.get("debug_mode")

        # paths
        self.path = core.get_path(os.path.join("channels", "webui_rewrite"))
        self.template_path = os.path.join(self.path, "templates")
        self.assets_path = os.path.join(self.path, "assets")

        # fastapi-specific instances
        if debug: self.log(self.name, "Loading templates..")
        self.templates = fastapi.templating.Jinja2Templates(self.template_path)

        # aaand create it
        if debug: self.log(self.name, "Creating FastAPI instance..")
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

        # initialize the websocket manager
        self.websocket_manager = WebSocketManager(self)

    async def run(self):
        self.log("webui", f"Starting WebUI on {self.url}")

        # serve the app using uvicorn
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="error")
        self.server = uvicorn.Server(config)

        await self.server.serve()

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

# -------------------
# Websocket Manager
# -------------------
# TODO: clean this up
class WebSocketManager:
    def __init__(self, channel):
        self.channel = channel

        self.active_connections = []

        self.log_buffer = []
        self.max_log_buffer = 1000

        self.stream_buffer = []
        self.active_stream_task = None
        self.active_chat_id = None
        self.webui_ready = False

    async def connect(self, websocket: fastapi.WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        current_chat_id = await self.channel.context.chat.get_id()

        if self.log_buffer:
            await websocket.send_json({
                "type": "log_history",
                "logs": self.log_buffer
            })

        if current_chat_id:
            await websocket.send_json({
                "type": "sync_state",
                "active_chat_id": current_chat_id,
                "buffer": self.stream_buffer
            })

        asyncio.create_task(self.queue_ready_signal())

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.connection_users.pop(websocket, None)

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
                if connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    def add_log(self, category: str, message: str):
        self.log_buffer.append({
            "category": category,
            "message": message
        })
        if len(self.log_buffer) > self.max_log_buffer:
            self.log_buffer = self.log_buffer[-self.max_log_buffer:]

    async def start_background_stream(self, chat_id: str, generator):
        if self.active_stream_task and not self.active_stream_task.done():
            self.active_stream_task.cancel()

        self.active_chat_id = chat_id
        self.stream_buffer = []
        next_index = len(await channel.context.chat.get())

        async def stream_worker():
            try:
                async for token_data in generator:
                    if isinstance(token_data, dict):
                        p_type = token_data.get("type")
                        status_str = "idle"
                        if p_type == "reasoning": status_str = "thinking"
                        elif p_type == "content": sttus_str = "content"
                        elif p_type in ["tool_call_delta", "tool", "tool_calls"]: status_str = "tool_call"
                        elif p_type == "tool": status_str = "tool_exec"

                        payload = serialize_for_json(token_data)

                        self.stream_buffer.append(payload)
                        await self.broadcast({
                            "type": "token",
                            "message": payload
                        })
                    else:
                        self.stream_buffer.append(str(token_data))
                        await self.broadcast({
                            "type": "token",
                            "content": token_data
                        })

                await self.broadcast({
                    "type": "stream_complete",
                    "buffer": self.stream_buffer,
                    "index": next_index
                })

                self.stream_buffer = []
                self.active_chat_id = None

            except asyncio.CancelledError:
                pass
            except Exception as e:
                channel.log("webui", f"Background stream error: {core.detail_error(e)}")
                self.stream_buffer = []
                self.active_chat_id = None

        self.active_stream_task = asyncio.create_task(stream_worker())

# -------------------
# FastAPI creator (contains routes and so on)
# -------------------
def api_result(obj = None, success: bool = True):
    if obj is None:
        result = {}
    else:
        result = obj

    return {"data": result, "success": success}

async def create_fastapi(channel):
    app = fastapi.FastAPI()

    debug = channel.config.get("debug_mode")

    # serve asset files (formerly /static) using fastAPI's mount()
    if debug: channel.log(channel.name, "Serving assets..") 
    app.mount("/assets", fastapi.staticfiles.StaticFiles(directory=channel.assets_path), name="assets")

    @app.get("/")
    async def root(request: fastapi.Request):
        js_files = os.listdir(os.path.join(channel.assets_path, "js"))
        js_files.remove("libs")

        return channel.templates.TemplateResponse(request, "index.html", {
            "version": channel.version,
            "css_files": os.listdir(os.path.join(channel.assets_path, "css")),
            "js_files": js_files
        })

    # ------------------
    # API routes (/api)
    # ------------------

    # --- chats
    # -- GET
    @app.get("/api/chat/load/{id}")
    async def chat_load(id: str):
        success = await channel.context.chat.load(id)
        if not success:
            # that likely means this is already the loaded chat
            if not channel.context.chat.current:
                return api_result(success=False)

            return api_result(channel.context.chat.data[channel.context.chat.current], success=True)

        return api_result(channel.context.chat.data[channel.context.chat.current], success=True)

    @app.get("/api/chat/messages")
    async def chat_messages():
       messages = await channel.context.chat.get() 
       return api_result(messages, success=(len(messages)>0))

    @app.get("/api/chats")
    async def get_chats(request: fastapi.Request):
        filtered_chats = []

        # get rid of messages, for faster loading
        for chat in await channel.context.chat.get_all():
            chat_copy = dict(chat)
            chat_copy.pop("messages")
            filtered_chats.append(chat_copy)

        return api_result(filtered_chats, success=True)

    @app.get("/api/chats/categories")
    async def get_chat_categories():
        return api_result(await channel.context.chat.get_categories(), True)

    # -- POST
    @app.post("/api/chat/new")
    async def chat_new():
        return api_result(success=await channel.context.chat.new())

    @app.post("/api/chat/delete/{id}")
    async def chat_delete(id: str):
        return api_result(success=await channel.context.chat.delete(id))

    return app

    # ------------------
    # WebSocket endpoint
    # ------------------
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: fastapi.WebSocket):
        ws_mgr = channel.websocket_manager
        await ws_mgr.connect(websocket, user)

        try:
            while True:
                data_text = await websocket.receive_text()
                try:
                    data = json.loads(data_text)
                    msg_type = data.get("type")

                    if msg_type == "stop":
                        if channel:
                            await channel.manager.API.cancel()
                            ws_mgr.stream_buffer.clear()

                    elif msg_type == "cancel":
                        stream_id = data.get("id")
                        if stream_id:
                            channel.stream_cancellations.add(stream_id)

                    elif msg_type == "reload_messages":
                        await ws_mgr.broadcast({
                            "type": "messages_updated",
                            "messages": await channel.context.chat.get()
                        })

                    elif msg_type == "rename":
                        new_title = data.get("title")
                        if channel and new_title:
                            await channel.context.chat.set_title(new_title)
                            await ws_mgr.broadcast({
                                "type": "chat_metadata_updated",
                                "title": new_title,
                                "tags": await channel.context.chat.get_tags() or []
                            })

                    elif msg_type == "switch_chat":
                        new_chat_id = data.get("chat_id")
                        if new_chat_id:
                            if ws_mgr.active_stream_task and not ws_mgr.active_stream_task.done():
                                ws_mgr.active_stream_task.cancel()

                            await channel.context.chat.load(new_chat_id)
                            ws_mgr.active_chat_id = new_chat_id

                            await ws_mgr.broadcast({
                                "type": "chat_switched",
                                "chat_id": new_chat_id,
                                "buffer": ws_mgr.stream_buffer
                            })

                    elif msg_type == "new_chat":
                        if ws_mgr.active_stream_task and not ws_mgr.active_stream_task.done():
                            ws_mgr.active_stream_task.cancel()

                        new_id = await channel.context.chat.new()
                        ws_mgr.active_chat_id = new_id

                        await ws_mgr.broadcast({
                            "type": "chat_switched",
                            "chat_id": new_id,
                            "buffer": []
                        })

                    elif msg_type == "chat_delete":
                        chat_id = data.get("chat_id")
                        if not chat_id:
                            return False

                        await channel.context.chat.delete(chat_id)
                        await ws_mgr.broadcast({
                            "type": "chat_switched",
                            "chat_id": channel.context.chat.current,
                            "buffer": []
                        })

                    elif msg_type == "user_message":
                        content = data.get("content")
                        if content:
                            try:
                                chat_id = await channel.context.chat.get_id() or "default"
                                payload = content if isinstance(content, dict) else {"role": "user", "content": content}
                                await start_ai_stream_task(channel, chat_id, payload)
                            except Exception as e:
                                channel.log("webui", f"WebSocket user_message error: {core.detail_error(e)}")
                                await ws_mgr.broadcast({
                                    "type": "error",
                                    "error": str(e)
                                })

                    elif msg_type == "message_delete":
                        index = data.get("index")
                        if not index:
                            return False

                        await channel.context.chat.delete_from(index-1)
                        await ws_mgr.broadcast({
                            "type": "messages_updated",
                            "messages": await channel.context.chat.get()
                        })

                    elif msg_type == "message_regenerate":
                        index = data.get("index")

                        if index is not None and channel:
                            last_user_message_index = await channel.context.chat.get_last_message_with_role("user", cutoff_index=index)
                            user_message = await channel.context.chat.get_message(last_user_message_index)
                            await channel.context.chat.delete_from(last_user_message_index-1)

                            if user_message:
                                await ws_mgr.broadcast({
                                    "type": "messages_updated",
                                    "messages": await channel.context.chat.get()
                                })
                                await start_ai_stream_task(channel, await channel.context.chat.get_id(), user_message)
                            else:
                                await ws_mgr.broadcast({
                                    "type": "error",
                                    "error": "Could not regenerate message (no preceding user message found)."
                                })

                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    channel.log("webui", f"WebSocket command error: {core.detail_error(e)}")

        except WebSocketDisconnect:
            ws_mgr.disconnect(websocket)
        except Exception as e:
            channel.log("webui", f"WebSocket error: {core.detail_error(e)}")
            ws_mgr.disconnect(websocket)


