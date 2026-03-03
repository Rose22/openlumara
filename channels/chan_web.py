"""
OptiClaw WebUI - A modern chat interface for AI interactions.

This module provides a Flask-based web interface with:
- Real-time streaming responses
- Multiple theme support (24 themes)
- PWA support for mobile installation
- Connection monitoring and auto-reconnection
- File upload capabilities
- Markdown rendering with syntax highlighting
"""

import asyncio
import json
import logging
import uuid
import base64
import socket
from flask import Flask, render_template_string, request, jsonify, Response, cli
from threading import Thread
from queue import Queue

import core

# ==============================================================================
# Flask Application Setup
# ==============================================================================

app = Flask(__name__)

# Disable Flask's default server banner and werkzeug logging for cleaner output
cli.show_server_banner = lambda *args: print(end="")
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
log.disabled = True

# Global reference to the channel instance (set during initialization)
channel_instance = None

# Set of stream IDs that have been cancelled
stream_cancellations = set()

# ==============================================================================
# HTML/CSS/JavaScript Template
# ==============================================================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#111111">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="OptiClaw">
    <link rel="manifest" href="/manifest.json">
    <link rel="apple-touch-icon" href="/icon-192.png">
    <title>OptiClaw</title>

    <!-- External dependencies -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.11.1/build/styles/github-dark.css">
    <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.11.1/build/highlight.min.js"></script>

    <style>
        /* ==========================================================================
           CSS Custom Properties (Theme Variables)
           ========================================================================== */
        :root {
            --bg-primary: #0a0a0a;
            --bg-secondary: #111111;
            --bg-tertiary: #1a1a1a;
            --bg-message-user: linear-gradient(135deg, #3a3a3a 0%, #2d2d2d 100%);
            --bg-message-ai: #1a1a1a;
            --bg-message-announce: linear-gradient(135deg, #2a2a2a 0%, #1f1f1f 100%);
            --bg-message-command: linear-gradient(135deg, #1a2a1a 0%, #0f1f0f 100%);
            --bg-input: #161616;
            --bg-code: #0a0a0a;
            --border-color: #2a2a2a;
            --border-message: #333333;
            --border-user: #444444;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0a0;
            --text-muted: #666666;
            --text-code: #d0d0d0;
            --accent: #4ade80;
            --accent-glow: rgba(74, 222, 128, 0.6);
            --error: #f08080;
            --error-bg: linear-gradient(135deg, #3a1a1a 0%, #2a0a0a 100%);
            --error-border: #5a2a2a;
            --important: #dada80;
            --important-bg: linear-gradient(135deg, #3a3a1a 0%, #2a2a0a 100%);
            --important-border: #5a5a2a;
            --info: #80b0d0;
            --info-bg: linear-gradient(135deg, #1a2a3a 0%, #0a1a2a 100%);
            --info-border: #2a4a6a;
            --button-bg: linear-gradient(135deg, #3a3a3a 0%, #2a2a2a 100%);
            --button-hover: linear-gradient(135deg, #444444 0%, #333333 100%);
            --button-stop: linear-gradient(135deg, #5a2a2a 0%, #3a1a1a 100%);
            --scrollbar: #2a2a2a;
            --scrollbar-hover: #3a3a3a;
            --shadow-soft: 0 2px 8px rgba(0, 0, 0, 0.3);
            --shadow-glow: 0 0 20px var(--accent-glow);
            --radius-sm: 4px;
            --radius-md: 8px;
            --radius-lg: 12px;
            --radius-xl: 16px;
            --radius-full: 24px;
        }

        /* ==========================================================================
           Base Styles & Reset
           ========================================================================== */
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        html, body {
            height: 100%;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 
                         Oxygen, Ubuntu, Cantarell, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }

        /* ==========================================================================
           App Container
           ========================================================================== */
        .app-container {
            display: flex;
            flex-direction: column;
            height: 100%;
            max-width: 900px;
            margin: 0 auto;
            background: var(--bg-secondary);
            box-shadow: 0 0 40px rgba(0, 0, 0, 0.8);
        }

        /* ==========================================================================
           Header
           ========================================================================== */
        header {
            padding: 16px 20px;
            background: linear-gradient(180deg, var(--bg-tertiary) 0%, var(--bg-primary) 100%);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        header h1 {
            font-size: 1.3rem;
            font-weight: 600;
            letter-spacing: -0.02em;
        }

        /* Status indicator dot */
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            transition: all 0.3s ease;
        }

        .status-dot.connected {
            background: #4ade80;
            box-shadow: 0 0 10px rgba(74, 222, 128, 0.6);
        }

        .status-dot.disconnected {
            background: #f87171;
            box-shadow: 0 0 10px rgba(248, 113, 113, 0.6);
        }

        .status-dot.connecting {
            background: #fbbf24;
            box-shadow: 0 0 10px rgba(251, 191, 36, 0.6);
            animation: pulse 1s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.9); }
        }

        .header-btn {
            padding: 8px 12px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            color: var(--text-secondary);
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .header-btn:hover {
            background: var(--bg-secondary);
            color: var(--text-primary);
            border-color: var(--accent);
        }

        .header-btn svg {
            width: 16px;
            height: 16px;
        }

        /* ==========================================================================
           Settings Modal
           ========================================================================== */
        .settings-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.7);
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.2s, visibility 0.2s;
            z-index: 1000;
            backdrop-filter: blur(4px);
        }

        .settings-overlay.show {
            opacity: 1;
            visibility: visible;
        }

        .settings-modal {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) scale(0.95);
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-lg);
            width: 90%;
            max-width: 500px;
            max-height: 80vh;
            overflow-y: auto;
            opacity: 0;
            visibility: hidden;
            transition: all 0.2s ease;
            z-index: 1001;
            box-shadow: var(--shadow-soft);
        }

        .settings-modal.show {
            opacity: 1;
            visibility: visible;
            transform: translate(-50%, -50%) scale(1);
        }

        .settings-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
        }

        .settings-header h2 {
            font-size: 1.2rem;
            color: var(--text-primary);
        }

        .settings-close {
            background: none;
            border: none;
            font-size: 1.5rem;
            color: var(--text-secondary);
            cursor: pointer;
            padding: 4px 8px;
            border-radius: var(--radius-sm);
            transition: all 0.2s;
            line-height: 1;
        }

        .settings-close:hover {
            background: var(--bg-tertiary);
            color: var(--text-primary);
        }

        .settings-content {
            padding: 16px 20px;
        }

        .settings-content h3 {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .theme-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
            gap: 8px;
        }

        .theme-btn {
            padding: 10px 6px;
            border: 2px solid var(--border-color);
            border-radius: var(--radius-md);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: center;
        }

        .theme-btn:hover {
            border-color: var(--accent);
            transform: translateY(-2px);
        }

        .theme-btn.active {
            border-color: var(--accent);
            box-shadow: 0 0 10px var(--accent-glow);
        }

        .theme-preview {
            width: 100%;
            height: 24px;
            border-radius: var(--radius-sm);
            margin-bottom: 6px;
        }

        /* ==========================================================================
           Chat Container & Messages
           ========================================================================== */
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: var(--bg-primary);
        }

        .message {
            max-width: 85%;
            padding: 12px 16px;
            border-radius: var(--radius-xl);
            line-height: 1.6;
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

        /* User messages */
        .message.user {
            align-self: flex-end;
            background: var(--bg-message-user);
            border: 1px solid var(--border-user);
            border-bottom-right-radius: var(--radius-sm);
        }

        /* AI messages */
        .message.ai {
            align-self: flex-start;
            background: var(--bg-message-ai);
            border: 1px solid var(--border-message);
            border-bottom-left-radius: var(--radius-sm);
        }

        /* System announcements */
        .message.announce {
            align-self: center;
            background: var(--bg-message-announce);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-style: italic;
            text-align: center;
            font-size: 0.9rem;
            max-width: 90%;
        }

        .message.announce.important {
            background: var(--important-bg);
            border-color: var(--important-border);
            color: var(--important);
            font-style: normal;
            font-weight: 500;
        }

        .message.announce.error {
            background: var(--error-bg);
            border-color: var(--error-border);
            color: var(--error);
            font-style: normal;
            font-weight: 500;
        }

        .message.announce.info {
            background: var(--info-bg);
            border-color: var(--info-border);
            color: var(--info);
            font-style: normal;
        }

        /* Command messages */
        .message.command {
            align-self: flex-start;
            background: var(--bg-message-command);
            border: 1px solid #2a4a2a;
            font-family: 'Consolas', 'Monaco', 'Menlo', monospace;
            font-size: 0.9rem;
            border-bottom-left-radius: var(--radius-sm);
            max-width: 85%;
        }

        /* Timestamp */
        .message .timestamp {
            display: block;
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-top: 6px;
            opacity: 0.8;
        }

        .message.user .timestamp { text-align: right; }
        .message.ai .timestamp { text-align: left; }
        .message.announce .timestamp { text-align: center; }

        /* Code blocks */
        .message pre {
            background: var(--bg-code);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            padding: 12px;
            overflow-x: auto;
            margin: 8px 0;
            position: relative;
        }

        .message code {
            font-family: 'Consolas', 'Monaco', 'Menlo', monospace;
            font-size: 0.9em;
        }

        .message pre code {
            background: transparent;
            padding: 0;
        }

        .message :not(pre) > code {
            background: var(--bg-tertiary);
            padding: 2px 6px;
            border-radius: var(--radius-sm);
        }

        .copy-btn {
            position: absolute;
            top: 8px;
            right: 8px;
            padding: 4px 8px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-sm);
            color: var(--text-secondary);
            font-size: 0.75rem;
            cursor: pointer;
            opacity: 0;
            transition: all 0.2s;
        }

        .message pre:hover .copy-btn { opacity: 1; }
        .copy-btn:hover { 
            background: var(--bg-secondary); 
            color: var(--text-primary); 
        }
        .copy-btn.copied {
            color: var(--accent);
            border-color: var(--accent);
        }

        /* Markdown elements */
        .message h1, .message h2, .message h3 { margin: 12px 0 8px; }
        .message h1 { font-size: 1.4em; }
        .message h2 { font-size: 1.2em; }
        .message h3 { font-size: 1.1em; }

        .message ul, .message ol {
            margin: 8px 0;
            padding-left: 24px;
        }

        .message li { margin: 4px 0; }

        .message blockquote {
            border-left: 3px solid var(--accent);
            margin: 8px 0;
            padding-left: 12px;
            color: var(--text-secondary);
        }

        .message a {
            color: var(--accent);
            text-decoration: none;
        }

        .message a:hover { text-decoration: underline; }

        .message table {
            border-collapse: collapse;
            margin: 8px 0;
        }

        .message th, .message td {
            border: 1px solid var(--border-message);
            padding: 8px 12px;
        }

        .message th {
            background: var(--bg-tertiary);
        }

        .message hr {
            border: none;
            border-top: 1px solid var(--border-color);
            margin: 12px 0;
        }

        /* Typing indicator */
        .typing-indicator {
            display: none;
            align-self: flex-start;
            padding: 12px 16px;
            background: var(--bg-message-ai);
            border: 1px solid var(--border-message);
            border-radius: var(--radius-xl);
            border-bottom-left-radius: var(--radius-sm);
        }

        .typing-indicator.show {
            display: flex;
            gap: 4px;
            align-items: center;
        }

        .typing-indicator span {
            width: 8px;
            height: 8px;
            background: var(--text-muted);
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out;
        }

        .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
        .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0.8); }
            40% { transform: scale(1.2); }
        }

        /* ==========================================================================
           Input Area
           ========================================================================== */
        .input-area {
            padding: 16px;
            background: var(--bg-primary);
            border-top: 1px solid var(--border-color);
            display: flex;
            gap: 12px;
            align-items: flex-end;
            flex-shrink: 0;
        }

        #upload {
            padding: 14px 16px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-full);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        #upload:hover {
            background: var(--bg-secondary);
            color: var(--accent);
            border-color: var(--accent);
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
            padding: 12px 18px;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-full);
            background: var(--bg-input);
            color: var(--text-primary);
            font-size: 1rem;
            outline: none;
            transition: all 0.2s;
            resize: none;
            min-height: 48px;
            max-height: 200px;
            overflow: hidden;
            font-family: inherit;
            line-height: 1.4;
        }

        #message:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        #message::placeholder { 
            color: var(--text-muted); 
        }

        #message:disabled { 
            opacity: 0.5; 
            cursor: not-allowed; 
        }

        #send, #stop {
            padding: 14px 24px;
            border-radius: var(--radius-full);
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            flex-shrink: 0;
        }

        #send {
            background: var(--button-bg);
            border: 1px solid var(--accent);
            color: var(--text-primary);
        }

        #send.hidden { display: none; }

        #send:hover {
            background: var(--button-hover);
            box-shadow: var(--shadow-glow);
        }

        #send:active { transform: scale(0.96); }
        #send:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

        #stop {
            background: var(--error-bg);
            border: 1px solid var(--error-border);
            color: var(--error);
            display: none;
        }

        #stop:hover {
            background: linear-gradient(135deg, #5a2a2a 0%, #4a1a1a 100%);
            box-shadow: 0 0 15px rgba(248, 113, 113, 0.3);
        }

        #stop:active { transform: scale(0.96); }
        #stop.show { display: block; }

        /* Scrollbar styling */
        .chat-container::-webkit-scrollbar { width: 6px; }
        .chat-container::-webkit-scrollbar-track { background: var(--bg-primary); }
        .chat-container::-webkit-scrollbar-thumb { 
            background: var(--scrollbar); 
            border-radius: 3px; 
        }
        .chat-container::-webkit-scrollbar-thumb:hover { 
            background: var(--scrollbar-hover); 
        }

        /* ==========================================================================
           Responsive Styles
           ========================================================================== */
        @media (max-width: 600px) {
            header { padding: 12px 16px; }
            header h1 { font-size: 1.1rem; }
            .header-btn { padding: 6px 10px; font-size: 0.8rem; }
            .chat-container { padding: 12px; }
            .message { max-width: 90%; padding: 10px 14px; }
            .input-area { padding: 12px; gap: 8px; }
            #upload { padding: 12px; }
            #message { padding: 12px 16px; }
            #send, #stop { padding: 12px 18px; }
            .message pre { padding: 10px; font-size: 0.85rem; }
            .copy-btn { opacity: 1; padding: 6px 10px; }
        }

        @media (max-width: 400px) {
            .header-left { gap: 8px; }
            .status-dot { width: 8px; height: 8px; }
            .message { padding: 8px 12px; font-size: 0.95rem; }
            #send, #stop { padding: 12px 14px; font-size: 0.9rem; }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <!-- Header -->
        <header>
            <div class="header-left">
                <div class="status-dot" id="status"></div>
                <h1>AI Chat</h1>
            </div>
            <div class="header-right">
                <button class="header-btn" id="settings-btn" onclick="toggleSettings()" title="Settings">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="3"></circle>
                        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                    </svg>
                </button>
                <button class="header-btn" onclick="clearChat()" title="Clear chat history">
                    Clear
                </button>
            </div>
        </header>

        <!-- Settings Modal -->
        <div class="settings-overlay" id="settings-overlay" onclick="closeSettings(event)"></div>
        <div class="settings-modal" id="settings-modal">
            <div class="settings-header">
                <h2>Settings</h2>
                <button class="settings-close" onclick="toggleSettings()">×</button>
            </div>
            <div class="settings-content">
                <h3>Theme</h3>
                <div class="theme-grid" id="theme-grid"></div>
            </div>
        </div>

        <!-- Chat Container -->
        <div class="chat-container" id="chat">
            <div class="typing-indicator" id="typing">
                <span></span><span></span><span></span>
            </div>
        </div>

        <!-- Input Area -->
        <div class="input-area">
            <button id="upload" onclick="document.getElementById('file-input').click()" title="Upload file">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
                </svg>
            </button>
            <input type="file" id="file-input" onchange="handleFileUpload(event)">
            <textarea id="message" placeholder="Type a message..." onkeydown="handleKeyDown(event)" rows="1"></textarea>
            <button id="send" onclick="send()">Send</button>
            <button id="stop" onclick="stopGeneration()">Stop</button>
        </div>
    </div>

    <script>
    // =============================================================================
    // State Management
    // =============================================================================

    // Connection state
    let isConnected = false;
    let reconnectAttempts = 0;
    let reconnectTimer = null;
    let hasShownReconnecting = false;
    let reconnectingMsgEl = null;

    // Message state
    let lastAnnouncementId = 0;
    let isStreaming = false;
    let currentAiMsg = null;
    let currentController = null;
    let currentStreamId = null;
    let conversationHistory = [];

    // DOM references
    const chat = document.getElementById('chat');
    const typing = document.getElementById('typing');
    const inputField = document.getElementById('message');
    const sendBtn = document.getElementById('send');
    const stopBtn = document.getElementById('stop');
    const statusDot = document.getElementById('status');

    // =============================================================================
    // Configuration
    // =============================================================================

    const CONFIG = {
        RECONNECT_BASE_DELAY: 1000,
        RECONNECT_MAX_DELAY: 30000,
        RECONNECT_DELAY_FACTOR: 1.5,
        CONNECTION_TIMEOUT: 3000,
        POLL_INTERVAL: 500,
        POLL_TIMEOUT: 5000
    };

    // =============================================================================
    // Markdown Rendering
    // =============================================================================

    marked.setOptions({
        breaks: true,
        gfm: true
    });

    function renderMarkdown(text) {
        return marked.parse(text);
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
                        btn.classList.add('copied');
                        setTimeout(() => {
                            btn.textContent = 'Copy';
                            btn.classList.remove('copied');
                        }, 1500);
                    });
                };
                pre.style.position = 'relative';
                pre.appendChild(btn);
            }
        });
    }

    // =============================================================================
    // History Management
    // =============================================================================

    function saveHistory() {
        localStorage.setItem('chatHistory', JSON.stringify(conversationHistory));
    }

    function loadHistory() {
        const saved = localStorage.getItem('chatHistory');
        if (saved) {
            try {
                conversationHistory = JSON.parse(saved);
                conversationHistory.forEach(msg => {
                    createMessageElement(msg.role, msg.content, msg.timestamp);
                });
            } catch (e) {
                console.error('Failed to load history:', e);
                conversationHistory = [];
            }
        }
    }

    function clearChatUI() {
        conversationHistory = [];
        saveHistory();
        const messages = chat.querySelectorAll('.message');
        messages.forEach(msg => msg.remove());
        currentAiMsg = null;
    }

    // =============================================================================
    // Utility Functions
    // =============================================================================

    function formatTime(date) {
        if (date) return date;
        return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            chat.scrollTop = chat.scrollHeight;
        });
    }

    function scrollToBottomDelayed() {
        setTimeout(() => {
            requestAnimationFrame(() => {
                chat.scrollTop = chat.scrollHeight;
            });
        }, 10);
    }

    function autoResize(textarea) {
        if (!textarea.value) {
            textarea.style.height = '48px';
        } else {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
        }
    }

    function clearInput() {
        inputField.value = '';
        autoResize(inputField);
    }

    // =============================================================================
    // Connection Management
    // =============================================================================

    function updateConnectionStatus(status) {
        statusDot.className = 'status-dot ' + status;

        if (status === 'disconnected') {
            sendBtn.disabled = true;
        } else if (status === 'connected') {
            sendBtn.disabled = false;
            reconnectAttempts = 0;
        }
    }

    function removeReconnectingMessage() {
        if (reconnectingMsgEl) {
            reconnectingMsgEl.remove();
            reconnectingMsgEl = null;
        }
        hasShownReconnecting = false;
    }

    async function checkConnection() {
        try {
            const response = await fetch('/poll?id=' + lastAnnouncementId, {
                method: 'GET',
                signal: AbortSignal.timeout(CONFIG.CONNECTION_TIMEOUT)
            });

            if (response.ok) {
                const wasReconnecting = hasShownReconnecting && !isConnected;

                if (!isConnected) {
                    isConnected = true;
                    updateConnectionStatus('connected');
                    removeReconnectingMessage();

                    if (wasReconnecting || reconnectAttempts > 0) {
                        addAnnouncement('Reconnected to server', 'info');
                    }
                }
            } else {
                throw new Error('Server error');
            }
        } catch (err) {
            handleConnectionError();
        }
    }

    function handleConnectionError() {
        const wasConnected = isConnected;

        if (isConnected) {
            isConnected = false;
            updateConnectionStatus('disconnected');
            removeReconnectingMessage();
            addAnnouncement('Disconnected from server. Reconnecting...', 'info');
        }

        scheduleReconnect();
    }

    function scheduleReconnect() {
        if (reconnectTimer) clearTimeout(reconnectTimer);

        reconnectAttempts++;
        const delay = Math.min(
            CONFIG.RECONNECT_BASE_DELAY * Math.pow(CONFIG.RECONNECT_DELAY_FACTOR, Math.min(reconnectAttempts, 10)),
            CONFIG.RECONNECT_MAX_DELAY
        );

        updateConnectionStatus('connecting');

        if (!hasShownReconnecting) {
            hasShownReconnecting = true;
            reconnectingMsgEl = addAnnouncement('Reconnecting...', 'info');
            if (reconnectingMsgEl) {
                reconnectingMsgEl.classList.add('reconnecting');
            }
        }

        reconnectTimer = setTimeout(async () => {
            await checkConnection();
            if (!isConnected) {
                scheduleReconnect();
            }
        }, delay);
    }

    // =============================================================================
    // Message Creation
    // =============================================================================

    function createMessageElement(role, content, timestamp) {
        const div = document.createElement('div');
        div.className = 'message ' + role;
        const timeStr = timestamp || formatTime();

        if (role === 'ai' || role === 'user') {
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
        scrollToBottomDelayed();
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
        scrollToBottom();
    }

    function addAnnouncement(content, type = null) {
        const div = document.createElement('div');
        div.className = 'message announce';
        if (type) div.classList.add(type);

        const timeStr = formatTime();
        div.innerHTML = content + '<span class="timestamp">' + timeStr + '</span>';

        if (isStreaming && currentAiMsg) {
            chat.insertBefore(div, currentAiMsg);
        } else {
            chat.insertBefore(div, typing);
        }
        scrollToBottom();
        return div;
    }

    // =============================================================================
    // Input Handling
    // =============================================================================

    function setInputState(disabled, showTyping = false, showStop = false) {
        inputField.disabled = false;
        sendBtn.disabled = disabled;
        statusDot.classList.toggle('inactive', disabled);

        typing.classList.toggle('show', showTyping);
        sendBtn.classList.toggle('hidden', showStop);
        stopBtn.classList.toggle('show', showStop);
    }

    function handleKeyDown(event) {
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

        if (!isMobile && event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            send();
        }
    }

    // Auto-resize input on input event
    document.getElementById('message').addEventListener('input', function() {
        autoResize(this);
    });

    // =============================================================================
    // Command Handling
    // =============================================================================

    async function sendCommand(cmd) {
        if (isStreaming) {
            await stopGeneration();
        }

        if (cmd.startsWith("/new")) {
            clearChatUI();
        }
        if (cmd.startsWith("/stop")) {
            await stopGeneration();
            return;
        }

        const timestamp = formatTime();
        conversationHistory.push({ role: 'user', content: cmd, timestamp: timestamp });
        saveHistory();
        createMessageElement('user', cmd, timestamp);

        try {
            const response = await fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: cmd })
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
                clearChatUI();
                const timestamp = formatTime();
                conversationHistory.push({ role: 'command', content: "restarting server", timestamp: timestamp });
                saveHistory();
                createMessageElement('command', "restarting server..", timestamp);
                return;
            }
            addMessage('announce', 'Error: ' + err.message);
        }
        inputField.focus();
    }

    // =============================================================================
    // Main Send Function
    // =============================================================================

    async function send() {
        if (!isConnected) {
            addAnnouncement('Cannot send message - not connected to server', 'error');
            return;
        }

        const message = inputField.value.trim();
        if (!message) return;

        if (message.startsWith('/')) {
            clearInput();
            await sendCommand(message);
            return;
        }
        if (isStreaming) return;

        clearInput();
        const timestamp = formatTime();
        addMessage('user', message);

        setInputState(true, true, true);
        isStreaming = true;
        currentController = new AbortController();

        // Create AI message container
        const aiMsg = document.createElement('div');
        aiMsg.className = 'message ai hidden';
        chat.insertBefore(aiMsg, typing);
        currentAiMsg = aiMsg;

        let aiContent = '';
        let streamStarted = false;

        try {
            const response = await fetch('/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message }),
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
                                aiMsg.classList.remove('hidden');
                                aiMsg.innerHTML = '<span style="color:#f88;">[Cancelled]</span>';
                                const ts = document.createElement('span');
                                ts.className = 'timestamp';
                                ts.textContent = formatTime();
                                aiMsg.appendChild(ts);
                                finishStream();
                                return;
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
                                scrollToBottomDelayed();
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
                        } catch (e) {
                            // Ignore parse errors
                        }
                    }
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
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
            finishStream();
        }
    }

    function finishStream() {
        setInputState(false, false, false);
        isStreaming = false;
        currentController = null;
        currentAiMsg = null;
        currentStreamId = null;
        inputField.focus();
    }

    async function stopGeneration() {
        // Stop the frontend stream
        if (currentController) {
            currentController.abort();
            currentController = null;
        }

        // Cancel the backend stream
        if (currentStreamId) {
            try {
                await fetch('/cancel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: currentStreamId })
                });
            } catch (e) {
                // Ignore cancellation errors
            }
            currentStreamId = null;
        }

        // Update UI
        if (currentAiMsg) {
            currentAiMsg.classList.remove('hidden');

            let existingContent = currentAiMsg.innerText || '';
            existingContent = existingContent.replace(/\\s*\\d{1,2}:\\d{2}\\s*(?:AM|PM)?\\s*$/i, '').trim();

            if (existingContent) {
                currentAiMsg.innerHTML = renderMarkdown(existingContent) + ' <span style="color:#f88;">[Stopped]</span>';
            } else {
                currentAiMsg.innerHTML = '<span style="color:#f88;">[Stopped]</span>';
            }

            const ts = document.createElement('span');
            ts.className = 'timestamp';
            ts.textContent = formatTime();
            currentAiMsg.appendChild(ts);

            const finalContent = existingContent ? existingContent + ' [Stopped]' : '[Stopped]';
            conversationHistory.push({ role: 'ai', content: finalContent, timestamp: formatTime() });
            saveHistory();

            currentAiMsg = null;
        }

        // Send stop command to backend
        fetch('/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: '/stop' })
        }).catch(() => {});

        finishStream();
    }

    function clearChat() {
        clearChatUI();
        sendCommand('/new');
    }

    // =============================================================================
    // File Upload
    // =============================================================================

    async function handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        event.target.value = '';

        const timestamp = formatTime();
        const uploadMsg = '[Uploading: ' + file.name + ']';
        addMessage('announce', uploadMsg);

        try {
            const reader = new FileReader();
            const base64 = await new Promise((resolve, reject) => {
                reader.onload = () => resolve(reader.result.split(',')[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });

            const response = await fetch('/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: file.name,
                    content: base64,
                    mimetype: file.type
                })
            });

            const data = await response.json();

            if (data.success) {
                const ts = formatTime();
                conversationHistory.push({ role: 'user', content: '[Uploaded: ' + file.name + ']', timestamp: ts });
                saveHistory();
                createMessageElement('user', '[Uploaded: ' + file.name + ']', ts);

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

    // =============================================================================
    // Polling for Announcements
    // =============================================================================

    async function pollAnnouncements() {
        if (!isConnected) return;

        try {
            const response = await fetch('/poll?id=' + lastAnnouncementId, {
                signal: AbortSignal.timeout(CONFIG.POLL_TIMEOUT)
            });

            if (!response.ok) throw new Error('Poll failed');

            const data = await response.json();
            if (data.messages) {
                for (const msg of data.messages) {
                    addAnnouncement(msg.content, msg.type);
                    lastAnnouncementId = msg.id;
                }
            }
        } catch (err) {
            console.error('Poll error:', err);
            isConnected = false;
            updateConnectionStatus('disconnected');
            addAnnouncement('Disconnected from server. Reconnecting...', 'info');
            scheduleReconnect();
        }
    }

    // Poll for announcements periodically
    setInterval(() => {
        if (isConnected) pollAnnouncements();
    }, CONFIG.POLL_INTERVAL);

    // =============================================================================
    // Theme System
    // =============================================================================

    const themes = {
        'dark-black': {
            name: 'Black',
            mode: 'dark',
            vars: {
                '--bg-primary': '#0a0a0a',
                '--bg-secondary': '#111111',
                '--bg-tertiary': '#1a1a1a',
                '--bg-message-user': 'linear-gradient(135deg, #3a3a3a 0%, #2d2d2d 100%)',
                '--bg-message-ai': '#1a1a1a',
                '--bg-message-announce': 'linear-gradient(135deg, #2a2a2a 0%, #1f1f1f 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #1a2a1a 0%, #0f1f0f 100%)',
                '--bg-input': '#161616',
                '--bg-code': '#0a0a0a',
                '--border-color': '#2a2a2a',
                '--border-message': '#333333',
                '--border-user': '#444444',
                '--text-primary': '#e0e0e0',
                '--text-secondary': '#a0a0a0',
                '--text-muted': '#666666',
                '--text-code': '#d0d0d0',
                '--accent': '#555555',
                '--accent-glow': 'rgba(255, 255, 255, 0.3)',
                '--error': '#f08080',
                '--error-bg': 'linear-gradient(135deg, #3a1a1a 0%, #2a0a0a 100%)',
                '--error-border': '#5a2a2a',
                '--important': '#dada80',
                '--important-bg': 'linear-gradient(135deg, #3a3a1a 0%, #2a2a0a 100%)',
                '--important-border': '#5a5a2a',
                '--info': '#80b0d0',
                '--info-bg': 'linear-gradient(135deg, #1a2a3a 0%, #0a1a2a 100%)',
                '--info-border': '#2a4a6a',
                '--button-bg': 'linear-gradient(135deg, #2a2a2a 0%, #1a1a1a 100%)',
                '--button-hover': 'linear-gradient(135deg, #3a3a3a 0%, #2a2a2a 100%)',
                '--button-stop': 'linear-gradient(135deg, #5a2a2a 0%, #3a1a1a 100%)',
                '--scrollbar': '#2a2a2a',
                '--scrollbar-hover': '#3a3a3a'
            }
        },
        'dark-gray': {
            name: 'Gray',
            mode: 'dark',
            vars: {
                '--bg-primary': '#1a1a1a',
                '--bg-secondary': '#242424',
                '--bg-tertiary': '#2e2e2e',
                '--bg-message-user': 'linear-gradient(135deg, #404040 0%, #363636 100%)',
                '--bg-message-ai': '#2e2e2e',
                '--bg-message-announce': 'linear-gradient(135deg, #383838 0%, #2e2e2e 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #2e382e 0%, #243024 100%)',
                '--bg-input': '#2a2a2a',
                '--bg-code': '#1a1a1a',
                '--border-color': '#404040',
                '--border-message': '#484848',
                '--border-user': '#505050',
                '--text-primary': '#f0f0f0',
                '--text-secondary': '#b0b0b0',
                '--text-muted': '#808080',
                '--text-code': '#e0e0e0',
                '--accent': '#60a0f0',
                '--accent-glow': 'rgba(96, 160, 240, 0.4)',
                '--error': '#f08080',
                '--error-bg': 'linear-gradient(135deg, #3a1a1a 0%, #2a0a0a 100%)',
                '--error-border': '#5a2a2a',
                '--important': '#dada80',
                '--important-bg': 'linear-gradient(135deg, #3a3a1a 0%, #2a2a0a 100%)',
                '--important-border': '#5a5a2a',
                '--info': '#80b0d0',
                '--info-bg': 'linear-gradient(135deg, #1a2a3a 0%, #0a1a2a 100%)',
                '--info-border': '#2a4a6a',
                '--button-bg': 'linear-gradient(135deg, #404040 0%, #303030 100%)',
                '--button-hover': 'linear-gradient(135deg, #505050 0%, #404040 100%)',
                '--button-stop': 'linear-gradient(135deg, #5a2a2a 0%, #3a1a1a 100%)',
                '--scrollbar': '#404040',
                '--scrollbar-hover': '#505050'
            }
        },
        'dark-pink': {
            name: 'Pink',
            mode: 'dark',
            vars: {
                '--bg-primary': '#1a0a14',
                '--bg-secondary': '#24101c',
                '--bg-tertiary': '#2e1828',
                '--bg-message-user': 'linear-gradient(135deg, #482838 0%, #3a2030 100%)',
                '--bg-message-ai': '#2e1828',
                '--bg-message-announce': 'linear-gradient(135deg, #382030 0%, #2e1828 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #283028 0%, #202820 100%)',
                '--bg-input': '#201018',
                '--bg-code': '#1a0a14',
                '--border-color': '#482840',
                '--border-message': '#503048',
                '--border-user': '#583850',
                '--text-primary': '#f0d0e0',
                '--text-secondary': '#c090a8',
                '--text-muted': '#886878',
                '--text-code': '#e0b8d0',
                '--accent': '#f060a0',
                '--accent-glow': 'rgba(240, 96, 160, 0.4)',
                '--error': '#f08080',
                '--error-bg': 'linear-gradient(135deg, #3a1a1a 0%, #2a0a0a 100%)',
                '--error-border': '#5a2a2a',
                '--important': '#dada80',
                '--important-bg': 'linear-gradient(135deg, #3a3a1a 0%, #2a2a0a 100%)',
                '--important-border': '#5a5a2a',
                '--info': '#80b0d0',
                '--info-bg': 'linear-gradient(135deg, #1a2a3a 0%, #0a1a2a 100%)',
                '--info-border': '#2a4a6a',
                '--button-bg': 'linear-gradient(135deg, #482838 0%, #382030 100%)',
                '--button-hover': 'linear-gradient(135deg, #583848 0%, #482838 100%)',
                '--button-stop': 'linear-gradient(135deg, #5a2a2a 0%, #3a1a1a 100%)',
                '--scrollbar': '#482840',
                '--scrollbar-hover': '#583850'
            }
        },
        'dark-blue': {
            name: 'Blue',
            mode: 'dark',
            vars: {
                '--bg-primary': '#0a0e14',
                '--bg-secondary': '#101820',
                '--bg-tertiary': '#182430',
                '--bg-message-user': 'linear-gradient(135deg, #283850 0%, #203038 100%)',
                '--bg-message-ai': '#182430',
                '--bg-message-announce': 'linear-gradient(135deg, #203040 0%, #182430 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #183020 0%, #142818 100%)',
                '--bg-input': '#0c1218',
                '--bg-code': '#0a0e14',
                '--border-color': '#283850',
                '--border-message': '#304060',
                '--border-user': '#384868',
                '--text-primary': '#d0e0f0',
                '--text-secondary': '#90b0d0',
                '--text-muted': '#5878a0',
                '--text-code': '#b0d0f0',
                '--accent': '#4090e0',
                '--accent-glow': 'rgba(64, 144, 224, 0.4)',
                '--error': '#f08080',
                '--error-bg': 'linear-gradient(135deg, #3a1a1a 0%, #2a0a0a 100%)',
                '--error-border': '#5a2a2a',
                '--important': '#dada80',
                '--important-bg': 'linear-gradient(135deg, #3a3a1a 0%, #2a2a0a 100%)',
                '--important-border': '#5a5a2a',
                '--info': '#80b0d0',
                '--info-bg': 'linear-gradient(135deg, #1a2a3a 0%, #0a1a2a 100%)',
                '--info-border': '#2a4a6a',
                '--button-bg': 'linear-gradient(135deg, #283850 0%, #183038 100%)',
                '--button-hover': 'linear-gradient(135deg, #384860 0%, #283850 100%)',
                '--button-stop': 'linear-gradient(135deg, #5a2a2a 0%, #3a1a1a 100%)',
                '--scrollbar': '#283850',
                '--scrollbar-hover': '#384860'
            }
        },
        'dark-green': {
            name: 'Green',
            mode: 'dark',
            vars: {
                '--bg-primary': '#0a140e',
                '--bg-secondary': '#101c14',
                '--bg-tertiary': '#182820',
                '--bg-message-user': 'linear-gradient(135deg, #284038 0%, #1c3828 100%)',
                '--bg-message-ai': '#182820',
                '--bg-message-announce': 'linear-gradient(135deg, #204030 0%, #183020 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #283820 0%, #1c2818 100%)',
                '--bg-input': '#0c140e',
                '--bg-code': '#0a140e',
                '--border-color': '#284030',
                '--border-message': '#305038',
                '--border-user': '#385840',
                '--text-primary': '#c8e8d0',
                '--text-secondary': '#80c090',
                '--text-muted': '#487058',
                '--text-code': '#a8e0b8',
                '--accent': '#50c870',
                '--accent-glow': 'rgba(80, 200, 112, 0.4)',
                '--error': '#f08080',
                '--error-bg': 'linear-gradient(135deg, #3a1a1a 0%, #2a0a0a 100%)',
                '--error-border': '#5a2a2a',
                '--important': '#dada80',
                '--important-bg': 'linear-gradient(135deg, #3a3a1a 0%, #2a2a0a 100%)',
                '--important-border': '#5a5a2a',
                '--info': '#80b0d0',
                '--info-bg': 'linear-gradient(135deg, #1a2a3a 0%, #0a1a2a 100%)',
                '--info-border': '#2a4a6a',
                '--button-bg': 'linear-gradient(135deg, #284038 0%, #183828 100%)',
                '--button-hover': 'linear-gradient(135deg, #385048 0%, #284038 100%)',
                '--button-stop': 'linear-gradient(135deg, #5a2a2a 0%, #3a1a1a 100%)',
                '--scrollbar': '#284030',
                '--scrollbar-hover': '#385038'
            }
        },
        'dark-catpuccin': {
            name: 'Catpuccin',
            mode: 'dark',
            vars: {
                '--bg-primary': '#1e1e2e',
                '--bg-secondary': '#181825',
                '--bg-tertiary': '#313244',
                '--bg-message-user': 'linear-gradient(135deg, #45475a 0%, #3b3b4f 100%)',
                '--bg-message-ai': '#313244',
                '--bg-message-announce': 'linear-gradient(135deg, #3a3b4a 0%, #313244 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #2e3a2e 0%, #243024 100%)',
                '--bg-input': '#1e1e2e',
                '--bg-code': '#11111b',
                '--border-color': '#45475a',
                '--border-message': '#585b70',
                '--border-user': '#6c6f85',
                '--text-primary': '#cdd6f4',
                '--text-secondary': '#bac2de',
                '--text-muted': '#6c7086',
                '--text-code': '#a6adc8',
                '--accent': '#cba6f7',
                '--accent-glow': 'rgba(203, 166, 247, 0.4)',
                '--error': '#f38ba8',
                '--error-bg': 'linear-gradient(135deg, #453038 0%, #352028 100%)',
                '--error-border': '#6c4050',
                '--important': '#f9e2af',
                '--important-bg': 'linear-gradient(135deg, #454030 0%, #353520 100%)',
                '--important-border': '#6c6050',
                '--info': '#89dceb',
                '--info-bg': 'linear-gradient(135deg, #283545 0%, #182535 100%)',
                '--info-border': '#405068',
                '--button-bg': 'linear-gradient(135deg, #45475a 0%, #35374a 100%)',
                '--button-hover': 'linear-gradient(135deg, #585b70 0%, #45475a 100%)',
                '--button-stop': 'linear-gradient(135deg, #5a2a2a 0%, #3a1a1a 100%)',
                '--scrollbar': '#45475a',
                '--scrollbar-hover': '#585b70'
            }
        },
        'light-black': {
            name: 'Black',
            mode: 'light',
            vars: {
                '--bg-primary': '#ffffff',
                '--bg-secondary': '#f8f8f8',
                '--bg-tertiary': '#f0f0f0',
                '--bg-message-user': 'linear-gradient(135deg, #e8e8e8 0%, #e0e0e0 100%)',
                '--bg-message-ai': '#f5f5f5',
                '--bg-message-announce': 'linear-gradient(135deg, #f0f0f0 0%, #e8e8e8 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #e8f0e8 0%, #e0ebe0 100%)',
                '--bg-input': '#ffffff',
                '--bg-code': '#f8f8f8',
                '--border-color': '#d0d0d0',
                '--border-message': '#c8c8c8',
                '--border-user': '#b8b8b8',
                '--text-primary': '#1a1a1a',
                '--text-secondary': '#505050',
                '--text-muted': '#909090',
                '--text-code': '#303030',
                '--accent': '#000000',
                '--accent-glow': 'rgba(0, 0, 0, 0.2)',
                '--error': '#c04040',
                '--error-bg': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--error-border': '#d8a8a8',
                '--important': '#a08040',
                '--important-bg': 'linear-gradient(135deg, #f8f0d8 0%, #f0e8c8 100%)',
                '--important-border': '#d8c8a8',
                '--info': '#4080b0',
                '--info-bg': 'linear-gradient(135deg, #d8f0f8 0%, #c8e8f0 100%)',
                '--info-border': '#a8c8d8',
                '--button-bg': 'linear-gradient(135deg, #e8e8e8 0%, #d8d8d8 100%)',
                '--button-hover': 'linear-gradient(135deg, #d0d0d0 0%, #c0c0c0 100%)',
                '--button-stop': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--scrollbar': '#c0c0c0',
                '--scrollbar-hover': '#a0a0a0'
            }
        },
        'light-blue': {
            name: 'Blue',
            mode: 'light',
            vars: {
                '--bg-primary': '#f8faff',
                '--bg-secondary': '#f0f4fc',
                '--bg-tertiary': '#e8ecf8',
                '--bg-message-user': 'linear-gradient(135deg, #d8e4f8 0%, #d0dcf0 100%)',
                '--bg-message-ai': '#f0f4fc',
                '--bg-message-announce': 'linear-gradient(135deg, #e0e8f8 0%, #f0f4fc 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #e0f0e8 0%, #d8ecd8 100%)',
                '--bg-input': '#f8faff',
                '--bg-code': '#f0f4fc',
                '--border-color': '#b8c8e8',
                '--border-message': '#a8b8d8',
                '--border-user': '#98a8c8',
                '--text-primary': '#182030',
                '--text-secondary': '#384868',
                '--text-muted': '#7888a8',
                '--text-code': '#283858',
                '--accent': '#4080c0',
                '--accent-glow': 'rgba(64, 128, 192, 0.3)',
                '--error': '#c04040',
                '--error-bg': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--error-border': '#d8a8a8',
                '--important': '#a08040',
                '--important-bg': 'linear-gradient(135deg, #f8f0d8 0%, #f0e8c8 100%)',
                '--important-border': '#d8c8a8',
                '--info': '#4080b0',
                '--info-bg': 'linear-gradient(135deg, #d8f0f8 0%, #c8e8f0 100%)',
                '--info-border': '#a8c8d8',
                '--button-bg': 'linear-gradient(135deg, #d8e4f8 0%, #d0dcf0 100%)',
                '--button-hover': 'linear-gradient(135deg, #c8d8f0 0%, #c0d0e8 100%)',
                '--button-stop': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--scrollbar': '#b0c0e0',
                '--scrollbar-hover': '#90a0c0'
            }
        },
        'light-green': {
            name: 'Green',
            mode: 'light',
            vars: {
                '--bg-primary': '#f8fff8',
                '--bg-secondary': '#f0fcf0',
                '--bg-tertiary': '#e8f8e8',
                '--bg-message-user': 'linear-gradient(135deg, #d8f0d8 0%, #d0ecd0 100%)',
                '--bg-message-ai': '#f0fcf0',
                '--bg-message-announce': 'linear-gradient(135deg, #e0f8e0 0%, #f0fcf0 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #e8f0d8 0%, #e0ecd0 100%)',
                '--bg-input': '#f8fff8',
                '--bg-code': '#f0fcf0',
                '--border-color': '#a8d0a8',
                '--border-message': '#98c098',
                '--border-user': '#88b088',
                '--text-primary': '#182818',
                '--text-secondary': '#386838',
                '--text-muted': '#709870',
                '--text-code': '#285828',
                '--accent': '#40a060',
                '--accent-glow': 'rgba(64, 160, 96, 0.3)',
                '--error': '#c04040',
                '--error-bg': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--error-border': '#d8a8a8',
                '--important': '#a08040',
                '--important-bg': 'linear-gradient(135deg, #f8f0d8 0%, #f0e8c8 100%)',
                '--important-border': '#d8c8a8',
                '--info': '#4080b0',
                '--info-bg': 'linear-gradient(135deg, #d8f0f8 0%, #c8e8f0 100%)',
                '--info-border': '#a8c8d8',
                '--button-bg': 'linear-gradient(135deg, #d8f0d8 0%, #d0ecd0 100%)',
                '--button-hover': 'linear-gradient(135deg, #c8e8c8 0%, #c0e0c0 100%)',
                '--button-stop': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--scrollbar': '#a0d0a0',
                '--scrollbar-hover': '#80b080'
            }
        },
        'light-catpuccin': {
            name: 'Catpuccin',
            mode: 'light',
            vars: {
                '--bg-primary': '#eff1f5',
                '--bg-secondary': '#e6e9ef',
                '--bg-tertiary': '#dce0e8',
                '--bg-message-user': 'linear-gradient(135deg, #ccd0da 0%, #bcc0cc 100%)',
                '--bg-message-ai': '#e6e9ef',
                '--bg-message-announce': 'linear-gradient(135deg, #d0d4de 0%, #e6e9ef 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #d0e6d0 0%, #c8dcc8 100%)',
                '--bg-input': '#eff1f5',
                '--bg-code': '#e6e9ef',
                '--border-color': '#bcc0cc',
                '--border-message': '#acb0bc',
                '--border-user': '#9ca0ac',
                '--text-primary': '#4c4f69',
                '--text-secondary': '#5c5f72',
                '--text-muted': '#8c8fa1',
                '--text-code': '#5c5f72',
                '--accent': '#8839ef',
                '--accent-glow': 'rgba(136, 57, 239, 0.3)',
                '--error': '#d20f39',
                '--error-bg': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--error-border': '#d8a8a8',
                '--important': '#df8e1d',
                '--important-bg': 'linear-gradient(135deg, #f8f0d8 0%, #f0e8c8 100%)',
                '--important-border': '#d8c8a8',
                '--info': '#179299',
                '--info-bg': 'linear-gradient(135deg, #d8f0f8 0%, #c8e8f0 100%)',
                '--info-border': '#a8c8d8',
                '--button-bg': 'linear-gradient(135deg, #ccd0da 0%, #bcc0cc 100%)',
                '--button-hover': 'linear-gradient(135deg, #bcc0cc 0%, #acb0bc 100%)',
                '--button-stop': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--scrollbar': '#bcc0cc',
                '--scrollbar-hover': '#acb0bc'
            }
        }
    };

    let currentTheme = 'dark-black';

    function applyTheme(themeId) {
        const theme = themes[themeId];
        if (!theme) return;

        const root = document.documentElement;
        for (const [varName, value] of Object.entries(theme.vars)) {
            root.style.setProperty(varName, value);
        }

        currentTheme = themeId;
        localStorage.setItem('theme', themeId);
        updateThemeButtons();
    }

    function updateThemeButtons() {
        document.querySelectorAll('.theme-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.theme === currentTheme);
        });
    }

    function createThemeButtons() {
        const grid = document.getElementById('theme-grid');
        grid.innerHTML = '';

        const darkThemes = Object.entries(themes).filter(([id, t]) => t.mode === 'dark');
        const lightThemes = Object.entries(themes).filter(([id, t]) => t.mode === 'light');

        const createButtons = (themeList) => {
            themeList.forEach(([id, theme]) => {
                const btn = document.createElement('button');
                btn.className = 'theme-btn' + (id === currentTheme ? ' active' : '');
                btn.dataset.theme = id;

                const bgColor = theme.vars['--bg-primary'];
                const accentColor = theme.vars['--accent'];

                btn.innerHTML = `
                    <div class="theme-preview" style="background: linear-gradient(135deg, ${bgColor} 50%, ${accentColor} 50%);"></div>
                    ${theme.name}
                `;

                btn.onclick = () => applyTheme(id);
                grid.appendChild(btn);
            });
        };

        createButtons(darkThemes);
        createButtons(lightThemes);
    }

    function toggleSettings() {
        const overlay = document.getElementById('settings-overlay');
        const modal = document.getElementById('settings-modal');

        overlay.classList.toggle('show');
        modal.classList.toggle('show');
    }

    function closeSettings(event) {
        if (event.target.id === 'settings-overlay') {
            toggleSettings();
        }
    }

    function loadTheme() {
        const saved = localStorage.getItem('theme');
        if (saved && themes[saved]) {
            applyTheme(saved);
        } else {
            applyTheme('dark-black');
        }
        createThemeButtons();
    }

    // =============================================================================
    // Service Worker Registration (PWA)
    // =============================================================================

    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js')
                .then(reg => console.log('Service Worker registered'))
                .catch(err => console.log('Service Worker registration failed:', err));
        });
    }

    // =============================================================================
    // Initialization
    // =============================================================================

    // Set initial connection status
    updateConnectionStatus('connecting');

    // Check connection immediately
    setTimeout(() => {
        checkConnection().catch(err => {
            isConnected = false;
            updateConnectionStatus('disconnected');
            addAnnouncement('Disconnected from server. Reconnecting...', 'info');
            scheduleReconnect();
        });
    }, 100);

    // Load chat history and theme
    loadHistory();
    loadTheme();
    </script>
</body>
</html>
'''

# ==============================================================================
# WebUI Channel Class
# ==============================================================================

class Webui(core.channel.Channel):
    """
    A web-based channel for communicating with the AI through a browser interface.

    This channel provides:
    - Real-time streaming responses via Server-Sent Events
    - Connection monitoring with automatic reconnection
    - Theme customization with 24 built-in themes
    - File upload support
    - PWA support for mobile installation
    - Markdown rendering with syntax highlighting
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.announcement_queue = []
        self.announcement_id = 0
        self.main_loop = None

    async def on_ready(self):
        """Called when the channel is ready to receive messages."""
        await asyncio.sleep(2)
        await self.announce("Server is up!")

    async def run(self):
        """
        Start the Flask web server to handle HTTP requests.

        The server runs in a separate thread to avoid blocking
        the asyncio event loop.
        """
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

        # Keep the coroutine running
        while True:
            await asyncio.sleep(1)

    def _run_flask(self):
        """Run Flask in a separate thread with proper socket configuration."""
        from werkzeug.serving import make_server

        host = core.config.get("webui_host", "127.0.0.1")
        port = core.config.get("webui_port", 5000)

        server = make_server(host, port, app, threaded=True)
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.serve_forever()

    async def announce(self, message: str, type: str = None):
        """
        Handle announcements from the framework and push to web UI.

        Args:
            message: The announcement message to display
            type: Optional type (info, error, important)
        """
        core.log("webui channel", f"Announcement: {message}")
        self.announcement_id += 1
        self.announcement_queue.append({
            'id': self.announcement_id,
            'content': message.replace('\n', '<br>'),
            'type': type,
        })

# ==============================================================================
# Flask Routes
# ==============================================================================

@app.route('/')
def index():
    """Serve the main HTML page."""
    return render_template_string(HTML_TEMPLATE)

@app.route('/poll')
def poll_announcements():
    """
    Return announcements newer than the given ID.

    Query params:
        id: Last announcement ID received by client

    Returns:
        JSON object with list of new messages
    """
    try:
        last_id = int(request.args.get('id', 0))
    except ValueError:
        last_id = 0

    messages = [msg for msg in channel_instance.announcement_queue if msg['id'] > last_id]
    return jsonify({'messages': messages})

@app.route('/stream', methods=['POST'])
def stream_message():
    """
    Stream AI response token by token using Server-Sent Events.

    This endpoint:
    1. Receives user message
    2. Generates a unique stream ID
    3. Streams tokens from the AI
    4. Handles cancellation via stream_cancellations set

    Returns:
        SSE stream with JSON data for each token
    """
    global channel_instance

    data = request.get_json()
    user_message = data.get('message', '')
    stream_id = str(uuid.uuid4())[:8]

    def generate():
        token_queue = Queue()
        done = object()

        async def collect_tokens():
            """Collect tokens from the AI and put them in the queue."""
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

        # Run the async token collection in the main event loop
        future = asyncio.run_coroutine_threadsafe(collect_tokens(), channel_instance.main_loop)

        # Send stream ID first
        yield f"data: {json.dumps({'id': stream_id})}\n\n"

        # Stream tokens
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

        # Ensure the async task completes
        future.result()

    return Response(generate(), mimetype='text/event-stream')

@app.route('/send', methods=['POST'])
def send_message():
    """
    Send a message and wait for complete response.

    Used for commands that need immediate response.
    """
    global channel_instance

    data = request.get_json()
    user_message = data.get('message', '')

    future = asyncio.run_coroutine_threadsafe(
        channel_instance.send("user", user_message),
        channel_instance.main_loop
    )
    response = future.result()

    return jsonify({'response': response})

@app.route('/cancel', methods=['POST'])
def cancel_stream():
    """
    Cancel an ongoing stream.

    Sets the cancel flag on the API and adds the stream ID to cancellations.
    """
    global channel_instance

    data = request.get_json()
    stream_id = data.get('id')

    # Set the cancel flag on the API
    if channel_instance:
        channel_instance.manager.API.cancel_request = True

    if stream_id:
        stream_cancellations.add(stream_id)

    return jsonify({'success': True})

@app.route('/upload', methods=['POST'])
def upload_file():
    """
    Handle file upload.

    Receives base64-encoded file content and processes it.
    """
    global channel_instance

    data = request.get_json()
    filename = data.get('filename', '')
    content_b64 = data.get('content', '')
    mimetype = data.get('mimetype', '')

    try:
        content = base64.b64decode(content_b64).decode('utf-8', errors='replace')

        # Insert the file content into the conversation
        result = f"File uploaded: {filename} ({len(content)} bytes)"
        channel_instance.manager.API.insert_turn("user", f"[File: {filename}]\n{content[:1000]}...")

        return jsonify({'success': True, 'message': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==============================================================================
# PWA Support Routes
# ==============================================================================

@app.route('/manifest.json')
def manifest():
    """Serve the PWA manifest."""
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
    """Serve the service worker for offline support."""
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
    """Serve a placeholder icon for PWA."""
    # Minimal black PNG (2x2)
    png_hex = "89504e470d0a1a0a0000000d494844520000000200000002080200000001f338dd0000000c4944415408d763f8ffffcf0001000100737a55b00000000049454e44ae426082"
    return bytes.fromhex(png_hex), 200, {'Content-Type': 'image/png'}
