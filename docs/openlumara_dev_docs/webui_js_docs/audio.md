# Documentation: `audio.js`

## Overview
`audio.js` implements the `TypewriterAudioManager`, a high-performance audio system designed to play sound effects (like typewriter clicks) during real-time text streaming. It uses **IndexedDB** for persistent storage of audio files and the **Web Audio API** for low-latency, non-blocking playback.

## Architecture

### Storage (IndexedDB)
To avoid repeated network requests and heavy disk I/O, audio files are stored in a browser-managed IndexedDB database named `TypewriterSoundsDB`.
- **`sounds` Object Store**: Stores audio files using their ID (e.g., `typewriter`, `completion`) as the key.
- **Persistence**: Once a user uploads a sound, it remains in the database across sessions.

### Audio Engine (Web Audio API)
The system uses a centralized `AudioContext` and a single `masterGainNode` to manage all sound playback.
- **Master Gain Node**: A single volume control applied to all sounds, which improves performance by avoiding the creation of new gain nodes for every keystroke.
- **Memory Buffers**: Decoded audio data is cached in memory (`this.buffers`) for instantaneous playback during the typewriter effect.

## Primary API

### `init()`
Initializes the manager.
1. Loads the user's volume preference from `localStorage`.
2. Opens the `TypewriterSoundsDB` IndexedDB.
3. Pre-loads existing sounds from the database into memory buffers.

### `play(id)`
Plays a cached sound effect.
- **Non-Blocking**: Uses `setTimeout(..., 0)` to ensure that the audio playback logic does not interfere with the high-frequency updates of the typewriter animation loop.
- **Autoplay Handling**: Automatically calls `ctx.resume()` if the `AudioContext` is suspended due to browser autoplay policies.

### `saveFile(id, file)`
Uploads a new audio file to the system.
1. Reads the file as an `ArrayBuffer` via `FileReader`.
2. Saves the raw buffer to **IndexedDB**.
3. Decodes the buffer and caches it in the **in-memory buffer** for immediate use.

### `setVolume(vol)`
Sets the global volume (0.0 to 1.0).
- Updates `localStorage`.
- Immediately updates the `masterGainNode` to reflect the change without needing to restart playback.

### `deleteFile(id)`
Removes an audio file from both the in-memory cache and the IndexedDB storage.

## Workflow Example: Typewriter Effect
1. The `send.js` module starts a typewriter animation.
2. For every character being "typed", `TypewriterAudioManager.play('typewriter')` is called.
3. The manager finds the pre-decoded buffer in memory.
4. The buffer is connected to the `masterGainNode` and played instantly, synchronized with the visual character appearance.
