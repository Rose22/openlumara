# OpenLumara Architecture Overview

OpenLumara is designed as a modular, highly efficient AI agent framework. Its architecture is centered around a core management system that orchestrates communication, intelligence, and persistence.

## High-Level Architecture

The system is composed of four primary layers:

1.  **Core Layer (`core/`)**: The heart of the framework. It manages the lifecycle of the application, handles the main loop, orchestrates modules and channels, and manages the API connection.
2.  **Module Layer (`modules/`)**: Provides extensible functionality. Modules can inject themselves into the system prompt, run background tasks, handle user/assistant messages, and provide tools (functions) for the AI to use.
3.  **Channel Layer (`channels/`)**: Defines how the user interacts with the system. Channels (like WebUI, Telegram, or CLI) handle input/output and maintain their own unique context windows.
4.  |**Data/Persistence Layer (`data/`)**: Handles the storage of chats, characters, memories, and other persistent information using efficient formats like JSON and MessagePack.

## Key Components

### The Manager (`core.Manager`)
The central orchestrator. It is responsible for:
- Loading and starting all enabled channels and modules.
- Managing the active channel.
- Handling the main execution loop.
- Managing the API connection.
- Orchestrating the shutdown process.

### Modules (`core.Module`)
The extensibility mechanism. Modules are Python classes that can:
- **Inject Prompts**: Add content to the system prompt or the end of the conversation history.
- **Provide Tools**: Expose functions that the AI can call via function calling.
- **Listen to Events**: React to user messages, assistant messages, or system readiness.
- **Run Background Tasks**: Execute continuous tasks like schedulers or monitors.

### Channels (`core.Channel`)
The interface layer. Each channel:
- Manages its own **Context** (conversation history and token usage).
- Implements its own input/output logic (e.g., web sockets for WebUI, long polling for Telegram).
- Handles command processing (e.g., `/module`).
- Provides a way to "push" announcements to the user.

### Context (`core.Context`)
The intelligence-enabling component. It manages the "view" of the conversation that is sent to the AI, ensuring:
- **Token Efficiency**: Trimming history to fit within limits.
- **Prompt Construction**: Combining system prompts, message history, and end-prompts in the correct order.
- **Role Management**: Ensuring proper turn-taking (system -> user -> assistant).

## Data Flow

1.  **User Input**: A user sends a message through a **Channel**.
2.  **Processing**: The Channel passes the message to the **Manager**, which triggers any relevant **Module** hooks (e.g., `on_user_message`).
3.  **Context Building**: The **Context** builds the full prompt by gathering data from the **Chat** history and all active **Modules**.
4.  **AI Request**: The **Manager** sends the constructed context to the **APIClient**.
5.  **AI Response**: The **APIClient** returns the AI's response.
6.  **Tool Execution (if needed)**: If the AI requests a tool, the **ToolcallManager** executes the corresponding function from a **Module**.
7.  **Output**: The final response (or tool result) is sent back through the **Channel** to the user.
