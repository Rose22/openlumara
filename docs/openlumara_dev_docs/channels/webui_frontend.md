# WebUI Frontend

The WebUI frontend is a modern, responsive Single Page Application (SPA) designed to provide a smooth, real-time chat experience. It is served as static files and interacts with the FastAPI backend via REST API and WebSockets.

## Architecture

The frontend architecture is modular, with specific JavaScript files handling distinct responsibilities. This modularity allows for easier maintenance and clear separation of concerns.

### Core JavaScript Modules

The following files are loaded in a specific order to ensure dependencies are met:

| File | Responsibility |
| :--- | :--- |
| `init.js` | Handles application initialization, WebSocket connection management, service worker registration, and global state. |
| `messages.js` | Manages the rendering of chat messages, including complex logic for assistant turns, tool calls, and reasoning blocks. |
| `chats.js` | Handles the sidebar, listing chats, and loading/switching between chat sessions. |
| `send.js` | Manages the input field, message sending (both standard and streaming), and file uploads. |
| `sidebar.js` | Controls the sidebar UI, including chat list interaction and navigation. |
| `polling.js` | Provides fallback/heartbeat mechanism for checking API status. |
| `storage_editor.js` | Implements the UI for the built-in data/storage editor. |
| `modals.js` | Manages various UI modals (settings, chat info, etc.). |
| `themes.js` / `theming.js` | Handles theme switching and application of CSS variables. |
| `markdown.js` | Integrates markdown parsing for message content. |
| `utils.js` | Contains common utility functions used across the app. |
| `notif.js` | Manages browser notifications. |
| `status.js` | Handles the visual representation of connection and API status. |
| `tags.js` | Manages chat tagging and filtering. |
| `search.js` | Implements chat search functionality. |
| `export.js` | Handles exporting chat history. |
| `upload.js` | Manplements the file upload process. |
| `audio.js` | Handles audio playback/features (if applicable). |
| `responsive.js` | Ensures the UI adapts to different screen sizes. |

## Key Implementation Details

### Real-time Updates (WebSockets)
The application maintains a persistent WebSocket connection to the backend. This connection is used to:
- **Receive new messages**: When a message is added (by the user or the AI), the backend broadcasts a `message_added` event, which the frontend uses to render the message immediately without a page refresh.
- **Sync metadata**: Changes to chat titles or tags are broadcast via `chat_metadata_updated`.
- **Handle status updates**: Connection or API status changes are relayed via `status_updated`.

### Message Rendering & Turn Handling
The `messages.js` module implements sophisticated rendering logic to support the "OpenAI-style" message structure:
- **Assistant Turns**: Instead of rendering every assistant message as a separate bubble, the frontend groups multiple assistant messages (including tool calls and tool responses) into a single coherent "turn" for a cleaner UI.
- **Reasoning Blocks**: Supports the rendering of "thought" or "reasoning" blocks, which can be expanded or collapsed by the user.
- **Tool Call Visualization**: Tool calls are rendered as specialized cards that show the tool name, arguments, and the resulting response from the tool.

### State Management
The application uses a combination of:
- **Global Variables**: For core state like `isConnected`, `chat`, and `lastMessageIndex`.
- **LocalStorage**: To persist user preferences such as `fontSize`, `theme`, and `reasoningExpandedByDefault`.
- **DOM-based State**: Using `data-*` attributes (e.g., `data-index`) to track message positions and facilitate efficient updates.

### PWA Support
The WebUI is configured as a Progressive Web App (PWA), including a `manifest.json` and a service worker (`sw.js`), allowing for offline capabilities and an app-like experience on mobile devices.
