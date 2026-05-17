# modals.js Documentation

`modals.js` provides the core infrastructure for managing modal dialogs throughout the application. It handles the opening, closing, and state management of various overlays like Settings, Export, and Shortcuts.

## Core Functionality

### Modal Lifecycle
- `toggleModal(modalName)`: The primary function to open or close a modal.
  - It looks for an element with the ID `{modalName}-modal`.
  - It manages the visibility of both the modal itself and its associated overlay.
  - **Safety Check**: If the `settings` modal is being closed while there are unsaved changes, it prompts the user for confirmation.

### Global Modals
- **Settings Modal**: Triggered via `toggleModal('settings')`. Loads settings on open.
- **Export Modal**: Triggered via `showExportModal()`.
- **Shortcuts Modal**: Triggered via `showShortcutsModal()`.
- **Global Search Modal**: Triggered via `openGlobalSearch()` (from `search.js`).

## Integration
- **Keyboard Support**: The `Escape` key is globally listened for. It uses a priority system to close the most relevant modal (Global Search $\rightarrow$ Any Open Modal $\rightarrow$ Chat Search $\rightarrow$ Sidebar $\rightarrow$ Stop Generation).
- **Focus Management**: When a modal is opened, focus is automatically shifted to the relevant input field (e.g., the search input in the Global Search modal).
- **Overlay Management**: Uses a semi-transparent overlay to dim the background and capture clicks outside the modal to close it.
