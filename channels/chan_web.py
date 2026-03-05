"""
OptiClaw WebUI - A modern chat interface for AI interactions.

This module provides a Flask-based web interface with:
- Real-time streaming responses
- Multiple theme support (12 themes)
- PWA support for mobile installation
- Connection monitoring and auto-reconnection
- File upload capabilities (button + drag & drop)
- Markdown rendering with syntax highlighting
- Message editing, deletion, search, and export
- Keyboard shortcuts and accessibility features
- Conversation history sidebar (desktop always visible, mobile swipe/button)
- Persistent conversation storage
"""

import asyncio
import json
import logging
import uuid
import base64
import socket
import secrets
import time
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, Response, cli
from threading import Thread
from queue import Queue

import core

# ==============================================================================
# Flask Application Setup
# ==============================================================================

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

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
# Security Headers
# ==============================================================================

@app.after_request
def add_security_headers(response):
    """Add security and cache-control headers to all responses."""
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

    # Prevent caching of the main page and service worker
    if request.path == '/' or request.path == '/sw.js':
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    return response

# ==============================================================================
# HTML/CSS/JavaScript Template
# ==============================================================================

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#111111">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="OptiClaw">
    <meta name="description" content="AI Chat Interface">
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
            --bg-sidebar: #0d0d0d;
            --border-color: #2a2a2a;
            --border-message: #333333;
            --border-user: #444444;
            --border-sidebar: #222222;
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
            --sidebar-width: 280px;
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
            width: 100%;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
                         Oxygen, Ubuntu, Cantarell, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
            overflow: hidden;
        }

        /* Skip link for accessibility */
        .skip-link {
            position: absolute;
            top: -40px;
            left: 0;
            padding: 8px 16px;
            background: var(--accent);
            color: var(--bg-primary);
            z-index: 2000;
            text-decoration: none;
            font-weight: 600;
            border-radius: 0 0 var(--radius-md) 0;
            transition: top 0.2s;
        }

        .skip-link:focus {
            top: 0;
        }

        /* ==========================================================================
           App Container
           ========================================================================== */
        .app-wrapper {
            display: flex;
            height: 100%;
            width: 100%;
        }

        /* ==========================================================================
           Sidebar
           ========================================================================== */
        .sidebar {
            width: var(--sidebar-width);
            min-width: var(--sidebar-width);
            height: 100%;
            background: var(--bg-sidebar);
            border-right: 1px solid var(--border-sidebar);
            display: flex;
            flex-direction: column;
            transition: transform 0.3s ease, opacity 0.3s ease;
            z-index: 100;
        }

        .sidebar.collapsed {
            transform: translateX(-100%);
            opacity: 0;
            pointer-events: none;
        }

        .sidebar-header {
            padding: 16px;
            border-bottom: 1px solid var(--border-sidebar);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .sidebar-title {
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .sidebar-content {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
        }

        .sidebar-footer {
            padding: 12px 16px;
            border-top: 1px solid var(--border-sidebar);
        }

        /* New conversation button */
        .new-conv-btn {
            width: 100%;
            padding: 12px 16px;
            background: var(--accent);
            border: none;
            border-radius: var(--radius-md);
            color: var(--bg-primary);
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        .new-conv-btn:hover {
            filter: brightness(1.1);
            transform: translateY(-1px);
        }

        .new-conv-btn svg {
            width: 18px;
            height: 18px;
        }

        /* Conversation list */
        .conv-list {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .conv-item {
            padding: 12px 14px;
            background: var(--bg-tertiary);
            border: 1px solid transparent;
            border-radius: var(--radius-md);
            cursor: pointer;
            transition: all 0.15s;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .conv-item:hover {
            background: var(--bg-secondary);
            border-color: var(--border-color);
        }

        .conv-item.active {
            background: var(--bg-secondary);
            border-color: var(--accent);
        }

        .conv-item-title {
            font-size: 0.9rem;
            color: var(--text-primary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .conv-item-meta {
            font-size: 0.75rem;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .conv-item-actions {
            display: flex;
            gap: 4px;
            opacity: 0;
            transition: opacity 0.2s;
        }

        .conv-item:hover .conv-item-actions {
            opacity: 1;
        }

        .conv-action-btn {
            padding: 4px 8px;
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-sm);
            color: var(--text-secondary);
            font-size: 0.7rem;
            cursor: pointer;
            transition: all 0.15s;
        }

        .conv-action-btn:hover {
            background: var(--bg-secondary);
            color: var(--text-primary);
            border-color: var(--accent);
        }

        .conv-action-btn.delete:hover {
            border-color: var(--error);
            color: var(--error);
        }

        /* Sidebar scrollbar */
        .sidebar-content::-webkit-scrollbar { width: 4px; }
        .sidebar-content::-webkit-scrollbar-track { background: transparent; }
        .sidebar-content::-webkit-scrollbar-thumb {
            background: var(--scrollbar);
            border-radius: 2px;
        }

        /* Mobile sidebar overlay */
        .sidebar-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
            z-index: 99;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.3s, visibility 0.3s;
        }

        .sidebar-overlay.show {
            opacity: 1;
            visibility: visible;
        }

        /* ==========================================================================
           Main Content Area
           ========================================================================== */
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            width: 100%;
            height: 100%;
            min-width: 0;
            min-height: 0;
        }

        .app-container {
            display: flex;
            flex-direction: column;
            width: 100%;
            height: 100%;
            max-width: 900px;
            margin: 0 auto;
            background: var(--bg-secondary);
            box-shadow: 0 0 40px rgba(0, 0, 0, 0.8);
            min-height: 0;
        }

        /* Drag and drop overlay */
        .drop-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.8);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 2000;
            pointer-events: none;
        }

        .drop-overlay.active {
            display: flex;
        }

        .drop-overlay-content {
            background: var(--bg-tertiary);
            border: 2px dashed var(--accent);
            border-radius: var(--radius-lg);
            padding: 40px 60px;
            text-align: center;
        }

        .drop-overlay-content svg {
            width: 48px;
            height: 48px;
            margin-bottom: 16px;
            color: var(--accent);
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

        /* Menu button for mobile */
        .menu-btn {
            display: none;
            padding: 8px;
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s;
        }

        .menu-btn:hover {
            background: var(--bg-tertiary);
            color: var(--text-primary);
        }

        .menu-btn svg {
            width: 20px;
            height: 20px;
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
           Search Bar
           ========================================================================== */
        .search-container {
            display: none;
            padding: 12px 16px;
            background: var(--bg-primary);
            border-bottom: 1px solid var(--border-color);
        }

        .search-container.active {
            display: flex;
            gap: 8px;
        }

        .search-input {
            flex: 1;
            padding: 10px 16px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-full);
            color: var(--text-primary);
            font-size: 0.9rem;
            outline: none;
        }

        .search-input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        .search-count {
            padding: 10px 16px;
            background: var(--bg-tertiary);
            border-radius: var(--radius-full);
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        /* ==========================================================================
           Modals (Settings, Export, etc.)
           ========================================================================== */
        .modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.7);
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.2s, visibility 0.2s;
            z-index: 1000;
            backdrop-filter: blur(4px);
        }

        .modal-overlay.show {
            opacity: 1;
            visibility: visible;
        }

        .modal {
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
            transition: opacity 0.2s, visibility 0.2s, transform 0.2s;
            z-index: 1001;
            box-shadow: var(--shadow-soft);
        }

        .modal.show {
            opacity: 1;
            visibility: visible;
            transform: translate(-50%, -50%) scale(1);
        }

        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-color);
        }

        .modal-header h2 {
            font-size: 1.2rem;
            color: var(--text-primary);
        }

        .modal-close {
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

        .modal-close:hover {
            background: var(--bg-tertiary);
            color: var(--text-primary);
        }

        .modal-content {
            padding: 16px 20px;
        }

        .modal-content h3 {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        /* Theme grid */
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

        /* Export options */
        .export-options {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .export-btn {
            padding: 12px 16px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            color: var(--text-primary);
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s;
            text-align: left;
        }

        .export-btn:hover {
            border-color: var(--accent);
            background: var(--bg-secondary);
        }

        .export-btn-title {
            font-weight: 600;
            margin-bottom: 4px;
        }

        .export-btn-desc {
            font-size: 0.8rem;
            color: var(--text-muted);
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
            gap: 16px;
            background: var(--bg-primary);
            min-height: 0;
        }

        /* Drag over state */
        .chat-container.drag-over {
            background: linear-gradient(var(--bg-primary), var(--bg-primary)) padding-box,
                        linear-gradient(90deg, var(--accent) 50%, transparent 50%) border-box;
            border: 2px dashed var(--accent);
        }

        /* Message wrapper - groups message bubble with actions */
        .message-wrapper {
            display: flex;
            flex-direction: column;
            gap: 6px;
            animation: slideIn 0.2s ease-out;
        }

        .message-wrapper.hidden {
            display: none;
        }

        .message-wrapper.user {
            align-items: flex-end;
        }

        .message-wrapper.ai {
            align-items: flex-start;
        }

        .message-wrapper.announce {
            align-items: center;
        }

        .message-wrapper.command {
            align-items: flex-start;
        }

        .message-wrapper.user_command {
            align-items: flex-end;
        }

        @keyframes slideIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message {
            max-width: 85%;
            padding: 12px 16px;
            border-radius: var(--radius-xl);
            word-wrap: break-word;
            position: relative;
        }

        .message.search-highlight {
            background: var(--important-bg) !important;
        }

        .message.search-highlight mark {
            background: var(--accent);
            color: var(--bg-primary);
            padding: 1px 4px;
            border-radius: 2px;
        }

        /* User messages */
        .message.user {
            background: var(--bg-message-user);
            border: 1px solid var(--border-user);
            border-bottom-right-radius: var(--radius-sm);
        }

        /* AI messages */
        .message.ai {
            background: var(--bg-message-ai);
            border: 1px solid var(--border-message);
            border-bottom-left-radius: var(--radius-sm);
        }

        /* System announcements */
        .message.announce {
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
            background: var(--bg-message-command);
            border: 1px solid #2a4a2a;
            font-family: 'Consolas', 'Monaco', 'Menlo', monospace;
            font-size: 0.8rem;
            border-bottom-left-radius: var(--radius-sm);
            max-width: 85%;
            white-space: pre-wrap;
        }
        .message.user_command {
            background: var(--bg-message-command);
            border: 1px solid #2a4a2a;
            font-family: 'Consolas', 'Monaco', 'Menlo', monospace;
            font-size: 0.9rem;
            border-bottom-right-radius: var(--radius-sm);
            white-space: pre-wrap;
        }

        /* Tool messages */
        .message.tool {
            display: none;
            padding: 0;
            margin: 0;
            position: absolute;
        }

        /* Message actions - now below the bubble */
        .message-actions {
            display: flex;
            gap: 4px;
            opacity: 0;
            transition: opacity 0.2s;
        }

        .message-wrapper:hover .message-actions {
            opacity: 1;
        }

        .message-action-btn {
            width: 32px;
            height: 32px;
            padding: 0;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-md);
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.15s;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .message-action-btn:hover {
            background: var(--bg-secondary);
            color: var(--text-primary);
            border-color: var(--accent);
        }

        .message-action-btn.delete:hover {
            border-color: var(--error);
            color: var(--error);
        }

        .message-action-btn svg {
            width: 16px;
            height: 16px;
        }

        /* Timestamp */
        .message .timestamp {
            display: block;
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-top: 0px;
            opacity: 0.8;
        }

        .message .timestamp-left { text-align: left; }
        .message .timestamp-right { text-align: right; }
        .message .timestamp-center { text-align: center; }

        .message .edit-indicator {
            font-size: 0.7rem;
            color: var(--text-muted);
            margin-left: 6px;
        }

        /* Backend index badge */
        .message .index-badge {
            font-size: 0.65rem;
            color: var(--text-muted);
            background: var(--bg-tertiary);
            padding: 1px 4px;
            border-radius: var(--radius-sm);
            margin-left: 6px;
            opacity: 0.6;
        }

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

        .message p {
            margin: 8px 0;
            min-height: 1em;
        }

        .message p:first-child {
            margin-top: 0;
        }

        .message p:last-child {
            margin-bottom: 0;
        }

        .message div {
            margin: 8px 0;
        }

        /* Preserve whitespace in all block elements */
        .message p,
        .message div,
        .message li,
        .message blockquote {
            white-space: pre-wrap;
        }

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

        /* Edit textarea */
        .edit-textarea {
            width: 100%;
            min-height: 60px;
            background: var(--bg-primary);
            border: 1px solid var(--accent);
            border-radius: var(--radius-md);
            padding: 8px;
            color: var(--text-primary);
            font-family: inherit;
            font-size: inherit;
            resize: vertical;
            outline: none;
        }

        .edit-actions {
            display: flex;
            gap: 8px;
            margin-top: 8px;
            justify-content: flex-end;
        }

        .edit-actions button {
            padding: 6px 12px;
            border-radius: var(--radius-sm);
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s;
        }

        .edit-save {
            background: var(--accent);
            border: none;
            color: var(--bg-primary);
        }

        .edit-cancel {
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
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
           Keyboard Shortcuts Modal
           ========================================================================== */
        .shortcuts-list {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .shortcut-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid var(--border-color);
        }

        .shortcut-item:last-child {
            border-bottom: none;
        }

        .shortcut-keys {
            display: flex;
            gap: 4px;
        }

        .shortcut-key {
            padding: 4px 8px;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-sm);
            font-family: monospace;
            font-size: 0.8rem;
        }

        .shortcut-desc {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        /* ==========================================================================
           Responsive Styles
           ========================================================================== */
        @media (min-width: 769px) {
            .sidebar {
                position: relative;
                transform: none;
            }

            .sidebar-overlay {
                display: none;
            }

            .menu-btn {
                display: none;
            }
        }

        @media (max-width: 768px) {
            .sidebar {
                position: fixed;
                left: 0;
                top: 0;
                height: 100%;
                transform: translateX(-100%);
                z-index: 1000;
            }

            .sidebar.open {
                transform: translateX(0);
            }

            .menu-btn {
                display: flex;
            }
        }

        @media (max-width: 600px) {
            header { padding: 12px 16px; }
            header h1 { font-size: 1.1rem; }
            .header-btn { padding: 6px 10px; font-size: 0.8rem; }
            .chat-container { padding: 12px; }
            .message { max-width: 90%; padding: 10px 14px; }
            .message-actions { opacity: 1; }
            .input-area { padding: 12px; gap: 8px; }
            #upload { padding: 12px; }
            #message { padding: 12px 16px; }
            #send, #stop { padding: 12px 18px; }
            .message pre { padding: 10px; font-size: 0.85rem; }
            .copy-btn { opacity: 1; padding: 6px 10px; }
            .shortcuts-btn { display: none; }
        }

        @media (max-width: 400px) {
            .header-left { gap: 8px; }
            .status-dot { width: 8px; height: 8px; }
            .message { padding: 8px 12px; font-size: 0.95rem; }
            #send, #stop { padding: 12px 14px; font-size: 0.9rem; }
        }

        /* Focus visible for accessibility */
        :focus-visible {
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }

        /* Screen reader only */
        .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        }
    </style>
</head>
<body>
    <a href="#message" class="skip-link">Skip to input</a>

    <div class="sidebar-overlay" id="sidebar-overlay" onclick="closeSidebar()"></div>

    <div class="app-wrapper">
        <!-- Sidebar -->
        <aside class="sidebar" id="sidebar">
            <div class="sidebar-header">
                <span class="sidebar-title">Conversations</span>
            </div>
            <div class="sidebar-content">
                <div class="conv-list" id="conv-list">
                    <!-- Conversations will be loaded here -->
                </div>
            </div>
            <div class="sidebar-footer">
                <button class="new-conv-btn" onclick="newConversation()">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
                    </svg>
                    New Conversation
                </button>
            </div>
        </aside>

        <!-- Main Content -->
        <div class="main-content">
            <div class="drop-overlay" id="drop-overlay" aria-hidden="true">
                <div class="drop-overlay-content">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
                    </svg>
                    <div style="font-size: 1.2rem; font-weight: 600;">Drop file to upload</div>
                </div>
            </div>

            <div class="app-container">
                <!-- Header -->
                <header>
                    <div class="header-left">
                        <button class="menu-btn" onclick="toggleSidebar()" title="Toggle sidebar">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
                            </svg>
                        </button>
                        <div class="status-dot" id="status" role="status" aria-label="Connection status"></div>
                        <h1>AI Chat</h1>
                    </div>
                    <div class="header-right">
                        <button class="header-btn" id="search-btn" onclick="toggleSearch()" title="Search messages (Ctrl+F)">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="11" cy="11" r="8"></circle>
                                <path d="m21 21-4.35-4.35"></path>
                            </svg>
                        </button>
                        <button class="header-btn" id="settings-btn" onclick="toggleModal('settings')" title="Settings (Ctrl+S)">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <circle cx="12" cy="12" r="3"></circle>
                                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
                            </svg>
                        </button>
                        <button class="header-btn" onclick="showExportModal()" title="Export chat">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                <polyline points="7,10 12,15 17,10"></polyline>
                                <line x1="12" y1="15" x2="12" y2="3"></line>
                            </svg>
                        </button>
                        <button class="header-btn shortcuts-btn" onclick="showShortcutsModal()" title="Keyboard shortcuts (?)">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <rect x="2" y="4" width="20" height="16" rx="2" ry="2"></rect>
                                <path d="M6 8h.001M10 8h.001M14 8h.001M18 8h.001M8 12h.001M12 12h.001M16 12h.001M6 16h12"></path>
                            </svg>
                        </button>
                        <button class="header-btn" onclick="clearChat()" title="Clear chat">Clear</button>
                    </div>
                </header>

                <!-- Search Bar -->
                <div class="search-container" id="search-container">
                    <input type="text" class="search-input" id="search-input" placeholder="Search messages..." oninput="performSearch(this.value)">
                    <div class="search-count" id="search-count">0 results</div>
                    <button class="header-btn" onclick="clearSearch()">✕</button>
                </div>

                <!-- Settings Modal -->
                <div class="modal-overlay" id="settings-overlay" onclick="closeModalOnOverlay(event, 'settings')"></div>
                <div class="modal" id="settings-modal" role="dialog" aria-labelledby="settings-title">
                    <div class="modal-header">
                        <h2 id="settings-title">Settings</h2>
                        <button class="modal-close" onclick="toggleModal('settings')" aria-label="Close settings">×</button>
                    </div>
                    <div class="modal-content">
                        <h3>Theme</h3>
                        <div class="theme-grid" id="theme-grid"></div>
                    </div>
                </div>

                <!-- Export Modal -->
                <div class="modal-overlay" id="export-overlay" onclick="closeModalOnOverlay(event, 'export')"></div>
                <div class="modal" id="export-modal" role="dialog" aria-labelledby="export-title">
                    <div class="modal-header">
                        <h2 id="export-title">Export Chat</h2>
                        <button class="modal-close" onclick="toggleModal('export')" aria-label="Close export">×</button>
                    </div>
                    <div class="modal-content">
                        <div class="export-options">
                            <button class="export-btn" onclick="exportChat('json')">
                                <div class="export-btn-title">JSON</div>
                                <div class="export-btn-desc">Full chat data with metadata</div>
                            </button>
                            <button class="export-btn" onclick="exportChat('markdown')">
                                <div class="export-btn-title">Markdown</div>
                                <div class="export-btn-desc">Formatted for reading and sharing</div>
                            </button>
                            <button class="export-btn" onclick="exportChat('txt')">
                                <div class="export-btn-title">Plain Text</div>
                                <div class="export-btn-desc">Simple text format</div>
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Shortcuts Modal -->
                <div class="modal-overlay" id="shortcuts-overlay" onclick="closeModalOnOverlay(event, 'shortcuts')"></div>
                <div class="modal" id="shortcuts-modal" role="dialog" aria-labelledby="shortcuts-title">
                    <div class="modal-header">
                        <h2 id="shortcuts-title">Keyboard Shortcuts</h2>
                        <button class="modal-close" onclick="toggleModal('shortcuts')" aria-label="Close shortcuts">×</button>
                    </div>
                    <div class="modal-content">
                        <div class="shortcuts-list">
                            <div class="shortcut-item">
                                <span class="shortcut-desc">Send message</span>
                                <div class="shortcut-keys">
                                    <span class="shortcut-key">Ctrl</span>
                                    <span class="shortcut-key">Enter</span>
                                </div>
                            </div>
                            <div class="shortcut-item">
                                <span class="shortcut-desc">New line</span>
                                <div class="shortcut-keys">
                                    <span class="shortcut-key">Shift</span>
                                    <span class="shortcut-key">Enter</span>
                                </div>
                            </div>
                            <div class="shortcut-item">
                                <span class="shortcut-desc">Clear chat</span>
                                <div class="shortcut-keys">
                                    <span class="shortcut-key">Ctrl</span>
                                    <span class="shortcut-key">L</span>
                                </div>
                            </div>
                            <div class="shortcut-item">
                                <span class="shortcut-desc">Settings</span>
                                <div class="shortcut-keys">
                                    <span class="shortcut-key">Ctrl</span>
                                    <span class="shortcut-key">S</span>
                                </div>
                            </div>
                            <div class="shortcut-item">
                                <span class="shortcut-desc">Search</span>
                                <div class="shortcut-keys">
                                    <span class="shortcut-key">Ctrl</span>
                                    <span class="shortcut-key">F</span>
                                </div>
                            </div>
                            <div class="shortcut-item">
                                <span class="shortcut-desc">Export</span>
                                <div class="shortcut-keys">
                                    <span class="shortcut-key">Ctrl</span>
                                    <span class="shortcut-key">E</span>
                                </div>
                            </div>
                            <div class="shortcut-item">
                                <span class="shortcut-desc">Stop generation</span>
                                <div class="shortcut-keys">
                                    <span class="shortcut-key">Escape</span>
                                </div>
                            </div>
                            <div class="shortcut-item">
                                <span class="shortcut-desc">Show shortcuts</span>
                                <div class="shortcut-keys">
                                    <span class="shortcut-key">Ctrl</span>
                                    <span class="shortcut-key">/</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Chat Container -->
                <div class="chat-container" id="chat" role="log" aria-live="polite" aria-label="Chat messages">
                    <div class="typing-indicator" id="typing" aria-label="AI is typing">
                        <span></span><span></span><span></span>
                    </div>
                </div>

                <!-- Input Area -->
                <div class="input-area">
                    <button id="upload" onclick="document.getElementById('file-input').click()" title="Upload file" aria-label="Upload file">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
                        </svg>
                    </button>
                    <input type="file" id="file-input" onchange="handleFileUpload(event)" aria-hidden="true">
                    <textarea id="message" placeholder="Type a message..." onkeydown="handleKeyDown(event)" rows="1" aria-label="Message input"></textarea>
                    <button id="send" onclick="send()" aria-label="Send message">Send</button>
                    <button id="stop" onclick="stopGeneration()" aria-label="Stop generation">Stop</button>
                </div>
            </div>
        </div>
    </div>

    <script>
    // =============================================================================
    // Icon Templates for Action Buttons
    // =============================================================================

    const ICONS = {
        copy:`<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`,
        edit:`<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>`,
        trash:`<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`,
        check:`<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`
    };

    // =============================================================================
    // State Management
    // =============================================================================

    // Connection state
    let isConnected = false;
    let reconnectAttempts = 0;
    let reconnectTimer = null;
    let hasShownReconnecting = false;
    let hasShownDisconnected = false;

    // Message state - displayMessages is the source of truth for the UI
    // It includes ALL messages: backend messages (with backendIndex), commands, and announcements
    let displayMessages = [];

    // Current conversation ID (null for new/unsaved conversations)
    let currentConversationId = null;

    // Stream state
    let lastAnnouncementId = 0;
    let isStreaming = false;
    let currentAiMsg = null;
    let currentController = null;
    let currentStreamId = null;
    let editingIndex = null;

    // Search state
    let searchQuery = '';
    let searchResults = [];
    let currentSearchIndex = -1;

    // DOM references
    const chat = document.getElementById('chat');
    const typing = document.getElementById('typing');
    const inputField = document.getElementById('message');
    const sendBtn = document.getElementById('send');
    const stopBtn = document.getElementById('stop');
    const statusDot = document.getElementById('status');
    const dropOverlay = document.getElementById('drop-overlay');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

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
                btn.setAttribute('aria-label', 'Copy code');
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
    // Sidebar Management
    // =============================================================================

    function toggleSidebar() {
        sidebar.classList.toggle('open');
        sidebarOverlay.classList.toggle('show');
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('show');
    }

    // Touch swipe handling for mobile sidebar
    let touchStartX = 0;
    let touchEndX = 0;

    document.addEventListener('touchstart', (e) => {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });

    document.addEventListener('touchend', (e) => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, { passive: true });

    function handleSwipe() {
        const swipeThreshold = 50;
        const diff = touchEndX - touchStartX;

        // Swipe right to open sidebar (only if starting from left edge)
        if (diff > swipeThreshold && touchStartX < 30) {
            sidebar.classList.add('open');
            sidebarOverlay.classList.add('show');
        }
        // Swipe left to close sidebar
        else if (diff < -swipeThreshold && sidebar.classList.contains('open')) {
            closeSidebar();
        }
    }

    // =============================================================================
    // Conversation Management
    // =============================================================================

    async function loadConversations() {
        try {
            const response = await fetch('/conversations');
            const data = await response.json();
            renderConversationList(data.conversations || []);
        } catch (e) {
            console.error('Failed to load conversations:', e);
        }
    }

    function renderConversationList(conversations) {
        const list = document.getElementById('conv-list');
        list.innerHTML = '';

        conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conv-item' + (conv.id === currentConversationId ? ' active' : '');
            item.onclick = () => loadConversation(conv.id);

            const title = document.createElement('div');
            title.className = 'conv-item-title';
            title.textContent = conv.title || 'New Conversation';

            const meta = document.createElement('div');
            meta.className = 'conv-item-meta';

            const date = document.createElement('span');
            date.textContent = formatDate(conv.updated || conv.created);

            const actions = document.createElement('div');
            actions.className = 'conv-item-actions';

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'conv-action-btn delete';
            deleteBtn.textContent = 'Delete';
            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                deleteConversation(conv.id);
            };

            actions.appendChild(deleteBtn);
            meta.appendChild(date);
            meta.appendChild(actions);

            item.appendChild(title);
            item.appendChild(meta);
            list.appendChild(item);
        });
    }

    function formatDate(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;

        if (diff < 60000) return 'Just now';
        if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
        if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
        if (diff < 604800000) return Math.floor(diff / 86400000) + 'd ago';

        return date.toLocaleDateString();
    }

    async function newConversation() {
        // Save current conversation first if it has messages
        if (displayMessages.length > 0) {
            await saveCurrentConversation();
        }

        // Clear the UI and reset state
        clearChatUI();
        currentConversationId = null;

        // Clear backend context
        try {
            await fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: '/new' })
            });
        } catch (e) {
            console.error('Failed to clear backend:', e);
        }

        // Refresh conversation list
        await loadConversations();
        closeSidebar();
    }

    async function loadConversation(convId) {
        if (isStreaming) {
            await stopGeneration();
        }

        try {
            const response = await fetch('/conversation/load?id=' + convId);
            const data = await response.json();

            if (data.success && data.conversation) {
                currentConversationId = convId;
                displayMessages = data.conversation.messages || [];
                renderAllMessages();
                await loadConversations();
                closeSidebar();
            }
        } catch (e) {
            console.error('Failed to load conversation:', e);
        }
    }

    async function saveCurrentConversation() {
        // Don't save empty conversations
        if (displayMessages.length === 0) return;

        try {
            const response = await fetch('/conversation/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: currentConversationId,
                    messages: displayMessages
                })
            });

            const data = await response.json();
            if (data.success) {
                currentConversationId = data.id;
                // Update sidebar to show new/updated conversation
                loadConversations();
            }
        } catch (e) {
            console.error('Failed to save conversation:', e);
        }
    }

    async function deleteConversation(convId) {
        if (!confirm('Delete this conversation?')) return;

        try {
            const response = await fetch('/conversation/delete?id=' + convId, { method: 'POST' });
            const data = await response.json();

            if (data.success) {
                if (currentConversationId === convId) {
                    currentConversationId = null;
                    clearChatUI();
                }
                await loadConversations();
            }
        } catch (e) {
            console.error('Failed to delete conversation:', e);
        }
    }

    // =============================================================================
    // Message Rendering - Display messages from displayMessages array
    // =============================================================================

    function renderAllMessages() {
        // Clear existing messages
        const wrappers = chat.querySelectorAll('.message-wrapper');
        wrappers.forEach(wrapper => wrapper.remove());

        // Render all messages from displayMessages
        displayMessages.forEach((msg, index) => {
            createMessageElement(msg, index);
        });

        scrollToBottom();
    }

    function createMessageElement(msg, index) {
        const role = msg.role;
        const content = msg.content || '';
        const timestamp = msg.timestamp || formatTime();
        const edited = msg.edited || false;
        const backendIndex = msg.backendIndex; // null for commands/announcements

        const wrapper = document.createElement('div');
        wrapper.className = 'message-wrapper ' + role;
        wrapper.setAttribute('role', 'article');
        wrapper.dataset.displayIndex = index;

        const msgDiv = document.createElement('div');
        msgDiv.className = 'message ' + role;

        if (role === 'ai' || role === 'user') {
            msgDiv.innerHTML = renderMarkdown(content);
            highlightCode(msgDiv);
        } else {
            msgDiv.innerHTML = content;
        }

        // Timestamp with optional edit indicator and backend index
        const ts = document.createElement('span');
        ts.className = 'timestamp';

        if (role === 'user') ts.classList.add('timestamp-right');
        else if (role === 'ai') ts.classList.add('timestamp-left');
        else ts.classList.add('timestamp-center');

        ts.textContent = timestamp;

        if (edited) {
            const editIndicator = document.createElement('span');
            editIndicator.className = 'edit-indicator';
            editIndicator.textContent = '(edited)';
            ts.appendChild(editIndicator);
        }

        // Show backend index for debugging (optional, can be hidden in production)
        if (backendIndex !== undefined && backendIndex !== null) {
            const indexBadge = document.createElement('span');
            indexBadge.className = 'index-badge';
            indexBadge.textContent = '#' + backendIndex;
            ts.appendChild(indexBadge);
        }

        msgDiv.appendChild(ts);
        wrapper.appendChild(msgDiv);

        // Add action buttons for editable messages (only those with backendIndex)
        if (role === 'user' || role === 'ai') {
            const actions = createActionButtons(role, index, content, backendIndex);
            wrapper.appendChild(actions);
        }

        chat.insertBefore(wrapper, typing);
        return wrapper;
    }

    function addMessage(msg) {
        displayMessages.push(msg);
        createMessageElement(msg, displayMessages.length - 1);
        scrollToBottom();
    }

    function addAnnouncement(content, type = null) {
        const msg = {
            role: 'announce',
            content: content,
            timestamp: formatTime(),
            type: type
        };
        addMessage(msg);
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

    function clearChatUI() {
        displayMessages = [];
        const wrappers = chat.querySelectorAll('.message-wrapper');
        wrappers.forEach(wrapper => wrapper.remove());
        currentAiMsg = null;
        editingIndex = null;
        clearSearch();
    }

    // =============================================================================
    // Connection Management
    // =============================================================================

    function updateConnectionStatus(status) {
        statusDot.className = 'status-dot ' + status;
        statusDot.setAttribute('aria-label', 'Connection status: ' + status);

        if (status === 'disconnected') {
            sendBtn.disabled = true;
        } else if (status === 'connected') {
            sendBtn.disabled = false;
            reconnectAttempts = 0;
        }
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

                    // Load conversations on first connect
                    if (currentConversationId === null && displayMessages.length === 0) {
                        // Load current backend messages as a starting point
                        await loadBackendMessages();
                        await loadConversations();
                    }

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

    async function loadBackendMessages() {
        try {
            const response = await fetch('/history');
            const data = await response.json();

            if (data.messages) {
                displayMessages = data.messages;
                renderAllMessages();
            }
        } catch (e) {
            console.error('Failed to load backend messages:', e);
        }
    }

    function handleConnectionError() {
        const wasConnected = isConnected;

        if (isConnected) {
            isConnected = false;
            updateConnectionStatus('disconnected');
            if (!hasShownDisconnected) {
                addAnnouncement('Disconnected from server.', 'info');
                hasShownDisconnected = true;
            }
        }

        scheduleReconnect();
    }

    function scheduleReconnect() {
        if (reconnectTimer) clearTimeout(reconnectTimer);

        reconnectAttempts++;
        const delay = 1000;
        updateConnectionStatus('connecting');

        if (!hasShownReconnecting) {
            hasShownReconnecting = true;
            addAnnouncement('Reconnecting...', 'info');
        }

        reconnectTimer = setTimeout(async () => {
            await checkConnection();
            if (!isConnected) {
                scheduleReconnect();
            }
        }, delay);
    }

    // =============================================================================
    // Message Action Buttons Helper
    // =============================================================================

    function createActionButtons(role, displayIndex, content, backendIndex) {
        const actions = document.createElement('div');
        actions.className = 'message-actions';

        // Copy button - always available
        const copyBtn = document.createElement('button');
        copyBtn.className = 'message-action-btn';
        copyBtn.innerHTML = ICONS.copy;
        copyBtn.setAttribute('aria-label', 'Copy message');
        copyBtn.setAttribute('title', 'Copy');
        copyBtn.onclick = () => {
            navigator.clipboard.writeText(content).then(() => {
                copyBtn.innerHTML = ICONS.check;
                copyBtn.classList.add('copied');
                setTimeout(() => {
                    copyBtn.innerHTML = ICONS.copy;
                    copyBtn.classList.remove('copied');
                }, 1500);
            });
        };
        actions.appendChild(copyBtn);

        // Edit button - only for user messages with backend index
        if (role === 'user' && backendIndex !== undefined && backendIndex !== null) {
            const editBtn = document.createElement('button');
            editBtn.className = 'message-action-btn';
            editBtn.innerHTML = ICONS.edit;
            editBtn.setAttribute('aria-label', 'Edit message');
            editBtn.setAttribute('title', 'Edit');
            editBtn.onclick = () => editMessage(displayIndex, backendIndex);
            actions.appendChild(editBtn);
        }

        // Delete button - only for messages with backend index
        if (backendIndex !== undefined && backendIndex !== null) {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'message-action-btn delete';
            deleteBtn.innerHTML = ICONS.trash;
            deleteBtn.setAttribute('aria-label', 'Delete message and all following');
            deleteBtn.setAttribute('title', 'Delete');
            deleteBtn.onclick = () => deleteMessage(displayIndex, backendIndex);
            actions.appendChild(deleteBtn);
        }

        return actions;
    }

    // =============================================================================
    // Message Editing & Deletion - Use backend index directly
    // =============================================================================

    function editMessage(displayIndex, backendIndex) {
        if (editingIndex !== null) {
            cancelEdit();
        }

        const msg = displayMessages[displayIndex];
        if (!msg) return;

        // Can only edit user messages
        if (msg.role !== 'user') {
            addAnnouncement('Can only edit your own messages', 'error');
            return;
        }

        editingIndex = displayIndex;

        const messageEl = chat.querySelector('[data-display-index="' + displayIndex + '"]');
        if (!messageEl) return;

        const originalContent = msg.content || '';

        const editContainer = document.createElement('div');
        editContainer.className = 'edit-container';

        const textarea = document.createElement('textarea');
        textarea.className = 'edit-textarea';
        textarea.value = originalContent;
        textarea.setAttribute('aria-label', 'Edit message');

        const actions = document.createElement('div');
        actions.className = 'edit-actions';

        const saveBtn = document.createElement('button');
        saveBtn.className = 'edit-save';
        saveBtn.textContent = 'Save';
        saveBtn.onclick = () => saveEdit(displayIndex, backendIndex, textarea.value);

        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'edit-cancel';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.onclick = cancelEdit;

        actions.appendChild(cancelBtn);
        actions.appendChild(saveBtn);

        editContainer.appendChild(textarea);
        editContainer.appendChild(actions);

        messageEl.innerHTML = '';
        messageEl.appendChild(editContainer);

        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);

        textarea.onkeydown = (e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                saveEdit(displayIndex, backendIndex, textarea.value);
            }
            if (e.key === 'Escape') {
                cancelEdit();
            }
        };
    }

    async function saveEdit(displayIndex, backendIndex, newContent) {
        newContent = (newContent || '').trim();
        if (!newContent) {
            cancelEdit();
            return;
        }

        // Update backend first
        try {
            const response = await fetch('/edit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ index: backendIndex, content: newContent })
            });
            const data = await response.json();

            if (data.success) {
                // Update local display
                displayMessages[displayIndex].content = newContent;
                displayMessages[displayIndex].edited = true;

                // Re-render from this point
                reRenderMessagesFrom(displayIndex);
            } else {
                addAnnouncement('Failed to edit message: ' + (data.error || 'Unknown error'), 'error');
            }
        } catch (e) {
            console.error('Failed to edit message:', e);
            addAnnouncement('Failed to edit message', 'error');
        }

        editingIndex = null;
    }

    function cancelEdit() {
        if (editingIndex === null) return;

        const index = editingIndex;
        editingIndex = null;

        reRenderMessagesFrom(index);
    }

    async function deleteMessage(displayIndex, backendIndex) {
        if (!confirm("Delete this message and all messages after it?\n\nThis will affect the AI's memory of the conversation.")) {
            return;
        }

        try {
            const response = await fetch('/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ index: backendIndex })
            });
            const data = await response.json();

            if (data.success) {
                // Remove all messages from displayIndex onwards that have a backend index >= backendIndex
                // But keep announcements and commands
                displayMessages = displayMessages.filter((msg, idx) => {
                    if (idx < displayIndex) return true;
                    // Keep messages without backend index (commands, announcements)
                    if (msg.backendIndex === undefined || msg.backendIndex === null) return true;
                    return false;
                });

                // Re-render everything
                renderAllMessages();
            } else {
                addAnnouncement('Failed to delete message: ' + (data.error || 'Unknown error'), 'error');
            }
        } catch (e) {
            console.error('Failed to delete message:', e);
            addAnnouncement('Failed to delete message', 'error');
        }
    }

    function reRenderMessagesFrom(startIndex) {
        // Remove all messages from startIndex onwards
        const wrappers = chat.querySelectorAll('.message-wrapper');
        wrappers.forEach(wrapper => {
            const idx = parseInt(wrapper.dataset.displayIndex);
            if (!isNaN(idx) && idx >= startIndex) {
                wrapper.remove();
            }
        });

        // Re-render from startIndex
        for (let i = startIndex; i < displayMessages.length; i++) {
            createMessageElement(displayMessages[i], i);
        }

        scrollToBottom();
    }

    // =============================================================================
    // Search
    // =============================================================================

    function toggleSearch() {
        const container = document.getElementById('search-container');
        const input = document.getElementById('search-input');

        if (container.classList.contains('active')) {
            clearSearch();
        } else {
            container.classList.add('active');
            input.focus();
        }
    }

    function clearSearch() {
        const container = document.getElementById('search-container');
        const input = document.getElementById('search-input');
        const count = document.getElementById('search-count');

        container.classList.remove('active');
        input.value = '';
        count.textContent = '0 results';
        searchQuery = '';
        searchResults = [];
        currentSearchIndex = -1;

        // Re-render all messages to remove highlights
        renderAllMessages();
    }

    function performSearch(query) {
        searchQuery = query.toLowerCase();
        if (!searchQuery) {
            document.getElementById('search-count').textContent = '0 results';
            return;
        }

        searchResults = [];

        displayMessages.forEach((msg, index) => {
            if ((msg.content || '').toLowerCase().includes(searchQuery)) {
                searchResults.push(index);
            }
        });

        document.getElementById('search-count').textContent = searchResults.length + ' result' + (searchResults.length !== 1 ? 's' : '');

        // Re-render with highlights
        renderSearchResults();

        // Scroll to first result
        if (searchResults.length > 0) {
            const firstResult = chat.querySelector('[data-display-index="' + searchResults[0] + '"]');
            if (firstResult) {
                firstResult.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }

    function renderSearchResults() {
        const wrappers = chat.querySelectorAll('.message-wrapper');
        wrappers.forEach(wrapper => wrapper.remove());

        displayMessages.forEach((msg, index) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'message-wrapper ' + msg.role;
            wrapper.dataset.displayIndex = index;
            wrapper.setAttribute('role', 'article');

            const msgDiv = document.createElement('div');
            msgDiv.className = 'message ' + msg.role;

            const timeStr = msg.timestamp || formatTime();
            let content = msg.content || '';

            if (msg.role === 'ai' || msg.role === 'user') {
                // Apply search highlight
                if (searchResults.includes(index) && searchQuery) {
                    msgDiv.classList.add('search-highlight');
                    const escapedQuery = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\$&');
                    const regex = new RegExp('(' + escapedQuery + ')', 'gi');
                    content = content.replace(regex, '<mark>$1</mark>');
                }

                msgDiv.innerHTML = renderMarkdown(content);
                highlightCode(msgDiv);
            } else {
                msgDiv.innerHTML = content;
            }

            const ts = document.createElement('span');
            ts.className = 'timestamp';
            if (msg.role === 'user') ts.classList.add('timestamp-right');
            else if (msg.role === 'ai') ts.classList.add('timestamp-left');
            else ts.classList.add('timestamp-center');
            ts.textContent = timeStr;

            if (msg.edited) {
                const editIndicator = document.createElement('span');
                editIndicator.className = 'edit-indicator';
                editIndicator.textContent = '(edited)';
                ts.appendChild(editIndicator);
            }

            if (msg.backendIndex !== undefined && msg.backendIndex !== null) {
                const indexBadge = document.createElement('span');
                indexBadge.className = 'index-badge';
                indexBadge.textContent = '#' + msg.backendIndex;
                ts.appendChild(indexBadge);
            }

            msgDiv.appendChild(ts);
            wrapper.appendChild(msgDiv);

            if (msg.role === 'user' || msg.role === 'ai') {
                const actions = createActionButtons(msg.role, index, msg.content || '', msg.backendIndex);
                wrapper.appendChild(actions);
            }

            chat.insertBefore(wrapper, typing);
        });

        scrollToBottom();
    }

    // =============================================================================
    // Export
    // =============================================================================

    function showExportModal() {
        toggleModal('export');
    }

    function exportChat(format) {
        let content, filename, mimeType;

        if (format === 'json') {
            content = JSON.stringify(displayMessages, null, 2);
            filename = 'chat-export.json';
            mimeType = 'application/json';
        } else if (format === 'markdown') {
            let md = '# Chat Export\n\n';
            md += 'Exported on ' + new Date().toLocaleString() + '\n\n---\n\n';

            displayMessages.forEach(msg => {
                const role = msg.role.charAt(0).toUpperCase() + msg.role.slice(1);
                md += '**' + role + '** (' + (msg.timestamp || 'unknown') + '):\n\n';
                md += (msg.content || '') + '\n\n---\n\n';
            });

            content = md;
            filename = 'chat-export.md';
            mimeType = 'text/markdown';
        } else { // txt
            let txt = '';
            txt += 'Chat Export\n';
            txt += 'Exported on ' + new Date().toLocaleString() + '\n';
            txt += '================================\n\n';

            displayMessages.forEach(msg => {
                const role = msg.role.charAt(0).toUpperCase() + msg.role.slice(1);
                txt += '[' + (msg.timestamp || 'unknown') + '] ' + role + ':\n';
                txt += (msg.content || '') + '\n\n';
            });

            content = txt;
            filename = 'chat-export.txt';
            mimeType = 'text/plain';
        }

        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        toggleModal('export');
    }

    // =============================================================================
    // Modal Management
    // =============================================================================

    function toggleModal(modalName) {
        const overlay = document.getElementById(modalName + '-overlay');
        const modal = document.getElementById(modalName + '-modal');

        overlay.classList.toggle('show');
        modal.classList.toggle('show');

        // Focus management for accessibility
        if (modal.classList.contains('show')) {
            modal.querySelector('button, input, [tabindex]:not([tabindex="-1"])')?.focus();
        }
    }

    function closeModalOnOverlay(event, modalName) {
        if (event.target.id === modalName + '-overlay') {
            toggleModal(modalName);
        }
    }

    function showShortcutsModal() {
        toggleModal('shortcuts');
    }

    // =============================================================================
    // Input Handling
    // =============================================================================

    function setInputState(disabled, showTyping = false, showStop = false) {
        inputField.disabled = false;
        sendBtn.disabled = disabled;

        typing.classList.toggle('show', showTyping);
        sendBtn.classList.toggle('hidden', showStop);
        stopBtn.classList.toggle('show', showStop);
    }

    function handleKeyDown(event) {
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

        // Keyboard shortcuts
        if (event.ctrlKey || event.metaKey) {
            if (event.key === 'Enter') {
                event.preventDefault();
                send();
                return;
            }
            if (event.key === 'l' || event.key === 'L') {
                event.preventDefault();
                newConversation();
                return;
            }
            if (event.key === 's' || event.key === 'S') {
                event.preventDefault();
                toggleModal('settings');
                return;
            }
            if (event.key === 'f' || event.key === 'F') {
                event.preventDefault();
                toggleSearch();
                return;
            }
            if (event.key === 'e' || event.key === 'E') {
                event.preventDefault();
                showExportModal();
                return;
            }
            if (event.key === '/') {
                showShortcutsModal();
                return;
            }
        }

        if (event.key === 'Escape') {
            if (isStreaming) {
                stopGeneration();
            }
            // Close any open modal
            document.querySelectorAll('.modal.show').forEach(modal => {
                const modalName = modal.id.replace('-modal', '');
                toggleModal(modalName);
            });
            // Close sidebar on mobile
            closeSidebar();
            // Clear search
            if (document.getElementById('search-container').classList.contains('active')) {
                clearSearch();
            }
            return;
        }

        // Mobile: Enter always adds newline, desktop: Enter sends, Shift+Enter newline
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
    // Drag and Drop File Upload
    // =============================================================================

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        chat.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        chat.addEventListener(eventName, () => {
            chat.classList.add('drag-over');
            dropOverlay.classList.add('active');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        chat.addEventListener(eventName, () => {
            chat.classList.remove('drag-over');
            dropOverlay.classList.remove('active');
        }, false);
    });

    chat.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;

        if (files.length > 0) {
            handleFileUpload({ target: { files: files } });
        }
    }, false);

    // Also handle drops on the entire page
    document.body.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropOverlay.classList.add('active');
    });

    document.body.addEventListener('dragleave', (e) => {
        if (e.target === document.body || !e.relatedTarget) {
            dropOverlay.classList.remove('active');
        }
    });

    document.body.addEventListener('drop', (e) => {
        e.preventDefault();
        dropOverlay.classList.remove('active');

        const dt = e.dataTransfer;
        const files = dt.files;

        if (files.length > 0) {
            handleFileUpload({ target: { files: files } });
        }
    });

    // =============================================================================
    // Command Handling
    // =============================================================================

    async function sendCommand(cmd) {
        if (isStreaming) {
            await stopGeneration();
        }

        // Add command to display
        addMessage({
            role: 'user_command',
            content: cmd,
            timestamp: formatTime()
        });

        try {
            const response = await fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: cmd })
            });

            const data = await response.json();
            if (data.response) {
                addMessage({
                    role: 'command',
                    content: data.response,
                    timestamp: formatTime()
                });
            }
            saveCurrentConversation();

            // Special handling for /new command
            if (cmd.startsWith('/new') || cmd.startsWith('/clear')) {
                displayMessages = [];
                currentConversationId = null;
                renderAllMessages();
                await loadConversations();
            }
        } catch (err) {
            if (cmd.startsWith('/restart')) {
                addMessage({
                    role: 'command',
                    content: 'Restarting server...',
                    timestamp: formatTime()
                });
                return;
            }
            addAnnouncement('Error: ' + err.message, 'error');
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

        // Add user message to display
        addMessage({
            role: 'user',
            content: message,
            timestamp: formatTime(),
            backendIndex: null // Will be set after stream completes
        });

        saveCurrentConversation();

        setInputState(true, true, true);
        isStreaming = true;
        currentController = new AbortController();

        // Create AI message wrapper
        const aiWrapper = document.createElement('div');
        aiWrapper.className = 'message-wrapper ai hidden';
        aiWrapper.dataset.displayIndex = displayMessages.length;
        chat.insertBefore(aiWrapper, typing);
        currentAiMsg = aiWrapper;

        const aiMsgDiv = document.createElement('div');
        aiMsgDiv.className = 'message ai';
        aiWrapper.appendChild(aiMsgDiv);

        let aiContent = '';
        let streamStarted = false;
        let backendIndex = null;

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
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));

                            if (data.id) {
                                currentStreamId = data.id;
                            }

                            if (data.cancelled) {
                                aiWrapper.classList.remove('hidden');
                                aiMsgDiv.innerHTML = '<span style="color:#f88;">[Cancelled]</span>';
                                const ts = document.createElement('span');
                                ts.className = 'timestamp timestamp-left';
                                ts.textContent = formatTime();
                                aiMsgDiv.appendChild(ts);
                                finishStream();
                                return;
                            }

                            if (data.token) {
                                if (!streamStarted) {
                                    streamStarted = true;
                                    typing.classList.remove('show');
                                    aiWrapper.classList.remove('hidden');
                                }
                                aiContent += data.token;
                                aiMsgDiv.innerHTML = renderMarkdown(aiContent);
                                highlightCode(aiMsgDiv);

                                const ts = aiMsgDiv.querySelector('.timestamp');
                                if (!ts) {
                                    const tsEl = document.createElement('span');
                                    tsEl.className = 'timestamp timestamp-left';
                                    aiMsgDiv.appendChild(tsEl);
                                }
                                scrollToBottomDelayed();
                            }

                            if (data.done) {
                                aiMsgDiv.innerHTML = renderMarkdown(aiContent);
                                highlightCode(aiMsgDiv);
                                const ts = document.createElement('span');
                                ts.className = 'timestamp timestamp-left';
                                ts.textContent = formatTime();

                                // Add backend index badge
                                if (data.backendIndex !== undefined && data.backendIndex !== null) {
                                    const indexBadge = document.createElement('span');
                                    indexBadge.className = 'index-badge';
                                    indexBadge.textContent = '#' + data.backendIndex;
                                    ts.appendChild(indexBadge);
                                }

                                aiMsgDiv.appendChild(ts);

                                // Update the user message's backend index now that we know it
                                if (data.userIndex !== undefined && data.userIndex !== null) {
                                    // Find the last user message and set its backend index
                                    for (let i = displayMessages.length - 1; i >= 0; i--) {
                                        if (displayMessages[i].role === 'user') {
                                            displayMessages[i].backendIndex = data.userIndex;
                                            break;
                                        }
                                    }
                                }

                                // Add AI message to display
                                displayMessages.push({
                                    role: 'ai',
                                    content: aiContent,
                                    timestamp: formatTime(),
                                    backendIndex: data.backendIndex
                                });
                                aiWrapper.dataset.displayIndex = displayMessages.length - 1;

                                // Add action buttons
                                const actions = createActionButtons('ai', parseInt(aiWrapper.dataset.displayIndex), aiContent, data.backendIndex);
                                aiWrapper.appendChild(actions);

                                // Save conversation
                                saveCurrentConversation();
                            }

                            if (data.error) {
                                if (!streamStarted) {
                                    aiWrapper.classList.remove('hidden');
                                }
                                aiMsgDiv.innerHTML = '<span style="color:#f88;">[Error: ' + data.error + ']</span>';
                                const ts = document.createElement('span');
                                ts.className = 'timestamp timestamp-left';
                                ts.textContent = formatTime();
                                aiMsgDiv.appendChild(ts);
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
                    aiWrapper.classList.remove('hidden');
                }
                aiMsgDiv.innerHTML = '<span style="color:#f88;">Error: ' + err.message + '</span>';
                const ts = document.createElement('span');
                ts.className = 'timestamp timestamp-left';
                ts.textContent = formatTime();
                aiMsgDiv.appendChild(ts);
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

            const aiMsgDiv = currentAiMsg.querySelector('.message');
            if (aiMsgDiv) {
                let existingContent = aiMsgDiv.innerText || '';
                existingContent = existingContent.replace(/\s*\d{1,2}:\d{2}\s*(?:AM|PM)?\s*$/i, '').trim();

                if (existingContent) {
                    aiMsgDiv.innerHTML = renderMarkdown(existingContent) + ' <span style="color:#f88;">[Stopped]</span>';
                } else {
                    aiMsgDiv.innerHTML = '<span style="color:#f88;">[Stopped]</span>';
                }

                const ts = document.createElement('span');
                ts.className = 'timestamp timestamp-left';
                ts.textContent = formatTime();
                aiMsgDiv.appendChild(ts);

                const finalContent = existingContent ? existingContent + ' [Stopped]' : '[Stopped]';
                displayMessages.push({
                    role: 'ai',
                    content: finalContent,
                    timestamp: formatTime(),
                    backendIndex: null // Stopped messages don't have a backend index
                });
                currentAiMsg.dataset.displayIndex = displayMessages.length - 1;

                // Add action buttons (no edit/delete for stopped messages)
                const actions = createActionButtons('ai', parseInt(currentAiMsg.dataset.displayIndex), finalContent, null);
                currentAiMsg.appendChild(actions);
            }

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
        newConversation();
    }

    // =============================================================================
    // File Upload
    // =============================================================================

    async function handleFileUpload(event) {
        const file = event.target.files ? event.target.files[0] : event.dataTransfer.files[0];
        if (!file) return;

        if (event.target) {
            event.target.value = '';
        }

        addAnnouncement('[Uploading: ' + file.name + ']', 'info');

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
                addMessage({
                    role: 'user',
                    content: '[Uploaded: ' + file.name + ']',
                    timestamp: formatTime(),
                    backendIndex: data.backendIndex
                });

                if (data.message) {
                    addAnnouncement(data.message, 'info');
                }
            } else {
                addAnnouncement('Error: ' + (data.error || 'Upload failed'), 'error');
            }
        } catch (err) {
            addAnnouncement('Error: ' + err.message, 'error');
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
            if (!hasShownDisconnected) {
                addAnnouncement('Disconnected from server.', 'info');
                hasShownDisconnected = true;
            }
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
                '--bg-sidebar': '#0d0d0d',
                '--border-color': '#2a2a2a',
                '--border-message': '#333333',
                '--border-user': '#444444',
                '--border-sidebar': '#222222',
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
                '--bg-sidebar': '#141414',
                '--border-color': '#404040',
                '--border-message': '#484848',
                '--border-user': '#505050',
                '--border-sidebar': '#303030',
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
                '--bg-sidebar': '#12080e',
                '--border-color': '#482840',
                '--border-message': '#503048',
                '--border-user': '#583850',
                '--border-sidebar': '#382030',
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
                '--bg-sidebar': '#080c10',
                '--border-color': '#283850',
                '--border-message': '#304060',
                '--border-user': '#384868',
                '--border-sidebar': '#182838',
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
                '--bg-sidebar': '#080e0a',
                '--border-color': '#284030',
                '--border-message': '#305038',
                '--border-user': '#385840',
                '--border-sidebar': '#183820',
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
        'dark-sepia': {
            name: 'Sepia',
            mode: 'dark',
            vars: {
                '--bg-primary': '#1a1510',
                '--bg-secondary': '#242018',
                '--bg-tertiary': '#302820',
                '--bg-message-user': 'linear-gradient(135deg, #483828 0%, #3c3020 100%)',
                '--bg-message-ai': '#302820',
                '--bg-message-announce': 'linear-gradient(135deg, #403020 0%, #302818 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #304828 0%, #243820 100%)',
                '--bg-input': '#20180c',
                '--bg-code': '#1a1510',
                '--bg-sidebar': '#12100c',
                '--border-color': '#483820',
                '--border-message': '#504028',
                '--border-user': '#584830',
                '--border-sidebar': '#302818',
                '--text-primary': '#f0e0d0',
                '--text-secondary': '#c8a878',
                '--text-muted': '#907850',
                '--text-code': '#e8d0b8',
                '--accent': '#c09050',
                '--accent-glow': 'rgba(192, 144, 80, 0.4)',
                '--error': '#f08080',
                '--error-bg': 'linear-gradient(135deg, #3a1a1a 0%, #2a0a0a 100%)',
                '--error-border': '#5a2a2a',
                '--important': '#dada80',
                '--important-bg': 'linear-gradient(135deg, #3a3a1a 0%, #2a2a0a 100%)',
                '--important-border': '#5a5a2a',
                '--info': '#80b0d0',
                '--info-bg': 'linear-gradient(135deg, #1a2a3a 0%, #0a1a2a 100%)',
                '--info-border': '#2a4a6a',
                '--button-bg': 'linear-gradient(135deg, #483828 0%, #383020 100%)',
                '--button-hover': 'linear-gradient(135deg, #584838 0%, #483828 100%)',
                '--button-stop': 'linear-gradient(135deg, #5a2a2a 0%, #3a1a1a 100%)',
                '--scrollbar': '#483820',
                '--scrollbar-hover': '#584830'
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
                '--bg-sidebar': '#13131a',
                '--border-color': '#45475a',
                '--border-message': '#585b70',
                '--border-user': '#6c6f85',
                '--border-sidebar': '#313244',
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
                '--bg-sidebar': '#fafafa',
                '--border-color': '#d0d0d0',
                '--border-message': '#c8c8c8',
                '--border-user': '#b8b8b8',
                '--border-sidebar': '#e0e0e0',
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
        'light-pink': {
            name: 'Pink',
            mode: 'light',
            vars: {
                '--bg-primary': '#fff8fa',
                '--bg-secondary': '#fff0f4',
                '--bg-tertiary': '#f8e8ec',
                '--bg-message-user': 'linear-gradient(135deg, #f8d8e4 0%, #f0d0dc 100%)',
                '--bg-message-ai': '#f8f0f4',
                '--bg-message-announce': 'linear-gradient(135deg, #f8e0e8 0%, #fff0f4 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #e0f0e0 0%, #d8ecd8 100%)',
                '--bg-input': '#fff8fa',
                '--bg-code': '#fff0f4',
                '--bg-sidebar': '#fffcfd',
                '--border-color': '#e8b8c8',
                '--border-message': '#d8a8b8',
                '--border-user': '#c898a8',
                '--border-sidebar': '#f0d0dc',
                '--text-primary': '#2a1820',
                '--text-secondary': '#684858',
                '--text-muted': '#a08090',
                '--text-code': '#483040',
                '--accent': '#d06090',
                '--accent-glow': 'rgba(208, 96, 144, 0.3)',
                '--error': '#c04040',
                '--error-bg': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--error-border': '#d8a8a8',
                '--important': '#a08040',
                '--important-bg': 'linear-gradient(135deg, #f8f0d8 0%, #f0e8c8 100%)',
                '--important-border': '#d8c8a8',
                '--info': '#4080b0',
                '--info-bg': 'linear-gradient(135deg, #d8f0f8 0%, #c8e8f0 100%)',
                '--info-border': '#a8c8d8',
                '--button-bg': 'linear-gradient(135deg, #f8d8e4 0%, #f0d0dc 100%)',
                '--button-hover': 'linear-gradient(135deg, #f0c8d8 0%, #e8c0d0 100%)',
                '--button-stop': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--scrollbar': '#e0b0c0',
                '--scrollbar-hover': '#c090a0'
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
                '--bg-sidebar': '#fcfeff',
                '--border-color': '#b8c8e8',
                '--border-message': '#a8b8d8',
                '--border-user': '#98a8c8',
                '--border-sidebar': '#d0dcf0',
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
                '--bg-sidebar': '#fcfffc',
                '--border-color': '#a8d0a8',
                '--border-message': '#98c098',
                '--border-user': '#88b088',
                '--border-sidebar': '#c0e8c0',
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
        'light-sepia': {
            name: 'Sepia',
            mode: 'light',
            vars: {
                '--bg-primary': '#faf8f4',
                '--bg-secondary': '#f6f0e8',
                '--bg-tertiary': '#f0e8dc',
                '--bg-message-user': 'linear-gradient(135deg, #f0e0d0 0%, #e8d8c8 100%)',
                '--bg-message-ai': '#f6f0e8',
                '--bg-message-announce': 'linear-gradient(135deg, #f0e4d8 0%, #f6f0e8 100%)',
                '--bg-message-command': 'linear-gradient(135deg, #e0f0e0 0%, #d8ecd8 100%)',
                '--bg-input': '#faf8f4',
                '--bg-code': '#f6f0e8',
                '--bg-sidebar': '#fcfaf6',
                '--border-color': '#d8c8a8',
                '--border-message': '#c8b898',
                '--border-user': '#b8a888',
                '--border-sidebar': '#e8d8c0',
                '--text-primary': '#2a2018',
                '--text-secondary': '#684828',
                '--text-muted': '#a08060',
                '--text-code': '#483018',
                '--accent': '#a08040',
                '--accent-glow': 'rgba(160, 128, 64, 0.3)',
                '--error': '#c04040',
                '--error-bg': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--error-border': '#d8a8a8',
                '--important': '#a08040',
                '--important-bg': 'linear-gradient(135deg, #f8f0d8 0%, #f0e8c8 100%)',
                '--important-border': '#d8c8a8',
                '--info': '#4080b0',
                '--info-bg': 'linear-gradient(135deg, #d8f0f8 0%, #c8e8f0 100%)',
                '--info-border': '#a8c8d8',
                '--button-bg': 'linear-gradient(135deg, #f0e0d0 0%, #e8d8c8 100%)',
                '--button-hover': 'linear-gradient(135deg, #e8d8c0 0%, #e0d0b8 100%)',
                '--button-stop': 'linear-gradient(135deg, #f8d8d8 0%, #f0d0d0 100%)',
                '--scrollbar': '#d0c0a0',
                '--scrollbar-hover': '#b0a080'
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
                '--bg-sidebar': '#f4f6f8',
                '--border-color': '#bcc0cc',
                '--border-message': '#acb0bc',
                '--border-user': '#9ca0ac',
                '--border-sidebar': '#d0d4de',
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

    // Initialize the app
    async function init() {
        // Check connection
        try {
            await checkConnection();
        } catch (err) {
            isConnected = false;
            updateConnectionStatus('disconnected');
            addAnnouncement('Disconnected from server.', 'info');
            hasShownDisconnected = true;
            scheduleReconnect();
        }

        // Load theme (keep this in localStorage as it's UI preference)
        loadTheme();
    }

    // Start the app
    init();

    // Save conversation before leaving page
    window.addEventListener('beforeunload', () => {
        if (displayMessages.length > 0) {
            // Use sendBeacon for reliable save on page unload
            const data = JSON.stringify({
                id: currentConversationId,
                messages: displayMessages
            });
            navigator.sendBeacon('/conversation/save', data);
        }
    });

    </script>
</body>
</html>
"""

# ==============================================================================
# WebUI Channel Class
# ==============================================================================

class Webui(core.channel.Channel):
    """
    A web-based channel for communicating with the AI through a browser interface.

    This channel provides:
    - Real-time streaming responses via Server-Sent Events
    - Connection monitoring with automatic reconnection
    - Theme customization with 12 built-in themes
    - File upload support (button + drag & drop)
    - PWA support for mobile installation
    - Markdown rendering with syntax highlighting
    - Message editing, deletion, search, and export
    - Keyboard shortcuts and accessibility features
    - Conversation history sidebar with persistent storage
    - Proper handling of backend messages vs commands/announcements
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.announcement_queue = []
        self.announcement_id = 0
        self.main_loop = None

        # Storage for saved conversations
        self.conversations = core.storage.StorageList("conversations", "json")
        
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

    def get_backend_messages(self):
        """
        Get messages from the backend API.
        Returns list of messages with role='user' or role='assistant'.
        """
        if not self.manager or not hasattr(self.manager, 'API'):
            return []

        # Access the renamed _messages attribute
        messages = self.manager.API._messages if hasattr(self.manager.API, '_messages') else []

        result = []
        for i, msg in enumerate(messages):
            role = msg.get('role', 'user')
            # Convert 'assistant' to 'ai' for frontend display
            if role == 'assistant':
                role = 'ai'
            content = msg.get('content', '')
            if content:
                result.append({
                    'role': role,
                    'content': content,
                    'backendIndex': i,  # Attach backend index
                    'timestamp': None
                })

        return result

    def set_backend_messages(self, messages):
        """
        Set messages in the backend API.
        """
        if not self.manager or not hasattr(self.manager, 'API'):
            return

        # Convert 'ai' back to 'assistant' for backend
        backend_messages = []
        for msg in messages:
            role = msg.get('role', 'user')
            if role == 'ai':
                role = 'assistant'
            content = msg.get('content', '')
            if content:
                backend_messages.append({
                    'role': role,
                    'content': content
                })

        # Use set_messages if available, otherwise set directly
        if hasattr(self.manager.API, 'set_messages'):
            self.manager.API.set_messages(backend_messages)
        else:
            self.manager.API._messages = backend_messages

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

    messages = []
    for msg in channel_instance.announcement_queue:
        if msg['id'] > last_id:
            messages.append(msg)

    # Clear the queue after sending
    channel_instance.announcement_queue = []

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
    5. Returns backend indices for proper message tracking

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

        future = asyncio.run_coroutine_threadsafe(collect_tokens(), channel_instance.main_loop)

        # Send stream ID first
        yield f"data: {json.dumps({'id': stream_id})}\n\n"

        # Get user message index after it was inserted
        user_index = len(channel_instance.manager.API._messages) - 1 if hasattr(channel_instance.manager.API, '_messages') else 0

        # Stream tokens
        while True:
            item = token_queue.get()

            if item is done:
                # NOW send backend indices - after stream completes successfully
                assistant_index = len(channel_instance.manager.API._messages) - 1 if hasattr(channel_instance.manager.API, '_messages') else 0
                yield f"data: {json.dumps({'done': True, 'backendIndex': assistant_index, 'userIndex': user_index})}\n\n"
                break
            elif isinstance(item, tuple):
                if item[0] == 'error':
                    # Roll back the user message on error
                    if hasattr(channel_instance.manager.API, '_messages'):
                        messages = channel_instance.manager.API._messages
                        if len(messages) > 0 and messages[-1].get('role') == 'user':
                            messages.pop()
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

@app.route('/history')
def get_history():
    """
    Return the current conversation history from the backend.

    Each message includes a backendIndex for proper edit/delete operations.
    Only returns messages that exist in the backend (user and assistant messages).
    """
    global channel_instance

    if not channel_instance or not hasattr(channel_instance, 'manager') or not hasattr(channel_instance.manager, 'API'):
        return jsonify({'messages': []})

    messages = channel_instance.get_backend_messages()

    return jsonify({'messages': messages})

@app.route('/edit', methods=['POST'])
def edit_message():
    """
    Edit a message in the backend conversation history.

    Uses the backend index directly for reliable editing.
    """
    global channel_instance

    data = request.get_json()
    index = data.get('index', 0)
    new_content = data.get('content', '')

    if not channel_instance or not hasattr(channel_instance, 'manager') or not hasattr(channel_instance.manager, 'API'):
        return jsonify({'success': False, 'error': 'API not available'})

    messages = channel_instance.manager.API._messages if hasattr(channel_instance.manager.API, '_messages') else []

    if 0 <= index < len(messages):
        if messages[index].get('role') not in ('user', 'assistant'):
            return jsonify({'success': False, 'error': 'Cannot edit system messages'})

        old_content = messages[index].get('content', '')[:50]
        messages[index]['content'] = new_content
        core.log("webui", f"Edited message {index}: '{old_content}...' -> '{new_content[:50]}...'")
        return jsonify({'success': True, 'messages_count': len(messages)})

    core.log("webui", f"Edit failed: index {index} out of range (messages has {len(messages)})")
    return jsonify({'success': False, 'error': f'Index {index} out of range'})

@app.route('/delete', methods=['POST'])
def delete_message():
    """
    Delete a message and all messages after it from the backend context.

    Uses the backend index directly for reliable deletion.
    """
    global channel_instance

    data = request.get_json()
    index = data.get('index', 0)

    if not channel_instance or not hasattr(channel_instance, 'manager') or not hasattr(channel_instance.manager, 'API'):
        return jsonify({'success': False, 'error': 'API not available'})

    messages = channel_instance.manager.API._messages if hasattr(channel_instance.manager.API, '_messages') else []
    original_count = len(messages)

    if 0 <= index < len(messages):
        if messages[index].get('role') not in ('user', 'assistant'):
            return jsonify({'success': False, 'error': 'Cannot delete system messages'})

        removed_count = len(messages) - index
        # Keep only messages before the index
        channel_instance.manager.API._messages = messages[:index]
        remaining_count = len(channel_instance.manager.API._messages)
        core.log("webui", f"Deleted {removed_count} messages from index {index}, {remaining_count} remaining")
        return jsonify({
            'success': True,
            'removed': removed_count,
            'remaining': remaining_count,
            'messages_count': remaining_count
        })

    core.log("webui", f"Delete failed: index {index} out of range (messages has {len(messages)})")
    return jsonify({'success': False, 'error': f'Index {index} out of range'})

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
    Returns the backend index of the inserted message.
    """
    global channel_instance

    data = request.get_json()
    filename = data.get('filename', '')
    content_b64 = data.get('content', '')
    mimetype = data.get('mimetype', '')

    try:
        content = base64.b64decode(content_b64).decode('utf-8', errors='replace')

        # Get the index before insertion
        messages = channel_instance.manager.API._messages if hasattr(channel_instance.manager.API, '_messages') else []
        backend_index = len(messages)

        # Insert the file content into the conversation
        result = f"File uploaded: {filename} ({len(content)} bytes)"
        asyncio.run_coroutine_threadsafe(
            channel_instance.manager.API.insert_message("user", f"[File: {filename}]\n{content}..."),
            channel_instance.main_loop
        ).result()

        return jsonify({
            'success': True,
            'message': result,
            'backendIndex': backend_index
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==============================================================================
# Conversation Management Routes
# ==============================================================================

@app.route('/conversations')
def list_conversations():
    """
    List all saved conversations.
    """
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

    # Sort by updated time, most recent first
    conversations.sort(key=lambda x: x.get('updated', ''), reverse=True)

    return jsonify({'conversations': conversations})

@app.route('/conversation/save', methods=['POST'])
def save_conversation():
    """
    Save the current conversation.

    Accepts the full displayMessages array from the frontend, which includes
    all message types (user, ai, command, announcement).

    Returns the conversation ID.
    """
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    data = request.get_json()
    conv_id = data.get('id')
    messages = data.get('messages', [])

    # Generate a title from the first user message
    title = 'New Conversation'
    for msg in messages:
        if msg.get('role') in ('user', 'user_command'):
            content = msg.get('content', '')
            if content and not content.startswith('/'):
                # Take first 50 chars as title
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
                    'title': title,
                    'messages': messages,
                    'created': conv.get('created', now),
                    'updated': now
                }
                channel_instance.conversations.save()
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

    return jsonify({'success': True, 'id': conv_id})

@app.route('/conversation/load')
def load_conversation():
    """
    Load a conversation by ID.

    Restores all messages (including commands and announcements) to the frontend.
    Also sets the backend messages for the AI context.
    """
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    conv_id = request.args.get('id')
    if not conv_id:
        return jsonify({'success': False, 'error': 'No conversation ID provided'})

    for conv in channel_instance.conversations:
        if conv.get('id') == conv_id:
            messages = conv.get('messages', [])

            # Extract only user and assistant messages for backend
            backend_messages = []
            for msg in messages:
                role = msg.get('role')
                if role in ('user', 'ai'):
                    backend_role = 'assistant' if role == 'ai' else 'user'
                    content = msg.get('content', '')
                    if content:
                        backend_messages.append({
                            'role': backend_role,
                            'content': content
                        })

            # Set backend messages
            channel_instance.set_backend_messages(backend_messages)

            return jsonify({
                'success': True,
                'conversation': conv
            })

    return jsonify({'success': False, 'error': 'Conversation not found'})

@app.route('/conversation/delete', methods=['POST'])
def delete_conversation():
    """
    Delete a conversation by ID.
    """
    global channel_instance

    if not channel_instance:
        return jsonify({'success': False, 'error': 'Channel not available'})

    conv_id = request.args.get('id')
    if not conv_id:
        return jsonify({'success': False, 'error': 'No conversation ID provided'})

    for i, conv in enumerate(channel_instance.conversations):
        if conv.get('id') == conv_id:
            channel_instance.conversations.pop(i)
            channel_instance.conversations.save()
            return jsonify({'success': True})

    return jsonify({'success': False, 'error': 'Conversation not found'})

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
    sw_code = """
const CACHE_VERSION = '3.0.0';
const CACHE_NAME = 'ai-chat-v-' + CACHE_VERSION;

// Only cache LOCAL resources that we control
// DO NOT cache third-party CDNs - they have their own caching
const LOCAL_ASSETS = [
    '/',
    '/manifest.json'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(LOCAL_ASSETS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Only intercept LOCAL requests (same origin)
    // Let CDN requests pass through to the browser
    if (url.origin !== location.origin) {
        return; // Browser handles CDN requests normally
    }

    // For navigation requests (HTML), try network first
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                    return response;
                })
                .catch(() => caches.match(event.request))
        );
        return;
    }

    // For other local requests, try cache first
    // event.respondWith(
    //    caches.match(event.request)
    //        .then((response) => response || fetch(event.request))
    // );
});
"""
    response = Response(sw_code, mimetype='application/javascript')
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/icon-192.png')
@app.route('/icon-512.png')
def icon():
    """Serve a placeholder icon for PWA."""
    # Minimal black PNG (2x2)
    png_hex = "89504e470d0a1a0a0000000d494844520000000200000002080200000001f338dd0000000c4944415408d763f8ffffcf0001000100737a55b00000000049454e44ae426082"
    return bytes.fromhex(png_hex), 200, {'Content-Type': 'image/png'}
