"""
OptiClaw WebUI - A modern chat interface for AI interactions.

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

WEBUI_DIR = core.get_path("channels/webui")

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

# Load HTML template
HTML_TEMPLATE = None
with open(os.path.join(WEBUI_DIR, "index.html"), "r") as f:
    HTML_TEMPLATE = f.read()

# Global reference to the channel instance
channel_instance = None

# Set of stream IDs that have been cancelled
stream_cancellations = set()

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
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'

    if request.path == '/' or request.path == '/sw.js':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response

class Webui(core.channel.Channel):
    """
    Web-based channel that polls the backend for messages.

    The backend (chat.get()) is the single source of truth.
    All messages including user messages, AI responses, commands, and
    announcements are stored in the backend and polled by the frontend.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_loop = None

    async def run(self):
        """Start the Flask web server."""
        core.log("webui", "Starting WebUI")

        self.main_loop = asyncio.get_running_loop()

        global channel_instance
        channel_instance = self

        # Start Flask in a separate thread
        flask_thread = Thread(target=self._run_flask, daemon=True)
        flask_thread.start()

        host = core.config.get("channels").get("settings").get("webui").get("host", "127.0.0.1")
        port = core.config.get("channels").get("settings").get("webui").get("port", 5000)
        core.log("webui", f"WebUI started on {host}:{port}")

        while True:
            await asyncio.sleep(1)

    def _run_flask(self):
        """Run Flask in a separate thread."""
        from werkzeug.serving import make_server

        host = core.config.get("channels").get("settings").get("webui").get("host", "127.0.0.1")
        port = core.config.get("channels").get("settings").get("webui").get("port", 5000)

        server = make_server(host, port, app, threaded=True)
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.serve_forever()

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
    return render_template_string(HTML_TEMPLATE)

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

@app.route('/stream', methods=['POST'])
def stream_message():
    """
    Stream AI response token by token using Server-Sent Events.
    """
    global channel_instance

    data = request.get_json()
    user_message = data.get('message', '')
    stream_id = str(uuid.uuid4())[:8]

    def generate():
        token_queue = Queue()
        done = object()

        async def collect_tokens():
            try:
                async for token_data in channel_instance.send_stream({"role": "user", "content": user_message}):
                    if stream_id in stream_cancellations:
                        stream_cancellations.discard(stream_id)
                        token_queue.put(('cancelled', True))
                        break
                    token_queue.put(token_data)
            except Exception as e:
                token_queue.put(('error', str(e)))
            finally:
                token_queue.put(done)

        future = asyncio.run_coroutine_threadsafe(
            collect_tokens(),
            channel_instance.main_loop
        )

        yield f"data: {json.dumps({'id': stream_id})}\n\n"

        while True:
            item = token_queue.get()

            if item is done:
                total = len(_run_async(channel_instance.context.chat.get()))
                yield f"data: {json.dumps({'done': True, 'total': total})}\n\n"
                break

            elif isinstance(item, tuple):
                if item[0] == 'error':
                    yield f"data: {json.dumps({'error': item[1]})}\n\n"
                    break
                elif item[0] == 'cancelled':
                    yield f"data: {json.dumps({'cancelled': True})}\n\n"
                    break

            elif isinstance(item, dict):
                yield f"data: {json.dumps(item)}\n\n"

            else:
                yield f"data: {json.dumps({'type': 'content', 'text': str(item)})}\n\n"

        future.result()

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

@app.route('/send', methods=['POST'])
def send_message():
    """Send a message and wait for complete response."""
    global channel_instance

    data = request.get_json()
    user_message = data.get('message', '')

    future = asyncio.run_coroutine_threadsafe(
        channel_instance.send({"role": "user", "content": user_message}),
        channel_instance.main_loop
    )
    response = future.result()

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
    """Handle file upload and insert into backend."""
    global channel_instance

    data = request.get_json()
    filename = data.get('filename', '')
    content_b64 = data.get('content', '')
    mimetype = data.get('mimetype', '')

    try:
        content = base64.b64decode(content_b64).decode('utf-8', errors='replace')

        async def insert_file():
            await channel_instance.context.chat.add({
                "role": "user",
                "content": f"[File: {filename}]\n{content}..."
            })

        asyncio.run_coroutine_threadsafe(
            insert_file(),
            channel_instance.main_loop
        ).result()

        total = len(_run_async(channel_instance.context.chat.get()))
        return jsonify({'success': True, 'total': total})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
            content = msg.get('content', '')
            if content:
                messages_preview.append({
                    'role': msg.get('role'),
                    'content': content[:500]
                })

        chats.append({
            'id': conv.get('id'),
            'title': conv.get('title', 'New Chat'),
            'tags': conv.get('tags', []),  # Include tags
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

    conv_id = request.args.get('id')
    if not conv_id:
        return jsonify({'success': False, 'error': 'No chat ID provided'})

    success = _run_async(channel_instance.context.chat.load(conv_id))
    if not success:
        return jsonify({'success': False, 'error': 'Chat not found'})

    messages = _run_async(channel_instance.context.chat.get()) or []
    title = _run_async(channel_instance.context.chat.get_title())
    loaded_id = _run_async(channel_instance.context.chat.get_id())
    tags = _run_async(channel_instance.context.chat.get_tags()) or []

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
            'title': title or 'New Chat',
            'tags': tags,
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
            'title': title or 'New Chat',
            'tags': tags,
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

    data = request.get_json() or {}
    title = data.get('title', 'New Chat')

    _run_async(channel_instance.context.chat.new(title))

    return jsonify({
        'success': True,
        'chat': {
            'id': _run_async(channel_instance.context.chat.get_id()),
            'title': title,
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

# =============================================================================
# Server control routes
# =============================================================================
@app.route("/server/restart", methods=["POST"])
def restart_server():
    _run_async(core.restart())
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
