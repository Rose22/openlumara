# input.js Documentation

`input.js` manages the global keyboard shortcuts, input field behavior, and the state of the message input area.

## Keyboard Shortcuts

The script listens for global `keydown` events to provide power-user functionality.

### Global Shortcuts (Ctrl / Cmd)
- **Ctrl + Enter**: Sends the current message.
- **Ctrl + L**: Clears the current chat.
- **Ctrl + S**: Opens the Settings modal.
- **Ctrl + F**: Toggles the Chat Search bar.
- **Ctrl + E**: Opens the Export modal.
- **Ctrl + /**: Opens the Shortcuts help modal.
- **Ctrl + B**: Toggles the Sidebar visibility.

### Context-Aware Shortcuts
- **Ctrl + Space**: Toggles the Global Search overlay.
- **Escape**:
  - If Global Search is open: Closes it.
  - If a Modal is open: Closes the modal.
  - If Chat Search is open: Clears the search.
  - If Sidebar is open (Mobile): Closes the sidebar.
  - If Streaming is in progress: Stops the current generation.

### Search Navigation (In-Chat Search)
- **Enter**: Navigates to the next search result.
- **Shift + Enter**: Navigates to the previous search result.
- **Escape**: Clears the search.

## Input Field Behavior

### Auto-Resizing
The `message` textarea automatically grows in height as the user types, up to a maximum of 200px. This is handled via the `input` event listener.

### Input State Management
The `setInputState(disabled, showTyping, showStop)` function manages the UI state of the input area during streaming:
- **`disabled`**: Disables the Send button (but keeps the input enabled so users can type commands).
- **`showTyping`**: Shows/hides the "typing..." indicator.
- **`showStop`**: Hides the Send button and shows the Stop button.
