# WebUI Channel (Backend)

The `Webui` channel is implemented using **FastAPI**, providing a high-performance, asynchronous web interface for interacting with OpenLumara. It serves both as a web server for the frontend and as an API for client-side interactions.

## Key Features

- **Asynchronous Support**: Native `asyncio` support via FastAPI.
- **Real-time Communication**: Uses **WebSockets** (`/ws`) to broadcast message updates, status changes, and metadata updates (like chat titles) to all connected clients.
- **Authentication**: Supports both session-based authentication (for browser users) and Bearer token authentication (for API/client access).
- **Streaming API**: Implements an event-stream (`/stream`) endpoint that allows clients to receive token-by-token AI responses in real-time.
- **Storage Editor**: Provides built-in API endpoints to browse, load, and edit configuration and data files (JSON, YAML, MsgPack, Text, MD) directly through the WebUI.

## API Endpoints

### Chat Management
- `GET /chats`: Lists all available chats with previews.
- `GET /chat/load?id=<id>`: Loads a specific chat.
- `GET /chat/current`: Gets the currently active chat.
- `POST /chat/new`: Creates a new chat.
- `POST /chat/rename`: Renames the current chat.
- `POST /chat/update_category`: Updates the category of a chat.
- `POST /chat/tag`: Adds a tag to the current chat.
- `POST /chat/delete`: Deletes a chat.
- `POST /chat/clear`: Clears the current chat.

### Message Operations
- `GET /messages`: Retrieves all messages in the current chat.
- `GET /messages/since?index=<index>`: Retrieves messages starting from a specific index (efficient for incremental updates).
- `POST /send`: Sends a single message (non-streaming).
- `POST /stream`: Starts an asynchronous stream of AI tokens.
- `POST /edit`: Edits a message by its index.
- `POST /delete`: Deletes a message by its index.
- `POST /upload`: Handles file uploads (images or text files).

### Settings & Configuration
- `GET /settings/load`: Retrieves the current system configuration.
- `POST /settings/save`: Saves new configuration settings.
- `GET /settings/get_module_info`: Retrieves metadata and settings schemas for all loaded modules.

### Storage Editor
- `GET /storage/list`: Lists all files in the data directory.
- `GET /storage/load?file=<path>`: Loads a specific storage file.
- `POST /storage/save`: Saves changes to a storage file.
- `POST /storage/delete-key`: Deletes a key from a dictionary-based file.
- `POST /storage/add-key`: Adds a new key to a dictionary-based file.

### System & API
- `GET /api/status`: Returns the current API connection status, including model and configuration info.
- `POST /api/reconnect`: Attempts to reconnect the channel to the AI API.
- `POST /api/disconnect`: Disconnects the channel from the AI API.
- `GET /api/models`: Lists available models from the configured API.
- `POST /server/restart`: Triggers a server restart.

## WebSocket Events

The WebSocket connection (`/ws`) handles real-time events:
- `message_added`: Broadcasts a new message to all clients.
- `chat_metadata_updated`: Notifies clients of title or tag changes.
- `status_updated`: Communicates connection/status changes.
- `stop`: Signals the API to stop the current request.
- `cancel`: Cancels a specific stream by ID.
