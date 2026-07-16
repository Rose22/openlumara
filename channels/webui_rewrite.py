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

    async def run(self):
        self.log("webui", f"Starting WebUI on {self.url}")

        # serve the app using uvicorn
        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="error")
        self.server = uvicorn.Server(config)

        await self.server.serve()

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
            return api_result(success=False)

        return api_result(channel.context.chat.data, success=True)

    @app.get("/api/chat/messages")
    async def chat_messages():
       messages = await channel.context.chat.get() 
       return api_result(messages, success=(len(messages)>0))

    @app.get("/api/chats")
    async def get_chats(request: fastapi.Request):
        return {
            "chats": await channel.context.chat.get_all()
        }

    # -- POST
    @app.post("/api/chat/new")
    async def chat_new():
        return api_result(success=await channel.context.chat.new())

    @app.post("/api/chat/delete/{id}")
    async def chat_delete(id: str):
        return api_result(success=await channel.context.chat.delete(id))

    return app
