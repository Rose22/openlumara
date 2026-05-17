# Matrix Channel

The `Matrix` channel enables communication with OpenLumara via the Matrix protocol. It connects to a Matrix homeserver and listens for messages in a specific room.

## Features

- **Asynchronous Syncing**: Uses the `matrix-nio` library to maintain a persistent connection to the homeserver via a sync loop.
- **Room Filtering**: Only listens to and responds to messages within a configured `room_id`.
- **Chunked Messaging**: Automatically splits long AI responses into smaller chunks to respect Matrix room/bridge message size limits.

## Configuration Settings

| Setting | Description | Default |
| :--- | :--- | :--- |
| `homeserver` | The URL of the Matrix homeserver (e.g., `https://matrix.org`). | `https://matrix.org` |
| `user_id` | The full Matrix user ID for the bot (e.g., `@bot:matrix.org`). | `None` |
| `access_token` | The Matrix access token for the bot user. | `None` |
| `room_id` | The specific Matrix Room ID to listen to. | `None` |
| `device_id` | The name of the bot's device session. | `OpenLumara` |
| `chunk_size` | The maximum number of characters per Matrix message. | `4000` |

## Implementation Details

### Event Handling
The channel uses an event callback (`_on_matrix_message`) that is triggered whenever a `RoomMessageText` event is received.
1. The bot verifies the sender is not itself.
2. The bot verifies the message is in the correct `room_id`.
3. The message body is sent to the Core framework via `self.send()`.
4. The resulting AI response is then sent back to the room using `_send_chunked()`.

### Sync Loop
The connection is maintained by an asynchronous `sync_forever` loop. This loop is wrapped in a task that provides error handling and can be cancelled during channel shutdown.
