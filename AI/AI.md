hey! It's good to have you, AI agent. This is Openlumara, an agent harness. It competes with 
Claude code, Claude chat, and openwebui. Read this entire file before working on OpenLumara - it is
 more than worth it. This doc is not a deep dive, and it's not meant to be. 
Go read src to understand exactly how things work.
It's a fully opensource project made by rose22, Rosie with Local AI since February 2026. 
Sincerely, welcome. 
-Written by Starwaves1 October 26 2026 3:53pm EST

This project is unlike most opensource projects that are Vibecoded without effort, or 
even knowledge, of the architecture or key decisions. You'll find that Openlumara is
not feature-complete with Claude or Hermes Agent yet it is filled with surprisingly good design
 decisions from the Module system, to container choices, to the care spent on auto-scrolling.
The development of OL has been careful, thoughtful, and the vast majority was hand-written by Rosie.
The codebase is mostly human made and maintained. When there is AI, it's
often local. AI-written code is often re-written by a human. As a human writing this to an AI,
 please write lean, human maintainable code. Some things humans *really* appreciate
are:
1. Simple, readable, concise
2. Concise helpful comments. Not paragraphs. Short sentences saying what it is/does when it's not
 obvious merely by looking at that one section of code. Don't explain that which is plainly written
 in the code. print("word") doesn't need to be explained. Look at and copy the human style of writing
 lean, readable code with concise, helpful, and non-redundant comments.
3. Looks like a human absolutely would have written it.
4. Call out what model you are. (required). When making any PRs, or modifying code say what model
 you are like this:

//AI Written: Deepseek V4.1 flash:
(code)

This makes it a breese to review the diffs and approve/edit/remove. 

About the project:
AI is amazing. It's why we made this. This project has a dual goal: Make it capable/intuitive/great 
while structurally preventing AI-induced failures such as prompt injection,
destruction, data exfiltration, etc. It does this by (by default) giving the AI tools via modules 
instead of unrestricted bash to the user's home dir. That's where Modules come in and they're
the secret sauce of OL.

Goals: Context efficiency, capability, safety, and modularity.
Enabled modules are loaded at session start. They live in modules/ and are managed by the user
 in settings. They also allow for incredible frontend abilities, not just backend capability.
 See: meditation module for frontend capability.

 "We want to reserve human time and attention for things only humans can handle, while making sure 
 we have enough automation to cover the rest." Addy Osmani from Claude Code

 Help us with the process by reviewing your own code before maintainers look at it.
 This can be in the form of reviewing the change from a fresh context window, running tests, etc.

 