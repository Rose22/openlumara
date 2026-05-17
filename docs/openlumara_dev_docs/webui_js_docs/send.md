# Documentation: `send.js`

## Overview
`send.js` is the core JavaScript module responsible for managing the message sending process, handling real-time streaming responses from the AI, and dynamically updating the User Interface (UI). It supports advanced features such as reasoning (thinking) blocks, multimodal input, file uploads, tool call streaming (with incremental JSON parsing), and a typewriter animation effect.

## Core State Management

The module maintains several global variables to track the state of the current stream:

| Variable | Description |
| :--- | :--- |
| `streamSegments` | An array of objects representing different parts of the stream (e.g., `reasoning`, `content`, `tool_calls`). |
| `segCounter` | A counter used to assign unique IDs to each segment. |
| `activeTypewriterSegId` | Tracks the ID of the segment currently undergoing the typewriter animation. |
| `streamingToolCalls` | An object storing the current state of ongoing tool calls. |
| `toolCallsContainer` | A reference to the DOM element containing all active tool call cards. |
| `manuallyCollapsedReasoning` | A `Set` containing IDs of reasoning blocks that the user has manually collapsed. |
| `isStreaming` | Boolean flag indicating if a request is currently in progress. |
| `isDataStreaming` | Boolean flag indicating if the actual data payload is still arriving. |

## Primary Functions

### `async send(providedContent = null)`
The main entry point for sending a message.
1. **Preparation**: Determines if it's a new message or a regeneration. Extracts text from the input field or provided content.
2. **Command Handling**: If the message starts with `/` or `STOP`, it routes to `sendCommand`.
3. **Connectivity Check**: Verifies if the API is connected via `/api/status`.
4. **Payload Construction**: Builds the JSON payload, including text content and any queued file uploads (multimodal support).
5. **Streaming Initiation**: Performs a `POST` request to `/stream`.
6. **Stream Processing**: Reads the response stream line-by-line, parsing `data: ` prefixed JSON chunks.
7. **UI Updates**: Manages the transition from a "Sending..." placeholder to the AI message wrapper, handles the typewriter effect, and renders tool calls.
8. **Finalization**: Cleans up state, updates chat indices, and enables input once the stream is complete or errors occur.

### `async sendCommand(message)`
Handles special user commands:
- `/connect`: Attempts to reconnect to the API.
- `/stop` or `STOP`: Triggers `stopGeneration` to abort the current process.

### `async stopGeneration(sent_from_command = false)`
Aborts the current stream and notifies the backend to stop processing. It resets the typewriter queue and finalizes any partially rendered content to ensure a clean UI state.

## Streaming Segment Types

The module categorizes stream data into specific types to allow for specialized rendering:

| Type | Description | Rendering Behavior |
| :--- | :--- | :--- |
| `reasoning` | The AI's "thinking" process. | Rendered in a collapsible block with a "Thinking" or "Thoughts" label. |
| `content` | The actual message text. | Rendered as Markdown. Supports an optional typewriter effect. |
| `tool_calls` | Metadata about tools being called. | A container for individual tool call cards. |
| `tool_call_delta` | Incremental updates to a tool call. | Updates the arguments of an existing tool call card in real-time. |
| `tool` | The result of a tool execution. | Populates the "Response" section of a tool call card. |

## Tool Call Management

The module implements a robust system for handling tool calls during streaming:

### Incremental JSON Parsing
Because tool arguments are streamed as incomplete JSON strings, `parseAccumulatedJson` and `extractJsonValue` are used to gracefully parse partial data. This allows the UI to show key-value pairs as they are being typed, even if the JSON structure is not yet valid.

### Tool Call UI
- **`renderStreamingToolCall`**: Creates or updates a "card" for each tool call. It shows the function name, the current arguments (parsed), and a "streaming" status.
- **`handleToolResponse`**: When a tool's result is received, the card is updated to show the "Response" section and marked as "done".
- **`addProcessingIndicator`**: Shows a "processing result..." spinner below a tool call while waiting for the final response.

## UI & Animation

### Typewriter Effect
Implemented via `startTypewriterProcessSegments`, this function queues characters from the stream and renders them one by one with a configurable delay, creating a natural typing appearance.

### Optimistic UI
The module uses `createPlaceholderUserMessage` to immediately show the user's message in the chat as "Sending...", providing instant feedback before the network request completes.

## Error Handling

The module handles errors at multiple levels:
- **Server Errors**: `handleServerError` processes non-OK HTTP responses (e.g., 500, 503, 401).
- **Inline Stream Errors**: `handleInlineError` processes error metadata sent *within* a successful SSE stream.
- **Network Errors**: `handleCatchError` catches low-level fetch or connection failures.
