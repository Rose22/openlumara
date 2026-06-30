import core
import re
from flask import Flask, request, render_template_string, redirect, url_for
from werkzeug.serving import make_server
import uuid
import threading
import asyncio
import time

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ channel_name }} WebUI</title>
    {% if processing %}
    <meta http-equiv="refresh" content="1">
    {% endif %}
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: var(--font), Verdana, sans-serif;
            background: #000000;
            color: var(--primary-color);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        p {
            margin-bottom: 8px;
        }
        a, a:hover, a:active, a:visited {
            color: var(--secondary-color);
        }
        hr {
            margin-top: 8px;
            border-color: var(--secondary-color);
            margin-bottom: 8px;
        }
        header {
            background: #001100;
            padding: 10px 15px;
            border-bottom: 2px solid var(--primary-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        header h1 {
            font-size: 1.1em;
            color: var(--primary-color);
        }
        header a {
            color: var(--primary-color);
            text-decoration: none;
            font-size: 0.8em;
            padding: 4px 10px;
            border: 1px solid var(--primary-color);
            border-radius: 4px;
            transition: background 0.2s;
        }
        #chat-container {
            padding: 10px;
            flex-grow: 1;
            height: 0;
            overflow-y: auto;
            max-width: 800px;
            width: 100%;
            margin: 0 auto;
        }
        .message {
            margin-bottom: 10px;
            padding: 10px;
            border-radius: 0px;
            word-wrap: break-word;
        }
        .message.user {
            background: #000000;
            border-left: 3px solid var(--primary-color);
        }
        .message.user .label {
            color: var(--primary-color);
        }
        .message.assistant {
            background: #000000;
            border-left: 3px solid var(--secondary-color);
            color: var(--secondary-color);
        }
        .message.assistant .label {
            color: var(--secondary-color);
        }
        .label {
            font-weight: bold;
            font-size: 0.75em;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 5px;
            display: block;
        }
        .message .content {
            font-size: 0.9em;
            white-space: pre-wrap;
        }
        #input-container {
            background: #000000;
            padding: 10px 15px;
            border-top: 2px solid var(--primary-color);
        }
        #input-container form {
            max-width: 800px;
            margin: 0 auto;
            display: flex;
            gap: 8px;
        }
        #input-container input {
            flex: 1;
            padding: 8px 10px;
            border: 2px solid var(--primary-color);
            border-radius: 6px;
            background: #000000;
            color: var(--primary-color);
            font-family: inherit;
            font-size: 0.9em;
        }
        #input-container input::placeholder {
            color: var(--secondary-color);
        }
        #input-container input:focus {
            outline: none;
            border-color: var(--primary-color);
        }
        #input-container button {
            padding: 8px 18px;
            background: #000000;
            color: var(--primary-color);
            border: 1px solid var(--primary-color);
            border-radius: 6px;
            font-size: 0.9em;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.2s;
            align-self: flex-end;
            height: 40px;
        }
        #input-container button:hover {
            background: var(--primary-color);
        }
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--secondary-color);
        }
        .empty-state h1, h2, h3, h4, h5, h6 {
            color: var(--primary-color);
            margin-bottom: 8px;
        }
        .processing {
            text-align: center;
            padding: 30px;
            color: var(--primary-color);
            font-style: italic;
        }

        /* Webkit browsers (Chrome, Safari, Edge) */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }

        ::-webkit-scrollbar-track {
            background: transparent;
        }

        ::-webkit-scrollbar-thumb {
            background: var(--primary-color);
        }

        ::-webkit-scrollbar-thumb:hover {
            background: var(--primary-color);
        }

        ::-webkit-scrollbar-corner {
            background: transparent;
        }

        /* Firefox */
        * {
            scrollbar-width: thin;
            scrollbar-color: var(--primary-color) transparent;
        }
    </style>
</head>
<body>
    <header>
        <h1>{{ channel_name }}</h1>
        <a href="{{ url_for('clear_chat') }}">Clear Chat</a>
    </header>

    <div id="chat-container">
        {% if processing %}
            <div class="processing">
                Processing your message... (page will auto-refresh)
            </div>
        {% endif %}

        {% if messages %}
            {% for msg in messages|reverse %}
            <div class="message {{ msg.role }}">
                <span class="label">{{ msg.role }}</span>
                <div class="content">{{ msg.content }}</div>
            </div>
            {% endfor %}

        {% elif not processing %}
            <div class="empty-state">
                <<welcome_message>>
            </div>
        {% endif %}
    </div>

    <div id="input-container">
        <form method="POST" action="{{ url_for('index') }}">
            <input type="text" name="message" placeholder="Type your message...">{{ last_user_message }}</input>
            <button type="submit">Send</button>
        </form>
    </div>
</body>
</html>
"""

class SimpleWebui(core.channel.Channel):
    """
    A simple HTML-only, javascript-less, Flask-based web UI for interacting with the AI. Suitable as an alternative to the full webUI. It's safer to expose to the internet due to the total lack of admin panels.
    """

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
            "default": 5000
        },
        "allow_commands": {
            "description": "Whether to allow running `/commands` in this instance. Do NOT enable this if your instance is exposed to the public.",
            "default": False
        },
        "enable_logging": {
            "description": "Whether to log all messages flowing through this channel to the console. Helps you see what's going on if you have exposed it as a public instance!",
            "default": True
        },
        "name": {
            "default": "OpenLumara",
            "description": "The name of your webUI instance. Shows up in headers and the like."
        },
        "welcome_message": {
            "default": """
<h2>Welcome!</h2>
<p>Send a message below to start chatting with the AI.</p>
            """.strip(),
            "description": "Raw HTML content to serve the user as the welcome message, shown when the page is first opened, before sending their first message to the AI"
        },
        "font": {
            "default": "monospace",
            "description": "The font to use for your page"
        },
        "primary_color": {
            "default": "#FFFFFF",
            "description": "Color (in hex code format) to use as the primary accent color for the page"
        },
        "secondary_color": {
            "default": "#CCCCCC",
            "description": "Color (in hex code format) to use as the secondary accent color for the page"
        }
    }
    dependencies = ["flask", "werkzeug"]

    HTML_CLEAN_PATTERN = re.compile('<.*?>')

    def _sync_send(self, message_dict):
        """
        Helper method to call async self.send() from a synchronous context.
        Uses asyncio.new_event_loop() + run_until_complete to bridge the gap.
        """
        loop = asyncio.new_event_loop()
        try:
            task = asyncio.ensure_future(self.send(message_dict, commands_authorized=self.config.get("allow_commands")), loop=loop)
            return loop.run_until_complete(task)
        finally:
            loop.close()

    def _sync_clear(self):
        loop = asyncio.new_event_loop()
        try:
            task = asyncio.ensure_future(self.context.chat.clear(), loop=loop)
            return loop.run_until_complete(task)
        finally:
            loop.close()

    async def on_ready(self):
        """Initialize Flask app and start it in a background thread."""
        self.app = Flask(__name__)
        self.app.secret_key = str(uuid.uuid4())
        self.thread = None
        self.html_template = HTML_TEMPLATE.replace("var(--primary-color)", self.config.get("primary_color"))
        self.html_template = self.html_template.replace("var(--secondary-color)", self.config.get("secondary_color"))
        self.html_template = self.html_template.replace("var(--font)", self.config.get("font"))
        self.html_template = self.html_template.replace("<<welcome_message>>", self.config.get("welcome_message"))

        # Instance-level state (thread-safe enough for this use case)
        self._messages = []
        self._processing = False
        self._pending_user_input = None
        self._lock = threading.Lock()

        @self.app.route("/", methods=["GET", "POST"])
        def index():
            with self._lock:
                messages = list(self._messages)
                processing = self._processing

            if request.method == "POST":
                user_input = request.form.get("message", "").strip()
                user_input = re.sub(self.HTML_CLEAN_PATTERN, '', user_input)
                if not user_input:
                    return redirect(url_for("index"))

                # Save user message immediately
                with self._lock:
                    self._messages.append({"role": "user", "content": user_input})
                    if self.config.get("enable_logging"):
                        self.log(self.name, f"USER: {user_input}")

                    self._pending_user_input = user_input
                    self._processing = True

                # Start AI call in background thread
                def handle_ai_call():
                    try:
                        # Call AI synchronously (helper bridges async->sync)
                        response_dict = self._sync_send({"role": "user", "content": self._pending_user_input})

                        if response_dict:
                            response_content = response_dict.get("content", "")
                            response_content = re.sub(self.HTML_CLEAN_PATTERN, '', response_content)

                            with self._lock:
                                self._messages.append({"role": "assistant", "content": response_content})

                                if self.config.get("enable_logging"):
                                    self.log(self.name, f"ASSISTANT: {response_content}")
                    finally:
                        with self._lock:
                            self._processing = False

                thread = threading.Thread(target=handle_ai_call, daemon=True)
                thread.start()

                # Return immediately with processing state
                return render_template_string(
                    self.html_template,
                    channel_name=self.config.get("name"),
                    messages=messages,
                    last_user_message="",
                    processing=True
                )

            with self._lock:
                messages = list(self._messages)
                processing = self._processing

            return render_template_string(
                self.html_template,
                channel_name=self.config.get("name"),
                messages=messages,
                last_user_message="",
                processing=processing
            )

        @self.app.route("/clear", methods=["GET"])
        def clear_chat():
            with self._lock:
                self._sync_clear()
                self._messages = []
                self._processing = False
            return redirect(url_for("index"))

        network_mode = self.config.get("network_mode")
        host = None
        port = self.config.get("port")
        match network_mode:
            case "local":
                host = "127.0.0.1"
            case "internet":
                host = "0.0.0.0"
            case "custom":
                host = self.config.get("custom_host")
            case _:
                host = "127.0.0.1"

        self.server = make_server(host, port, self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        self.log(self.name, f"Simple WebUI is running at http://{host}:{port}")

    async def run(self):
        """This channel doesn't use the traditional run loop - Flask runs in a background thread."""
        pass  # Flask runs in background thread

    async def on_push(self, message: dict):
        """Handle push messages from the framework — display them as assistant messages."""
        content = message.get("content", "")
        if not content:
            return
        with self._lock:
            content = re.sub(self.HTML_CLEAN_PATTERN, '', content)
            self._messages.append({"role": "assistant", "content": content})

    async def on_shutdown(self):
        if hasattr(self, "server") and self.server:
            self.server.server_close()  # Closes the listening socket, unblocking serve_forever()
            self.thread.join(timeout=2.0)  # Waits for thread to exit cleanly
