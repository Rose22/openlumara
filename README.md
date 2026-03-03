# OptiClaw

This is not your average claw agent! This is a modular, token-efficient AI agent framework written from scratch in Python by hand.

AI Disclaimer: Everything in opticlaw was coded by hand, with the exception of  chan_web.py (the Web UI channel). Here and there I asked the AI how to do certain things in Python, but no code was inserted without me personally auditing it and modifying it. This is not a vibe-coded project.

Features:
- Modular. You can turn any component on or off, including what other claw clones consider core components. Shell access is disabled by default for security.
- Supports multiple communication channels. Right now that's the terminal, web UI, and discord, but i'll be adding more.
- Scheduler system, like openclaw's cronjobs but written from scratch
- Laser focused on token efficiency. You can see how big the context window (input tokens) is at any time, and even see exactly what's being sent
- Fluid identity. The AI can define its own identity! Uses a simple custom system, not IDENTITY.md. Much more token-efficient. It's a module, so you can just turn it off!
- Memory system! Works by letting the AI save memories, or having you ask it to. Also a module, so you can simply turn it off! Saves data in messagepack format, which is compact and very fast.
- Command system that bypasses the AI completely. Lets you do things like force restart the server using `/restart` no matter what the AI is doing.
- Modules are simple python classes with a few custom functions. Very easy to develop for! A proper plugin downloading system is coming later.

# How to install

Clone the git repository, then:
```
cd opticlaw
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run it once. It will create a folder called `data`, and inside it, a file called `config.yml`. Set up your API url and key there, and customize opticlaw to your liking!
