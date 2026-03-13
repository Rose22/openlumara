let isConnected = false;
let reconnectAttempts = 0;
let reconnectTimer = null;
let lastMessageIndex = 0;
let currentChatId = null;
let userIsEditing = false
let currentTitleBarTags = [];;

// Stream state
let isStreaming = false;
let streamFrozen = false;
let currentController = null;
let currentStreamId = null;
let editingIndex = null;

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
let tagFilterCollapsed = true; // Default to collapsed
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
    CONNECTION_TIMEOUT: 3000,
    POLL_INTERVAL: 500
};
