import core
import asyncio
import time
import uuid
import uvicorn
import json
import socket
import fastapi
import fastapi.responses
import fastapi.middleware.cors

# -------------------------
#   CONFIGURATION
# -------------------------

class ApiBridge(core.channel.Channel):
    """
    Lets you use any application or UI (for example, koboldlite, openwebui, etc) to talk to your OpenLumara instance. Simply connect your chosen application to the port you specify in this channel's settings.
    """

    settings = {
        "network_mode": {
            "type": "select",
            "options": {
                "local": "Allows only the device OpenLumara is running on to access the API bridge (sets hostname to `localhost`)",
                "internet": "Allows any device to access the API bridge (sets hostname to `0.0.0.0`)",
                "custom": "Use the custom hostname defined below"
            },
            "default": "local"
        },
        "custom_host": {
            "description": "If you want to use a custom hostname, set it here. If you don't know what that is, don't bother with this! Just use the network mode setting on either local or internet.",
            "default": None
        },
        "port": {
            "type": "number",
            "description": "The port for the API server.",
            "default": 8000
        },
        "api_key_required": {
            "type": "boolean",
            "description": "Whether to require an API key to use this api endpoint. Recommended for public instances, otherwise anyone can use your AI!",
            "default": False
        },
        "api_key": {
            "type": "string",
            "description": "Your chosen API key. This acts like a password, so choose a good one!",
            "default": "sk-openlumara-dummy-key"
        },
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        },
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": False
        }
    }

    dependencies = ["fastapi", "uvicorn"]
    # pydantic and httpx are already included with openlumara

    # -------------------------
    #   EVENT HANDLERS
    # -------------------------

    async def on_ready(self):
        network_mode = self.config.get("network_mode")
        self.host = None
        self.port = self.config.get("port")
        match network_mode:
            case "local":
                self.host = "127.0.0.1"
            case "internet":
                self.host = "0.0.0.0"
            case "custom":
                self.host = self.config.get("custom_host")
            case _:
                self.host = "127.0.0.1"

        self.server = None
        self.server_running = False

    async def run(self):
        """The main loop: Starts the FastAPI server."""
        app = fastapi.FastAPI(title="OpenLumara OpenAI Bridge")

        # allow requests from any origin
        app.add_middleware(
            fastapi.middleware.cors.CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"]
        )

        # require API key if set up that way
        @app.middleware("http")
        async def auth_middleware(request: fastapi.Request, call_next):
            if self.config.get("api_key_required"):
                auth_header = request.headers.get("Authorization")
                if not auth_header or auth_header != f"Bearer {self.config.get('api_key')}":
                    return fastapi.responses.JSONResponse(
                        status_code=401,
                        content={"error": {"message": "Invalid API key", "type": "invalid_request_error", "param": None, "code": "invalid_api_key"}}
                    )
            return await call_next(request)

        @app.get("/v1")
        async def index():
            return fastapi.responses.RedirectResponse("/v1/health", status_code=307)

        @app.post("/v1")
        async def completions_redirect():
            return fastapi.responses.RedirectResponse("/v1/chat/completions", status_code=307)

        @app.get("/v1/health")
        async def health():
            return {"status": "OK"}

        @app.get("/v1/models")
        async def list_models():
            """Returns a fake model list that basically just contains openlumara as a model. Use the `/model` command to switch models inside openlumara."""
            return {
                "object": "list",
                "data": [{
                    "id": "openlumara",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "openlumara"
                }]
            }

        @app.post("/v1/chat/completions")
        async def chat_completions(request: fastapi.Request):
            body = await request.json()
            
            if not body.get("messages"):
                raise fastapi.HTTPException(status_code=400, detail="No messages provided")
            
            last_msg = body["messages"][-1]
            stream = body.get("stream", False)

            if stream:
                return fastapi.responses.StreamingResponse(
                    self._stream_handler(last_msg.get("content", ""), "openlumara"),
                    media_type="text/event-stream"
                )
            else:
                return await self._completion_handler(last_msg.get("content", ""), body.get("model", "openlumara"))

        # Start the server with SO_REUSEADDR to handle "address already in use" errors
        # Create a socket with SO_REUSEADDR
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(5)
            
            config = uvicorn.Config(app, host=self.host, port=self.port, log_level="error")
            self.server = uvicorn.Server(config)

            self.log("api bridge", f"The API bridge is up and running on {self.host}:{self.port}")
            self.server_running = True
            await self.server.serve(sockets=[sock])
            self.server_running = False
            sock.close()
        except Exception as e:
            self.log("api bridge", f"Error while starting API bridge: {core.detail_error(e)}")

    async def on_shutdown(self):
        # this is a flag exposed by uvicorn itself, which causes it to start gracefully shutting down when set
        self.server.should_exit = True

        # wait for uvicorn to actually finish shutting down
        try:
            await asyncio.wait_for(self.server.shutdown(), timeout=5.0)
        except (AttributeError, asyncio.TimeoutError):
            # fallback: just give it a moment to release the socket
            await asyncio.sleep(0.5)

        self.log("api bridge", "API bridge server shut down successfully.")

    async def _completion_handler(self, message, model):
        try:
            # send the request to the framework and format it
            response_dict = await self.send(message, commands_authorized=True)
            response_dict = self.format_message(response_dict)
            content = response_dict.get("content", "")

            # return the response as a full openAI-compatible json object
            return fastapi.responses.JSONResponse({
                "id": f"chatcmpl-{uuid.uuid4()}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": 0, 
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
            })
        except Exception as e:
            self.log(self.name, f"Error in completion: {str(e)}")
            return fastapi.responses.JSONResponse(
                status_code=500,
                content={"error": {"message": str(e), "type": "server_error", "param": None, "code": "internal_error"}}
            )

    async def _stream_handler(self, message, model):
        try:
            chat_id = f"chatcmpl-{uuid.uuid4()}"
            created_time = int(time.time())

            # Initial empty chunk to satisfy some clients
            yield f"data: {self._openai_chunk(chat_id, created_time, model, '')}\n\n"

            try:
                async for token in self.format_stream_for_text(
                    self.send_stream(message, commands_authorized=True)
                ):
                    token_type = token.get("type")
                    token_content = token.get("content")

                    if token_type == "formatted":
                        yield f"data: {self._openai_chunk(chat_id, created_time, model, token_content)}\n\n"
            finally:
                yield "data: [DONE]\n\n"

        except Exception as e:
            self.log(self.name, f"Error in stream: {core.detail_error(e)}")
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

    def _openai_chunk(self, chat_id, created, model, delta):
        chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"content": delta},
                "finish_reason": None
            }]
        }
        return json.dumps(chunk)

    async def on_push(self, msg):
        # no
        pass

    def on_log(self, cat, msg):
        # no
        return
