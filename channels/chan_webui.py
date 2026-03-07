"""
OptiClaw WebUI - A modern chat interface for AI interactions.

This module provides a Flask-based web interface that polls the backend
for messages, treating the backend (API.get_messages()) as the single
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

    The backend (manager.API.get_messages()) is the single source of truth.
    All messages including user messages, AI responses, commands, and 
    announcements are stored in the backend and polled by the frontend.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_loop = None

        # Storage for saved conversations (frontend metadata only)
        self.conversations = core.storage.StorageList("conversations", "msgpack")

        # Track currently active conversation
        self.current_conversation_id = None

    async def run(self):
        """Start the Flask web server."""
        core.log("webui", "Starting WebUI")

        self.main_loop = asyncio.get_running_loop()

        global channel_instance
        channel_instance = self

        # Start Flask in a separate thread
        flask_thread = Thread(target=self._run_flask, daemon=True)
        flask_thread.start()

        host = core.config.get("webui_host", "127.0.0.1")
        port = core.config.get("webui_port", 5000)
        core.log("webui", f"WebUI started on {host}:{port}")

        while True:
            await asyncio.sleep(1)

    def _run_flask(self):
        """Run Flask in a separate thread."""
        from werkzeug.serving import make_server

        host = core.config.get("webui_host", "127.0.0.1")
        port = core.config.get("webui_port", 5000)

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

    def get_messages(self):
        """Get all messages from the backend API."""
        messages = self.manager.API.get_messages()
        result = []

        for i, msg in enumerate(messages):
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if content:
                result.append({
                    'role': role,
                    'content': content,
                    'index': i
                })

        return result

    def get_messages_since(self, since_index):
        """Get messages from the backend starting from an index."""
        messages = self.manager.API.get_messages()
        result = []

        for i in range(since_index, len(messages)):
            msg = messages[i]
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if content:
                result.append({
                    'role': role,
                    'content': content,
                    'index': i
                })

        return result

    def set_messages(self, messages):
        """Set messages in the backend API."""
        backend_messages = []

        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')

            if role == 'ai':
                role = 'assistant'

            if content:
                backend_messages.append({
                    'role': role,
                    'content': content
                })

        self.manager.API.set_messages(backend_messages)

# =============================================================================
# Flask Routes
# =============================================================================

HTML_TEMPLATE = None
with open(core.get_path("channels/webui/index.html"), "r") as f:
    HTML_TEMPLATE = f.read()

@app.route('/')
def index():
    """Serve the main HTML page."""
    return render_template_string(HTML_TEMPLATE)

@app.route('/messages')
def get_messages():
    """
    Get all messages from the backend.

    This is the primary endpoint for the frontend to sync with the backend.
    Returns messages with their indices for proper tracking.
    """
    if not channel_instance:
        return jsonify({'messages': [], 'count': 0})

    messages = channel_instance.get_messages()
    return jsonify({
        'messages': messages,
        'count': len(messages)
    })

@app.route('/messages/since')
def get_messages_since():
    """
    Get messages since a specific index.

    More efficient than getting all messages when just polling for updates.
    """
    if not channel_instance:
        return jsonify({'messages': [], 'count': 0})

    try:
        since_index = int(request.args.get('index', 0))
    except ValueError:
        since_index = 0

    messages = channel_instance.get_messages_since(since_index)
    return jsonify({
        'messages': messages,
        'count': len(messages),
        'total': len(channel_instance.manager.API.get_messages())
    })

@app.route('/stream', methods=['POST'])
def stream_message():
    """
    Stream AI response token by token using Server-Sent Events.

    Inserts the user message first, then streams the AI response.
    Both messages are stored in the backend.
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
                # Send via the channel (handles commands vs regular messages)
                response_text = []
                async for token in channel_instance.send_stream("user", user_message):
                    if stream_id in stream_cancellations:
                        stream_cancellations.discard(stream_id)
                        token_queue.put(('cancelled', True))
                        break
                    token_queue.put(token)
                    response_text.append(token)
            except Exception as e:
                token_queue.put(('error', str(e)))
            finally:
                token_queue.put(done)

        future = asyncio.run_coroutine_threadsafe(collect_tokens(), channel_instance.main_loop)

        # Send stream ID first
        yield f"data: {json.dumps({'id': stream_id})}\n\n"

        # Stream tokens
        while True:
            item = token_queue.get()

            if item is done:
                # Get final message count
                total = len(channel_instance.manager.API.get_messages())
                yield f"data: {json.dumps({'done': True, 'total': total})}\n\n"
                break
            elif isinstance(item, tuple):
                if item[0] == 'error':
                    yield f"data: {json.dumps({'error': item[1]})}\n\n"
                    break
                elif item[0] == 'cancelled':
                    yield f"data: {json.dumps({'cancelled': True})}\n\n"
                    break
            else:
                yield f"data: {json.dumps({'token': item})}\n\n"

        future.result()

    return Response(generate(), mimetype='text/event-stream')

@app.route('/send', methods=['POST'])
def send_message():
    """
    Send a message and wait for complete response.

    Used for commands that need immediate response.
    The base Channel class handles inserting both the command and response.
    """
    global channel_instance

    data = request.get_json()
    user_message = data.get('message', '')

    future = asyncio.run_coroutine_threadsafe(
        channel_instance.send("user", user_message),
        channel_instance.main_loop
    )
    response = future.result()

    # Return response and updated message count
    total = len(channel_instance.manager.API.get_messages())
    return jsonify({
        'response': response,
        'total': total
    })

@app.route('/edit', methods=['POST'])
def edit_message():
    """Edit a message in the backend by index."""
    global channel_instance

    data = request.get_json()
    index = data.get('index', 0)
    new_content = data.get('content', '')

    messages = channel_instance.manager.API.get_messages()

    if 0 <= index < len(messages):
        if messages[index].get('role') not in ('user', 'assistant'):
            return jsonify({'success': False, 'error': 'Cannot edit this message type'})

        messages[index]['content'] = new_content
        core.log("webui", f"Edited message {index}")
        return jsonify({'success': True, 'total': len(messages)})

    return jsonify({'success': False, 'error': f'Index {index} out of range'})

@app.route('/delete', methods=['POST'])
def delete_message():
    """Delete a message and all messages after it from the backend."""
    global channel_instance

    data = request.get_json()
    index = data.get('index', 0)

    messages = channel_instance.manager.API.get_messages()

    if 0 <= index < len(messages):
        if messages[index].get('role') not in ('user', 'assistant', 'command', 'command_response'):
            if not messages[index].get('role', '').startswith('announce_'):
                return jsonify({'success': False, 'error': 'Cannot delete this message type'})

        # Keep only messages before the index
        channel_instance.manager.API.set_messages(messages[:index])
        remaining = len(channel_instance.manager.API.get_messages())
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
            await channel_instance.manager.API.insert_message("user", f"[File: {filename}]\n{content}...")

        asyncio.run_coroutine_threadsafe(
            insert_file(),
            channel_instance.main_loop
        ).result()

        total = len(channel_instance.manager.API.get_messages())
        return jsonify({'success': True, 'total': total})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# =============================================================================
# Conversation Management Routes
# =============================================================================
@app.route('/conversations')
def list_conversations():
    """List all saved conversations."""
    global channel_instance

    if not channel_instance:
        return jsonify({'conversations': []})

    conversations = []
    for conv in channel_instance.conversations:
        conversations.append({
            'id': conv.get('id'),
            'title': conv.get('title', 'New Conversation'),
            'created': conv.get('created'),
            'updated': conv.get('updated'),
            'message_count': len(conv.get('messages', []))
        })

    conversations.sort(key=lambda x: x.get('updated', ''), reverse=True)
    return jsonify({'conversations': conversations})

@app.route('/conversation/save', methods=['POST'])
def save_conversation():
    """Save current conversation from backend to StorageList."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    data = request.get_json() if request.is_json else {}
    conv_id = data.get('id')

    # Get messages from backend (source of truth)
    messages = channel_instance.get_messages()

    # Generate title from first user message
    title = 'New Conversation'
    for msg in messages:
        if msg.get('role') == 'user':
            content = msg.get('content', '')
            if content and not content.startswith('/') and not content.startswith("[Command") and not content.startswith("[System"):
                title = content[:50]
                if len(content) > 50:
                    title += '...'
                break

    now = datetime.utcnow().isoformat()

    if conv_id:
        # Update existing conversation
        for i, conv in enumerate(channel_instance.conversations):
            if conv.get('id') == conv_id:
                channel_instance.conversations[i] = {
                    'id': conv_id,
                    'title': conv.get("title"),
                    'messages': messages,
                    'created': conv.get('created', now),
                    'updated': now
                }
                channel_instance.conversations.save()
                channel_instance.current_conversation_id = conv_id
                return jsonify({'success': True, 'id': conv_id})

    # Create new conversation
    conv_id = conv_id or str(uuid.uuid4())[:8]
    channel_instance.conversations.append({
        'id': conv_id,
        'title': title,
        'messages': messages,
        'created': now,
        'updated': now
    })
    channel_instance.conversations.save()
    channel_instance.current_conversation_id = conv_id

    return jsonify({'success': True, 'id': conv_id})

@app.route('/conversation/load')
def load_conversation():
    """Load conversation from StorageList and push to backend."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    conv_id = request.args.get('id')
    if not conv_id:
        return jsonify({'success': False, 'error': 'No conversation ID provided'})

    for conv in channel_instance.conversations:
        if conv.get('id') == conv_id:
            messages = conv.get('messages', [])

            # Push messages to backend
            channel_instance.set_messages(messages)

            # Track active conversation
            channel_instance.current_conversation_id = conv_id

            return jsonify({
                'success': True,
                'conversation': {
                    'id': conv.get('id'),
                    'title': conv.get('title', 'New Conversation'),
                    'messages': messages
                }
            })

    return jsonify({'success': False, 'error': 'Conversation not found'})

@app.route('/conversation/current')
def get_current_conversation():
    """Get the currently active conversation ID and its messages."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    conv_id = channel_instance.current_conversation_id

    if not conv_id:
        return jsonify({
            'success': True,
            'current_id': None,
            'conversation': None
        })

    for conv in channel_instance.conversations:
        if conv.get('id') == conv_id:
            return jsonify({
                'success': True,
                'current_id': conv_id,
                'conversation': {
                    'id': conv.get('id'),
                    'title': conv.get('title', 'New Conversation'),
                    'messages': conv.get('messages', [])
                }
            })

    # ID set but conversation not found - clear it
    channel_instance.current_conversation_id = None
    return jsonify({
        'success': True,
        'current_id': None,
        'conversation': None
    })

@app.route('/conversation/rename', methods=['POST'])
def rename_conversation():
    """Rename a saved conversation."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    data = request.get_json()
    conv_id = data.get('id')
    new_title = data.get('title', '').strip()

    if not conv_id:
        return jsonify({'success': False, 'error': 'No conversation ID provided'})

    if not new_title:
        return jsonify({'success': False, 'error': 'Title cannot be empty'})

    for i, conv in enumerate(channel_instance.conversations):
        if conv.get('id') == conv_id:
            channel_instance.conversations[i]['title'] = new_title[:100]
            channel_instance.conversations.save()
            return jsonify({'success': True, 'title': new_title[:100]})

    return jsonify({'success': False, 'error': 'Conversation not found'})

@app.route('/conversation/delete', methods=['POST'])
def delete_conversation():
    """Delete a saved conversation."""
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    conv_id = request.args.get('id') or request.get_json(silent=True).get('id')

    if not conv_id:
        return jsonify({'success': False, 'error': 'No conversation ID provided'})

    for i, conv in enumerate(channel_instance.conversations):
        if conv.get('id') == conv_id:
            del channel_instance.conversations[i]
            channel_instance.conversations.save()
            return jsonify({'success': True})

    return jsonify({'success': False, 'error': 'Conversation not found'})

# =============================================================================
# PWA Support Routes
# =============================================================================

@app.route('/manifest.json')
def manifest():
    """Serve the PWA manifest."""
    with open(core.get_path("channels/webui/manifest.json")) as f:
        manifest = json.loads(f.read());
    return jsonify(manifest)

@app.route('/sw.js')
def service_worker():
    """Serve the service worker."""
    with open(core.get_path("channels/webui/sw.js")) as f:
        sw_code = f.read();
    response = Response(sw_code, mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route('/icon-192.png')
@app.route('/icon-512.png')
def icon():
    """Serve a placeholder icon for PWA."""
    png_hex = "89504e470d0a1a0a0000000d494844520000000200000002080200000001f338dd0000000c4944415408d763f8ffffcf0001000100737a55b00000000049454e44ae426082"
    return bytes.fromhex(png_hex), 200, {'Content-Type': 'image/png'}
