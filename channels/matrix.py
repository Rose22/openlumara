import core
import os
import asyncio
import time
import json
import json_repair
from typing import Optional, Dict, List, Any
from nio import (
    AsyncClient,
    AsyncClientConfig,
    LoginResponse,
    RoomMessageText,
    RoomMessageEmote,
    MegolmEvent,
    InviteMemberEvent,
    RoomMemberEvent,
    SyncResponse,
    SyncError,
    RoomSendResponse,
    KeyVerificationStart,
    KeyVerificationCancel,
    KeyVerificationKey,
    KeyVerificationMac,
    RoomKeyRequest,
    RoomKeyRequestCancellation,
)
from nio.crypto import OlmDevice
from nio.store import SqliteStore

class Matrix(core.channel.Channel):
    """
    A Matrix channel with E2EE support using matrix-nio.
    """

    running = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            cfg = core.config.get("channels").get("settings").get("matrix", {})
            self.homeserver = self.homeserver or cfg.get("homeserver")
            self.user_id = self.user_id or cfg.get("user_id")
            self.password = self.password or cfg.get("password")
            self.access_token = self.access_token or cfg.get("access_token")
            self.device_id = self.device_id or cfg.get("device_id", "CORE_BOT")
            self.device_name = self.device_name or cfg.get("device_name", "Core Bot")
        except (AttributeError, TypeError):
            pass

        self.client: Optional[AsyncClient] = None
        self._shutting_down = False
        self._store_path = self._get_store_path()
        self.rooms: Dict[str, Dict[str, Any]] = {}
        self._sync_token: Optional[str] = None
        self._key_verifications: Dict[str, Dict] = {}
        self._auto_join = os.getenv("MATRIX_AUTO_JOIN", "true").lower() == "true"

    def _get_store_path(self) -> str:
        store_path = os.path.join(core.get_data_path(), "matrix_store")
        os.makedirs(store_path, exist_ok=True)
        return store_path

    async def run(self):
        if not all([self.homeserver, self.user_id]):
            await self._announce("Matrix channel failed: Missing homeserver or user_id.", "error")
            return False

        if not self.password and not self.access_token:
            await self._announce("Matrix channel failed: No password or access_token.", "error")
            return False

        try:
            await self._initialize_client()
            await self._login()
            await self._setup_callbacks()
            await self._initial_sync()

            self.running = True
            await self._announce(f"Matrix connected as {self.user_id} (E2EE enabled).", "status")
            await self._main_loop()

        except Exception as e:
            core.log("matrix", f"Critical Error: {str(e)}")
            import traceback
            core.log("matrix", traceback.format_exc())
            return False
        finally:
            await self._cleanup()

        return True

    async def _initialize_client(self):
        config = AsyncClientConfig(
            store_sync_tokens=True,
            encryption_enabled=True,
        )

        self.client = AsyncClient(
            self.homeserver,
            self.user_id,
            device_id=self.device_id,
            store_path=self._store_path,
            config=config,
        )

        try:
            self.client.load_store()
            core.log("matrix", "Loaded existing session.")
        except Exception:
            core.log("matrix", "Creating new session.")

    async def _login(self):
        if self.access_token:
            self.client.access_token = self.access_token
            self.client.user_id = self.user_id
            self.client.device_id = self.device_id
            return

        response = await self.client.login(password=self.password, device_name=self.device_name)
        if isinstance(response, LoginResponse):
            self.device_id = response.device_id
        else:
            raise Exception(f"Login failed: {response}")

    async def _setup_callbacks(self):
        self.client.add_event_callback(self._on_room_message, (RoomMessageText, RoomMessageEmote))
        self.client.add_event_callback(self._on_megolm_event, (MegolmEvent,))
        self.client.add_event_callback(self._on_invite, (InviteMemberEvent,))
        self.client.add_event_callback(self._on_room_member, (RoomMemberEvent,))

        self.client.add_to_device_callback(
            self._on_key_verification,
            (KeyVerificationStart, KeyVerificationCancel, KeyVerificationKey, KeyVerificationMac)
        )
        self.client.add_to_device_callback(
            self._on_key_request,
            (RoomKeyRequest, RoomKeyRequestCancellation)
        )

    async def _initial_sync(self):
        sync_response = await self.client.sync(timeout=30000)
        if isinstance(sync_response, SyncError):
            raise Exception(f"Initial sync failed: {sync_response}")

        self._sync_token = sync_response.next_batch
        await self._process_sync(sync_response)
        await self._ensure_encryption_keys()

    async def _ensure_encryption_keys(self):
        if self.client.should_upload_keys:
            await self.client.keys_upload()
        if self.client.should_query_keys:
            await self.client.keys_query()

    async def _main_loop(self):
        backoff = 1
        while self.running and not self._shutting_down:
            try:
                sync_response = await self.client.sync(timeout=30000, since=self._sync_token)
                if isinstance(sync_response, SyncResponse):
                    self._sync_token = sync_response.next_batch
                    await self._process_sync(sync_response)
                    if self.client.should_query_keys:
                        await self.client.keys_query()
                    backoff = 1
                elif isinstance(sync_response, SyncError):
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
            except Exception as e:
                core.log("matrix", f"Sync error: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _process_sync(self, response: SyncResponse):
        for room_id, room in response.rooms.join.items():
            await self._update_room_info(room_id, room)
        for room_id in response.rooms.leave.keys():
            self.rooms.pop(room_id, None)

    async def _update_room_info(self, room_id: str, room):
        is_encrypted = False
        if hasattr(self.client, 'rooms') and room_id in self.client.rooms:
            matrix_room = self.client.rooms[room_id]
            is_encrypted = getattr(matrix_room, 'encrypted', False)

        room_name = room_id
        if hasattr(room, 'summary') and room.summary:
            room_name = getattr(room.summary, 'display_name', room_id) or room_id

        is_dm = False
        if hasattr(self.client, 'rooms') and room_id in self.client.rooms:
            matrix_room = self.client.rooms[room_id]
            is_dm = len(getattr(matrix_room, 'users', {})) == 2

        self.rooms[room_id] = {"encrypted": is_encrypted, "name": room_name, "is_dm": is_dm}

    async def _on_room_message(self, room, event):
        if event.sender == self.user_id:
            return

        body = getattr(event, 'body', '')
        if not body or not body.strip():
            return

        room_info = self.rooms.get(room.room_id, {})
        enc_str = "encrypted" if room_info.get("encrypted") else "plain"
        dm_str = "DM" if room_info.get("is_dm") else "room"
        core.log("matrix", f"[{dm_str}][{enc_str}] {room_info.get('name')}: {body[:50]}...")

        await self._handle_message(room.room_id, body.strip())

    async def _on_megolm_event(self, room, event):
        core.log("matrix", f"Undecrypted MegolmEvent in {room.room_id}, session: {event.session_id}")

    async def _handle_message(self, room_id: str, message: str):
        typing_task = asyncio.create_task(self._keep_typing(room_id))
        last_event_id = None
        last_edit_time = 0
        tool_calls_display = []
        response_buffer = []

        try:
            async for token in self.send_stream({"role": "user", "content": message}):
                t_type = token.get("type")
                content = token.get("content", "")

                if t_type == "tool_calls" and content:
                    tools = content if isinstance(content, list) else [content]
                    for tool in tools:
                        tool_calls_display.append(self._format_tool_call(tool))
                elif t_type in ["content", "error"]:
                    response_buffer.append(content)

                tools_text = "\n".join(tool_calls_display)
                text_part = "".join(response_buffer)
                visual_buffer = f"{tools_text}\n\n{text_part}" if tools_text and text_part else tools_text + text_part

                now = time.time()
                if visual_buffer:
                    if last_event_id is None:
                        response = await self._send_room_message(room_id, visual_buffer)
                        if isinstance(response, RoomSendResponse):
                            last_event_id = response.event_id
                        last_edit_time = now
                    elif now - last_edit_time >= 2.0:
                        await self._edit_room_message(room_id, last_event_id, visual_buffer)
                        last_edit_time = now

            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

            final = "".join(response_buffer)
            final_buffer = f"{tools_text}\n\n{final}" if tools_text and final else tools_text + final
            if last_event_id and final_buffer:
                await self._edit_room_message(room_id, last_event_id, final_buffer)
            elif final_buffer:
                await self._send_room_message(room_id, final_buffer)

        except Exception as e:
            if not typing_task.done():
                typing_task.cancel()
            core.log("matrix", f"Error: {e}")
            await self._send_room_message(room_id, f"❌ Error: {str(e)}")

    async def _send_room_message(self, room_id: str, text: str) -> RoomSendResponse:
        return await self.client.room_send(
            room_id, "m.room.message", {"msgtype": "m.text", "body": text},
            ignore_unverified_devices=True,
        )

    async def _edit_room_message(self, room_id: str, event_id: str, new_text: str):
        return await self.client.room_send(
            room_id, "m.room.message",
            {
                "msgtype": "m.text",
                "body": f"* {new_text}",
                "m.new_content": {"msgtype": "m.text", "body": new_text},
                "m.relates_to": {"rel_type": "m.replace", "event_id": event_id},
            },
            ignore_unverified_devices=True,
        )

    async def _on_invite(self, room, event):
        if event.membership != "invite":
            return
        core.log("matrix", f"Invited to {room.room_id} by {event.sender}")
        if self._auto_join:
            response = await self.client.join(room.room_id)
            if hasattr(response, 'room_id'):
                await self._announce(f"Joined room: {room.room_id}", "status")

    async def _on_room_member(self, room, event):
        pass

    async def _on_key_verification(self, event):
        core.log("matrix", f"Key verification: {type(event).__name__}")

        if isinstance(event, KeyVerificationStart):
            self._key_verifications[event.transaction_id] = {"sender": event.sender}
            try:
                await self.client.accept_key_verification(event.transaction_id)
            except Exception as e:
                core.log("matrix", f"Accept verification failed: {e}")

        elif isinstance(event, KeyVerificationKey):
            sas = self.client.key_verifications.get(event.transaction_id)
            if sas:
                emojis = sas.get_emoji()
                if emojis:
                    core.log("matrix", f"SAS: {' '.join([e[0] for e in emojis])}")
                    try:
                        await self.client.confirm_short_auth_string(event.transaction_id)
                    except Exception as e:
                        core.log("matrix", f"SAS confirm failed: {e}")

        elif isinstance(event, KeyVerificationCancel):
            self._key_verifications.pop(event.transaction_id, None)
            core.log("matrix", f"Verification cancelled: {event.reason}")

    async def _on_key_request(self, event):
        if isinstance(event, RoomKeyRequest) and event.sender == self.user_id:
            try:
                await self.client.forward_event_key_to_devices(event)
            except Exception as e:
                core.log("matrix", f"Key forward failed: {e}")

    def _format_tool_call(self, tool_data) -> str:
        try:
            if hasattr(tool_data, 'function'):
                func_name = getattr(tool_data.function, 'name', 'unknown')
                raw_args = getattr(tool_data.function, 'arguments', '{}')
            elif isinstance(tool_data, dict) and 'function' in tool_data:
                func_name = tool_data['function'].get('name', 'unknown')
                raw_args = tool_data['function'].get('arguments', '{}')
            else:
                return "🔧 Calling tool..."

            args_dict = json_repair.loads(raw_args) if isinstance(raw_args, str) else (raw_args if isinstance(raw_args, dict) else {})
            arg_strs = [f'{k}="{str(v)[:30]}"' for k, v in args_dict.items()]
            return f"🔧 {func_name}({', '.join(arg_strs)})"
        except Exception:
            return "🔧 Calling tool..."

    async def _keep_typing(self, room_id: str):
        try:
            while True:
                await self.client.room_typing(room_id, True, timeout=15000)
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            try:
                await self.client.room_typing(room_id, False)
            except:
                pass
            raise

    async def _cleanup(self):
        if self.client:
            await self.client.close()

    def shutdown(self):
        self._announce("Shutting down Matrix channel...", "status")
        self.running = False
        self._shutting_down = True
        return True

    async def _announce(self, message: str, type: str = None):
        type = type or "info"
        core.log("matrix", f"[{type}] {message}")
        if not self.client:
            return
        emoji = {"error": "🚨", "warning": "⚠️", "status": "ℹ️", "info": "💬"}.get(type, "🔔")
        text = f"{emoji} {type.upper()}: {message}"
        for room_id in list(self.rooms.keys()):
            try:
                await self._send_room_message(room_id, text)
            except Exception as e:
                core.log("matrix", f"Announce failed to {room_id}: {e}")

    async def send_to_room(self, room_id: str, message: str):
        return await self._send_room_message(room_id, message) if self.client else None

    async def get_room_encryption_status(self, room_id: str) -> Dict:
        info = self.rooms.get(room_id, {})
        return {"encrypted": info.get("encrypted", False), "is_dm": info.get("is_dm", False), "name": info.get("name", room_id)}

    async def get_all_rooms(self) -> Dict[str, Dict]:
        return dict(self.rooms)
