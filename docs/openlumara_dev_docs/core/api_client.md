# Core: The API Client (`core.APIClient`)

The `APIClient` is a wrapper around the OpenAI Python library that provides a unified, easy-to-use interface for interacting with any OpenAI-compatible AI backend (local or cloud).

## Responsibilities

### 1. Connection Management
The `APIClient` handles the complexities of establishing and maintaining a connection to the AI provider:
- **Authentication**: Validates API keys and handles authentication errors.
- **Connection Lifecycle**: Provides methods to `connect()`, `disconnect()`, and `reconnect()` to the API server.
- **TLS Support**: Allows for insecure TLS connections (useful for local development with self-signed certificates).
- **Status Monitoring**: Provides real-time status of the connection, including error messages and configuration checks.

### 2. Request Orchestration
The client abstracts the details of making requests to the LLM:
- **Unified Interface**: Provides a consistent way to send messages via `send()` (for standard responses) and `send_stream()` (for streaming responses).
- **Parameter Management**: Automatically applies configuration settings from `config.yml`, such as `temperature`, `max_completion_tokens`, and `reasoning_effort`.
- **Tool Integration**: Handles the inclusion and formatting of tool definitions (function calling) for the AI.
- **Request Cancellation**: Provides a mechanism to cancel an ongoing request mid-process.

### 3. Response Processing
The `APIClient` translates raw API responses into structured, easy-to-use data:
- **Standard Responses**: Extracts the message content, reasoning content, and tool calls from the AI's response.
- **Streaming Responses**: An asynchronous generator that yields tokens, reasoning chunks, and tool call deltas as they arrive from the server.
- **Error Handling**: Catches and categorizes various API errors (authentication, rate limits, connection issues, etc.) and returns them in a structured format.
- **Token Usage Tracking**: Captures and yields token usage data provided by the API, enabling real-time monitoring.

## Key Methods

| Method | Description |
| :--- | :--- |
| `connect()` | Establishes the connection to the configured API provider. |
| `disconnect()` | Closes the connection and cleans up resources. |
| `reconnect()` | Disconnects and then attempts to reconnect. |
| `send(context, tools=None, ...)` | Sends a complete context to the AI and returns the processed response. |
| `send_stream(context, tools=None)` | Sends a context and returns an async generator that yields streamed tokens and metadata. |
| `cancel()` | Signals that the current request should be aborted. |
| `get_connection_status()` | Returns a dictionary containing the current state of the API connection. |
| `list_models()` | Retrieves an alphabetically sorted list of available models from the provider. |

## Error Handling

The `APIClient` categorizes common errors to help the system and user respond appropriately:
- `auth_failed`: The API key is invalid or unauthorized.
- `connection_lost`: The connection to the server was interrupted.
- `rate_limit`: The user has exceeded the allowed number of requests.
- `api_error`: The server returned an error status.
- `cancelled`: The request was manually aborted.
