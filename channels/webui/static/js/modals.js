// =============================================================================
// Modal Management
// =============================================================================

function toggleModal(modalName) {
    const overlay = document.getElementById(modalName + '-overlay');
    const modal = document.getElementById(modalName + '-modal');

    // make the close button visible again in case we hid it (with a forced modal)
    const closeBtn = document.getElementById(modalName + '-close');
    if (closeBtn) {
        closeBtn.style.visibility = "visible";
    }

    if (overlay) {
        overlay.classList.toggle('show');
    }
    if (modal) {
        modal.classList.toggle('show');
    }
}

function showModal(modalName, forced=false) {
    const overlay = document.getElementById(modalName + '-overlay');
    const modal = document.getElementById(modalName + '-modal');

    if (overlay) {
        overlay.classList.add('show');
    }
    if (modal) {
        modal.classList.add('show');
        if (forced) {
            modal.classList.add('forced');
            const closeBtn = document.getElementById(modalName + '-close');
            closeBtn.style.visibility = "hidden";
        }
    }
}

function closeModal(modalName) {
    const overlay = document.getElementById(modalName + '-overlay');
    const modal = document.getElementById(modalName + '-modal');

    if (overlay) {
        overlay.classList.remove('show');
    }
    if (modal) {
        modal.classList.remove('show');
        modal.classList.remove('forced');
    }
}

function closeModalOnOverlay(event, modalName) {
    // don't allow closing forced modals using the overlay
    const modal = document.getElementById(modalName + '-modal');
    if (modal.classList.contains('forced')) {
        return;
    }

    if (event.target.id === modalName + '-overlay') {
        toggleModal(modalName);
    }
}

function showShortcutsModal() {
    toggleModal('shortcuts');
}

function showConfirmDialog(message) {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'confirm-overlay';
        overlay.innerHTML = `
        <div class="confirm-modal">
        <p class="confirm-message">${message}</p>
        <div class="confirm-actions">
        <button class="confirm-btn cancel">Cancel</button>
        <button class="confirm-btn confirm">Proceed</button>
        </div>
        </div>
        `;

        const handleCancel = () => {
            document.body.removeChild(overlay);
            resolve(false);
        };

        const handleConfirm = () => {
            document.body.removeChild(overlay);
            resolve(true);
        };

        overlay.querySelector('.cancel').onclick = handleCancel;
        overlay.querySelector('.confirm').onclick = handleConfirm;

        // Close on overlay click
        overlay.onclick = (e) => {
            if (e.target === overlay) handleCancel();
        };

            document.body.appendChild(overlay);
    });
}
