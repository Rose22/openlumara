# init.js Documentation

`init.js` serves as the primary entry point for the OpenLumara WebUI. It manages the initial setup, WebSocket connections, and high-level lifecycle events like cleanup.

## Key Functions

### `cleanup()`
Cleans up resources to prevent memory leaks and hanging connections when the user leaves the page.
- Clears `pollIntervalId`.
- Clears `apiStatusIntervalId`.
- Clears `reconnectTimer`.
- Closes the WebSocket connection (`window.socket`).
- Hides the connection status UI.

### `init()`
The main asynchronous initialization routine.
1. **Permissions**: Requests notification permissions.
2. **Connection Check**: Calls `checkConnection()` to verify server availability.
3. **State Restoration**: If connected, calls `restoreCurrentChat()` to load the previous session.
4. **UI Setup**:
   - Applies the user's saved font size from `localStorage`.
   - Calls `loadTheme()`, `loadChats()`, and `initTagFilterState()`.
   - Sets up a resize listener for the title bar.
5. **WebSocket Management**:
   - Defines `connectWebSocket()` which establishes a connection to `/ws`.
   - Handles `onopen`: Sets `isConnected = true`.
   - Handles `onmessage`: Parses JSON and dispatches events:
     - `message_added`: Triggers `handleNewMessage()`.
     - `chat_metadata_updated`: Updates the title bar and reloads chats.
     - `status_updated`: Updates the connection status UI.
   - Handles `onclose`: Implements an exponential backoff reconnection strategy.
6. **Message Handling**:
   - `handleNewMessage(msg)`: Renders new messages if the user isn't currently editing or if the assistant isn't streaming.
7. **Polling**: Starts a periodic API status check using `apiStatusIntervalId`.

## Lifecycle
- **Service Worker**: Registers `sw.js` on window load for offline capabilities/caching.
- **Cleanup**: Listens for the `beforeunload` event to trigger `cleanup()`.
