# CLI Channels

OpenLumara provides two types of Command Line Interface (CLI) channels: a full-featured interactive CLI and a simplified non-streaming CLI.

## 1. Interactive CLI (`Cli`)

The `Cli` channel provides a rich, terminal-based interactive session using `prompt_toolkit`.

### Features
- **Rich Terminal UI**: Uses `prompt_toolkit` for styled text, including colors for prompts, reasoning, tool calls, and errors.
- **History Support**: Automatically saves and loads command history from a local file.
- **Advanced Tool Call Rendering**: Features a `ToolCallRenderer` that provides a beautiful, structured visualization of tool calls and their arguments directly in the terminal.
- **Real-time Stream Rendering**: Supports real-time rendering of AI tokens, including reasoning blocks and tool call deltas.

### Implementation Highlights
- **Tool Rendering**: The `ToolCallRenderer` handles the "live" updates of tool arguments, allowing the user to see the JSON arguments being built in real-time.
- **Turn Grouping**: The CLI intelligently groups assistant messages and their subsequent tool responses into single logical "turns" in the terminal.

## 2. Non-Streaming CLI (`CliNonstream`)

The `CliNonstream` channel is a minimal, lightweight implementation designed for simple, sequential interactions.

### Features
- **Simplicity**: A basic loop that takes user input and prints the direct response from the AI.
- **Low Overhead**: Does not support streaming or complex UI elements, making it suitable for environments with limited terminal capabilities or for simple automation tasks.

### Implementation Highlights
- **Synchronous Flow**: It uses a simple `input()` loop and waits for the full response from `self.send()` before printing the result.
