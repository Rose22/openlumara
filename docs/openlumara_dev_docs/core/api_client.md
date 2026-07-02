# Core: The API Client (`core.APIClient`)

The `APIClient` is a wrapper around the OpenAI Python library (`openai.AsyncOpenAI`) that provides a unified, easy-to-use interface for interacting with any OpenAI-compatible AI backend (local or cloud).

## Instance Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `manager` | `Manager` | Reference to the OpenLumara manager instance. |
| `connected` | `bool` | Whether currently connected to the API. |
| `_AI` | `openai.AsyncOpenAI \| None` | The underlying OpenAI async client instance. |
| `_model` | `str \| None` | The currently selected model name. |
| `_messages` | `list` | Reserved for future use. |
| `cancel_request` | `bool` | Flag set to True to cancel an ongoing request. |
| `_connection_error` | `str \| None` | The last connection error message. |
| `_last_connection_attempt` | `float \| None` | Timestamp of the last connection attempt. |
| `_connection_attempts` | `int` | Counter of connection attempts. |
| `_httpx_client` | `httpx.AsyncClient \| None` | The underlying HTTP client (for TLS config). |
| `supports_developer_role` | `bool` | Whether the API supports the `developer` role. |

## Responsibilities

### 1. Connection Management
The `APIClient` handles the complexities of establishing and maintaining a connection to the AI provider:
- **Authentication**: Validates API keys and handles authentication errors with user-friendly messages.
- **Connection Lifecycle**: Provides methods to `connect()`, `disconnect()`, and `reconnect()` to the API server.
- **TLS Support**: Allows for insecure TLS connections (useful for local development with self-signed certificates) via `--insecure-tls` flag.
- **Status Monitoring**: Provides real-time status of the connection, including error messages and configuration checks.
- **Connection Attempts**: Tracks the number of connection attempts for status display.

### 2. Request Orchestration
The client abstracts the details of making requests to the LLM:
- **Unified Interface**: Provides a consistent way to send messages via `send()` (for standard responses) and `send_stream()` (for streaming responses).
- **Parameter Management**: Automatically applies configuration settings:
  - `model.temperature` (default 0.2)
  - `api.max_output_tokens` (default 8192)
  - `model.enable_thinking` (passed via `extra_body.chat_template_kwargs`)
  - `model.reasoning_effort`
  - `api.custom_fields` (arbitrary additional request fields)
- **Tool Integration**: Handles the inclusion and formatting of tool definitions (function calling) for the AI.
- **Request Cancellation**: Provides a mechanism to cancel an ongoing request mid-process using a background task monitor (since OpenAI's async client doesn't natively support an abort signal).
- **Debug Logging**: In debug mode, logs the full request structure (base_url, model, stream, message count, tool count, temperature, etc.) to `debug:request`.

### 3. Response Processing
The `APIClient` translates raw API responses into structured, easy-to-use data:
- **Standard Responses** (`_recv()`): Extracts the message content, reasoning content, and tool calls from the AI's response. Returns a dict with `content`, `reasoning_content`, `tool_calls`, and `role` keys.
- **Streaming Responses** (`_recv_stream()`): An asynchronous generator that yields typed tokens:
  - `content` → Normal text tokens
  - `reasoning` → Thinking/reasoning tokens
  - `tool_call_delta` → Streaming tool call argument updates (with incremental key-value rendering)
  - `tool_calls` → Full assembled tool call object (after streaming completes)
  - `token_usage` → Token usage data from the API
  - `prompt_progress` → Prompt processing progress (if supported by the API)
  - `timings` → Native timing data from the API
  - `error` → Error tokens
- **Error Handling**: Catches and categorizes various API errors (authentication, rate limits, connection issues, etc.) and returns them in a structured format with both user-friendly messages and raw error details.

## Key Methods

| Method | Description |
| :--- | :--- |
| `connect()` | Establishes the connection to the configured API provider. Returns `True` on success, or an error dict for model_not_found. |
| `disconnect()` | Closes the HTTP client and resets all state. Returns `True`. |
| `reconnect()` | Disconnects and then attempts to reconnect. |
| `send(context, system_prompt=True, use_tools=True, tools=None, use_thinking=True, **kwargs)` | Sends a complete context to the AI and returns the processed response dict (or error dict). |
| `send_stream(context, use_tools=True, tools=None, use_thinking=True, **kwargs)` | Sends a context and returns an async generator that yields streamed tokens and metadata. |
| `cancel()` | Sets `cancel_request = True` to signal the ongoing request to abort. |
| `get_connection_status()` | Returns a dict: `{connected, error, url, model, attempts, url_configured, key_configured, model_configured}`. |
| `list_models()` | Retrieves an alphabetically sorted list of available model IDs from the provider. |
| `get_model()` | Returns the current model name. |
| `set_model(name)` | Sets the current model name. |
| `get_last_error()` | Returns the last connection error message string. |
| `_get_user_friendly_message(error_type, exception)` | Maps technical error types to polite, actionable messages. Returns dict with `message` and optionally `raw_error`. |

## Request Structure

The `_request()` method builds the following request body:
```python
{
    "model": self._model,
    "messages": context,
    "tools": tools,
    "stream": stream,
    "temperature": 0.2,  # from config
    "max_completion_tokens": 8192,  # from config
    "extra_body": {
        "chat_template_kwargs": {"enable_thinking": True/False},
        "return_progress": True
    },
    # reasoning_effort (if configured)
    # stream_options.include_usage (if streaming)
    # custom_fields (from config)
    # **kwargs (passed through)
}
```

## Error Types

The `APIClient` categorizes common errors to help the system and user respond appropriately:
- `auth_failed`: The API key is invalid or unauthorized.
- `connection_lost`: The connection to the server was interrupted.
- `rate_limit`: The user has exceeded the allowed number of requests.
- `api_error`: The server returned an error status (400, 500, etc.).
- `model_not_found`: The selected model doesn't exist on the server.
- `cancelled`: The request was manually aborted.
- `blank_request`: The request was empty.
- `processing_failed`: Trouble reading the response from the AI.
- `invalid_response`: The AI returned an unexpected format.
- `not_connected`: The AI service is not connected.
- `unknown`: An unexpected error occurred.
