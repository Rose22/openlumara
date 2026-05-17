# Core: The Channel System (`core.Channel`)

The `Channel` class provides the interface between the user and the OpenLumara agent. While the `Manager` handles the logic, the `Channel` handles the communication.

## Channel Architecture

A channel is a specialized class that manages a specific communication medium (e.g., a terminal, a web browser, or a chat app like Telegram). Each channel has its own unique **Context** window, meaning different channels can have different conversation histories or different token limits.

## Key Responsibilities

### 1. Input/Output (I/O)
The primary role of a channel is to:
- Listen for user input (text, commands, or files).
- Send messages (text, reasoning, or tool calls) back to the user.
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

| Method | Description |
| :--- | :--- |
| `send(message)` | Sends a single message to the AI and returns the response. |
| `send_stream(message)` | Sends a message and returns an asynchronous generator for streaming the response. |
| `announce(message, type)` | Pushes a system message/notification to the user. |
| `format_message(message)` | Formats raw AI messages (including reasoning and tool calls) for display in the channel. |
| `_set_as_active_channel()` | Updates the `Manager` to reflect that this channel is currently receiving user input. |

## Implementation Workflow (Sending a Message)

1.  **User Input**: The channel receives a message from the user.
2.  **Command Check**: The channel checks if the input is a command (e.g., starts with `/`). If so, it processes it and returns the result immediately.
3.  **Context Update**: If it's a regular message, the channel adds it to its `Context`.
4.  **Prompt Assembly**: The channel asks its `Context` to build the full prompt for the AI.
5.  **AI Request**: The channel calls `manager.API.send(context)`.
6.  **Response Handling**: The AI's response is received, processed (including tool calls), and added to the `Context`.
7.  **Output**: The final formatted response is sent back to the user via the channel's output mechanism.
