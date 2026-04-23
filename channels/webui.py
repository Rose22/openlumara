"""
OpenLumara WebUI - A modern chat interface for AI interactions.

This module provides a Flask-based web interface that polls the backend
for messages, treating the backend (chat.get()) as the single
source of truth for all messages including user messages, AI responses,
commands, and announcements.
"""

import os
import asyncio
import json
import uuid
import base64
import socket
import secrets
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, Response, cli
from threading import Thread
from queue import Queue
import logging

import core
import msgpack
import yaml

import io

WEBUI_DIR = core.get_path("channels/webui")

# ordered list of javascript files, to load in this exact order
JS_FILES = [
    "themes",
    "icons",
    "variables",
    "markdown",
    "content_helpers",
    "messages",
    "msg_actions",
    "sidebar",
    "utils",
    "notif",
    "status",
    "polling",
    "chats",
    "tags",
    "search",
    "export",
    "modals",
    "input",
    "send",
    "upload",
    "theming",
    "audio",
    "modal_settings",
    "storage_editor",
    "responsive",
    "init"
]

# same deal for css files
CSS_FILES = [
    "variables",
    "base",
    "containers",
    "sidebar",
    "tags",
    "rename",
    "content",
    "header",
    "titlebar",
    "search",
    "modals",
    "search",
    "containers",
    "messages",
    "input",
    "upload",
    "keyboard",
    "responsive",
    "typewriter",
    "settings",
    "storage_editor"
]

app = Flask(
    __name__,
    static_folder=os.path.join(WEBUI_DIR, "static")
)
app.secret_key = secrets.token_hex(32)

# Disable Flask logging
cli.show_server_banner = lambda *args: print(end="")
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
log.disabled = True

# disable json key sorting
app.json.sort_keys = False

# Load HTML template
HTML_TEMPLATE = None
with open(os.path.join(WEBUI_DIR, "index.html"), "r") as f:
    HTML_TEMPLATE = f.read()

# Global reference to the channel instance
channel_instance = None

# Set of stream IDs that have been cancelled
stream_cancellations = set()

def serialize_for_json(obj):
    """Recursively converts non-serializable objects into plain dicts/lists."""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(x) for x in obj]
    elif hasattr(obj, 'to_dict'):  # Many AI libraries use this
        return serialize_for_json(obj.to_dict())
    elif hasattr(obj, '__dict__'):  # Handles custom class instances
        return serialize_for_json(obj.__dict__)
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)  # Fallback to string representation

# Security headers
@app.after_request
def add_security_headers(response):
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'

    if request.path == '/' or request.path == '/sw.js':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response

class Webui(core.channel.Channel):
    settings = {
        "host": "localhost",
        "port": 5000,
        "use_short_replies": False
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_loop = None
        self.server = None
        self._shutdown_requested = False

    async def run(self):
        """Start the Flask web server."""
        core.log("webui", "Starting WebUI")

        self.main_loop = asyncio.get_running_loop()
        self._shutdown_requested = False

        global channel_instance
        channel_instance = self

        # Start Flask in a separate thread
        flask_thread = Thread(target=self._run_flask, daemon=True)
        flask_thread.start()

        host = core.config.get("channels").get("settings").get("webui").get("host", "127.0.0.1")
        port = core.config.get("channels").get("settings").get("webui").get("port", 5000)
        core.log("webui", f"WebUI started on http://{host}:{port}")

        try:
            while not self._shutdown_requested:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise

    def _run_flask(self):
        """Run Flask in a separate thread."""
        from werkzeug.serving import make_server

        host = core.config.get("channels").get("settings").get("webui").get("host", "127.0.0.1")
        port = core.config.get("channels").get("settings").get("webui").get("port", 5000)

        self.server = make_server(host, port, app, threaded=True)
        self.server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self.server.serve_forever()
        except:
            pass  # Server shutdown

    def on_shutdown(self):
        """Shutdown the Flask server."""
        self._shutdown_requested = True
        if self.server:
            self.server.shutdown()

    async def _announce(self, message: str, type: str = None):
        """
        Handle announcements - the base class already inserted into backend.

        Since we poll the backend for messages, no special handling needed here.
        The frontend will pick up announcements on the next poll.
        """
        core.log("webui", f"Announcement ({type}): {message[:50]}...")

def _run_async(coro):
    """Helper to run async coroutines from sync Flask routes."""
    if not channel_instance or not channel_instance.main_loop:
        return None
    future = asyncio.run_coroutine_threadsafe(coro, channel_instance.main_loop)
    return future.result()

# =============================================================================
# Flask Routes
# =============================================================================

@app.route('/')
def index():
    """Serve the main HTML page."""
    return render_template_string(HTML_TEMPLATE, js_files=JS_FILES, css_files=CSS_FILES)

def get_api_status():
    """
    Get detailed API connection status.
    Returns dict with connection info and actionable error messages.
    """
    if not channel_instance:
        return {
            'connected': False,
            'server_ok': False,
            'error': 'Channel not available',
            'error_type': 'server_error',
            'action': 'Please restart the application.'
        }

    status = channel_instance.manager.get_api_status()

    # Build response with actionable information
    result = {
        'connected': status.get('connected', False),
        'server_ok': True,
        'model': status.get('model'),
        'url_configured': status.get('url_configured', False),
        'key_configured': status.get('key_configured', False),
        'model_configured': status.get('model_configured', False),
    }

    if not result['connected']:
        error = status.get('error', 'Unknown error')
        result['error'] = error

        # Determine error type for frontend handling
        if not result['url_configured']:
            result['error_type'] = 'config_missing'
            result['action'] = 'Please configure your API URL in Settings.'
        elif not result['key_configured']:
            result['error_type'] = 'config_missing'
            result['action'] = 'Please configure your API key in Settings.'
        elif not result['model_configured']:
            result['error_type'] = 'config_missing'
            result['action'] = 'Please configure a model name in Settings.'
        elif error:
            if 'authentication' in error.lower() or 'api key' in error.lower():
                result['error_type'] = 'auth_failed'
                result['action'] = 'Your API key is invalid. Please check your settings.'
            elif 'connection' in error.lower() or 'reach' in error.lower():
                result['error_type'] = 'connection_failed'
                result['action'] = 'Could not reach the API server. Check the URL and your network.'
        else:
            result['error_type'] = 'unknown'
            result['action'] = f'Error: {error}'

    return result

@app.route('/api/status')
def api_status():
    """Check API connection status with detailed information."""
    return jsonify(get_api_status())

@app.route('/api/reconnect', methods=['POST'])
def api_reconnect():
    """Attempt to reconnect to the API."""
    if not channel_instance:
        return jsonify({
            'success': False,
            'error': 'Channel not available',
            'action': 'Please restart the application.'
        }), 500

    # Run reconnect in async context
    result = _run_async(channel_instance.manager.reconnect_api())
    return jsonify(result)

@app.route('/api/disconnect', methods=['POST'])
def api_disconnect():
    """Disconnect from the API."""
    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'}), 500

    _run_async(channel_instance.manager.API.disconnect())
    return jsonify({'success': True})

@app.route('/api/models')
def list_models():
    """List available models from the API."""
    if not channel_instance:
        return jsonify({'models': [], 'error': 'Channel not available'}), 500

    if not channel_instance.manager.API.connected:
        return jsonify({
            'models': [],
            'error': 'Not connected to API',
            'error_type': 'disconnected'
        }), 503

    try:
        models = _run_async(channel_instance.manager.API.list_models())
        return jsonify({'models': models})
    except Exception as e:
        return jsonify({
            'models': [],
            'error': str(e)
        }), 500

@app.route('/messages')
def get_messages():
    """Get all messages from the backend API."""
    if not channel_instance:
        return jsonify({'messages': [], 'count': 0})

    messages = _run_async(channel_instance.context.chat.get()) or []
    current_id = _run_async(channel_instance.context.chat.get_id())

    result = []
    for i, msg in enumerate(messages):
        msg_data = {
            'role': msg.get('role', 'user'),
            'content': msg.get('content', ''),
            'tool_calls': msg.get('tool_calls'),
            'tool_call_id': msg.get('tool_call_id'),
            'reasoning_content': msg.get('reasoning_content'),
            'segments': msg.get('segments', []),  # NEW: Store segment order
            'index': i
        }
        result.append(msg_data)

    return jsonify({
        'messages': result,
        'count': len(result),
        'current_chat_id': current_id
    })

@app.route('/messages/since')
def get_messages_since():
    """Get messages since a specific index."""
    if not channel_instance:
        return jsonify({'messages': [], 'count': 0})

    try:
        since_index = int(request.args.get('index', 0))
    except ValueError:
        since_index = 0

    messages = _run_async(channel_instance.context.chat.get()) or []
    current_id = _run_async(channel_instance.context.chat.get_id())
    current_title = _run_async(channel_instance.context.chat.get_title())
    current_tags = _run_async(channel_instance.context.chat.get_tags()) or []

    result = []
    for i in range(since_index, len(messages)):
        msg = messages[i]
        msg_data = {
            'role': msg.get('role', 'user'),
            'content': msg.get('content', ''),
            'tool_calls': msg.get('tool_calls'),
            'tool_call_id': msg.get('tool_call_id'),
            'reasoning_content': msg.get('reasoning_content'),
            'index': i
        }
        result.append(msg_data)

    return jsonify({
        'messages': result,
        'count': len(result),
        'total': len(messages),
        'current_chat_id': current_id,
        'current_chat_title': current_title,
        'current_chat_tags': current_tags
    })

@app.route('/api/token_usage')
def token_usage():
    """Get current token usage for the active chat."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'}), 500

    try:
        # Call the context class method
        usage = _run_async(channel_instance.context.get_token_usage())
        return jsonify(usage)
    except Exception as e:
        core.log("webui", f"Error getting token usage: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/stream', methods=['POST'])
def stream_message():
    """
    Stream AI response token by token using Server-Sent Events.
    """
    global channel_instance

    # Check API connection first with detailed status
    status = get_api_status()
    if not status['connected']:
        error_type = status.get('error_type', 'unknown')
        return jsonify({
            'error': status.get('error', 'Not connected'),
            'error_type': error_type,
            'action': status.get('action'),
            'api_error': True
        }), 503

    data = request.get_json()
    stream_id = str(uuid.uuid4())[:8]

    def generate():
        token_queue = Queue()
        done = object()

        async def collect_tokens():
            try:
                async for token_data in channel_instance.send_stream(data):
                    if stream_id in stream_cancellations:
                        stream_cancellations.discard(stream_id)
                        token_queue.put(('cancelled', True))
                        break

                    # Handle error tokens
                    if isinstance(token_data, dict) and token_data.get('type') == 'error':
                        error_content = token_data.get('content', {})
                        token_queue.put(('error', error_content))
                        break

                    token_queue.put(token_data)
            except Exception as e:
                token_queue.put(('error', {'error': 'exception', 'message': str(e)}))
            finally:
                token_queue.put(done)

        future = asyncio.run_coroutine_threadsafe(
            collect_tokens(),
            channel_instance.main_loop
        )

        # Initial connection signal (using _meta to stay out of the way)
        yield f"data: {json.dumps({'_meta': {'type': 'connection', 'status': 'connected'}, 'id': stream_id})}\n\n"

        while True:
            item = token_queue.get()

            # --- THE COMMIT PHASE (Hard Sync) ---
            if item is done:
                try:
                    # Fetch the authoritative truth from the backend context
                    full_history = _run_async(channel_instance.context.chat.get())
                    # Serialize the history using the existing safe serializer
                    serialized_history = [serialize_for_json(m) for m in full_history]

                    yield f"data: {json.dumps({
                        '_meta': {'type': 'commit'},
                        'history': serialized_history
                    })}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'_meta': {'type': 'error'}, 'error': str(e)})}\n\n"
                break

            # --- ERROR & CANCELLATION ---
            elif isinstance(item, tuple):
                if item[0] == 'error':
                    error_data = item[1] if isinstance(item[1], dict) else {'message': str(item[1])}
                    yield f"data: {json.dumps({'_meta': {'type': 'error'}, 'error_data': error_data})}\n\n"
                    break
                elif item[0] == 'cancelled':
                    yield f"data: {json.dumps({'_meta': {'type': 'cancelled'}})}\n\n"
                    break

            # --- THE DELTA PHASE (Streaming) ---
            elif isinstance(item, dict):
                # 1. Map the Core payload to a UI Status (The Decorator)
                p_type = item.get('type')
                status = "idle"
                if p_type == 'reasoning':
                    status = "thinking"
                elif p_type in ['tool_call_delta', 'tool', 'tool_calls']:
                    status = "tool_call"
                elif p_type == 'tool':
                    status = "tool_exec"

                # 2. Serialize the original item (Remains OpenAI-compliant)
                payload = serialize_for_json(item)

                # 3. Inject metadata at the top level without changing existing keys
                payload['_meta'] = {'type': 'delta', 'status': status}

                yield f"data: {json.dumps(payload)}\n\n"

            else:
                # Fallback for raw string tokens
                payload = {'type': 'content', 'text': str(item)}
                payload['_meta'] = {'type': 'delta', 'status': 'idle'}
                yield f"data: {json.dumps(payload)}\n\n"

        future.result()


    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

@app.route('/send', methods=['POST'])
def send_message():
    """Send a message and wait for complete response."""
    global channel_instance

    # Check API connection first with detailed status
    status = get_api_status()
    if not status['connected']:
        error_type = status.get('error_type', 'unknown')
        return jsonify({
            'error': status.get('error', 'Not connected'),
            'error_type': error_type,
            'action': status.get('action'),
            'api_error': True
        }), 503

    data = request.get_json()

    future = asyncio.run_coroutine_threadsafe(
        channel_instance.send(data),
        channel_instance.main_loop
    )
    response = future.result()

    # Check if response is an error
    if isinstance(response, dict) and 'error' in response:
        return jsonify({
            'error': response.get('message', 'Unknown error'),
            'error_type': response.get('error', 'unknown'),
            'api_error': True
        }), 500

    messages = _run_async(channel_instance.context.chat.get()) or []
    current_id = _run_async(channel_instance.context.chat.get_id())
    current_title = _run_async(channel_instance.context.chat.get_title())

    return jsonify({
        'response': response,
        'total': len(messages),
        'current_chat': {
            'id': current_id,
            'title': current_title
        }
    })

@app.route('/edit', methods=['POST'])
def edit_message():
    """Edit a message in the backend by index."""
    global channel_instance

    data = request.get_json()
    index = data.get('index', 0)
    new_content = data.get('content', '')

    messages = _run_async(channel_instance.context.chat.get())

    if 0 <= index < len(messages):
        if messages[index].get('role') not in ('user', 'assistant'):
            return jsonify({'success': False, 'error': 'Cannot edit this message type'})

        messages[index]['content'] = new_content
        _run_async(channel_instance.context.chat.set(messages))
        core.log("webui", f"Edited message {index}")
        return jsonify({'success': True, 'total': len(messages)})

    return jsonify({'success': False, 'error': f'Index {index} out of range'})

@app.route('/delete', methods=['POST'])
def delete_message():
    """Delete a message and all messages after it from the backend."""
    global channel_instance

    data = request.get_json()
    index = data.get('index', 0)

    messages = _run_async(channel_instance.context.chat.get())

    if 0 <= index < len(messages):
        if messages[index].get('role') not in ('user', 'assistant', 'command', 'command_response'):
            if not messages[index].get('role', '').startswith('announce_'):
                return jsonify({'success': False, 'error': 'Cannot delete this message type'})

        _run_async(channel_instance.context.chat.set(messages[:index]))
        remaining = len(_run_async(channel_instance.context.chat.get()))
        core.log("webui", f"Deleted messages from index {index}, {remaining} remaining")
        return jsonify({'success': True, 'remaining': remaining})

    return jsonify({'success': False, 'error': f'Index {index} out of range'})

@app.route('/cancel', methods=['POST'])
def cancel_stream():
    """Cancel an ongoing stream."""
    global channel_instance

    data = request.get_json()
    stream_id = data.get('id')

    channel_instance.manager.API.cancel_request = True

    if stream_id:
        stream_cancellations.add(stream_id)

    return jsonify({'success': True})

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle multiple file uploads and insert as a single multi-modal message."""
    global channel_instance

    data = request.get_json()
    files_data = data.get('files', [])
    if not files_data:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    try:
        message_content = []
        for f in files_data:
            filename = f.get('filename', '')
            content_b64 = f.get('content', '')
            is_image = f.get('is_image', False)

            if is_image:
                image_url = f"data:image/jpeg;base64,{content_b64}"

                # Add a text part for searchability/extraction
                message_content.append({
                    "type": "text",
                    "text": f"[Image: {filename}]"
                })
                # Add the image part
                message_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
            else:
                # Text file processing
                content = base64.b64decode(content_b64).decode('utf-8', errors='replace')
                # Add a text part for searchability/extraction
                message_content.append({
                    "type": "text",
                    "text": f"[File: {filename}]\n{content}"
                })

        async def insert_message():
            await channel_instance.context.chat.add({"role": "user", "content": message_content})

        asyncio.run_coroutine_threadsafe(insert_message(), channel_instance.main_loop).result()

        total = len(_run_async(channel_instance.context.chat.get()))
        return jsonify({'success': True, 'total': total, 'type': 'multi'})

    except Exception as e:
        core.log("webui", f"Upload error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# =============================================================================
# Chat Management Routes
# =============================================================================

@app.route('/chats')
def list_chats():
    """List all saved chats with message content for searching."""
    global channel_instance

    if not channel_instance:
        return jsonify({'chats': []})

    all_chats = _run_async(channel_instance.context.chat.get_all())
    chats = []

    for conv in all_chats:
        messages_preview = []
        for msg in conv.get('messages', [])[:5]:
            raw_content = msg.get('content', '')

            # NEW: Handle multimodal content extraction for preview
            text_content = ""
            if isinstance(raw_content, str):
                text_content = raw_content
            elif isinstance(raw_content, list):
                # Extract only text parts for the sidebar preview
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
                    'content': text_content[:500] # Safe slicing on string
                })

        chats.append({
            'id': conv.get('id'),
            'title': conv.get('title', ''),
            'category': conv.get('category', ''),
            'tags': conv.get('tags', []),
            'custom_data': conv.get('custom_data', {}),
            'created': conv.get('created'),
            'updated': conv.get('updated'),
            'message_count': len(conv.get('messages', [])),
            'messages': messages_preview
        })

    chats.sort(key=lambda x: x.get('updated', ''), reverse=True)
    return jsonify({'chats': chats})

@app.route('/chat/load')
def load_chat():
    """Load an existing chat by ID."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    # ensure we are the active channel
    # so that things like fetching token count work
    _run_async(channel_instance._set_as_active_channel())

    conv_id = request.args.get('id')
    if not conv_id:
        return jsonify({'success': False, 'error': 'No chat ID provided'})

    success = _run_async(channel_instance.context.chat.load(conv_id))
    if not success:
        return jsonify({'success': False, 'error': 'Chat not found'})

    messages = _run_async(channel_instance.context.chat.get()) or []
    title = _run_async(channel_instance.context.chat.get_title())
    loaded_id = _run_async(channel_instance.context.chat.get_id())
    category = _run_async(channel_instance.context.chat.get_category())
    tags = _run_async(channel_instance.context.chat.get_tags()) or []
    custom_data = _run_async(channel_instance.context.chat.get_data())

    # Add index to each message
    result = []
    for i, msg in enumerate(messages):
        msg_data = {
            'role': msg.get('role', 'user'),
            'content': msg.get('content', ''),
            'tool_calls': msg.get('tool_calls'),
            'tool_call_id': msg.get('tool_call_id'),
            'reasoning_content': msg.get('reasoning_content'),
            'index': i
        }
        result.append(msg_data)

    return jsonify({
        'success': True,
        'chat': {
            'id': loaded_id,
            'title': title,
            "category": category,
            'tags': tags,
            'custom_data': custom_data,
            'messages': result,
            'total': len(result)
        }
    })

@app.route('/chat/current')
def get_current_chat():
    """Get the currently active chat ID and its messages."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    chat = channel_instance.context.chat

    conv_id = _run_async(chat.get_id())
    if conv_id is None:
        return jsonify({
            'success': True,
            'current_id': None,
            'chat': None
        })

    messages = _run_async(chat.get()) or []
    title = _run_async(chat.get_title())
    tags = _run_async(chat.get_tags()) or []
    category = _run_async(channel_instance.context.chat.get_category())
    custom_data = _run_async(channel_instance.context.chat.get_data())

    # Add index to each message
    result = []
    for i, msg in enumerate(messages):
        msg_data = {
            'role': msg.get('role', 'user'),
            'content': msg.get('content', ''),
            'tool_calls': msg.get('tool_calls'),
            'tool_call_id': msg.get('tool_call_id'),
            'reasoning_content': msg.get('reasoning_content'),
            'index': i
        }
        result.append(msg_data)

    return jsonify({
        'success': True,
        'chat': {
            'id': conv_id,
            'title': title or 'New chat',
            'category': category or 'general',
            'tags': tags,
            'custom_data': custom_data,
            'messages': result,
            'total': len(result)
        }
    })

@app.route('/chat/rename', methods=['POST'])
def rename_chat():
    """Rename the current chat."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    # Only rename if we have an active chat
    conv_id = _run_async(channel_instance.context.chat.get_id())
    if conv_id is None:
        return jsonify({'success': False, 'error': 'No active chat'})

    data = request.get_json()
    new_title = data.get('title', '').strip()

    if not new_title:
        return jsonify({'success': False, 'error': 'Title cannot be empty'})

    _run_async(channel_instance.context.chat.set_title(new_title))

    return jsonify({'success': True, 'title': new_title})

@app.route('/chat/update_category', methods=['POST'])
def update_chat_category():
    """Update the category of a specific chat."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    data = request.get_json()
    chat_id = data.get('chat_id')
    new_category = data.get('category', '')

    if not chat_id:
        return jsonify({'success': False, 'error': 'Chat ID is required'})

    # Check if the requested chat is the current one
    current_id = _run_async(channel_instance.context.chat.get_id())
    was_current = (current_id == chat_id)

    try:
        # If it's not the current chat, we need to load it first to set category
        if not was_current:
            load_response = _run_async(channel_instance.context.chat.load(chat_id))
            if not load_response:
                return jsonify({'success': False, 'error': 'Failed to load chat'})

        # Set the category
        _run_async(channel_instance.context.chat.set_category(new_category))

        # If we loaded a different chat, restore the previous one to maintain UI state
        if not was_current and current_id:
            _run_async(channel_instance.context.chat.load(current_id))

        return jsonify({'success': True})
    except Exception as e:
        # Restore previous chat if something went wrong
        if not was_current and current_id:
            try:
                _run_async(channel_instance.context.chat.load(current_id))
            except:
                pass
        return jsonify({'success': False, 'error': str(e)})

@app.route('/chat/new', methods=['POST'])
def new_chat():
    """
    Start a fresh chat.

    Note: This explicitly creates a new empty chat. In most cases,
    you don't need to call this - just send a message and the chat system
    will auto-create a chat if needed.
    """
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    # ensure we are the active channel
    # so that things like fetching token count work
    _run_async(channel_instance._set_as_active_channel())

    data = request.get_json() or {}
    title = data.get('title', '')
    category = data.get('category', '')  # Accept category from frontend

    _run_async(channel_instance.context.chat.new(title=title, category=category))

    return jsonify({
        'success': True,
        'chat': {
            'id': _run_async(channel_instance.context.chat.get_id()),
            'title': title,
            'category': category,
            'messages': []
        }
    })
@app.route("/chat/clear", methods=["POST"])
def clear_chat():
    global channel_instance
    _run_async(channel_instance.context.chat.clear())
    return jsonify({"success": True})

@app.route('/chat/delete', methods=['POST'])
def delete_chat():
    """Delete a saved chat."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    data = request.get_json(silent=True) or {}
    conv_id = data.get('id') or request.args.get('id')

    if not conv_id:
        return jsonify({'success': False, 'error': 'No chat ID provided'})

    success = _run_async(channel_instance.context.chat.delete(conv_id))

    if not success:
        return jsonify({'success': False, 'error': 'Chat not found'})

    return jsonify({'success': True})

@app.route('/chat/tags', methods=['GET'])
def get_all_tags():
    """Get all unique tags across all chats."""
    global channel_instance

    if not channel_instance:
        return jsonify({'tags': []})

    all_chats = _run_async(channel_instance.context.chat.get_all()) or []
    tags = set()

    for chat in all_chats:
        for tag in chat.get('tags', []):
            tags.add(tag)

    return jsonify({'tags': sorted(list(tags))})

@app.route('/chat/tags', methods=['POST'])
def update_chat_tags():
    """Update tags for the current chat."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    data = request.get_json() or {}
    tags = data.get('tags', [])

    if not isinstance(tags, list):
        return jsonify({'success': False, 'error': 'Tags must be a list'})

    # Check if there's a current chat
    conv_id = _run_async(channel_instance.context.chat.get_id())
    if conv_id is None:
        return jsonify({'success': False, 'error': 'No active chat'})

    # Use the Chat methods
    _run_async(channel_instance.context.chat.set_tags(tags))

    return jsonify({'success': True, 'tags': tags})

@app.route('/chat/tag', methods=['POST'])
def add_chat_tag():
    """Add a single tag to the current chat."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    data = request.get_json() or {}
    tag = data.get('tag', '').strip()

    if not tag:
        return jsonify({'success': False, 'error': 'Tag cannot be empty'})

    conv_id = _run_async(channel_instance.context.chat.get_id())
    if conv_id is None:
        return jsonify({'success': False, 'error': 'No active chat'})

    success = _run_async(channel_instance.context.chat.add_tag(tag))

    return jsonify({'success': success, 'tag': tag})

@app.route('/chat/tag', methods=['DELETE'])
def remove_chat_tag():
    """Remove a single tag from the current chat."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    data = request.get_json() or {}
    tag = data.get('tag', '').strip()

    if not tag:
        return jsonify({'success': False, 'error': 'Tag cannot be empty'})

    conv_id = _run_async(channel_instance.context.chat.get_id())
    if conv_id is None:
        return jsonify({'success': False, 'error': 'No active chat'})

    success = _run_async(channel_instance.context.chat.pop_tag(tag))

    return jsonify({'success': success, 'tag': tag})

# =============================================================================
# Settings editing routes
# =============================================================================
@app.route('/settings/load')
def load_settings():
    return jsonify(core.config.config)

@app.route("/settings/save", methods=["POST"])
def save_settings():
    form_data = request.get_json()
    result = core.config.config.load(data=form_data)
    core.config.config.save()

    if not result:
        return jsonify({'success': False, 'error': 'something went wrong while saving settings!'})

    return jsonify({"success": True})

@app.route("/settings/get_module_info")
def get_module_info():
    module_info = {}
    import modules
    import user_modules

    loaded_module_classes = core.modules.load(modules, core.module.Module) + core.modules.load(user_modules, core.module.Module)
    for module_class in loaded_module_classes:
        module_name = core.modules.get_name(module_class)
        docstring = str(module_class.__doc__).strip()
        is_unsafe = getattr(module_class, 'unsafe', False)

        if docstring not in [None, "None"] and module_name not in module_info.keys():
            # only get the first class's docstring, dont overwrite it with docstrings from other classes in the file
            module_info[module_name] = {
                "description": docstring,
                "unsafe": is_unsafe
            }

    return jsonify({"success": True, "module_info": module_info})

# =============================================================================
# Storage Editor Routes
# =============================================================================

@app.route('/storage/list')
def list_storage_files():
    """List all storage files in the data folder."""
    data_dir = core.get_data_path()
    if not os.path.exists(data_dir):
        return jsonify({'files': []})

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
                            if isinstance(data, dict):
                                file_type = 'dict'
                            elif isinstance(data, list):
                                file_type = 'list'
                            else:
                                file_type = 'text'
                    elif ext in ['.yml', '.yaml']:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            data = yaml.safe_load(f)
                            if isinstance(data, dict):
                                file_type = 'dict'
                            elif isinstance(data, list):
                                file_type = 'list'
                            else:
                                file_type = 'text'
                    elif ext == '.mp':
                        with open(full_path, 'rb') as f:
                            data = msgpack.unpackb(f.read())
                            if isinstance(data, dict):
                                file_type = 'dict'
                            elif isinstance(data, list):
                                file_type = 'list'
                            else:
                                file_type = 'text'
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
    return jsonify({'files': files, 'data_dir': data_dir})

@app.route('/storage/load')
def load_storage_file():
    """Load a specific storage file."""
    file_path = request.args.get('file')
    if not file_path:
        return jsonify({'success': False, 'error': 'No file specified'})

    data_dir = core.get_data_path()
    full_path = os.path.join(data_dir, file_path)

    if not os.path.exists(full_path):
        return jsonify({'success': False, 'error': 'File not found'})

    # Security check
    if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
        return jsonify({'success': False, 'error': 'Access denied'})

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.json':
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return jsonify({
                    'success': True,
                    'type': 'dict',
                    'keys': sorted(data.keys()),
                    'data': data
                })
            elif isinstance(data, list):
                return jsonify({
                    'success': True,
                    'type': 'list',
                    'data': data
                })

        elif ext in ['.yml', '.yaml']:
            with open(full_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return jsonify({
                    'success': True,
                    'type': 'dict',
                    'keys': sorted(data.keys()),
                    'data': data
                })
            elif isinstance(data, list):
                return jsonify({
                    'success': True,
                    'type': 'list',
                    'data': data
                })

        elif ext == '.mp':
            with open(full_path, 'rb') as f:
                data = msgpack.unpackb(f.read())
            if isinstance(data, dict):
                return jsonify({
                    'success': True,
                    'type': 'dict',
                    'keys': sorted(data.keys()),
                    'data': data
                })
            elif isinstance(data, list):
                return jsonify({
                    'success': True,
                    'type': 'list',
                    'data': data
                })

        elif ext in ['.txt', '.md']:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return jsonify({
                'success': True,
                'type': 'text',
                'data': content
            })

        return jsonify({'success': False, 'error': 'Unsupported file type'})

    except Exception as e:
        core.log("webui", f"Error loading storage file: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/storage/save', methods=['POST'])
def save_storage_file():
    """Save a storage file."""
    data = request.get_json()
    file_path = data.get('file')
    storage_type = data.get('type')
    content = data.get('data')

    if not file_path:
        return jsonify({'success': False, 'error': 'No file specified'})

    data_dir = core.get_data_path()
    full_path = os.path.join(data_dir, file_path)

    # Security check
    if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
        return jsonify({'success': False, 'error': 'Access denied'})

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
                return jsonify({'success': False, 'error': 'Unsupported file type for dict'})

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
                return jsonify({'success': False, 'error': 'Unsupported file type for list'})

        elif storage_type == 'text':
            if ext in ['.txt', '.md']:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                return jsonify({'success': False, 'error': 'Unsupported file type for text'})

        else:
            return jsonify({'success': False, 'error': 'Unknown storage type'})

        core.log("webui", f"Saved storage file: {file_path}")
        return jsonify({'success': True})

    except Exception as e:
        core.log("webui", f"Error saving storage file: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/storage/delete-key', methods=['POST'])
def delete_storage_key():
    """Delete a key from a dict storage file."""
    data = request.get_json()
    file_path = data.get('file')
    key = data.get('key')

    if not file_path or key is None:
        return jsonify({'success': False, 'error': 'Missing file or key'})

    data_dir = core.get_data_path()
    full_path = os.path.join(data_dir, file_path)

    # Security check
    if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
        return jsonify({'success': False, 'error': 'Access denied'})

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
            return jsonify({'success': False, 'error': 'Unsupported file type'})

        if not isinstance(file_data, dict):
            return jsonify({'success': False, 'error': 'File is not a dictionary'})

        if key in file_data:
            del file_data[key]
        else:
            return jsonify({'success': False, 'error': 'Key not found'})

        if ext == '.json':
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(file_data, f, indent=2, ensure_ascii=False)
        elif ext in ['.yml', '.yaml']:
            with open(full_path, 'w', encoding='utf-8') as f:
                yaml.dump(file_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        elif ext == '.mp':
            with open(full_path, 'wb') as f:
                f.write(msgpack.packb(file_data))

        return jsonify({
            'success': True,
            'keys': sorted(file_data.keys()),
            'data': file_data
        })

    except Exception as e:
        core.log("webui", f"Error deleting key: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/storage/add-key', methods=['POST'])
def add_storage_key():
    """Add a new key to a dict storage file."""
    data = request.get_json()
    file_path = data.get('file')
    key = data.get('key', '').strip()

    if not file_path or not key:
        return jsonify({'success': False, 'error': 'Missing file or key'})

    data_dir = core.get_data_path()
    full_path = os.path.join(data_dir, file_path)

    # Security check
    if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
        return jsonify({'success': False, 'error': 'Access denied'})

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
            return jsonify({'success': False, 'error': 'Unsupported file type'})

        if not isinstance(file_data, dict):
            return jsonify({'success': False, 'error': 'File is not a dictionary'})

        if key in file_data:
            return jsonify({'success': False, 'error': 'Key already exists'})

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

        return jsonify({
            'success': True,
            'keys': sorted(file_data.keys()),
            'data': file_data
        })

    except Exception as e:
        core.log("webui", f"Error adding key: {e}")
        return jsonify({'success': False, 'error': str(e)})

# =============================================================================
# Server control routes
# =============================================================================
@app.route("/server/restart", methods=["POST"])
def restart_server():
    global channel_instance
    core.log("webui", "Restart triggered")
    _run_async(channel_instance.manager.restart())
    return jsonify({"success": True})

# =============================================================================
# PWA Support Routes
# =============================================================================

@app.route('/manifest.json')
def manifest():
    """Serve the PWA manifest."""
    with open(core.get_path("channels/webui/manifest.json")) as f:
        manifest = json.loads(f.read())
    return jsonify(manifest)

@app.route('/sw.js')
def service_worker():
    """Serve the service worker."""
    with open(core.get_path("channels/webui/sw.js")) as f:
        sw_code = f.read()
    response = Response(sw_code, mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route('/icon-192.png')
@app.route('/icon-512.png')
def icon():
    """Serve a placeholder icon for PWA."""
    png_hex = "89504e470d0a1a0a0000000d494844520000000200000002080200000001f338dd0000000c4944415408d763f8ffffcf0001000100737a55b00000000049454e44ae426082"
    return bytes.fromhex(png_hex), 200, {'Content-Type': 'image/png'}
