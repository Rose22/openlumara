import asyncio
from flask import Flask, render_template_string, request, jsonify, Response, cli
import core
from threading import Thread
import logging
import json

app = Flask(__name__)

# disable all logs
cli.show_server_banner = lambda *x: print(end="")
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
log.disabled = True

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#111111">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="OptiClaw">
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" href="/icon-192.png">

    <title>OptiClaw</title>

    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.11.1/build/styles/github-dark.css">
    <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.11.1/build/highlight.min.js"></script>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        html, body {
            height: 100%;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
                Ubuntu, sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
        }

        .app-container {
            display: flex;
            flex-direction: column;
            height: 100%;
            max-width: 900px;
            margin: 0 auto;
            background: #111;
            box-shadow: 0 0 40px rgba(0, 0, 0, 0.8);
        }

        header {
            padding: 16px 20px;
            background: linear-gradient(180deg, #1a1a1a 0%, #0f0f0f 100%);
            border-bottom: 1px solid #2a2a2a;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        header h1 {
            font-size: 1.3rem;
            font-weight: 600;
            color: #e8e8e8;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            background: #4ade80;
            border-radius: 50%;
            box-shadow: 0 0 10px rgba(74, 222, 128, 0.6);
            animation: pulse 2s infinite;
        }

        .status-dot.inactive {
            background: #f87171;
            box-shadow: 0 0 10px rgba(248, 113, 113, 0.6);
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        .header-btn {
            padding: 8px 12px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            color: #888;
            font-size: 0.85rem;
            cursor: pointer;
            transition: background 0.2s, color 0.2s;
        }

        .header-btn:hover {
            background: #222;
            color: #bbb;
        }

        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: #0d0d0d;
        }

        .message {
            max-width: 85%;
            padding: 12px 16px;
            border-radius: 16px;
            line-height: 1.5;
            word-wrap: break-word;
            animation: slideIn 0.2s ease-out;
        }

        .message.hidden {
            display: none;
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message.user {
            align-self: flex-end;
            background: linear-gradient(135deg, #3a3a3a 0%, #2d2d2d 100%);
            color: #f0f0f0;
            border: 1px solid #444;
            border-bottom-right-radius: 4px;
        }

        .message.ai {
            align-self: flex-start;
            background: #1a1a1a;
            border: 1px solid #333;
            color: #d0d0d0;
            border-bottom-left-radius: 4px;
        }

        .message.announce {
            align-self: center;
            background: linear-gradient(135deg, #2a2a2a 0%, #1f1f1f 100%);
            border: 1px solid #404040;
            color: #a0a0a0;
            font-style: italic;
            text-align: center;
            font-size: 0.9rem;
            max-width: 90%;
        }

        .message.command {
            align-self: flex-start;
            background: linear-gradient(135deg, #1a2a1a 0%, #0f1f0f 100%);
            border: 1px solid #2a4a2a;
            color: #a0d0a0;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.9rem;
            border-bottom-left-radius: 4px;
            max-width: 85%;
        }

        .message.command .timestamp {
            color: #4a6a4a;
        }

        .message .timestamp {
            display: block;
            font-size: 0.7rem;
            color: #666;
            margin-top: 6px;
            text-align: right;
        }

        .message.ai .timestamp {
            text-align: left;
        }

        .message.announce .timestamp {
            text-align: center;
        }

        .message pre {
            background: #0a0a0a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 12px;
            overflow-x: auto;
            margin: 8px 0;
            position: relative;
        }

        .message code {
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.9em;
        }

        .message pre code {
            background: transparent;
            padding: 0;
        }

        .message :not(pre) > code {
            background: #2a2a2a;
            padding: 2px 6px;
            border-radius: 4px;
        }

        .copy-btn {
            position: absolute;
            top: 8px;
            right: 8px;
            padding: 4px 8px;
            background: #2a2a2a;
            border: 1px solid #3a3a3a;
            border-radius: 4px;
            color: #888;
            font-size: 0.75rem;
            cursor: pointer;
            opacity: 0;
            transition: opacity 0.2s, background 0.2s;
        }

        .message pre:hover .copy-btn {
            opacity: 1;
        }

        .copy-btn:hover {
            background: #3a3a3a;
            color: #aaa;
        }

        .message h1, .message h2, .message h3 {
            margin: 12px 0 8px;
            color: #e0e0e0;
        }

        .message h1 { font-size: 1.4em; }
        .message h2 { font-size: 1.2em; }
        .message h3 { font-size: 1.1em; }

        .message ul, .message ol {
            margin: 8px 0;
            padding-left: 24px;
        }

        .message li {
            margin: 4px 0;
        }

        .message blockquote {
            border-left: 3px solid #4a4a4a;
            margin: 8px 0;
            padding-left: 12px;
            color: #a0a0a0;
        }

        .message a {
            color: #6a9fb5;
            text-decoration: none;
        }

        .message a:hover {
            text-decoration: underline;
        }

        .message table {
            border-collapse: collapse;
            margin: 8px 0;
        }

        .message th, .message td {
            border: 1px solid #3a3a3a;
            padding: 8px 12px;
        }

        .message th {
            background: #1a1a1a;
        }

        .message hr {
            border: none;
            border-top: 1px solid #3a3a3a;
            margin: 12px 0;
        }

        .typing-indicator {
            display: none;
            align-self: flex-start;
            padding: 12px 16px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 16px;
            border-bottom-left-radius: 4px;
        }

        .typing-indicator.show {
            display: flex;
            gap: 4px;
            align-items: center;
        }

        .typing-indicator span {
            width: 8px;
            height: 8px;
            background: #555;
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out;
        }

        .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
        .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0.8); }
            40% { transform: scale(1.2); }
        }

        .input-area {
            padding: 16px;
            background: #0a0a0a;
            border-top: 1px solid #222;
            display: flex;
            gap: 12px;
            align-items: center;
            flex-shrink: 0;
        }

        #upload {
            padding: 14px 16px;
            background: linear-gradient(135deg, #2a2a2a 0%, #1a1a1a 100%);
            border: 1px solid #3a3a3a;
            border-radius: 24px;
            color: #888;
            cursor: pointer;
            transition: background 0.2s, color 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        #upload:hover {
            background: linear-gradient(135deg, #3a3a3a 0%, #2a2a2a 100%);
            color: #aaa;
        }

        #upload svg {
            width: 20px;
            height: 20px;
        }

        #file-input {
            display: none;
        }

        #message {
            flex: 1;
            padding: 10px 18px;
            border: 1px solid #2a2a2a;
            border-radius: 24px;
            background: #161616;
            color: #e0e0e0;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
            resize: none;
            height: 44px;
            min-height: 36px;
            max-height: 200px;
            overflow-y: auto;
            font-family: inherit;
            line-height: 1.4;
        }

        #message:focus {
            border-color: #555;
            box-shadow: 0 0 0 3px rgba(80, 80, 80, 0.3);
        }

        #message::placeholder {
            color: #555;
        }

        #message:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        #send {
            padding: 14px 24px;
            background: linear-gradient(135deg, #3a3a3a 0%, #2a2a2a 100%);
            border: 1px solid #444;
            border-radius: 24px;
            color: #e0e0e0;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.1s, background 0.2s;
            flex-shrink: 0;
        }
        #send.hidden {
            display: none;
        }

        #send:hover {
            background: linear-gradient(135deg, #444 0%, #333 100%);
        }

        #send:active {
            transform: scale(0.96);
        }

        #send:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        #stop {
            padding: 14px 24px;
            background: linear-gradient(135deg, #5a2a2a 0%, #3a1a1a 100%);
            border: 1px solid #6a3a3a;
            border-radius: 24px;
            color: #e0e0e0;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.1s, background 0.2s;
            flex-shrink: 0;
            display: none;
        }

        #stop:hover {
            background: linear-gradient(135deg, #6a3a3a 0%, #4a2a2a 100%);
        }

        #stop:active {
            transform: scale(0.96);
        }

        #stop.show {
            display: block;
        }

        .chat-container::-webkit-scrollbar {
            width: 6px;
        }

        .chat-container::-webkit-scrollbar-track {
            background: #0a0a0a;
        }

        .chat-container::-webkit-scrollbar-thumb {
            background: #2a2a2a;
            border-radius: 3px;
        }

        .chat-container::-webkit-scrollbar-thumb:hover {
            background: #3a3a3a;
        }

        @media (max-width: 600px) {
            header {
                padding: 12px 16px;
            }

            header h1 {
                font-size: 1.1rem;
            }

            .header-btn {
                padding: 6px 10px;
                font-size: 0.8rem;
            }

            .chat-container {
                padding: 12px;
            }

            .message {
                max-width: 90%;
                padding: 10px 14px;
            }

            .input-area {
                padding: 12px;
                gap: 8px;
            }

            #upload {
                padding: 12px;
            }

            #message {
                padding: 12px 16px;
            }

            #send, #stop {
                padding: 12px 18px;
            }

            .message pre {
                padding: 10px;
                font-size: 0.85rem;
            }

            .copy-btn {
                opacity: 1;
                padding: 6px 10px;
            }
        }

        @media (max-width: 400px) {
            .header-left {
                gap: 8px;
            }

            .status-dot {
                width: 8px;
                height: 8px;
            }

            .message {
                padding: 8px 12px;
                font-size: 0.95rem;
            }

            #send, #stop {
                padding: 12px 14px;
                font-size: 0.9rem;
            }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <header>
            <div class="header-left">
                <div class="status-dot" id="status"></div>
                <h1>AI Chat</h1>
            </div>
            <button class="header-btn" onclick="clearChat()">Clear</button>
        </header>
        <div class="chat-container" id="chat">
            <div class="typing-indicator" id="typing">
                <span></span><span></span><span></span>
            </div>
        </div>
        <div class="input-area">
            <button id="upload" onclick="document.getElementById('file-input').click()">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
                </svg>
            </button>
            <input type="file" id="file-input" onchange="handleFileUpload(event)">
            <textarea id="message" placeholder="Type a message... (or /new for new chat)" onkeydown="handleKeyDown(event)" rows=1></textarea>
            <script>
            document.getElementById('message').addEventListener('input', function() {
                autoResize(this);
            });
            </script>
            <button id="send" onclick="send()">Send</button>
            <button id="stop" onclick="stopGeneration()">Stop</button>
        </div>
    </div>
    <script>
        let lastAnnouncementId = 0;
        const chat = document.getElementById('chat');
        const typing = document.getElementById('typing');
        const inputField = document.getElementById('message');
        const sendBtn = document.getElementById('send');
        const stopBtn = document.getElementById('stop');
        const statusDot = document.getElementById('status');
        let isStreaming = false;
        let currentAiMsg = null;
        let currentController = null;
        let conversationHistory = [];

        marked.setOptions({
            breaks: true,
            gfm: true
        });

        function renderMarkdown(text) {
            let html = marked.parse(text);
            return html;
        }

        function highlightCode(element) {
            if (typeof hljs === 'undefined') return;
            element.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);

                const pre = block.parentElement;
                if (!pre.querySelector('.copy-btn')) {
                    const btn = document.createElement('button');
                    btn.className = 'copy-btn';
                    btn.textContent = 'Copy';
                    btn.onclick = () => {
                        navigator.clipboard.writeText(block.textContent).then(() => {
                            btn.textContent = 'Copied!';
                            setTimeout(() => btn.textContent = 'Copy', 1500);
                        });
                    };
                    pre.style.position = 'relative';
                    pre.appendChild(btn);
                }
            });
        }

        function saveHistory() {
            localStorage.setItem('chatHistory', JSON.stringify(conversationHistory));
        }

        function loadHistory() {
            const saved = localStorage.getItem('chatHistory');
            if (saved) {
                conversationHistory = JSON.parse(saved);
                conversationHistory.forEach(msg => {
                    createMessageElement(msg.role, msg.content, msg.timestamp);
                });
            }
        }

        function formatTime(date) {
            if (date) return date;
            return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        function createMessageElement(role, content, timestamp) {
            const div = document.createElement('div');
            div.className = 'message ' + role;
            const timeStr = timestamp || formatTime();

            if (role === 'ai' || role === 'user' ) {
                div.innerHTML = renderMarkdown(content);
                highlightCode(div);
            } else {
                div.innerText = content;
            }

            const ts = document.createElement('span');
            ts.className = 'timestamp';
            ts.textContent = timeStr;
            div.appendChild(ts);

            chat.insertBefore(div, typing);
            chat.scrollTop = chat.scrollHeight;
            return div;
        }

        function addMessage(role, content, withTimestamp = true, timestamp = null) {
            const timeStr = timestamp || formatTime();
            const msg = { role: role, content: content, timestamp: timeStr };

            if (isStreaming && currentAiMsg && role === 'announce') {
                conversationHistory.push(msg);
                saveHistory();
                chat.insertBefore(createMessageElement(role, content, timeStr), currentAiMsg);
            } else {
                if (role !== 'announce') {
                    conversationHistory.push(msg);
                    saveHistory();
                }
                createMessageElement(role, content, timeStr);
            }
            chat.scrollTop = chat.scrollHeight;
        }

        function setInputState(disabled, showTyping = false, showStop = false) {
            inputField.disabled = false;
            sendBtn.disabled = disabled;
            statusDot.classList.toggle('inactive', disabled);

            if (showTyping) {
                typing.classList.add('show');
            } else {
                typing.classList.remove('show');
            }

            if (showStop) {
                sendBtn.classList.add('hidden');
                stopBtn.classList.add('show');
            } else {
                sendBtn.classList.remove('hidden');
                stopBtn.classList.remove('show');
            }
        }

        function handleKeyDown(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                send();
            }
        }

        function autoResize(textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
        }

        async function stopGeneration() {
            // Stop the frontend stream first
            if (currentController) {
                currentController.abort();
                currentController = null;
            }

            // Send /stop command to the channel
            const timestamp = formatTime();
            conversationHistory.push({ role: 'command', content: "stopping..", timestamp: timestamp });
            saveHistory();
            createMessageElement('command', "stopping..", timestamp);

            if (currentStreamId) {
                try {
                    await fetch('/cancel', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({id: currentStreamId})
                    });
                } catch (e) {}
                currentStreamId = null;

            }
            if (currentAiMsg) {
                    currentAiMsg.classList.remove('hidden');

                    // Get existing content (if any partial response was streamed)
                    let existingContent = currentAiMsg.innerText || '';
                    // Remove any existing timestamp from the content
                    existingContent = existingContent.replace(/\\s*\\d{1,2}:\\d{2}\\s*(?:AM|PM)?\\s*$/i, '').trim();

                    // Show stopped message
                    if (existingContent) {
                        currentAiMsg.innerHTML = renderMarkdown(existingContent) + ' <span style="color:#f88;">[Stopped]</span>';
                    } else {
                        currentAiMsg.innerHTML = '<span style="color:#f88;">[Stopped]</span>';
                    }

                    const ts = document.createElement('span');
                    ts.className = 'timestamp';
                    ts.textContent = formatTime();
                    currentAiMsg.appendChild(ts);

                    // Save to history
                    const finalContent = existingContent ? existingContent + ' <br><span style="color:#f88;">[Stopped]</span>' : '<span style="color:#f88;">[Stopped]</span>';
                    conversationHistory.push({ role: 'ai', content: finalContent, timestamp: formatTime() });
                    saveHistory();

                    currentAiMsg = null;
            }
            try {
                await fetch('/send', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: '/stop'})
                });
            } catch (e) {}

            setInputState(false, false, false);
            isStreaming = false;
            currentAiMsg = null;
            inputField.focus();
        }
        function clearChatUI() {
            conversationHistory = [];
            saveHistory();
            const messages = chat.querySelectorAll('.message');
            messages.forEach(msg => msg.remove());
            currentAiMsg = null;
        }

        function clearChat() {
            clearChatUI();
            sendCommand('/new');
        }

        async function sendCommand(cmd) {
            // Stop any ongoing stream first
            if (isStreaming) {
                await stopGeneration();
            }

            if (cmd.startsWith("/new")) {
                clearChatUI();
            }
            if (cmd.startsWith("/stop")) {
                await stopGeneration();
            }

            const timestamp = formatTime();
            conversationHistory.push({ role: 'user', content: cmd, timestamp: timestamp });
            saveHistory();
            createMessageElement('user', cmd, timestamp);

            try {
                const response = await fetch('/send', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: cmd})
                });

                const data = await response.json();
                if (data.response) {
                    const ts = formatTime();
                    const msg = { role: 'command', content: data.response, timestamp: ts };
                    conversationHistory.push(msg);
                    saveHistory();
                    createMessageElement('command', data.response, ts);
                }
            } catch (err) {
                if (cmd.startsWith("/restart")) {
                    // lol just ignore the error cuz server restarting n stuff
                    clearChatUI();

                    const timestamp = formatTime();
                    conversationHistory.push({ role: 'command', content: "restarting server", timestamp: timestamp });
                    saveHistory();
                    createMessageElement('command', "restarting server..", timestamp);

                    return;
                } else if (cmd.startsWith("/stop")) {
                    return;
                }
                addMessage('announce', 'Error: ' + err.message);
            }
            inputField.focus();
        }

        async function pollAnnouncements() {
            try {
                const response = await fetch('/poll?id=' + lastAnnouncementId);
                if (!response.ok) throw new Error('Poll failed');
                const data = await response.json();
                if (data.messages) {
                    for (const msg of data.messages) {
                        addMessage('announce', msg.content);
                        lastAnnouncementId = msg.id;
                    }
                }
            } catch (err) {
                console.error('Poll error:', err);
            }
        }

        setInterval(pollAnnouncements, 500);

        async function send() {
            const message = inputField.value.trim();
            if (!message) return;
            if (message.startsWith('/')) {
                inputField.value = '';
                await sendCommand(message);
                return;
            }
            if (isStreaming) return;

            inputField.value = '';

            const timestamp = formatTime();
            addMessage('user', message);

            setInputState(true, true, true);
            isStreaming = true;

            currentController = new AbortController();

            const aiMsg = document.createElement('div');
            aiMsg.className = 'message ai hidden';
            chat.insertBefore(aiMsg, typing);
            currentAiMsg = aiMsg;

            let aiContent = '';
            let streamStarted = false;

            try {
                const response = await fetch('/stream', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: message}),
                    signal: currentController.signal
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.slice(6));
                                if (data.id) {
                                    currentStreamId = data.id;
                                }
                                if (data.cancelled) {
                                    aiMsg.innerHTML = '<span style="color:#f88;">[Cancelled]</span>';
                                    const ts = document.createElement('span');
                                    ts.className = 'timestamp';
                                    ts.textContent = formatTime();
                                    aiMsg.appendChild(ts);
                                    setInputState(false, false, false);
                                    isStreaming = false;
                                    currentAiMsg = null;
                                    currentStreamId = null;
                                    return;  // Exit early
                                }
                                if (data.token) {
                                    if (!streamStarted) {
                                        streamStarted = true;
                                        typing.classList.remove('show');
                                        aiMsg.classList.remove('hidden');
                                    }
                                    aiContent += data.token;
                                    aiMsg.innerHTML = renderMarkdown(aiContent);
                                    highlightCode(aiMsg);
                                    const ts = aiMsg.querySelector('.timestamp');
                                    if (!ts) {
                                        const tsEl = document.createElement('span');
                                        tsEl.className = 'timestamp';
                                        aiMsg.appendChild(tsEl);
                                    }
                                    chat.scrollTop = chat.scrollHeight;
                                }
                                if (data.done) {
                                    aiMsg.innerHTML = renderMarkdown(aiContent);
                                    highlightCode(aiMsg);
                                    const ts = document.createElement('span');
                                    ts.className = 'timestamp';
                                    ts.textContent = formatTime();
                                    aiMsg.appendChild(ts);
                                    conversationHistory.push({ role: 'ai', content: aiContent, timestamp: formatTime() });
                                    saveHistory();
                                }
                                if (data.error) {
                                    if (!streamStarted) {
                                        aiMsg.classList.remove('hidden');
                                    }
                                    aiMsg.innerHTML = '<span style="color:#f88;">[Error: ' + data.error + ']</span>';
                                    const ts = document.createElement('span');
                                    ts.className = 'timestamp';
                                    ts.textContent = formatTime();
                                    aiMsg.appendChild(ts);
                                }
                            } catch (e) { /* ignore parse errors */ }
                        }
                    }
                }
            } catch (err) {
                if (err.name === 'AbortError') {
                    // User stopped - already handled in stopGeneration()
                } else {
                    if (!streamStarted) {
                        aiMsg.classList.remove('hidden');
                    }
                    aiMsg.innerHTML = '<span style="color:#f88;">Error: ' + err.message + '</span>';
                    const ts = document.createElement('span');
                    ts.className = 'timestamp';
                    ts.textContent = formatTime();
                    aiMsg.appendChild(ts);
                }
            } finally {
                setInputState(false, false, false);
                isStreaming = false;
                currentController = null;
                if (!isAborted) {
                    currentAiMsg = null;
                }
                inputField.focus();
            }
        }

        async function handleFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;

            // Reset file input
            event.target.value = '';

            // Show uploading message
            const timestamp = formatTime();
            const uploadMsg = `[Uploading: ${file.name}]`;
            addMessage('announce', uploadMsg);

            try {
                // Read file as base64
                const reader = new FileReader();
                const base64 = await new Promise((resolve, reject) => {
                    reader.onload = () => resolve(reader.result.split(',')[1]);
                    reader.onerror = reject;
                    reader.readAsDataURL(file);
                });

                // Send to backend
                const response = await fetch('/upload', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        filename: file.name,
                        content: base64,
                        mimetype: file.type
                    })
                });

                const data = await response.json();

                if (data.success) {
                    const ts = formatTime();
                    conversationHistory.push({ role: 'user', content: `[Uploaded: ${file.name}]`, timestamp: ts });
                    saveHistory();
                    createMessageElement('user', `[Uploaded: ${file.name}]`, ts);

                    if (data.message) {
                        addMessage('announce', data.message);
                    }
                } else {
                    addMessage('announce', 'Error: ' + (data.error || 'Upload failed'));
                }
            } catch (err) {
                addMessage('announce', 'Error: ' + err.message);
            }

            inputField.focus();
        }

        loadHistory();

        // Register Service Worker for PWA
        if ('serviceWorker' in navigator) {
            window.addEventListener('load', () => {
                navigator.serviceWorker.register('/sw.js')
                    .then(reg => console.log('Service Worker registered'))
                    .catch(err => console.log('Service Worker registration failed:', err));
            });
        }
    </script>
</body>
</html>
'''

class Webui(core.channel.Channel):
    """
    A web-based channel for communicating with the AI through a browser interface.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.announcement_queue = []
        self.announcement_id = 0
        self.main_loop = None

    async def on_ready(self):
        asyncio.sleep(2)
        await self.announce("Server is up!")

    async def run(self):
        """
        Start the Flask web server to handle HTTP requests.
        """
        core.log("webui", "Starting WebUI")

        self.main_loop = asyncio.get_running_loop()

        global channel_instance
        channel_instance = self

        flask_thread = Thread(target=self._run_flask, daemon=True)
        flask_thread.start()

        host = core.config.get("webui_host", "127.0.0.1")
        port = core.config.get("webui_port", 5000)
        core.log("webui", f"WebUI started on {host}:{port}")

        while True:
            await asyncio.sleep(1)

    def _run_flask(self):
        """Run Flask in a separate thread."""
        import socket
        from werkzeug.serving import make_server

        host = core.config.get("webui_host", "127.0.0.1")
        port = core.config.get("webui_port", 5000)

        server = make_server(host, port, app, threaded=True)
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.serve_forever()

    async def announce(self, message: str):
        """
        Handle announcements from the framework and push to web UI.
        """
        core.log("webui channel", f"Announcement: {message}")
        self.announcement_id += 1
        self.announcement_queue.append({
            'id': self.announcement_id,
            'content': message.replace('\n', '<br>')
        })

channel_instance = None

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/poll')
def poll_announcements():
    """
    Return announcements newer than the given ID.
    """
    try:
        last_id = int(request.args.get('id', 0))
    except ValueError:
        last_id = 0

    messages = [msg for msg in channel_instance.announcement_queue if msg['id'] > last_id]
    return jsonify({'messages': messages})

# Add at the top with other globals
stream_cancellations = set()

@app.route('/cancel', methods=['POST'])
def cancel_stream():
    """Cancel an ongoing stream"""
    data = request.get_json()
    stream_id = data.get('id')
    if stream_id:
        stream_cancellations.add(stream_id)
    return jsonify({'success': True})

@app.route('/stream', methods=['POST'])
def stream_message():
    """Stream AI response token by token."""
    global channel_instance
    data = request.get_json()
    user_message = data.get('message', '')
    import uuid
    stream_id = str(uuid.uuid4())[:8]

    def generate():
        from queue import Queue
        token_queue = Queue()
        done = object()

        async def collect_tokens():
            try:
                async for token in channel_instance.send_stream("user", user_message):
                    if stream_id in stream_cancellations:
                        stream_cancellations.discard(stream_id)
                        token_queue.put(('cancelled', True))
                        break
                    token_queue.put(token)
            except Exception as e:
                token_queue.put(('error', str(e)))
            finally:
                token_queue.put(done)

        future = asyncio.run_coroutine_threadsafe(collect_tokens(), channel_instance.main_loop)

        yield f"data: {json.dumps({'id': stream_id})}\n\n"

        while True:
            item = token_queue.get()
            if item is done:
                yield f"data: {json.dumps({'done': True})}\n\n"
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
    global channel_instance
    data = request.get_json()
    user_message = data.get('message', '')

    future = asyncio.run_coroutine_threadsafe(
        channel_instance.send("user", user_message),
        channel_instance.main_loop
    )
    response = future.result()

    return jsonify({'response': response})

@app.route('/upload', methods=['POST'])
def upload_file():
    global channel_instance
    data = request.get_json()
    filename = data.get('filename', '')
    content_b64 = data.get('content', '')
    mimetype = data.get('mimetype', '')

    try:
        import base64
        content = base64.b64decode(content_b64).decode('utf-8', errors='replace')

        # You can customize what to do with the file content here
        # For example, send it to the AI as context
        result = f"File uploaded: {filename} ({len(content)} bytes)"

        channel_instance.manager.API.insert_turn("user", f"[File: {filename}]\n{content[:1000]}...")
        # Or process it through the channel
        # future = asyncio.run_coroutine_threadsafe(
        #     channel_instance.send("user", f"[File: {filename}]\n{content[:1000]}..."),
        #     channel_instance.main_loop
        # )
        # response = future.result()

        return jsonify({'success': True, 'message': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# == PWA Support ==
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "OptiClaw",
        "short_name": "OptiClaw",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#111111",
        "theme_color": "#111111",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    })

@app.route('/sw.js')
def service_worker():
    return '''
const CACHE_NAME = 'ai-chat-v1';
const urlsToCache = ['/', '/manifest.json'];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
    );
});

self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request).then(response => {
            return response || fetch(event.request);
        })
    );
});
''', 200, {'Content-Type': 'application/javascript'}

@app.route('/icon-192.png')
@app.route('/icon-512.png')
def icon():
    # Generate a simple SVG icon and return it as PNG would require a library.
    # Here we return a minimal valid placeholder (or you can serve a real file).
    # A 1x1 transparent pixel PNG:
    import base64
    # Transparent pixel
    # png_data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
    # Simple colored square (black) - 192x192
    # Using a minimal valid PNG generator is complex inline, so using a simple SVG approach for icons:
    # For PWA to work, you need actual files or inline data URIs.
    # This creates a simple black PNG placeholder.
    # Better to create actual files, but for a single-file solution:
    # We'll just serve the same placeholder for both.

    # Minimal black PNG (2x2)
    png_hex = "89504e470d0a1a0a0000000d494844520000000200000002080200000001f338dd0000000c4944415408d763f8ffffcf0001000100737a55b00000000049454e44ae426082"
    return bytes.fromhex(png_hex), 200, {'Content-Type': 'image/png'}
