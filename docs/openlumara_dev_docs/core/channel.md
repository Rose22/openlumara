# Core: The Channel System (`core.Channel`)

The `Channel` class provides the interface between the user and the OpenLumara agent. While the `Manager` handles the logic, the `Channel` handles the communication.

## Channel Architecture

A channel is a specialized class that manages a specific communication medium (e.g., a terminal, a web browser, or a chat app like Telegram). Each channel has its own unique **Context** window, meaning different channels can have different conversation histories.

## Channel Class Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `settings` | `dict` | Default settings for the channel (merged from parent classes via `__init_subclass__`). |
| `dependencies` | `list` | Python dependencies that need to be installed for the channel to work. |

## Instance Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `manager` | `Manager` | Reference to the OpenLumara manager instance. |
| `name` | `str` | Shorthand alias for the channel's snake_case name. |
| `commands` | `Commands` | The command processing instance for this channel. |
| `context` | `Context` | The channel's own context window (holds chat history and prompt assembly). |
| `console_buffer` | `list` | Used to log system messages. |
| `tc_manager` | `ToolcallManager` | Manages tool call processing and display. |
| `agentic_loop_start` | `int` | Tracks the index of the first message in the current agentic loop (for reasoning preservation). |
| `config` | `ConfigManager` | Configuration wrapper for channel-specific settings. |
| `push_queue` | `asyncio.Queue` | Queue for push-based messages (announcements, reminders). |
| `_queue_task` | `asyncio.Task \| None` | The background task consuming the push queue. |
| `_tool_state` | `dict` | Persistent state for the tool renderer (tracks name, raw_args, keys_state for streaming). |
| `_shutting_down` | `bool` | Flag set to True during shutdown to stop queue processing. |

## Key Responsibilities

### 1. Input/Output (I/O)
The primary role of a channel is to:
- Listen for user input (text, commands, or files).
- Send that user input to the AI via .send() or .send_stream()
- Send the AI's response (text, reasoning, or tool calls) back to the user.
- Support streaming responses for a "real-time" feel.

### 2. Context Management
Each channel owns a `core.Context` object. The channel uses this context to:
- Track the current conversation history.
- Manage token usage.
- Build the complete prompt (system prompt + history + end prompt) to be sent to the AI.

### 3. Command Processing
Channels are responsible for detecting and routing user commands (e.g., `/module`, `/model`). Commands are processed by the `core.Commands` object, which bypasses the AI to perform direct actions.

### 4. Announcement System (Push Queue)
Channels implement a "push queue" that allows the system to send messages to the user *without* the user having to send a message first. This is used for:
- System notifications.
- Reminders from the scheduler.
- Module announcements.

## Core Methods

### Message Sending
| Method | Description |
| :--- | :--- |
| `send(message, commands_authorized=False)` | Sends a message to the AI. Checks for commands, auto-reconnects, adds message to context, runs `on_user_message` hooks, gets context, sends to API, handles tool calls via `tc_manager.process()`, runs `on_assistant_message` hooks, and formats the response. Returns formatted message or None (if tool calls occurred). |
| `send_stream(message, commands_authorized=False)` | Streaming version of `send()`. Yields token dicts with types: `content`, `reasoning`, `tool_call_delta`, `tool_calls`, `token_usage`, `new_chunk`, `error`. Handles token estimation, agentic loops, and recursive tool calling. |

### Message Formatting
| Method | Description |
| :--- | :--- |
| `format_message(message)` | Formats raw AI messages for display. Handles reasoning blocks (with show_reasoning config), conclusion headers, and tool call display via `tc_manager.display_call()`. |
| `format_stream_for_text(stream, chunk_size=None, use_markdown=True)` | Helper for text-based channels. Takes a token stream and yields formatted text tokens. Handles thinking/conclusion headers, tool call rendering, and chunk boundaries. Supports markdown and plain text modes. |
| `_render_tool_token(name, args_str)` | Renders partial/full tool call arguments in a fancy style for streaming. Handles key-value formatting with incremental updates. |

### Push Queue
| Method | Description |
| :--- | :--- |
| `push(message)` | Pushes a message to the push queue (displayed instantly, invisible to AI). Accepts str or dict. |
| `_start_push_queue()` | Starts the background consumer task for the push queue. |
| `_push_consumer()` | Async loop that consumes from `push_queue` and calls `on_push()`. |

### Channel Lifecycle
| Method | Description |
| :--- | :--- |
| `on_ready()` | Called when the entire framework has fully initialized (after "[CORE] Startup complete"). |
| `on_push(message)` | Overridable. Triggered when a message is pushed to the queue. Must be implemented by subclasses. |
| `on_install()` | Overridable. Triggered when the auto-installer installs channel dependencies. |
| `on_uninstall()` | Overridable. Triggered when the auto-installer uninstalls channel dependencies. |

### Logging
| Method | Description |
| :--- | :--- |
| `log(category, message)` | Propagates system messages to all channels via the manager. |
| `log_error(msg, e)` | Logs errors with full tracebacks in debug mode. |
| `on_log(category, message)` | Overridable. Called when a log message is broadcast to all channels. |

### Internal Methods
| Method | Description |
| :--- | :--- |
| `_set_as_active_channel()` | Updates `manager.channel` to this channel and propagates the channel reference to all modules. |
| `_get_disconnection_message()` | Builds a user-friendly disconnection message with error details and configuration hints. |
| `_extract_content(message_dict)` | Extracts text content from a message dict, handling both string and multimodal (list) content. |
| `_shutdown()` | Internal shutdown: sets `_shutting_down` flag and cancels the push queue task. |
| `__init_subclass__()` | Merges settings from parent channel classes into the subclass settings dict. |

## Implementation Workflow (Sending a Message)

1.  **User Input**: The channel receives a message from the user.
2.  **Command Check**: The channel checks if the input is a command (e.g., starts with `/`). If so, it processes it via `Commands.process_input()` and returns the result immediately (flagged as ghost).
3.  **Auto-Reconnect**: If not connected, attempts one reconnect.
4.  **Context Update**: Adds the message to the channel's `Context` chat.
5.  **Module Hooks**: Runs `on_user_message()` on all loaded modules.
6.  **Prompt Assembly**: Gets the full context window via `context.get()`.
7.  **AI Request**: Calls `manager.API.send()` or `manager.API.send_stream()`.
8.  **Tool Calls**: If tool calls are present, processes them via `tc_manager.process()` (recursive chain).
9.  **Module Hooks**: Runs `on_assistant_message()` on all loaded modules.
10. **Output**: Formats and returns the final message.

## Implementation Workflow (Streaming)

1.  **User Input**: Same as above.
2.  **Token Estimation**: Yields estimated token usage before sending.
3.  **Module Hooks**: Runs `on_user_message()` on all loaded modules.
4.  **Stream**: Yields each token from `API.send_stream()`:
    - `content` → yields as-is
    - `reasoning` → yields as-is
    - `tool_calls` → builds recursive request via `tc_manager._build_recursive_request()`, processes via `tc_manager.process()`, yields sub-tokens
    - `token_usage` → sets API token data flag, updates chat token usage
5.  **Final Message**: If no tool calls occurred, adds the assembled assistant message to context and runs `on_assistant_message()` hooks.
