# Advanced Tips & Tricks

There are a few very useful features that are normally kind of hard to find:

## Flags
When starting OpenLumara from the command line/terminal, there are a few very useful flags:

- `--cli` starts openlumara with only the CLI channel enabled. very useful for terminal-only sessions
- `--pure` starts openlumara with all modules disabled. very useful for quickly talking to the bare LLM!
- `--coder` starts openlumara with all modules except the coder disabled. Pure coding mode!
- `--tmp` puts you into a temporary private mode, where none of your data is saved to disk. All openlumara data that uses StorageList/StorageDict/StorageText (see dev documentation on storage), such as chats, memories, notes, lists, and so on, is all held in temporary RAM rather than saved to disk. When quitting openlumara while it's in temporary mode, all the data from that session will vanish forever. Note that modules that save data in sandboxed folders, like the coder and the sandboxed shell, will still persist data, as those are not using openlumara's storage system, but rather their own folders.

All these flags can be combined, e.g. `--cli --coder`
