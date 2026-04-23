// =============================================================================
// Sidebar Management
// =============================================================================

/**
 * =============================================================================
 * SIDEBAR STATE MANAGEMENT (PERSISTENCE)
 * =============================================================================
 */

// Key names for localStorage
const STORAGE_KEYS = {
    CATEGORY_STRIP: 'sidebar_category_collapsed',
    FULL_SIDEBAR: 'sidebar_full_collapsed'
};

/**
 * Toggles the entire sidebar (Mobile/Desktop)
 * Handles the main menu visibility.
 */
function toggleSidebar() {
    try {
        const isMobile = window.innerWidth <= 768;
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebar-overlay');
        const appWrapper = document.querySelector('.app-wrapper');

        if (!sidebar) {
            console.warn('Sidebar element not found');
            return;
        }

        if (isMobile) {
            sidebar.classList.toggle('open');
            if (sidebarOverlay) sidebarOverlay.classList.toggle('show');
        } else {
            // Desktop behavior
            // Note: Based on your previous code, desktop uses a specific 'desktop-hidden' class
            // This is a bit different from mobile, but we will persist the "hidden" state.
            window.desktopSidebarHidden = !window.desktopSidebarHidden;
            sidebar.classList.toggle('desktop-hidden', window.desktopSidebarHidden);
            if (appWrapper) appWrapper.classList.toggle('sidebar-hidden', window.desktopSidebarHidden);

            // Save state
            localStorage.setItem(STORAGE_KEYS.FULL_SIDEBAR, window.desktopSidebarHidden);
        }
    } catch (err) {
        console.error('Failed to toggle sidebar:', err);
    }
}

function closeSidebar() {
    try {
        const isMobile = window.innerWidth <= 768;
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebar-overlay');

        if (!sidebar) {
            console.warn('Sidebar element not found');
            return;
        }

        if (isMobile) {
            sidebar.classList.remove('open');
            if (sidebarOverlay) sidebarOverlay.classList.remove('show');
        }
    } catch (err) {
        console.error('Failed to close sidebar:', err);
    }
}

/**
 * Toggles the leftmost Category Strip (Inner Pane)
 */
function toggleCategoryStrip() {
    const categoryPane = document.getElementById('category-pane');
    if (!categoryPane) return;

    categoryPane.classList.toggle('collapsed');
    const isCollapsed = categoryPane.classList.contains('collapsed');
    localStorage.setItem(STORAGE_KEYS.CATEGORY_STRIP, isCollapsed);
}

/**
 * Initializes all sidebar states from localStorage on page load
 */
function initSidebarState() {
    try {
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebar-overlay');
        const categoryPane = document.getElementById('category-pane');
        const appWrapper = document.querySelector('.app-wrapper');

        if (!sidebar) {
            console.warn('Sidebar element not found during initialization');
            return;
        }

        // 1. Restore Full Sidebar State
        const isFullCollapsed = localStorage.getItem(STORAGE_KEYS.FULL_SIDEBAR) === 'true';
        if (isFullCollapsed) {
            const isMobile = window.innerWidth <= 768;
            if (!isMobile) {
                window.desktopSidebarHidden = true;
                sidebar.classList.add('desktop-hidden');
                if (appWrapper) appWrapper.classList.add('sidebar-hidden');
            }
        }

        // 2. Restore Category Strip State (Only if the main sidebar is open/visible)
        const isCatCollapsed = localStorage.getItem(STORAGE_KEYS.CATEGORY_STRIP) === 'true';
        if (isCatCollapsed && categoryPane) {
            categoryPane.classList.add('collapsed');
        }
    } catch (err) {
        console.error('Failed to initialize sidebar state:', err);
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', initSidebarState);

// Touch swipe handling for mobile sidebar
let touchStartX = 0;
let touchEndX = 0;

function handleSwipe() {
    try {
        const swipeThreshold = 50;
        const diff = touchEndX - touchStartX;

        if (diff > swipeThreshold && touchStartX < 30) {
            sidebar.classList.add('open');
            if (sidebarOverlay) sidebarOverlay.classList.add('show');
        } else if (diff < -swipeThreshold && sidebar.classList.contains('open')) {
            closeSidebar();
        }
    } catch (err) {
        console.error('Failed to handle swipe:', err);
    }
}

document.addEventListener('touchstart', (e) => {
    touchStartX = e.changedTouches[0].screenX;
}, { passive: true });

document.addEventListener('touchend', (e) => {
    touchEndX = e.changedTouches[0].screenX;
    handleSwipe();
}, { passive: true });
