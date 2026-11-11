"""Websocket Manager"""

import asyncio

import fastapi
import starlette.websockets

import core

import channels.webui.utils as utils

class WebSocketManager:
    # prevent the stream from stalling forever
    SEND_TIMEOUT = 10

    def __init__(self, channel):
        self.channel = channel
        self.active_connections = []
        self.active_stream_task = None
        self.webui_ready = False
        self.stream_state = "idle"
        self.turn_steps = {}
        self.turn_final = []

    def record_step_snapshot(self, step: dict):
        """track the newest snapshot of one streaming step (upsert by number)"""
        self.turn_steps[step.get("step")] = step

    def record_final_snapshot(self, messages: list):
        """track the newest final-bubble snapshot"""
        self.turn_final = messages

    def apply_step_delta(self, delta: dict):
        """fold a streaming append into the stored step snapshot, so a
        mid-stream reconnect replay stays current between checkpoints"""
        step = self.turn_steps.get(delta.get("step"))
        if step is None:
            return

        for append in delta.get("append", []):
            if append.get("field") == "reasoning_content":
                step["reasoning_content"] = (step.get("reasoning_content") or "") + append["text"]
            elif append.get("field") == "tool_response":
                for tool in step.get("tool_calls", []):
                    if tool.get("id") == append.get("id"):
                        meta = tool.setdefault("_metadata", {})
                        meta["response"] = (meta.get("response") or "") + append["text"]
                        break

    def apply_final_delta(self, delta: dict):
        if not self.turn_final:
            return
        last = self.turn_final[-1]
        last["content"] = (last.get("content") or "") + delta["text"]

    async def push_context_update(self, connection=None):
        """push the token usage and the full context breakdown
        over the websocket. called on every context-changing event"""
        try:
            size = utils.serialize_for_json(await self.channel.context.get_size())
            messages = [
                {"type": "token_usage", "content": size["total_tokens"], "source": "estimation"},
                {"type": "context_size", "content": size},
            ]
            
            for message in messages:
                if connection is not None:
                    await connection.send_json(message)
                else:
                    await self.broadcast(message)
        except Exception as e:
            self.channel.log(self.channel.name, f"error pushing context update: {core.detail_error(e)}")

    async def set_stream_state(self, state: str):
        """update the stream state and notify all clients"""
        if state == self.stream_state:
            return
        self.stream_state = state

        if state in ("message_sending", "idle"):
            # reset the buffers
            self.turn_steps = {}
            self.turn_final = []

        await self.broadcast({"type": "stream_state", "state": state})

    async def connect(self, websocket: fastapi.WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        current_chat_id = self.channel.context.chat.get("id")

        if current_chat_id:
            await websocket.send_json({
                "type": "ready"
            })

        # push the current stream state to the client
        await websocket.send_json({
            "type": "stream_state",
            "state": self.stream_state
        })

        # when reconnecting mid-stream, replay every step so far to the client
        if self.stream_state != "idle" and (self.turn_steps or self.turn_final):
            for step_num in sorted(self.turn_steps):
                await websocket.send_json({
                    "type": "turn_step",
                    "step": self.turn_steps[step_num]
                })
            await websocket.send_json({
                "type": "turn_final",
                "messages": self.turn_final
            })

        await self.push_context_update(connection=websocket)

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
        """broadcast a websocket event to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                if connection.client_state == starlette.websockets.WebSocketState.CONNECTED:
                    await asyncio.wait_for(
                        connection.send_json(message), timeout=self.SEND_TIMEOUT
                    )
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)
            try:
                await asyncio.wait_for(conn.close(), timeout=2)
            except Exception:
                pass

    async def _stream_task(self, message: str, index, files: list = None):
        self.channel._ws_stream_index = index

        try:
            await self.channel.push_stream(
                self.channel.send_stream(
                    message=message,
                    files=files,
                    commands_authorized=self.channel.config.get("enable_admin_settings", False)
                )
            )
        finally:
            # always finalize the stream, no matter what
            await self.broadcast({
                "type": "stream_complete"
            })
            await self.set_stream_state("idle")

    async def start_stream(self, channel, chat_id: str, message: str, files: list = None):
        if self.active_stream_task and not self.active_stream_task.done():
            # a turn is already running. instead of cancelling it, steer!
            descriptor = await channel.queue_steering_message(
                message,
                files=files,
                commands_authorized=channel.config.get("enable_admin_settings", False)
            )

            if descriptor:
                await self.broadcast({
                    "type": "queue_queued",
                    "messages": [descriptor]
                })
            return

        await self.set_stream_state("message_sending")

        next_index = len(await channel.context.chat.messages.get())

        try:
            self.active_stream_task = asyncio.create_task(self._stream_task(message, next_index, files=files))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            channel.log(channel.name, f"Background stream error: {core.detail_error(e)}")
