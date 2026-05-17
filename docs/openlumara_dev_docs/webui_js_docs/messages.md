# messages.js Documentation

`messages.js` is responsible for the complex task of rendering chat messages. It handles different message roles (user, assistant, tool, system) and implements OpenAI-compliant turn handling, including assistant reasoning and tool calls.

## Core Rendering Logic

### `renderAllMessages(messages, animate)`
Clears the chat container and iterates through an array of messages to render them. It uses a loop to group assistant messages into "turns" to ensure tool calls and responses are rendered together.

### `collectAssistantTurn(messages, startIndex)`
A critical function that groups multiple messages into a single logical "assistant turn".
- It collects all assistant messages.
- It identifies and includes subsequent `tool` messages that correspond to `tool_calls` within that turn.
- It stops when it encounters a different role or a message that isn't part of the sequence.

### `renderAssistantTurn(messages, index, animate)`
Renders a complete assistant turn as a single cohesive block.
- Creates a `.message-wrapper.ai` element.
- Renders assistant message parts (reasoning, content, tool calls).
- Generates and appends action buttons (Copy, Regenerate, Delete).

### `renderSingleMessage(msg, index, animate)`
The primary function for rendering individual messages (user, tool, command, etc.).
- **Role Detection**: Determines the CSS class based on the message role and content (e.g., `.user`, `.ai`, `.tool`, `.command_response`, `.announce`).
- **Parsing**: Uses `parseMessageContent` to detect system announcements or command outputs.
- **Content Rendering**:
  - Renders Markdown for standard content.
  - Renders specialized blocks for tool calls, schedules, and commands.
- **Code Highlighting**: Applies syntax highlighting to code blocks.

## Specialized Rendering

### Assistant Message Parts
`renderAssistantMessageParts` ensures the correct order of content for an assistant:
1. **Reasoning**: Renders the `reasoning_content` block (if present).
2. **Content**: Renders the main message text via Markdown.
3. **Tool Calls**: Renders tool calls and their corresponding responses.

### Tool Call Rendering
`renderToolCallsWithResponses` creates interactive cards for tool interactions.
- Each card shows the tool name, arguments, and status (pending/completed).
- It can expand/collapse to show detailed arguments and the resulting tool response.

### JSON & Tool Response Rendering
`renderJsonResponseCompact` provides a beautiful, depth-aware, and compact way to display JSON data returned by tools.
- Handles primitives (string, number, boolean, null).
- Recursively renders arrays and objects.
- Implements smart truncation and "expandable" summaries for deeply nested data.

## Helper Functions
- `parseMessageContent(content)`: Extracts metadata from special message prefixes like `[System Type]` or `[Command Output]`.
- `getRoleDisplay(role, content)`: Determines the human-readable name for a message sender (e.g., "You", "AI", "Command").
- `createActionButtons(role, index, content)`: Generates the UI buttons for interacting with messages (Copy, Edit, Regenerate, Delete).
