import core
import fastapi
import uvicorn

class WebuiRewrite(core.channel.Channel):
    dependencies = [
        "fastapi",
        "starlette>=1.0.1",
        "uvicorn"
    ]

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
        "password": "admin"
    }

    async def on_ready(self):
        self.app = await create_fastapi(self)

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

        config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="error")
        self.server = uvicorn.Server(config)

        await self.server.serve()

async def create_fastapi(channel):
    app = fastapi.FastAPI()

    @app.get("/")
    async def root():
        return {"message": "Working!"}

    return app
