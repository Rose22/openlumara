// =============================================================================
// State Variables
// =============================================================================

let isConnected = false;        // Server connection
let isApiConnected = false;     // API connection
let apiError = null;            // Last API error message
let apiErrorType = null;        // Type of API error (config_missing, auth_failed, etc.)
let apiAction = null;           // Suggested action for API error
let reconnectAttempts = 0;
let reconnectTimer = null;
let lastMessageIndex = 0;
let currentChatId = null;
let userIsEditing = false;
let currentTitleBarTags = [];

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
let tagFilterCollapsed = true;
let allTags = [];
let titleBarResizeTimeout = null;

// Global search
let globalSearchDebounce = null;
let globalSearchAborted = false;
let globalSearchActiveIndex = -1;

// Polling cleanup
let pollIntervalId = null;
let apiStatusIntervalId = null;

// Notification state
let notificationPermission = 'default';

// DOM references
const chat = document.getElementById('chat');
const typing = document.getElementById('typing');
const inputField = document.getElementById('message');
const sendBtn = document.getElementById('send');
const stopBtn = document.getElementById('stop');
const statusDot = document.getElementById('status');
const apiStatusDot = document.getElementById('api-status');
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
    API_STATUS_INTERVAL: 10000  // Check API status every 10 seconds
};
