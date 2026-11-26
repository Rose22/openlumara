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
        # one buffer per live on_stream invocation (the root answer turn plus
        # any nested compaction/subagent streams), keyed by stream id. sharing
        # one buffer let a nested stream clobber the main chain's steps/final
        # because both number their steps from 1.
        self.streams = {}        # id -> {"steps": {}, "final": [], "parent": id|None, "attach_step": n}
        self.stream_order = []   # stream ids in creation order, for replay
        self._next_stream_id = 0
        self.stack = []          # currently-open stream ids, root at index 0

    def begin_stream(self):
        """open a lane for one on_stream invocation; returns (id, parent_id, attach_step).
        parent_id is None for the root turn; attach_step is the parent's current
        top step so a nested chain renders inline under the step that spawned it."""
        self._next_stream_id += 1
        stream_id = self._next_stream_id
        parent = self.stack[-1] if self.stack else None

        attach_step = 0
        if parent is not None:
            parent_steps = self.streams.get(parent, {}).get("steps", {})
            if parent_steps:
                attach_step = max(parent_steps.keys())

        self.streams[stream_id] = {"steps": {}, "final": [], "parent": parent, "attach_step": attach_step}
        self.stream_order.append(stream_id)
        self.stack.append(stream_id)
        return stream_id, parent, attach_step

    def end_stream(self, stream_id):
        if stream_id in self.stack:
            self.stack.remove(stream_id)

    def reset_streams(self):
        self.streams = {}
        self.stream_order = []
        self._next_stream_id = 0
        self.stack = []

    def _buffer(self, stream_id):
        return self.streams.setdefault(
            stream_id, {"steps": {}, "final": [], "parent": None, "attach_step": 0}
        )

    def record_step_snapshot(self, stream_id, step: dict):
        """track the newest snapshot of one streaming step (upsert by number)"""
        self._buffer(stream_id)["steps"][step.get("step")] = step

    def record_final_snapshot(self, stream_id, messages: list):
        """track the newest final-bubble snapshot"""
        self._buffer(stream_id)["final"] = messages

    def apply_step_delta(self, stream_id, delta: dict):
        """fold a streaming append into the stored step snapshot, so a
        mid-stream reconnect replay stays current between checkpoints"""
        step = self._buffer(stream_id)["steps"].get(delta.get("step"))
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

    def apply_final_delta(self, stream_id, delta: dict):
        final = self._buffer(stream_id)["final"]
        if not final:
            return
        last = final[-1]
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
            # reset every lane's buffers
            self.reset_streams()

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

        # when reconnecting mid-stream, replay every lane so far, in creation
        # order, tagged with its stream id / parent / attach_step so nested
        # chains rebuild inline under the step that spawned them
        if self.stream_state != "idle" and self.stream_order:
            for stream_id in sorted(self.stream_order):
                buf = self.streams.get(stream_id)
                if not buf:
                    continue
                lane = {"stream_id": stream_id}
                if buf.get("parent") is not None:
                    lane["parent_id"] = buf["parent"]
                    lane["attach_step"] = buf.get("attach_step", 0)
                for step_num in sorted(buf["steps"]):
                    await websocket.send_json({
                        "type": "turn_step",
                        "step": buf["steps"][step_num],
                        **lane,
                    })
                await websocket.send_json({
                    "type": "turn_final",
                    "messages": buf["final"],
                    **lane,
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
        """broadcast a websocket event to all connected clients.

        -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
        sends run concurrently: one stalled client (backgrounded tab, full
        socket buffer) used to hold up delivery to every other client for up
        to SEND_TIMEOUT seconds per broadcast event."""
        async def _send(connection):
            try:
                if connection.client_state == starlette.websockets.WebSocketState.CONNECTED:
                    await asyncio.wait_for(
                        connection.send_json(message), timeout=self.SEND_TIMEOUT
                    )
            except Exception:
                return connection
            return None

        results = await asyncio.gather(
            *(_send(connection) for connection in list(self.active_connections))
        )

        for conn in results:
            if conn is None:
                continue
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
                "type": "stream_complete",
                "revision": getattr(self.channel.context.chat.messages, "revision", None),
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
