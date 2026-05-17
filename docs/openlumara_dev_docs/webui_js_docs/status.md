# status.js Documentation

`status.js` manages the visual connection status indicators for both the local server and the remote API. It provides real-time feedback to the user about the connectivity state of the application.

## Connection Indicators

### Server Connection (Local)
- **Status Dot**: A small dot in the UI (`statusDot`) that changes color based on the connection state (`connected`, `connecting`, `disconnected`).
- **Announcement Messages**: Large, formatted messages injected into the chat stream to notify the user of major connection events (e.g., "Disconnected from server", "Reconnecting...").
- **`showConnectionStatus(status)`**: Creates and inserts a status announcement into the chat.
- **`hideConnectionStatus()`**: Removes the active status announcement from the chat.

### API Connection (Remote)
- **API Status Dot**: A dot in the UI (`apiStatusDot`) that reflects the state of the remote AI API.
  - **Connected**: Green dot.
  - **Not Configured**: Warning (yellow/orange) dot.
  - **Disconnected**: Red dot.
- **`updateApiStatus(status)`**: Updates the API dot's color and accessibility attributes based on the response from `/api/status`.

## Connectivity Management

### Connection Checks
- **`checkConnection()`**: Periodically verifies the connection to the local server by attempting to fetch `/messages`.
  - If a connection is lost, it triggers `handleConnectionError()`.
  - If a connection is restored, it triggers `reconnectAttempts = 0` and shows a "Reconnected" message.
- **`checkApiStatus()`**: Fetches the current status of the remote API via `/api/status`.

### Reconnection Logic
- **`handleConnectionError()`**: Detects when the server has gone offline and initiates the reconnection process.
- **`scheduleReconnect()`**: Implements a retry loop using `setTimeout`. It increments `reconnectAttempts` and attempts to call `checkConnection()` again after a delay.
- **`reconnectApi()`**: Attempts to manually trigger an API reconnection via the `/api/reconnect` endpoint.

### Error Handling
- **`showApiConfigError(message, errorType, action)`**: Renders a highly visible, styled error card directly in the chat stream.
  - It handles specific error types (e.g., `auth_failed`, `config_missing`) by providing tailored messages and context-aware action buttons (like "Retry Connection" or "Open Settings").
