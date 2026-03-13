// =============================================================================
// Sidebar Management
// =============================================================================

function toggleSidebar() {
    const isMobile = window.innerWidth <= 768;

    if (isMobile) {
        // Mobile behavior: use overlay
        sidebar.classList.toggle('open');
        sidebarOverlay.classList.toggle('show');
    } else {
        // Desktop behavior: hide/show
        desktopSidebarHidden = !desktopSidebarHidden;
        sidebar.classList.toggle('desktop-hidden', desktopSidebarHidden);
        document.querySelector('.app-wrapper').classList.toggle('sidebar-hidden', desktopSidebarHidden);
    }
}

function closeSidebar() {
    const isMobile = window.innerWidth <= 768;

    if (isMobile) {
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('show');
    }
    // On desktop, we don't "close" the sidebar - it stays visible
    // User must use Ctrl+B to toggle
}

// Touch swipe handling for mobile sidebar
let touchStartX = 0;
let touchEndX = 0;

function handleSwipe() {
    const swipeThreshold = 50;
    const diff = touchEndX - touchStartX;

    if (diff > swipeThreshold && touchStartX < 30) {
        sidebar.classList.add('open');
        sidebarOverlay.classList.add('show');
    } else if (diff < -swipeThreshold && sidebar.classList.contains('open')) {
        closeSidebar();
    }
}

document.addEventListener('touchstart', (e) => {
    touchStartX = e.changedTouches[0].screenX;
}, { passive: true });

document.addEventListener('touchend', (e) => {
    touchEndX = e.changedTouches[0].screenX;
    handleSwipe();
}, { passive: true });
