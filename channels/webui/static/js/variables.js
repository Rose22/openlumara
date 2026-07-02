// =============================================================================
// State Variables
// =============================================================================

let isConnected = false;        // Server connection (HTTP)
let isWsConnected = false;       // WebSocket connection
let reconnectAttempts = 0;
let reconnectTimer = null;
let lastMessageIndex = 0;
let currentChatId = null;
let userIsEditing = false;
let currentTitleBarTags = [];

// Stream state
let isStreaming = false;
let isDataStreaming = false;    // Track if backend is still sending data
let promptProcessingReceived = false;  // Track if we received prompt_progress
let streamFrozen = false;
let currentController = null;
let currentStreamId = null;

// Search state
let searchQuery = '';
let searchResults = [];
let currentSearchIndex = -1;
let originalMessageContents = new Map();

// Sidebar states
let desktopSidebarHidden = false;
let allChats = [];
let searchInContent = false;
let activeTagFilter = null;
let tagFilterCollapsed = true;
let allTags = [];
let titleBarResizeTimeout = null;

// Global search
let globalSearchDebounce = null;
let globalSearchAborted = false;
let globalSearchActiveIndex = -1;

// Polling cleanup
let pollIntervalId = null;

// Notification state
let notificationPermission = 'default';

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
    CONNECTION_TIMEOUT: 10000,
    POLL_INTERVAL: 1000
};

// Default values for "standard" themes
// If a theme doesn't specify a variable, it falls back to this.
const BASE_THEME_VARS = {
    // Shapes
    '--radius-sm': '4px',
    '--radius-md': '8px',
    '--radius-lg': '12px',
    '--radius-xl': '16px',

    // Decorations (Reset these so patterns don't stick)
    '--bg-pattern': 'none',
    '--bg-pattern-size': '24px 24px',
    '--message-decoration': 'none',
    '--avatar-shape': '50%'
};
