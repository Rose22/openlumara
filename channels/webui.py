"""
OpenLumara WebUI - FastAPI Refactor

Refactored from Flask to FastAPI for native asyncio support,
removing the need for threading workarounds and Flask-SocketIO.
"""

import os
import asyncio
import json
import uuid
import base64
import secrets
import time
import copy
from datetime import datetime
from collections import defaultdict
from typing import List, Set, Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response, Depends, HTTPException, status, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse
from fastapi.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.websockets import WebSocketState

import core
import msgpack
import yaml
import logging
import io

WEBUI_DIR = core.get_path("channels/webui")

# ordered list of javascript files, to load in this exact order
JS_FILES = [
    "themes", "icons", "variables", "content_helpers", "markdown", "messages",
    "msg_actions", "sidebar", "utils", "notif", "status", "polling", "chats",
    "tags", "search", "export", "modals", "autocomplete", "input", "send", "upload", "theming",
    "audio", "modal_settings", "storage_editor", "responsive", "init"
]

# same deal for css files
CSS_FILES = [
    "variables", "base", "errors", "containers", "sidebar", "tags", "rename", "content",
    "header", "titlebar", "search", "modals", "search", "containers", "messages",
    "input", "upload", "keyboard", "responsive", "typewriter", "settings",
    "storage_editor", "autocomplete"
]

# Rate limiting for login attempts
FAILED_ATTEMPTS = defaultdict(list)
RATE_LIMIT_WINDOW = 900  # 15 minutes
MAX_ATTEMPTS = 5

# Set of active Bearer tokens for API access
ACTIVE_TOKENS: Set[str] = set()

# -----------------------------------------------------------------------------
# FastAPI App Setup
# -----------------------------------------------------------------------------

webui_config = core.config.get("channels", {}).get("settings", {}).get("webui", {})
SECRET_KEY = webui_config.get("secret_key", secrets.token_hex(32))

app = FastAPI(docs_url=None, redoc_url=None)

# Static files
app.mount("/static", StaticFiles(directory=os.path.join(WEBUI_DIR, "static")), name="static")

# Templates
templates = Jinja2Templates(directory=WEBUI_DIR)

# Disable logging
log = logging.getLogger('uvicorn')
log.setLevel(logging.ERROR)

# Global reference to the channel instance
channel_instance: Optional[Any] = None
stream_cancellations: Set[str] = set()

# -----------------------------------------------------------------------------
# WebSocket Manager
# -----------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_users: Dict[WebSocket, str] = {}  # Track authenticated users

    async def connect(self, websocket: WebSocket, user: str = "anonymous"):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_users[websocket] = user

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.connection_users.pop(websocket, None)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                if connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_json(message)
            except Exception:
                pass

manager = ConnectionManager()

async def authenticate_websocket(websocket: WebSocket) -> Optional[str]:
    """
    Authenticate WebSocket connection using token or session.
    Returns username if authenticated, None otherwise.
    """
    if not channel_instance:
        return None

    # If login not required, allow anonymous
    if not bool(channel_instance.config.get("require_login")):
        return "anonymous"

    # Method 1: Check session (via cookies - works with browser clients)
    session = getattr(websocket, 'session', None)
    if session and session.get('username'):
        return session.get('username')

    # Method 2: Check Bearer token in query parameters
    token = websocket.query_params.get('token')
    if token and token in ACTIVE_TOKENS:
        return "token_user"

    # Method 3: Check Authorization header (some clients send headers)
    auth_header = websocket.headers.get('authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        if token in ACTIVE_TOKENS:
            return "token_user"

    return None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Authenticate before accepting connection
    user = await authenticate_websocket(websocket)

    if user is None:
        # Reject unauthenticated connection
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await manager.connect(websocket, user)
    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                data = json.loads(data_text)
                msg_type = data.get("type")

                if msg_type == "stop":
                    # Signal the API to stop
                    if channel_instance and channel_instance.manager.API:
                        channel_instance.manager.API.cancel_request = True

                elif msg_type == "cancel":
                    stream_id = data.get("id")
                    if stream_id:
                        stream_cancellations.add(stream_id)

                elif msg_type == "rename":
                    new_title = data.get("title")
                    if channel_instance and new_title:
                        await channel_instance.context.chat.set_title(new_title)
                        # Broadcast the update
                        await manager.broadcast({
                            "type": "chat_metadata_updated",
                            "title": new_title,
                            "tags": await channel_instance.context.chat.get_tags() or []
                        })

            except json.JSONDecodeError:
                pass
            except Exception as e:
                core.log("webui", f"WebSocket command error: {e}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        core.log("webui", f"WebSocket error: {e}")
        manager.disconnect(websocket)


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

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

# -----------------------------------------------------------------------------
# Security & Auth Middleware
# -----------------------------------------------------------------------------

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.socket.io; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' wss:; "
        "frame-ancestors 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    if request.url.path in ['/', '/sw.js']:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

async def get_current_user(request: Request):
    if not channel_instance or not bool(channel_instance.config.get("require_login")):
        return "user"

    # Check Session
    if 'username' in request.session:
        return request.session['username']

    # Check Bearer Token
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[len('Bearer '):]
        if token in ACTIVE_TOKENS:
            return "token_user"

    return None

async def require_auth(request: Request):
    """Dependency to require authentication for specific routes."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

# Define paths that don't require authentication
PUBLIC_PATHS = {
    '/login', '/api/login', '/api/health',
    '/manifest.json', '/sw.js', '/icon-192.png', '/icon-512.png'
}

@app.middleware("http")
async def require_login_middleware(request: Request, call_next):
    global channel_instance

    # Allow static files and public paths immediately
    if request.url.path.startswith('/static') or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    if not channel_instance:
        return JSONResponse({'error': "Channel object not found"}, status_code=500)

    if not bool(channel_instance.config.get("require_login")):
        # Auto-logout if auth turned off
        if 'username' in request.session:
            request.session.pop('username', None)
        return await call_next(request)

    user = await get_current_user(request)
    if user:
        return await call_next(request)

    # Not authenticated
    # For API routes and JSON requests, return 401
    is_api_request = (
        request.url.path.startswith('/api') or
        request.url.path.startswith('/messages') or
        request.url.path.startswith('/send') or
        request.url.path.startswith('/stream') or
        request.url.path.startswith('/edit') or
        request.url.path.startswith('/delete') or
        request.url.path.startswith('/cancel') or
        request.url.path.startswith('/upload') or
        request.url.path.startswith('/chat') or
        request.url.path.startswith('/storage') or
        request.url.path.startswith('/settings') or
        request.url.path.startswith('/server') or
        request.url.path.startswith('/get_') or
        request.headers.get("accept") == "application/json"
    )

    if is_api_request:
        return JSONResponse({'error': 'Unauthorized'}, status_code=401)

    return RedirectResponse(url='/login', status_code=303)

# -----------------------------------------------------------------------------
# Authentication Routes
# -----------------------------------------------------------------------------

@app.get("/login")
async def login_page(request: Request):
    if not channel_instance or not bool(channel_instance.config.get("username")):
        return RedirectResponse(url='/')
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})

@app.post("/login")
async def login_post(request: Request):
    global channel_instance

    if not channel_instance or not bool(channel_instance.config.get("username")):
        return RedirectResponse(url='/')

    form = await request.form()
    ip_address = request.client.host if request.client else "unknown"
    now = time.time()

    # Rate limiting check
    attempts = FAILED_ATTEMPTS[ip_address]
    attempts[:] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
    if len(attempts) >= MAX_ATTEMPTS:
        return templates.TemplateResponse(request, "login.html", {"request": request, "error": "Too many failed attempts. Please try again in 15 minutes."})

    username = form.get('username')
    password = form.get('password')

    webui_config = core.config.get("channels", {}).get("settings", {}).get("webui", {})
    expected_username = webui_config.get("username")
    expected_password = webui_config.get("password")

    if expected_username and expected_password and username == expected_username and password == expected_password:
        request.session['username'] = username
        FAILED_ATTEMPTS.pop(ip_address, None)
        return RedirectResponse(url='/', status_code=303)
    else:
        FAILED_ATTEMPTS[ip_address].append(now)
        return templates.TemplateResponse(request, "login.html", {"request": request, "error": "Invalid username or password"})

@app.post("/api/login")
async def api_login(request: Request):
    data = await request.json()
    username = data.get('username')
    password = data.get('password')

    webui_config = core.config.get("channels", {}).get("settings", {}).get("webui", {})
    expected_username = webui_config.get("username")
    expected_password = webui_config.get("password")

    if not expected_username or not expected_password:
        raise HTTPException(status_code=500, detail='Authentication not configured on server')

    if username == expected_username and password == expected_password:
        token = secrets.token_urlsafe(32)
        ACTIVE_TOKENS.add(token)
        return {'token': token}
    else:
        raise HTTPException(status_code=401, detail="Invalid credentials")

@app.get("/logout")
async def logout(request: Request):
    request.session.pop('username', None)
    webui_config = core.config.get("channels", {}).get("settings", {}).get("webui", {})
    if not webui_config.get("username"):
        return RedirectResponse(url='/')
    return RedirectResponse(url='/login')

@app.post("/api/logout")
async def api_logout(request: Request):
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[len('Bearer '):]
        if token in ACTIVE_TOKENS:
            ACTIVE_TOKENS.remove(token)
    return {'success': True}

# -----------------------------------------------------------------------------
# Main Routes
# -----------------------------------------------------------------------------

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "js_files": JS_FILES,
            "css_files": CSS_FILES,
            "require_login": bool(channel_instance.config.get("require_login"))
        }
    )

@app.get("/api/health")
async def health_check():
    """Public health check endpoint - no auth required."""
    return {"status": "OK"}

def get_api_status():
    """Get detailed API connection status."""
    if not channel_instance:
        return {
            'connected': False, 'server_ok': False,
            'error': 'Channel not available', 'error_type': 'server_error',
            'action': 'Please restart the application.'
        }

    status = channel_instance.manager.get_api_status()
    result = {
        'connected': status.get('connected', False), 'server_ok': True,
        'model': status.get('model'),
        'url_configured': status.get('url_configured', False),
        'key_configured': status.get('key_configured', False),
        'model_configured': status.get('model_configured', False),
    }

    if not result['connected']:
        error = status.get('error', 'Unknown error')
        result['error'] = error
        if not result['url_configured']:
            result['error_type'], result['action'] = 'config_missing', 'Please configure your API URL in Settings.'
        elif not result['key_configured']:
            result['error_type'], result['action'] = 'config_missing', 'Please configure your API key in Settings.'
        elif not result['model_configured']:
            result['error_type'], result['action'] = 'config_missing', 'Please configure a model name in Settings.'
        elif error:
            if 'authentication' in error.lower() or 'api key' in error.lower():
                result['error_type'], result['action'] = 'auth_failed', 'Your API key is invalid. Please check your settings.'
            elif 'connection' in error.lower() or 'reach' in error.lower():
                result['error_type'], result['action'] = 'connection_failed', 'Could not reach the API server. Check the URL and your network.'
            else:
                result['error_type'], result['action'] = 'unknown', f'Error: {error}'
    return result

@app.get("/api/status")
async def api_status(user: str = Depends(require_auth)):
    return get_api_status()

@app.post("/api/reconnect")
async def api_reconnect(user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")
    result = await channel_instance.manager.reconnect_api()
    return result

@app.post("/api/disconnect")
async def api_disconnect(user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")
    await channel_instance.manager.API.disconnect()
    return {'success': True}

@app.get("/api/models")
async def list_models(user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")
    if not channel_instance.manager.API.connected:
        raise HTTPException(status_code=503, detail="Not connected to API")
    try:
        models = await channel_instance.manager.API.list_models()
        return {'models': models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/messages")
async def get_messages(user: str = Depends(require_auth)):
    if not channel_instance:
        return {'messages': [], 'count': 0}

    messages_orig = await channel_instance.context.chat.get() or []
    messages = copy.deepcopy(messages_orig)

    current_id = await channel_instance.context.chat.get_id()

    for i, msg in enumerate(messages):
        msg['index'] = i

    return {'messages': messages, 'count': len(messages), 'current_chat_id': current_id}

@app.get("/messages/since")
async def get_messages_since(index: int = 0, user: str = Depends(require_auth)):
    if not channel_instance:
        return {'messages': [], 'count': 0}

    messages_orig = await channel_instance.context.chat.get() or []
    messages = copy.deepcopy(messages_orig)

    current_id = await channel_instance.context.chat.get_id()
    current_title = await channel_instance.context.chat.get_title()
    current_tags = await channel_instance.context.chat.get_tags() or []

    for i, msg in enumerate(messages):
        msg['index'] = i

    messages_slice = messages[index:]

    return {
        'messages': messages_slice, 'count': len(messages_slice), 'total': len(messages_slice),
        'current_chat_id': current_id, 'current_chat_title': current_title,
        'current_chat_tags': current_tags
    }

@app.get("/api/token_usage")
async def token_usage(user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")
    try:
        usage = await channel_instance.context.get_token_usage()
        return usage
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/command_prefix")
async def get_command_prefix(user: str = Depends(require_auth)):
    return core.config.get("core", "cmd_prefix")

@app.get("/api/commands")
async def get_commands(user: str = Depends(require_auth)):
    global channel_instance
    return core.commands.get_commands(channel_instance.manager.modules)

@app.post("/stream")
async def stream_message(request: Request, user: str = Depends(require_auth)):
    global channel_instance

    status = get_api_status()
    if not status['connected']:
        raise HTTPException(status_code=503, detail=status)

    data = await request.json()
    stream_id = str(uuid.uuid4())[:8]

    async def event_generator():
        try:
            # Initial connection signal
            yield f"data: {json.dumps({'_meta': {'type': 'connection', 'status': 'connected'}, 'id': stream_id})}\n\n"

            async for token_data in channel_instance.send_stream(data):
                if stream_id in stream_cancellations:
                    stream_cancellations.discard(stream_id)
                    yield f"data: {json.dumps({'_meta': {'type': 'cancelled'}})}\n\n"
                    break

                if isinstance(token_data, dict) and token_data.get('type') == 'error':
                    yield f"data: {json.dumps({'_meta': {'type': 'error'}, 'error_data': token_data.get('content', {})})}\n\n"
                    break

                # Map status
                p_type = token_data.get("type")
                status_str = "idle"
                if p_type == "reasoning": status_str = "thinking"
                elif p_type in ["tool_call_delta", "tool", "tool_calls"]: status_str = "tool_call"
                elif p_type == "tool": status_str = "tool_exec"

                payload = serialize_for_json(token_data)
                payload["_meta"] = {"type": "delta", "status": status_str}
                yield f"data: {json.dumps(payload)}\n\n"

            # Post-stream: Broadcast the new message
            messages = await channel_instance.context.chat.get() or []
            if messages:
                last_msg = messages[-1]
                await manager.broadcast({
                    "type": "message_added",
                    "message": serialize_for_json(last_msg)
                })

            # Commit phase
            serialized_history = [serialize_for_json(m) for m in messages]
            yield f"data: {json.dumps({'_meta': {'type': 'commit'}, 'history': serialized_history})}\n\n"

        except Exception as e:
            err_msg = core.detail_error(e) if core.debug else str(e)
            yield f"data: {json.dumps({'_meta': {'type': 'error'}, 'error': err_msg})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    })


@app.post("/send")
async def send_message(request: Request, user: str = Depends(require_auth)):
    global channel_instance

    status = get_api_status()
    if not status['connected']:
        raise HTTPException(status_code=503, detail=status)

    data = await request.json()
    response = await channel_instance.send(data)

    if isinstance(response, dict) and 'error' in response:
        raise HTTPException(status_code=500, detail=response)

    messages = await channel_instance.context.chat.get() or []
    current_id = await channel_instance.context.chat.get_id()
    current_title = await channel_instance.context.chat.get_title()

    return {
        'response': response, 'total': len(messages),
        'current_chat': {'id': current_id, 'title': current_title}
    }

@app.post("/edit")
async def edit_message(request: Request, user: str = Depends(require_auth)):
    data = await request.json()
    index = data.get('index', 0)
    new_content = data.get('content', '')

    messages = await channel_instance.context.chat.get()
    if 0 <= index < len(messages):
        if messages[index].get('role') in ('user', 'assistant'):
            messages[index]['content'] = new_content
            await channel_instance.context.chat.set(messages)
            return {'success': True, 'total': len(messages)}
        return {'success': False, 'error': 'Cannot edit this message type'}
    return {'success': False, 'error': f'Index {index} out of range'}

@app.post("/delete")
async def delete_message(request: Request, user: str = Depends(require_auth)):
    data = await request.json()
    index = data.get('index', 0)

    messages = await channel_instance.context.chat.get()
    if 0 <= int(index) < len(messages):
        if messages[index].get('role') in ('user', 'assistant', 'command', 'command_response') or messages[index].get('role', '').startswith('announce_'):
            await channel_instance.context.chat.set(messages[:index])
            remaining = len(await channel_instance.context.chat.get())
            return {'success': True, 'remaining': remaining}
    return {'success': False, 'error': f'Index {index} out of range'}

@app.post("/cancel")
async def cancel_stream(request: Request, user: str = Depends(require_auth)):
    data = await request.json()
    stream_id = data.get('id')
    channel_instance.manager.API.cancel_request = True
    if stream_id:
        stream_cancellations.add(stream_id)
    return {'success': True}

@app.post("/upload")
async def upload_file(request: Request, user: str = Depends(require_auth)):
    data = await request.json()
    files_data = data.get('files', [])
    if not files_data:
        raise HTTPException(status_code=400, detail="No files provided")

    message_content = []
    for f in files_data:
        filename = f.get('filename', '')
        content_b64 = f.get('content', '')
        is_image = f.get('is_image', False)

        if is_image:
            image_url = f"data:image/jpeg;base64,{content_b64}"
            message_content.append({"type": "text", "text": f"[Image: {filename}]"})
            message_content.append({"type": "image_url", "image_url": {"url": image_url}})
        else:
            content = base64.b64decode(content_b64).decode('utf-8', errors='replace')
            message_content.append({"type": "text", "text": f"[File: {filename}]\n{content}"})

    await channel_instance.context.chat.add({"role": "user", "content": message_content})
    total = len(await channel_instance.context.chat.get())
    return {'success': True, 'total': total, 'type': 'multi'}

# =============================================================================
# Chat Management Routes
# =============================================================================

@app.post("/api/search")
async def search_chats(request: Request, user: str = Depends(require_auth)):
    if not channel_instance:
        return JSONResponse({'error': 'Channel not available'}, status_code=500)

    data = await request.json()
    query = data.get("query", "").lower().strip()
    search_in_content = data.get("search_in_content", True)
    category = data.get("category")

    if not query:
        return {"results": []}

    all_chats = await channel_instance.context.chat.get_all()

    # Filter by category if provided
    if category:
        if category == 'general':
            all_chats = [c for c in all_chats if not c.get('category') or c.get('category') == 'general']
        else:
            all_chats = [c for c in all_chats if c.get('category') == category]

    results = []

    for conv in all_chats:
        title = conv.get('title', '')
        title_lower = title.lower()
        title_match = query in title_lower
        content_match = False
        snippet = None

        if search_in_content and conv.get('messages'):
            for msg in conv['messages']:
                content_parts = []
                raw_content = msg.get('content', '')
                if isinstance(raw_content, str):
                    content_parts.append(raw_content)
                elif isinstance(raw_content, list):
                    for part in raw_content:
                        if isinstance(part, dict) and part.get('type') == 'text':
                            content_parts.append(part.get('text', ''))

                content = "".join(content_parts)
                content_lower = content.lower()

                if query in content_lower:
                    content_match = True
                    start_idx = content_lower.find(query)
                    end_idx = start_idx + len(query)

                    context_padding = 40
                    snippet_start = max(0, start_idx - context_padding)
                    snippet_end = min(len(content), end_idx + context_padding)
                    snippet = content[snippet_start:snippet_end]

                    if snippet_start > 0:
                        snippet = "..." + snippet
                    if snippet_end < len(content):
                        snippet = snippet + "..."
                    break

        if title_match or content_match:
            results.append({
                'chat': {
                    'id': conv.get('id'),
                    'title': title,
                    'updated': conv.get('updated'),
                    'created': conv.get('created'),
                    'tags': conv.get('tags', []),
                    'category': conv.get('category', 'general'),
                    'custom_data': conv.get('custom_data', {})
                },
                'title_match': title_match,
                'snippet': snippet
            })

    results.sort(key=lambda x: (
        not x['title_match'],
        -datetime.fromisoformat(x['chat']['updated']).timestamp() if x['chat']['updated'] else 0
    ))
    return {"results": results}


@app.get("/chats")
async def list_chats(user: str = Depends(require_auth)):
    if not channel_instance:
        return {'chats': []}

    all_chats = await channel_instance.context.chat.get_all()
    chats = []

    for conv in all_chats:
        messages_preview = []
        for msg in conv.get('messages', [])[:5]:
            raw_content = msg.get('content', '')
            text_content = ""
            if isinstance(raw_content, str):
                text_content = raw_content
            elif isinstance(raw_content, list):
                parts = []
                for part in raw_content:
                    if isinstance(part, dict) and part.get('type') == 'text':
                        parts.append(part.get('text', ''))
                    elif isinstance(part, dict) and part.get('type') == 'image_url':
                        parts.append("[Image]")
                text_content = " ".join(parts)

            if text_content:
                messages_preview.append({
                    'role': msg.get('role'),
                    'content': text_content[:500]
                })

        chats.append({
            'id': conv.get('id'), 'title': conv.get('title', ''),
            'category': conv.get('category', ''), 'tags': conv.get('tags', []),
            'custom_data': conv.get('custom_data', {}), 'created': conv.get('created'),
            'updated': conv.get('updated'), 'message_count': len(conv.get('messages', [])),
            'messages': messages_preview
        })

    chats.sort(key=lambda x: x.get('updated', ''), reverse=True)
    return {'chats': chats}

@app.get("/chat/load")
async def load_chat(id: str, user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")

    await channel_instance._set_as_active_channel()
    success = await channel_instance.context.chat.load(id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")

    messages_orig = await channel_instance.context.chat.get() or []
    messages = copy.deepcopy(messages_orig)

    title = await channel_instance.context.chat.get_title()
    loaded_id = await channel_instance.context.chat.get_id()
    category = await channel_instance.context.chat.get_category()
    tags = await channel_instance.context.chat.get_tags() or []
    custom_data = await channel_instance.context.chat.get_data()

    for i, msg in enumerate(messages):
        msg['index'] = i

    return {
        'success': True, 'chat': {
            'id': loaded_id, 'title': title, "category": category, 'tags': tags,
            'custom_data': custom_data, 'messages': messages, 'total': len(messages)
        }
    }

@app.get("/chat/current")
async def get_current_chat(user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")

    chat = channel_instance.context.chat
    conv_id = await chat.get_id()
    if conv_id is None:
        return {'success': True, 'current_id': None, 'chat': None}

    messages_orig = await channel_instance.context.chat.get() or []
    messages = copy.deepcopy(messages_orig)

    title = await chat.get_title()
    tags = await chat.get_tags() or []
    category = await chat.get_category()
    custom_data = await chat.get_data()

    for i, msg in enumerate(messages):
        msg['index'] = i

    return {
        'success': True, 'chat': {
            'id': conv_id, 'title': title or 'New chat', 'category': category or 'general',
            'tags': tags, 'custom_data': custom_data, 'messages': messages, 'total': len(messages)
        }
    }

@app.post("/chat/rename")
async def rename_chat(request: Request, user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")

    data = await request.json()
    new_title = data.get('title', '').strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    await channel_instance.context.chat.set_title(new_title)

    # Broadcast the update so all clients are in sync
    await manager.broadcast({
        "type": "chat_metadata_updated",
        "title": new_title,
        "tags": await channel_instance.context.chat.get_tags() or []
    })

    return {'success': True, 'title': new_title}


@app.post("/chat/update_category")
async def update_chat_category(request: Request, user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")

    data = await request.json()
    chat_id = data.get('chat_id')
    new_category = data.get('category', '')

    if not chat_id:
        raise HTTPException(status_code=400, detail="Chat ID is required")

    current_id = await channel_instance.context.chat.get_id()
    was_current = (current_id == chat_id)

    try:
        if not was_current:
            load_response = await channel_instance.context.chat.load(chat_id)
            if not load_response:
                raise HTTPException(status_code=404, detail="Failed to load chat")

        await channel_instance.context.chat.set_category(new_category)

        if not was_current and current_id:
            await channel_instance.context.chat.load(current_id)

        return {'success': True}
    except Exception as e:
        if not was_current and current_id:
            try:
                await channel_instance.context.chat.load(current_id)
            except:
                pass
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/new")
async def new_chat(request: Request, user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")

    await channel_instance._set_as_active_channel()
    data = await request.json() or {}

    await channel_instance.context.chat.new(title=data.get('title'), category=data.get('category'), metadata=data.get('metadata'))

    return {
        'success': True, 'chat': {
            'id': await channel_instance.context.chat.get_id(),
            'title': data.get('title', ''), 'category': data.get('category', ''),
            'messages': [], 'metadata': data.get('metadata', {})
        }
    }

@app.post("/chat/clear")
async def clear_chat(user: str = Depends(require_auth)):
    global channel_instance

    await channel_instance.context.chat.clear()
    return {"success": True}

@app.post("/chat/delete")
async def delete_chat(request: Request, user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")

    data = await request.json()
    conv_id = data.get('id')

    if not conv_id:
        raise HTTPException(status_code=400, detail="No chat ID provided")

    success = await channel_instance.context.chat.delete(conv_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {'success': True}

@app.get("/chat/tags")
async def get_all_tags(user: str = Depends(require_auth)):
    if not channel_instance:
        return {'tags': []}

    all_chats = await channel_instance.context.chat.get_all() or []
    tags = set()

    for chat in all_chats:
        for tag in chat.get('tags', []):
            tags.add(tag)

    return {'tags': sorted(list(tags))}

@app.post("/chat/tags")
async def update_chat_tags(request: Request, user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")

    data = await request.json()
    tags = data.get('tags', [])

    if not isinstance(tags, list):
        raise HTTPException(status_code=400, detail="Tags must be a list")

    await channel_instance.context.chat.set_tags(tags)
    return {'success': True, 'tags': tags}

@app.post("/chat/tag")
async def add_chat_tag(request: Request, user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")

    data = await request.json()
    tag = data.get('tag', '').strip()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag cannot be empty")

    success = await channel_instance.context.chat.add_tag(tag)
    return {'success': success, 'tag': tag}

@app.delete("/chat/tag")
async def remove_chat_tag(request: Request, user: str = Depends(require_auth)):
    if not channel_instance:
        raise HTTPException(status_code=500, detail="Channel not available")

    data = await request.json()
    tag = data.get('tag', '').strip()
    if not tag:
        raise HTTPException(status_code=400, detail="Tag cannot be empty")

    success = await channel_instance.context.chat.pop_tag(tag)
    return {'success': success, 'tag': tag}

# =============================================================================
# Settings editing routes
# =============================================================================

@app.get("/settings/load")
async def load_settings(user: str = Depends(require_auth)):
    return core.config.config

@app.post("/settings/save")
async def save_settings(request: Request, user: str = Depends(require_auth)):
    form_data = await request.json()
    result = core.config.config.load(data=form_data)
    core.config.config.save()

    if not result:
        raise HTTPException(status_code=500, detail="Something went wrong while saving settings!")

    return {"success": True}

@app.get("/settings/get_module_info")
async def get_module_info(user: str = Depends(require_auth)):
    module_info = {}
    for module_name, module_data in core.config.get_module_structure().items():
        metadata = module_data.get("metadata", {})
        settings_schema = module_data.get("settings", {})

        if module_name not in module_info.keys():
            module_info[module_name] = {
                "description": metadata.get("doc", ""),
                "unsafe": metadata.get("unsafe", False),
                "settings_schema": settings_schema
            }

    return {"success": True, "module_info": module_info}

# =============================================================================
# Storage Editor Routes
# =============================================================================

@app.get("/storage/list")
async def list_storage_files(user: str = Depends(require_auth)):
    """List all storage files in the data folder."""
    data_dir = core.get_data_path()
    if not os.path.exists(data_dir):
        return {'files': []}

    files = []

    for root, dirs, filenames in os.walk(data_dir):
        for filename in filenames:
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, data_dir)

            ext = os.path.splitext(filename)[1].lower()
            file_type = None

            if ext in ['.json', '.yml', '.yaml', '.mp']:
                try:
                    if ext == '.json':
                        with open(full_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            file_type = 'dict' if isinstance(data, dict) else 'list' if isinstance(data, list) else 'text'
                    elif ext in ['.yml', '.yaml']:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            data = yaml.safe_load(f)
                            file_type = 'dict' if isinstance(data, dict) else 'list' if isinstance(data, list) else 'text'
                    elif ext == '.mp':
                        with open(full_path, 'rb') as f:
                            data = msgpack.unpackb(f.read())
                            file_type = 'dict' if isinstance(data, dict) else 'list' if isinstance(data, list) else 'text'
                except Exception as e:
                    core.log("webui", f"Error reading {rel_path}: {e}")
                    file_type = 'unknown'
            elif ext in ['.txt', '.md']:
                file_type = 'text'
            else:
                continue

            files.append({
                'path': rel_path,
                'type': file_type,
                'name': filename
            })

    files.sort(key=lambda x: x['path'].lower())
    return {'files': files, 'data_dir': data_dir}

@app.get("/storage/load")
async def load_storage_file(file: str, user: str = Depends(require_auth)):
    """Load a specific storage file."""
    data_dir = core.get_data_path()
    full_path = os.path.join(data_dir, file)

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Security check - prevent path traversal
    if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    ext = os.path.splitext(file)[1].lower()

    try:
        if ext == '.json':
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {'success': True, 'type': 'dict', 'keys': sorted(data.keys()), 'data': data}
            elif isinstance(data, list):
                return {'success': True, 'type': 'list', 'data': data}

        elif ext in ['.yml', '.yaml']:
            with open(full_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return {'success': True, 'type': 'dict', 'keys': sorted(data.keys()), 'data': data}
            elif isinstance(data, list):
                return {'success': True, 'type': 'list', 'data': data}

        elif ext == '.mp':
            with open(full_path, 'rb') as f:
                data = msgpack.unpackb(f.read())
            if isinstance(data, dict):
                return {'success': True, 'type': 'dict', 'keys': sorted(data.keys()), 'data': data}
            elif isinstance(data, list):
                return {'success': True, 'type': 'list', 'data': data}

        elif ext in ['.txt', '.md']:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {'success': True, 'type': 'text', 'data': content}

        raise HTTPException(status_code=400, detail="Unsupported file type")

    except Exception as e:
        err_msg = core.detail_error(e) if core.debug else str(e)
        core.log("webui", f"Error loading storage file: {e}")
        raise HTTPException(status_code=500, detail=err_msg)

@app.post("/storage/save")
async def save_storage_file(request: Request, user: str = Depends(require_auth)):
    """Save a storage file."""
    data = await request.json()
    file_path = data.get('file')
    storage_type = data.get('type')
    content = data.get('data')

    if not file_path:
        raise HTTPException(status_code=400, detail="No file specified")

    data_dir = core.get_data_path()
    full_path = os.path.join(data_dir, file_path)

    # Security check - prevent path traversal
    if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if storage_type == 'dict':
            data_to_save = content
            if ext == '.json':
                with open(full_path, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            elif ext in ['.yml', '.yaml']:
                with open(full_path, 'w', encoding='utf-8') as f:
                    yaml.dump(data_to_save, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            elif ext == '.mp':
                with open(full_path, 'wb') as f:
                    f.write(msgpack.packb(data_to_save))
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type for dict")

        elif storage_type == 'list':
            data_to_save = content
            if ext == '.json':
                with open(full_path, 'w', encoding='utf-8') as f:
                    json.dump(data_to_save, f, indent=2, ensure_ascii=False)
            elif ext in ['.yml', '.yaml']:
                with open(full_path, 'w', encoding='utf-8') as f:
                    yaml.dump(data_to_save, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            elif ext == '.mp':
                with open(full_path, 'wb') as f:
                    f.write(msgpack.packb(data_to_save))
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type for list")

        elif storage_type == 'text':
            if ext in ['.txt', '.md']:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                raise HTTPException(status_code=400, detail="Unsupported file type for text")

        else:
            raise HTTPException(status_code=400, detail="Unknown storage type")

        core.log("webui", f"Saved storage file: {file_path}")
        return {'success': True}

    except Exception as e:
        err_msg = core.detail_error(e) if core.debug else str(e)
        core.log("webui", f"Error saving storage file: {e}")
        raise HTTPException(status_code=500, detail=err_msg)

@app.post("/storage/delete-key")
async def delete_storage_key(request: Request, user: str = Depends(require_auth)):
    """Delete a key from a dict storage file."""
    data = await request.json()
    file_path = data.get('file')
    key = data.get('key')

    if not file_path or key is None:
        raise HTTPException(status_code=400, detail="Missing file or key")

    data_dir = core.get_data_path()
    full_path = os.path.join(data_dir, file_path)

    # Security check - prevent path traversal
    if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.json':
            with open(full_path, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
        elif ext in ['.yml', '.yaml']:
            with open(full_path, 'r', encoding='utf-8') as f:
                file_data = yaml.safe_load(f)
        elif ext == '.mp':
            with open(full_path, 'rb') as f:
                file_data = msgpack.unpackb(f.read())
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        if not isinstance(file_data, dict):
            raise HTTPException(status_code=400, detail="File is not a dictionary")

        if key in file_data:
            del file_data[key]
        else:
            raise HTTPException(status_code=404, detail="Key not found")

        if ext == '.json':
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(file_data, f, indent=2, ensure_ascii=False)
        elif ext in ['.yml', '.yaml']:
            with open(full_path, 'w', encoding='utf-8') as f:
                yaml.dump(file_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        elif ext == '.mp':
            with open(full_path, 'wb') as f:
                f.write(msgpack.packb(file_data))

        return {
            'success': True,
            'keys': sorted(file_data.keys()),
            'data': file_data
        }

    except Exception as e:
        err_msg = core.detail_error(e) if core.debug else str(e)
        core.log("webui", f"Error deleting key: {e}")
        raise HTTPException(status_code=500, detail=err_msg)

@app.post("/storage/add-key")
async def add_storage_key(request: Request, user: str = Depends(require_auth)):
    """Add a new key to a dict storage file."""
    data = await request.json()
    file_path = data.get('file')
    key = data.get('key', '').strip()

    if not file_path or not key:
        raise HTTPException(status_code=400, detail="Missing file or key")

    data_dir = core.get_data_path()
    full_path = os.path.join(data_dir, file_path)

    # Security check - prevent path traversal
    if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
        raise HTTPException(status_code=403, detail="Access denied")

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.json':
            with open(full_path, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
        elif ext in ['.yml', '.yaml']:
            with open(full_path, 'r', encoding='utf-8') as f:
                file_data = yaml.safe_load(f)
        elif ext == '.mp':
            with open(full_path, 'rb') as f:
                file_data = msgpack.unpackb(f.read())
        else:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        if not isinstance(file_data, dict):
            raise HTTPException(status_code=400, detail="File is not a dictionary")

        if key in file_data:
            raise HTTPException(status_code=400, detail="Key already exists")

        file_data[key] = ''

        if ext == '.json':
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(file_data, f, indent=2, ensure_ascii=False)
        elif ext in ['.yml', '.yaml']:
            with open(full_path, 'w', encoding='utf-8') as f:
                yaml.dump(file_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        elif ext == '.mp':
            with open(full_path, 'wb') as f:
                f.write(msgpack.packb(file_data))

        return {
            'success': True,
            'keys': sorted(file_data.keys()),
            'data': file_data
        }

    except Exception as e:
        err_msg = core.detail_error(e) if core.debug else str(e)
        core.log("webui", f"Error adding key: {e}")
        raise HTTPException(status_code=500, detail=err_msg)

# =============================================================================
# Server control routes
# =============================================================================

@app.post("/server/restart")
async def restart_server(user: str = Depends(require_auth)):
    global channel_instance
    core.log("webui", "Restart triggered")
    await channel_instance.manager.restart()
    return {"success": True}

# =============================================================================
# PWA Support Routes
# =============================================================================

@app.get('/manifest.json')
async def manifest():
    """Serve the PWA manifest."""
    with open(core.get_path("channels/webui/manifest.json")) as f:
        manifest_data = json.loads(f.read())
    return manifest_data

@app.get('/sw.js')
async def service_worker():
    """Serve the service worker."""
    with open(core.get_path("channels/webui/sw.js")) as f:
        sw_code = f.read()
    return Response(content=sw_code, media_type='application/javascript', headers={'Cache-Control': 'no-store'})

@app.get('/icon-192.png')
@app.get('/icon-512.png')
async def icon():
    """Serve a placeholder icon for PWA."""
    png_hex = "89504e470d0a1a0a0000000d494844520000000200000002080200000001f338dd0000000c4944415408d763f8ffffcf0001000100737a55b00000000049454e44ae426082"
    return Response(content=bytes.fromhex(png_hex), media_type='image/png')

# =============================================================================
# Channel Class
# =============================================================================

class Webui(core.channel.Channel):
    """Polished web interface that can be used on any device, granting you a fully private way to talk to your AI."""

    settings = {
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
        """Start the FastAPI web server."""
        global channel_instance
        channel_instance = self

        core.log("webui", f"Starting WebUI on {self.url}")

        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="error")
        self.server = uvicorn.Server(config)

        await self.server.serve()

    async def on_shutdown(self):
        """Shutdown the server gracefully."""
        core.log("webui", "Shutting down WebUI server...")
        self.server.should_exit = True
        await asyncio.sleep(1) # Allow grace period

    async def on_push(self, message: dict):
        """Triggered when a message is pushed (announcements, etc)"""
        await manager.broadcast(message)

# Add SessionMiddleware with secure settings
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="webui_session",
    max_age=None,  # Session cookie (deleted when browser closes)
    same_site="lax",  # CSRF protection
    https_only=False  # Set to True in production with HTTPS
)
