"""The /ws websocket endpoint"""

import json
import time
import base64

import fastapi

import core

import channels.webui.utils as utils
import channels.webui.chat_ops as chat_ops

def register(app, channel):
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: fastapi.WebSocket):
        # check the origin of the request and reject if it's foreign
        ws_origin = websocket.headers.get("origin")
        if ws_origin and channel._origin_allowed(ws_origin, host_header=websocket.headers.get("host") or "") is False:
            channel.log(channel.name, f"websocket handshake rejected: foreign origin '{ws_origin}' (expected host '{channel.host}', port {channel.port}) - if this webui runs behind a proxy/tunnel, add that origin to the 'extra_allowed_origins' setting")
            await websocket.close(code=4003, reason="Foreign origin")
            return

        # WebSocket auth check (only when login is enforceable -- see
        # channel.auth_enforced)
        if channel.auth_enforced:
            ws_session = websocket.scope.get("session") or {}
            if not ws_session.get("authenticated", False):
                # check if rate limited
                client_ip = utils.trusted_client_ip(websocket)
                now = time.time()

                if client_ip in channel.login_attempts:
                    channel.login_attempts[client_ip] = [
                        t for t in channel.login_attempts[client_ip] if now - t < 900
                    ]
                    if len(channel.login_attempts[client_ip]) >= 5:
                        channel.log(channel.name, f"websocket handshake rejected: rate limited ({client_ip})")
                        await websocket.close(code=4001, reason="Rate limited")
                        return

                channel.log(channel.name, f"websocket handshake rejected: session not authenticated (cookie_present={channel.session_cookie_name in websocket.cookies}, client={client_ip})")
                await websocket.close(code=4001, reason="Unauthorized")
                return

        ws_mgr = channel.websocket_manager
        await ws_mgr.connect(websocket)

        try:
            while True:
                data_text = await websocket.receive_text()

                try:
                    data = json.loads(data_text)
                    msg_type = data.get("type")

                    match msg_type:
                        case "ping":
                            # keepalive ping
                            await websocket.send_json({"type": "pong"})
                        case "stop":
                            if channel:
                                await channel.manager.API.cancel()
                        case "reload_messages":
                            await ws_mgr.broadcast({
                                "type": "sync"
                            })
                            
                        case "rename":
                            new_title = data.get("title")
                            if channel and new_title:
                                await chat_ops.op_chat_rename(channel, new_title)
                        case "switch_chat":
                            new_chat_id = data.get("chat_id")
                            if new_chat_id:
                                success = await chat_ops.op_chat_switch(channel, new_chat_id)
                                if not success:
                                    await ws_mgr.broadcast({"type": "error", "content": "Failed to load chat"})
                        case "new_chat":
                            await chat_ops.op_chat_new(channel)
                        case "chat_delete":
                            chat_id = data.get("chat_id")
                            if not chat_id:
                                return False

                            await chat_ops.op_chat_delete(channel, chat_id)
                            
                        case "user_message":
                            text = data.get("content")
                            files_data = data.get("files")

                            if not text and not files_data:
                                break

                            files_dict = None
                            if files_data:
                                if not channel.config.get("enable_file_upload", True):
                                    await ws_mgr.broadcast({
                                        "type": "error",
                                        "error": "File uploads are disabled"
                                    })
                                    continue

                                files_dict = {
                                    f["name"]: base64.b64decode(f["data"])
                                    for f in files_data
                                }

                            chat_id = channel.context.chat.get("id") or "default"
                            await ws_mgr.start_stream(channel, chat_id, message=text, files=files_dict)
                        case "message_edit":
                            index = data.get("index")
                            if index < 0:
                                return False

                            message = await channel.context.chat.messages.get(index)
                            message["content"] = data.get("content")
                            await channel.context.chat.messages.edit(index, message)

                            await ws_mgr.broadcast({
                                "type": "sync"
                            })
                        case "message_delete":
                            index = data.get("index")
                            if index < 0:
                                return False

                            await channel.context.chat.messages.delete_from(index)
                            await ws_mgr.broadcast({
                                "type": "sync"
                            })
                        case "message_regenerate":
                            index = data.get("index")

                            if index is not None and channel:
                                last_user_message_index = await channel.context.chat.messages.get_last_message_with_role("user", cutoff_index=index)

                                if last_user_message_index == -1:
                                    await ws_mgr.broadcast({
                                        "type": "error",
                                        "error": "Could not regenerate message (no preceding user message found)"
                                    })
                                    return

                                user_message = await channel.context.chat.messages.get(last_user_message_index)

                                # delete_from deletes all messages after the target, so we need to do index-1
                                # max(0, index) clamps it so that it never goes below 0
                                await channel.context.chat.messages.delete_from(max(0, last_user_message_index))

                                await ws_mgr.broadcast({"type": "sync"})
                                await ws_mgr.start_stream(channel, channel.context.chat.get("id"), user_message.get("content"))
                        case _:
                            channel.log(channel.name, f"Unknown websocket command received: {msg_type}")

                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    channel.log(channel.name, f"WebSocket command error: {core.detail_error(e)}")

        except fastapi.WebSocketDisconnect as e:
            ws_mgr.disconnect(websocket)
        except Exception as e:
            channel.log(channel.name, f"WebSocket error: {core.detail_error(e)}")
            ws_mgr.disconnect(websocket)
