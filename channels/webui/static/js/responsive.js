// =============================================================================
// Responsive-ness
// =============================================================================

// Handle responsive changes
window.addEventListener('resize', () => {
    const isMobile = window.innerWidth <= 768;

    // If switching to mobile, ensure desktop-hidden is removed
    if (isMobile) {
        sidebar.classList.remove('desktop-hidden');
        document.body.classList.remove('sidebar-desktop-hidden');
        desktopSidebarHidden = false;
    }
});
