# sidebar.js Documentation

`sidebar.js` handles the visibility and state management of the sidebar and the category strip. It ensures that user preferences (like whether the sidebar is collapsed) are persisted across sessions using `localStorage`.

## Key Functions

### Sidebar Visibility
- `toggleSidebar()`: Toggles the main sidebar.
  - **Mobile**: Toggles the `open` class on the sidebar and `show` on the overlay.
  - **Desktop**: Toggles the `desktop-hidden` class on the sidebar and `sidebar-hidden` on the app wrapper. Saves state to `localStorage`.
- `closeSidebar()`: Closes the mobile sidebar.

### Category Strip (Inner Pane)
- `toggleCategoryStrip()`: Toggles the visibility of the leftmost category pane (the strip of icons). Saves state to `localStorage`.
- `initSidebarState()`: Called on page load. Restores the collapsed/expanded state of both the main sidebar and the category strip from `localStorage`.

## Mobile Support
- **Touch Gestures**: Implements swipe-to-open/close functionality using `touchstart` and `touchend` events.
  - Swiping right (from the left edge) opens the sidebar.
  - Swiping left (while the sidebar is open) closes it.

## State Persistence
Uses `localStorage` with the following keys:
- `sidebar_category_collapsed`: Boolean for category strip state.
- `sidebar_full_collapsed`: Boolean for desktop sidebar state.
