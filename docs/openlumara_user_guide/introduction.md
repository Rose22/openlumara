# Welcome to OpenLumara! 🌟

Think of OpenLumara as your very own personal AI assistant. To make it work its magic, it uses a few different parts working together:

## How it works

- **The Brain (Core)**: This is the heart of the system. It manages everything, from talking to the AI to making sure your messages get where they need to go.
- **The Tools (Modules)**: These are special abilities you can give your AI. They let it do things like run tasks in the background or use specific functions to help you.
- **The Ways You Talk (Channels)**: This is how you and the AI communicate. You can use a website, Telegram, Discord, or even a simple command line!
- **The Memory (Data)**: OpenLumara remembers your chats, your settings, and who you are, so it can be a better assistant every time you talk to it.

When you send a message, the Brain takes it, checks if any Tools are needed, builds the perfect message for the AI, and then sends the AI's response back to you through your favorite Channel!

# OpenLumara's purpose

This is written from the creator's perspective (Rose22, https://github.com/Rose22)

I created OpenLumara because i noticed most of the popular agents were causing a huge strain on datacenters, causing massive waste of tokens and by extension, energy, and humanity's resources. On top of that, many agents *claim* to work with local models, but since they are designed to work with multiple API requests at once, they often put local systems under very heavy load, tend to be very slow, and their agentic functionality (like heartbeats) disrupts critical functions. OpenLumara was designed from the ground up to solve many of these problems, by focusing on keeping the system prompt as small as possible, not relying on multiple concurrent requests processing at the same time, and testing with small local models while developing it. Due to its modular nature it's very easy to make it work with your setup because you can turn off anything you don't need.

In addition to that, the security of many popular agents was also lackluster. They all rely on a `SKILL.md` system that tell an agent how to do something - usually by invoking a shell command. Not only is a skill.md file usually many words (and thus tokens) in size, but they also force you to let your AI have total access to a command shell. OpenLumara solves this by using Tools instead, and granting the AI agent only exactly the tools it needs to do what you want it to do. For example, if you want your agent to access a website, the modules you can use for that are web_reader and http. They both come with a blacklist and whitelist so you can decide exactly which domains your AI can and cannot access.

Everything that accesses the filesystem is sandboxed by default. The module that lets your AI see your configuration values redacts all API keys, usernames and passwords without relying on prompting, instead redacting all known keys matching patterns such as `token`, `username`, `password`, etc, using pure python code. OpenLumara's security is built to enforce security *around* the model, not to rely on the model to provide security.

OpenLumara is free and open source and will always be free and open source.
