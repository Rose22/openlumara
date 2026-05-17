# Telegram Channel

The `Telegram` channel allows users to interact with OpenLumara through a Telegram bot. It provides a rich, real-time chat experience similar to the WebUI, including support for message streaming and tool call visualization.

## Features

- **Live Streaming**: Supports streaming AI responses to Telegram, providing a "typing" experience.
- **Sequential Processing**: Uses an internal queue to ensure that standard text messages are processed sequentially, preventing overlapping responses.
- **Command Pass-through**: Commands (e.g., `/stop`) are processed immediately and concurrently, allowing users to interrupt ongoing streams.
- **Tool Call Visualization**: Provides pretty-printed visualization of tool calls and their results.
- **Authorized Chat**: Can be configured to only respond to a specific, authorized Telegram Chat ID.

## Configuration Settings

| Setting | Description | Default |
| :--- | :--- | :--- |
| `token` | The Telegram Bot API token. | `TOKEN_HERE` |
| `use_message_streaming` | Whether to stream messages to Telegram. | `True` |
| `stream_tool_calls` | Whether to stream tool call arguments. | `False` |
| `show_reasoning` | Whether to show the model's internal reasoning. | `False` |
| `announce_startup` | Whether to send a startup message to the chat. | `False` |
| `announce_shutdown` | Whether to send a shutdown message to the chat. | `False` |

## Implementation Details

### Message Routing
The channel distinguishes between:
1. **Commands**: Messages starting with the configured command prefix (default `/`) are executed immediately in a separate task. This is crucial for allowing the `/stop` command to interrupt the `_process_queue_worker`.
2. **Normal Messages**: Text messages are added to an `asyncio.Queue` and processed one-by-one by a dedicated worker task.

### Streaming Logic
When `use_message_streaming` is enabled, the channel:
1. Sends a "processing your request..." message.
2. Consumes the token stream from the AI.
3. Periodically edits the Telegram message to include new chunks of content (to avoid hitting Telegram's rate limits).
4. Handles chunking to ensure messages do not exceed Telegram's character limits.

### Authorization
The channel uses `StorageText` to persist the `authorized_chat_id`. The first user to interact with the bot (if no ID is stored) becomes the authorized user for that session.
