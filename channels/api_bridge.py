import core
import asyncio
import time
import uuid
import uvicorn
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union

class ApiBridge(core.channel.Channel):
    """
    Lets you use any application or UI (for example, koboldlite, openwebui, etc) to talk to your OpenLumara instance. Simply connect your chosen application to the port you specify in this channel's settings.
    """

    # -------------------------
    #   CONFIGURATION
    # -------------------------

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
        }
    }

    dependencies = ["fastapi", "uvicorn"]
    # pydantic and httpx are already included with openlumara

    # -------------------------
    #   MODELS (OpenAI Spec)
    # -------------------------

    class ChatMessage(BaseModel):
        role: str
        content: Optional[str] = None
        name: Optional[str] = None

    class ChatCompletionRequest(BaseModel):
        model: str
        messages: List[ChatMessage]
        stream: Optional[bool] = False
        temperature: Optional[float] = 1.0
        top_p: Optional[float] = 1.0
        n: Optional[int] = 1
        max_tokens: Optional[int] = None
        stop: Optional[Union[str, List[str]]] = None
        presence_penalty: Optional[float] = 0.0
        frequency_penalty: Optional[float] = 0.0

    class Model(BaseModel):
        id: str
        object: str = "model"

    class ModelsResponse(BaseModel):
        object: str = "list"
        data: List[Model]

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

        self.log("api bridge", f"The bridge is up and running on {self.host}:{self.port}")

    async def run(self):
        """The main loop: Starts the FastAPI server."""
        app = FastAPI(title="OpenLumara OpenAI Bridge")

        # allow requests from any origin
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # require API key if set up that way
        @app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            if self.config.get("api_key_required"):
                auth_header = request.headers.get("Authorization")
                if not auth_header or auth_header != f"Bearer {self.config.get('api_key')}":
                    return JSONResponse(
                        status_code=401,
                        content={"error": {"message": "Invalid API key", "type": "invalid_request_error", "param": None, "code": "invalid_api_key"}}
                    )
            return await call_next(request)

        @app.get("/v1/models")
        async def list_models():
            """Returns a list of available models."""
            models = []
            for model_id in await self.manager.API.list_models():
                models.append(self.Model(id=model_id))
            return self.ModelsResponse(data=models)

        @app.post("/v1/chat/completions")
        async def chat_completions(request: Request):
            body = await request.json()
            chat_req = self.ChatCompletionRequest(**body)

            if not chat_req.messages:
                raise HTTPException(status_code=400, detail="No messages provided")
            
            last_msg = chat_req.messages[-1]
            ol_message = {"role": last_msg.role, "content": last_msg.content}

            if chat_req.stream:
                return StreamingResponse(
                    self._stream_handler(ol_message, chat_req.model),
                    media_type="text/event-stream"
                )
            else:
                return await self._completion_handler(ol_message, chat_req.model)

        # Start the server
        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="critical")
        server = uvicorn.Server(config)
        await server.serve()

    async def _completion_handler(self, ol_message: dict, model: str) -> JSONResponse:
        try:
            # send the request to the framework and format it
            response_dict = await self.send(ol_message, commands_authorized=True)
            response_dict = self.format_message(response_dict)
            content = response_dict.get("content", "")

            # return the response as a full openAI-compatible json object
            return JSONResponse({
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
            return JSONResponse(
                status_code=500,
                content={"error": {"message": str(e), "type": "server_error", "param": None, "code": "internal_error"}}
            )

    async def _stream_handler(self, ol_message: dict, model: str):
        try:
            chat_id = f"chatcmpl-{uuid.uuid4()}"
            created_time = int(time.time())

            # Initial empty chunk to satisfy some clients
            yield f"data: {self._openai_chunk(chat_id, created_time, model, '')}\n\n"

            async for token in self.format_stream_for_text(
                self.send_stream(ol_message, commands_authorized=True)
            ):
                token_type = token.get("type")
                token_content = token.get("content")

                if token_type == "content":
                    yield f"data: {self._openai_chunk(chat_id, created_time, model, token_content)}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            self.log(self.name, f"Error in stream: {str(e)}")
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

    def _openai_chunk(self, chat_id: str, created: int, model: str, delta: str) -> str:
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
