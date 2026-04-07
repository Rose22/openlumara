import core
import os
import shutil
import asyncio
import time
import json
import logging
import traceback
from typing import Optional, Dict, Any, List
from collections import deque
from nio import (
    AsyncClient,
    AsyncClientConfig,
    LoginResponse,
    RoomMessageText,
    RoomMessageEmote,
    RoomMessageImage,
    RoomMessageAudio,
    RoomMessageVideo,
    RoomMessageFile,
    MegolmEvent,
    InviteMemberEvent,
    SyncResponse,
    SyncError,
    RoomSendResponse,
    KeyVerificationStart,
    KeyVerificationCancel,
    KeyVerificationKey,
    KeyVerificationMac,
    RoomKeyRequest,
    RoomKeyRequestCancellation,
    ToDeviceError,
    KeysClaimError,
    ShareGroupSessionError,
    LocalProtocolError,
    UnknownEvent,
)
from nio.store import SqliteStore

# Attempt to import encrypted media classes (available in newer nio versions)
try:
    from nio import (
        RoomEncryptedImage,
        RoomEncryptedAudio,
        RoomEncryptedVideo,
        RoomEncryptedFile,
    )
    ENCRYPTED_MEDIA_CLASSES = (
        RoomEncryptedImage,
        RoomEncryptedAudio,
        RoomEncryptedVideo,
        RoomEncryptedFile,
    )
except ImportError:
    ENCRYPTED_MEDIA_CLASSES = ()

# ── Silence the noisy nio loggers ────────────────────────────────────────
for _noisy in (
    "nio.crypto",
    "nio.crypto.sessions",
    "nio.crypto.key_export",
    "nio.crypto.machine",
    "nio.crypto.olm_machine",
    "nio.responses",
    "nio.rooms",
    "nio.events",
    "nio.event_builders",
    "nio.client",
    "nio.client.async_client",
    "nio.store",
):
    logging.getLogger(_noisy).setLevel(logging.CRITICAL)
logging.getLogger("nio").setLevel(logging.WARNING)

class Matrix(core.channel.Channel):
    """
    A Matrix channel with E2EE support using matrix-nio.
    Merged with robust session handling and decryption retries.
    """

    running = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            cfg = core.config.get("channels", {}).get("settings", {}).get("matrix", {})
            self.homeserver: str = cfg.get("homeserver", "")
            self.user_id: str = cfg.get("user_id", "")
            self.password: str = cfg.get("password", "")
            self.access_token: str = cfg.get("access_token", "")
            self.device_id: str = cfg.get("device_id", "")
            self.device_name: str = cfg.get("device_name", "Core Bot")
        except (AttributeError, TypeError) as e:
            core.log("matrix", f"Config error: {e}")
            self.homeserver = ""
            self.user_id = ""
            self.password = ""
            self.access_token = ""
            self.device_id = ""
            self.device_name = "Core Bot"

        self.client: Optional[AsyncClient] = None
        self._shutting_down = False
        self._store_path = self._get_store_path()
        self._ready = False
        self._auto_join = os.getenv("MATRIX_AUTO_JOIN", "true").lower() == "true"
        self._blacklisted_devices: set[tuple[str, str]] = set()

        # ── Robustness members from reference code ───────────────────────────
        self._startup_ts: float = 0.0
        # Deduplication
        self._processed_events: deque = deque(maxlen=1000)
        # Buffer for undecrypted events (waiting for keys)
        self._pending_megolm: List[tuple] = []
        self._MAX_PENDING_EVENTS = 100
        self._PENDING_EVENT_TTL = 300  # seconds

    # ── helpers ───────────────────────────────────────────────────────────

    def _get_store_path(self) -> str:
        store_path = os.path.join(core.get_data_path(), "matrix_store")
        os.makedirs(store_path, exist_ok=True)
        return store_path

    def _get_credentials_path(self) -> str:
        return os.path.join(core.get_data_path(), "matrix_credentials.json")

    def _save_credentials(self, user_id: str, device_id: str, access_token: str):
        creds = {
            "user_id": user_id,
            "device_id": device_id,
            "access_token": access_token,
        }
        path = self._get_credentials_path()
        with open(path, "w") as f:
            json.dump(creds, f)
        core.log("matrix", f"Credentials saved to {path}")

    def _load_credentials(self) -> Optional[Dict[str, str]]:
        path = self._get_credentials_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                core.log("matrix", f"Failed to load credentials: {e}")
        return None

    def _room_display_name(self, room_id: str) -> str:
        if self.client and room_id in self.client.rooms:
            r = self.client.rooms[room_id]
            return r.display_name or r.canonical_alias or room_id
        return room_id

    def _room_is_encrypted(self, room_id: str) -> bool:
        if self.client and room_id in self.client.rooms:
            return getattr(self.client.rooms[room_id], "encrypted", False)
        return False

    def _room_is_dm(self, room_id: str) -> bool:
        if self.client and room_id in self.client.rooms:
            return len(self.client.rooms[room_id].users) <= 2
        return False

    def _is_duplicate_event(self, event_id: str) -> bool:
        if not event_id:
            return False
        if event_id in self._processed_events:
            return True
        self._processed_events.append(event_id)
        return False

    # ── lifecycle ─────────────────────────────────────────────────────────

    async def run(self):
        if not self.homeserver or not self.user_id:
            core.log("matrix", "Missing homeserver or user_id – aborting.")
            return False

        if not self.password and not self.access_token:
            saved = self._load_credentials()
            if not saved or not saved.get("access_token"):
                core.log("matrix", "No password or access_token – aborting.")
                return False

        try:
            core.log("matrix", "Initializing client…")
            self._initialize_client()

            core.log("matrix", "Logging in…")
            await self._login()

            self._setup_callbacks()

            core.log("matrix", "Running initial sync…")
            await self._initial_sync()

            # Set startup timestamp for grace period
            self._startup_ts = time.time()

            self._ready = True
            self.running = True

            await self.announce(
                f"Matrix connected as {self.user_id} (E2EE enabled).", "status"
            )

            await self._main_loop()

        except Exception as e:
            core.log("matrix", f"Critical error: {e}\n{traceback.format_exc()}")
            return False
        finally:
            await self._cleanup()

        return True

    def _initialize_client(self):
        config = AsyncClientConfig(
            store=SqliteStore,
            store_name="nio_store.db",
            store_sync_tokens=True,
            encryption_enabled=True,
        )

        self.client = AsyncClient(
            homeserver=self.homeserver,
            user=self.user_id,
            device_id=self.device_id or None,
            store_path=self._store_path,
            config=config,
        )

    async def _login(self):
        # Priority 1: Config-provided access token
        if self.access_token:
            core.log("matrix", "Using config-provided access token…")
            # Use restore_login to properly set up the client state
            self.client.restore_login(
                user_id=self.user_id,
                device_id=self.device_id or "",  # device_id must match stored keys
                access_token=self.access_token
            )
            # Ensure crypto store is loaded
            self.client.load_store()
            return

        # Priority 2: Previously saved credentials
        saved = self._load_credentials()
        if saved and saved.get("access_token"):
            core.log(
                "matrix",
                f"Restoring saved credentials (device: {saved.get('device_id')})…",
            )
            self.client.restore_login(
                user_id=saved["user_id"],
                device_id=saved["device_id"],
                access_token=saved["access_token"]
            )
            self.device_id = saved["device_id"]
            self.client.load_store()
            return

        # Priority 3: Fresh password login (creates a new device)
        if os.path.exists(self._store_path):
            core.log("matrix", "Wiping old crypto store for clean key registration…")
            shutil.rmtree(self._store_path)
            os.makedirs(self._store_path, exist_ok=True)
            self._initialize_client()

        response = await self.client.login(
            password=self.password, device_name=self.device_name
        )
        if isinstance(response, LoginResponse):
            self.device_id = response.device_id
            self.access_token = response.access_token
            core.log("matrix", f"Logged in, device_id={self.device_id}")
            self._save_credentials(
                response.user_id, response.device_id, response.access_token
            )
        else:
            raise RuntimeError(f"Login failed: {response}")

    # ── callbacks ─────────────────────────────────────────────────────────

    def _setup_callbacks(self):
        self.client.add_event_callback(
            self._on_room_message, (RoomMessageText, RoomMessageEmote)
        )

        # Media callbacks
        self.client.add_event_callback(
            self._on_room_message_media,
            (RoomMessageImage, RoomMessageAudio, RoomMessageVideo, RoomMessageFile)
        )
        # Encrypted media
        if ENCRYPTED_MEDIA_CLASSES:
            self.client.add_event_callback(
                self._on_room_message_media, ENCRYPTED_MEDIA_CLASSES
            )

        self.client.add_event_callback(self._on_megolm_event, (MegolmEvent,))
        self.client.add_event_callback(self._on_invite, (InviteMemberEvent,))

        # Catch-all for unknown events (e.g. reactions)
        self.client.add_event_callback(self._on_unknown_event, (UnknownEvent,))

        # ── Verification Callbacks ──
        self.client.add_to_device_callback(
            self._on_key_verification_start, (KeyVerificationStart,)
        )
        self.client.add_to_device_callback(
            self._on_key_verification_key, (KeyVerificationKey,)
        )
        self.client.add_to_device_callback(
            self._on_key_verification_mac, (KeyVerificationMac,)
        )
        self.client.add_to_device_callback(
            self._on_key_verification_cancel, (KeyVerificationCancel,)
        )

        # Key requests (for key forwarding)
        self.client.add_to_device_callback(
            self._on_key_request, (RoomKeyRequest, RoomKeyRequestCancellation)
        )

    async def _on_room_message(self, room, event):
        if not self._ready:
            return
        if event.sender == self.user_id:
            return

        # Deduplication
        if self._is_duplicate_event(event.event_id):
            return

        # Startup grace period: ignore old messages
        event_ts = getattr(event, "server_timestamp", 0) / 1000.0
        if event_ts and event_ts < self._startup_ts - 5:
            return

        body = getattr(event, "body", "")
        if not body or not body.strip():
            return

        enc_tag = "enc" if self._room_is_encrypted(room.room_id) else "plain"
        dm_tag = "DM" if self._room_is_dm(room.room_id) else "room"
        name = self._room_display_name(room.room_id)
        core.log(
            "matrix",
            f"[{dm_tag}][{enc_tag}] {name} | {event.sender}: {body[:80]}",
        )

        await self._handle_message(room.room_id, body.strip())

    async def _on_room_message_media(self, room, event):
        """Handle incoming media messages."""
        if not self._ready:
            return
        if event.sender == self.user_id:
            return
        if self._is_duplicate_event(event.event_id):
            return

        # Startup grace
        event_ts = getattr(event, "server_timestamp", 0) / 1000.0
        if event_ts and event_ts < self._startup_ts - 5:
            return

        body = getattr(event, "body", "")
        url = getattr(event, "url", "")

        enc_tag = "enc" if self._room_is_encrypted(room.room_id) else "plain"
        core.log("matrix", f"Media received in {self._room_display_name(room.room_id)}: {body} ({url})")
        # Logic to process media can be added here (e.g. download, transcribe, etc.)
        # For now, we just acknowledge it to avoid crashes.

    async def _on_unknown_event(self, room, event):
        """Fallback for events not natively parsed by matrix-nio (e.g. reactions)."""
        # Could log reactions here if needed.
        pass

    async def _on_megolm_event(self, room, event):
        """
        Handles events that could not be decrypted (MegolmEvent).
        We request the key and buffer the event for retry.
        """
        core.log(
            "matrix",
            f"Undecryptable event in {self._room_display_name(room.room_id)} "
            f"from {event.sender} (session …{event.session_id[-8:]})",
        )

        # Buffer for retry
        self._pending_megolm.append((room, event, time.time()))
        if len(self._pending_megolm) > self._MAX_PENDING_EVENTS:
            self._pending_megolm = self._pending_megolm[-self._MAX_PENDING_EVENTS:]

        # Try to request the key from other devices
        try:
            await self.client.request_room_key(event)
        except Exception:
            pass

    async def _on_invite(self, room, event):
        if not self._auto_join:
            core.log("matrix", f"Ignoring invite to {room.room_id} (auto-join off).")
            return

        core.log("matrix", f"Invited to {room.room_id} by {event.sender}, joining…")
        try:
            resp = await self.client.join(room.room_id)
            if hasattr(resp, "room_id"):
                core.log("matrix", f"Joined {room.room_id}")
                # Sync keys after joining to ensure encryption setup
                await self.client.keys_query()
                await self._establish_sessions_for_room(room.room_id)
        except Exception as e:
            core.log("matrix", f"Failed to join {room.room_id}: {e}")

    # ── key verification (SAS) ─────────────────────────────────────────────

    async def _on_key_verification_start(self, event):
        core.log(
            "matrix",
            f"Verification start from {event.sender} (txn: {event.transaction_id})",
        )
        try:
            resp = await self.client.accept_key_verification(event.transaction_id)
            if isinstance(resp, ToDeviceError):
                core.log("matrix", f"Failed to accept verification: {resp}")
                return
            core.log("matrix", "Verification accepted. Waiting for Key exchange...")
        except Exception as e:
            core.log("matrix", f"Error accepting verification: {e}")

    async def _on_key_verification_key(self, event):
        core.log("matrix", f"Received verification key from {event.sender}")
        sas = self.client.key_verifications.get(event.transaction_id)
        if not sas:
            core.log("matrix", f"Unknown verification transaction {event.transaction_id}")
            return

        try:
            # 1. Send our key
            todevice_msg = sas.share_key()
            resp = await self.client.to_device(todevice_msg)
            if isinstance(resp, ToDeviceError):
                core.log("matrix", f"Failed to share key: {resp}")
                return

            # 2. Display SAS (Emojis/Decimals)
            emojis = sas.get_emoji()
            if emojis:
                emoji_str = " ".join(f"{e[0]} ({e[1]})" for e in emojis)
                core.log("matrix", f"SAS Emojis: {emoji_str}")
            else:
                decimals = sas.get_decimals()
                if decimals:
                    core.log("matrix", f"SAS Decimals: {decimals}")

            # 3. Confirm the SAS
            resp = await self.client.confirm_short_auth_string(event.transaction_id)
            if isinstance(resp, ToDeviceError):
                core.log("matrix", f"Failed to confirm SAS: {resp}")
            else:
                core.log("matrix", "SAS confirmed. Verification almost complete.")

        except Exception as e:
            core.log("matrix", f"Error during key exchange: {e}")

    async def _on_key_verification_mac(self, event):
        core.log("matrix", f"Received verification MAC from {event.sender}")
        sas = self.client.key_verifications.get(event.transaction_id)
        if not sas:
            return

        try:
            if sas.other_olm_device:
                self.client.verify_device(sas.other_olm_device)
                core.log(
                    "matrix",
                    f"✅ Verified device {sas.other_olm_device.device_id} of {sas.other_olm_device.user_id}",
                )
            core.log("matrix", "✅ Verification successful.")
        except Exception as e:
            core.log("matrix", f"Error processing MAC: {e}")

    async def _on_key_verification_cancel(self, event):
        core.log(
            "matrix",
            f"Verification cancelled by {event.sender}: {event.reason} (code: {event.code})",
        )

    # ── key requests ──────────────────────────────────────────────────────

    async def _on_key_request(self, event):
        # If we have the keys, share them (helps other devices decrypt history)
        if isinstance(event, RoomKeyRequest) and event.sender == self.user_id:
            try:
                await self.client.export_keys_for_key_share(
                    event.room_id, event.session_id
                )
            except Exception:
                pass

    # ── session management (merged robust logic) ───────────────────────────

    async def _establish_sessions_for_room(self, room_id: str):
        """
        Ensure we have Olm sessions with all devices in the room, then share the Megolm session.
        """
        if not getattr(self.client.rooms.get(room_id), "encrypted", False):
            return

        try:
            # 1. Find devices we need to establish sessions with
            missing = self.client.get_missing_sessions(room_id)
            if missing:
                # Filter out blacklisted devices
                filtered: dict[str, list[str]] = {}
                for user_id, devices in missing.items():
                    good = [
                        d
                        for d in devices
                        if (user_id, d) not in self._blacklisted_devices
                    ]
                    if good:
                        filtered[user_id] = good

                if filtered:
                    device_count = sum(len(v) for v in filtered.values())
                    core.log(
                        "matrix",
                        f"Claiming keys for {device_count} device(s) in {self._room_display_name(room_id)}",
                    )
                    # 2. Claim one-time keys
                    resp = await self.client.keys_claim(filtered)
                    if isinstance(resp, KeysClaimError):
                        core.log("matrix", f"keys_claim failed: {resp.message}")

                # 3. Check if claiming failed again for some, blacklist them
                still_missing = self.client.get_missing_sessions(room_id)
                if still_missing:
                    for user_id, devices in still_missing.items():
                        for dev in devices:
                            key = (user_id, dev)
                            if key not in self._blacklisted_devices:
                                self._blacklisted_devices.add(key)
                                core.log(
                                    "matrix",
                                    f"Blacklisting device {dev} of {user_id} (failed to claim key).",
                                )

            # 4. Share the Megolm group session with the room
            resp = await self.client.share_group_session(
                room_id, ignore_unverified_devices=True
            )
            if isinstance(resp, ShareGroupSessionError):
                core.log(
                    "matrix",
                    f"share_group_session failed for {self._room_display_name(room_id)}: {resp.message}",
                )
        except Exception as e:
            core.log("matrix", f"Session setup for {room_id} failed: {e}")

    async def _auto_trust_devices(self):
        """
        Trust/verify all unverified devices we know about.
        This helps ensure other clients send us keys.
        """
        client = self.client
        if not client:
            return

        device_store = getattr(client, "device_store", None)
        if not device_store:
            return

        own_device = getattr(client, "device_id", None)
        trusted_count = 0

        try:
            # device_store is iterable of OlmDevice
            for device in device_store:
                if getattr(device, "device_id", None) == own_device:
                    continue
                if not getattr(device, "verified", False):
                    client.verify_device(device)
                    trusted_count += 1
        except Exception as exc:
            core.log("matrix", f"Auto-trust error: {exc}")

        if trusted_count:
            core.log("matrix", f"Auto-trusted {trusted_count} new device(s)")

    async def _retry_pending_decryptions(self):
        """Retry decrypting buffered MegolmEvents after new keys arrive."""
        client = self.client
        if not client or not self._pending_megolm:
            return

        now = time.time()
        still_pending: list = []

        for room, event, ts in self._pending_megolm:
            # Drop events that have aged past the TTL
            if now - ts > self._PENDING_EVENT_TTL:
                continue

            try:
                decrypted = client.decrypt_event(event)
            except Exception:
                # Still missing the key — keep in buffer
                still_pending.append((room, event, ts))
                continue

            # Successfully decrypted! Route to handler.
            # We dispatch to the text or media handler based on decrypted type
            core.log("matrix", f"Decrypted buffered event {event.event_id}")
            if hasattr(decrypted, "body"): # Text message
                await self._on_room_message(room, decrypted)
            elif isinstance(decrypted, (RoomMessageImage, RoomMessageAudio, RoomMessageVideo, RoomMessageFile)):
                await self._on_room_message_media(room, decrypted)

        self._pending_megolm = still_pending

    # ── sync loop ─────────────────────────────────────────────────────────

    async def _initial_sync(self):
        resp = await self.client.sync(timeout=30000, full_state=True)
        if isinstance(resp, SyncError):
            raise RuntimeError(f"Initial sync failed: {resp.message}")

        await self._ensure_keys_uploaded()
        await self._query_and_establish_sessions()

    async def _ensure_keys_uploaded(self):
        try:
            if self.client.should_upload_keys:
                await self.client.keys_upload()
                core.log("matrix", "Device keys uploaded.")
        except Exception as e:
            core.log("matrix", f"Key upload failed: {e}")

    async def _query_and_establish_sessions(self):
        try:
            if self.client.should_query_keys:
                await self.client.keys_query()
                core.log("matrix", "Keys query complete.")
                # Auto-trust devices found during query (common in bot workflows)
                await self._auto_trust_devices()

            for room_id in list(self.client.rooms):
                await self._establish_sessions_for_room(room_id)
        except Exception as e:
            core.log("matrix", f"Key query/establish failed: {e}")

    async def _sync_encryption_keys(self):
        """Called after every sync to keep keys fresh."""
        try:
            # 1. Upload our keys if needed
            if self.client.should_upload_keys:
                await self.client.keys_upload()

            # 2. Query for new devices/keys
            if self.client.should_query_keys:
                await self.client.keys_query()
                await self._auto_trust_devices()

            # 3. Process to-device messages (key shares)
            await self.client.send_to_device_messages()

            # 4. Claim keys for missing sessions in rooms
            for room_id in list(self.client.rooms):
                if not getattr(self.client.rooms.get(room_id), "encrypted", False):
                    continue
                missing = self.client.get_missing_sessions(room_id)
                if not missing:
                    continue
                # Filter blacklisted
                has_good = any(
                    (uid, d) not in self._blacklisted_devices
                    for uid, devs in missing.items()
                    for d in devs
                )
                if has_good:
                    await self._establish_sessions_for_room(room_id)

            # 5. Retry any pending decryption
            await self._retry_pending_decryptions()

        except Exception as e:
            core.log("matrix", f"Encryption key sync error: {e}")

    async def _main_loop(self):
        backoff = 1
        while self.running and not self._shutting_down:
            try:
                resp = await self.client.sync(timeout=30000)
                if isinstance(resp, SyncResponse):
                    await self._sync_encryption_keys()
                    backoff = 1
                elif isinstance(resp, SyncError):
                    core.log("matrix", f"Sync error: {resp.message}")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                core.log("matrix", f"Sync exception: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    # ── message handling / streaming ──────────────────────────────────────

    async def _handle_message(self, room_id: str, message: str):
        typing_task = asyncio.create_task(self._keep_typing(room_id))

        last_event_id: Optional[str] = None
        last_edit_time: float = 0
        tool_calls_display: list[str] = []
        response_parts: list[str] = []

        try:
            async for token in self.send_stream({"role": "user", "content": message}):
                t_type = token.get("type")
                content = token.get("content", "")

                if t_type == "tool_calls" and content:
                    tools = content if isinstance(content, list) else [content]
                    for tool in tools:
                        tool_calls_display.append(self._format_tool_call(tool))
                elif t_type in ("content", "error"):
                    response_parts.append(content)

                tools_text = "\n".join(tool_calls_display)
                body_text = "".join(response_parts)
                if tools_text and body_text:
                    visual = f"{tools_text}\n\n{body_text}"
                else:
                    visual = tools_text or body_text

                if not visual:
                    continue

                now = time.time()
                if last_event_id is None:
                    resp = await self._send_room_message(room_id, visual)
                    if isinstance(resp, RoomSendResponse):
                        last_event_id = resp.event_id
                    last_edit_time = now
                elif now - last_edit_time >= 2.0:
                    await self._edit_room_message(room_id, last_event_id, visual)
                    last_edit_time = now

            # ── final update ──────────────────────────────────────────
            tools_text = "\n".join(tool_calls_display)
            body_text = "".join(response_parts)
            if tools_text and body_text:
                final = f"{tools_text}\n\n{body_text}"
            else:
                final = tools_text or body_text

            if final:
                if last_event_id:
                    await self._edit_room_message(room_id, last_event_id, final)
                else:
                    await self._send_room_message(room_id, final)

        except Exception as e:
            core.log("matrix", f"Message handling error: {e}")
            await self._send_room_message(room_id, f"❌ Error: {e}")
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    def _format_tool_call(self, tool_data) -> str:
        # (Preserved from original)
        try:
            import json_repair
            if hasattr(tool_data, "function"):
                func_name = getattr(tool_data.function, "name", "unknown")
                raw_args = getattr(tool_data.function, "arguments", "{}")
            elif isinstance(tool_data, dict) and "function" in tool_data:
                func_name = tool_data["function"].get("name", "unknown")
                raw_args = tool_data["function"].get("arguments", "{}")
            else:
                return "🔧 Calling tool…"

            if isinstance(raw_args, str):
                args_dict = json_repair.loads(raw_args)
            elif isinstance(raw_args, dict):
                args_dict = raw_args
            else:
                args_dict = {}

            arg_strs = [f'{k}="{str(v)[:30]}"' for k, v in args_dict.items()]
            return f"🔧 {func_name}({', '.join(arg_strs)})"
        except Exception:
            return "🔧 Calling tool…"

    # ── room I/O ──────────────────────────────────────────────────────────

    async def _announce(self, message: str, type: str = "info"):
        emoji = {
            "error": "🚨",
            "warning": "⚠️",
            "status": "ℹ️",
            "info": "💬",
        }.get(type, "🔔")

        text = f"{emoji} **{type.upper()}**: {message}"
        core.log("matrix", f"[{type}] {message}")

        if not self.client:
            return

        for room_id in list(self.client.rooms):
            try:
                await self._send_room_message(room_id, text)
            except Exception as e:
                core.log("matrix", f"Announce to {room_id} failed: {e}")



    async def _send_room_message(self, room_id: str, text: str):
        try:
            return await self.client.room_send(
                room_id,
                "m.room.message",
                {"msgtype": "m.text", "body": text},
                ignore_unverified_devices=True,
            )
        except Exception as e:
            core.log("matrix", f"Send failed ({room_id}): {e}")
            return None

    async def _edit_room_message(self, room_id: str, event_id: str, new_text: str):
        try:
            return await self.client.room_send(
                room_id,
                "m.room.message",
                {
                    "msgtype": "m.text",
                    "body": f"* {new_text}",
                    "m.new_content": {"msgtype": "m.text", "body": new_text},
                    "m.relates_to": {
                        "rel_type": "m.replace",
                        "event_id": event_id,
                    },
                },
                ignore_unverified_devices=True,
            )
        except Exception as e:
            core.log("matrix", f"Edit failed ({room_id}): {e}")
            return None

    async def _keep_typing(self, room_id: str):
        try:
            while True:
                await self.client.room_typing(room_id, True, timeout=15000)
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            try:
                await self.client.room_typing(room_id, False)
            except Exception:
                pass

    # ── shutdown / cleanup ────────────────────────────────────────────────

    async def shutdown(self):
        core.log("matrix", "Shutting down…")
        self.running = False
        self._shutting_down = True
        return True

    async def _cleanup(self):
        self._ready = False
        if self.client:
            try:
                await self.client.close()
            except Exception:
                pass
