# Documentation: `export.js`

## Overview
`export.js` handles the functionality for exporting chat histories into different file formats. It supports exporting the current chat as JSON, Markdown, or plain Text, preserving the structure of the conversation, including AI reasoning and tool call results.

## Primary Functions

### `async exportChat(format)`
The main function for triggering a chat export.
1. **Title Retrieval**: Attempts to fetch the current chat's title to use as the base filename.
2. **Sanitization**: Sanitizes the chat title to ensure it is a valid filename (removing characters like `/`, `\`, `:`, etc.).
3. **Message Grouping**: Fetches all messages and groups them into "turns".
    - **Assistant Turns**: Groups an assistant message with any subsequent tool calls or tool responses that belong to that specific turn.
    - **Single Turns**: Treats user messages or other single messages as individual turns.
4. **Format Logic**:
    - **JSON**: Exports the raw array of message objects.
    - **Markdown**: Generates a human-readable `.md` file. It includes:
        - AI reasoning blocks.
        - Formatted tool call results (using code blocks for JSON).
        - Clear markers for user and assistant roles.
    - **Text**: Generates a simplified `.txt` file with plain text representations of all elements.
5. **Download Trigger**: Creates a `Blob` of the formatted content and triggers a browser download via a hidden anchor element.

## Export Formats

| Format | Extension | Description |
| :--- | :--- | :--- |
| `json` | `.json` | A machine-readable dump of the entire message array. Best for backups or importing into other tools. |
| `markdown` | `.md` | A highly readable, structured document. Best for humans and documentation. Supports Markdown syntax for code and reasoning. |
| `text` | `.txt` | A basic, plain-text version of the chat. Best for maximum compatibility. |

## Tool Call Formatting
During export (especially in Markdown and Text), tool calls are formatted to be human-readable:
- **Markdown**: Uses `> **ToolName**` blockquotes and ` ```json ` code blocks for responses.
- **Text**: Uses `[ToolName]:` prefixes.

## Error Handling
The function is wrapped in a `try...catch` block to handle errors during title retrieval, message fetching, or file generation, logging errors to the console to prevent the UI from crashing.
