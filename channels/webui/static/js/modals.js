// =============================================================================
// Modal Management
// =============================================================================

function toggleModal(modalName) {
    const overlay = document.getElementById(modalName + '-overlay');
    const modal = document.getElementById(modalName + '-modal');

    overlay.classList.toggle('show');
    modal.classList.toggle('show');
}

function closeModalOnOverlay(event, modalName) {
    if (event.target.id === modalName + '-overlay') {
        toggleModal(modalName);
    }
}

function showShortcutsModal() {
    toggleModal('shortcuts');
}
