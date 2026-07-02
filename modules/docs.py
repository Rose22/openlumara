import core

class Docs(core.module.Module):
    """Allows your AI to grab documentation about anything you want. Has OpenLumara documentation included!"""

    settings = {
        "documentation_path": {
            "description": "The folder to grab docs from. It uses folders with markdown files. Leave blank to set it to the built-in openlumara documentation!",
            "default": None
        },
        "insert_system_prompt": {
            "description": "Will make your AI aware of all documentation subjects available to it. Stays small in system prompt because it only lists the top-level folders, which are the topics the documentation is about, not the individual pages.",
            "default": True
        }
    }

    async def on_ready(self):
        docs_path = self.config.get("documentation_path") or core.get_path("docs")
        self.data = core.storage.StorageDict(".", "markdown", path=docs_path)

        # force load so it works in temporary mode
        self.data.load()

    async def on_system_prompt(self):
        if not self.config.get("insert_system_prompt"):
            return None

        topic_str = ", ".join(self.data.keys())

        return f"Topics available to fetch documentation on: {topic_str}"

    def _find_topic(self, topic: str):
        found = False
        for key in self.data.keys():
            if key.lower().strip() == topic.lower().strip():
                found = True
                break
        return found

    async def read(self, topic: str, subject: str = None):
        """Reads documentation about a specific subject within a specific topic. 
        If the subject is not provided or is a folder, it returns a list of available subjects.
        If the subject is a file, it returns the content.

        ALWAYS start with ONLY a topic first, without a subject. Then drill down deeper.

        """

        if not self._find_topic(topic):
            return self.result("Documentation about that topic was not found. Please rely on your own knowledge or try a web search if available.", success=False)

        topic_dict = self.data[topic.lower().strip()]
        
        # If no subject is provided, list everything in the topic
        if not subject or not subject.strip():
            subjects = [k for k in topic_dict.keys()]
            return self.result({
                "subjects": subjects,
                "instructions": "The subjects listed above are paths within this topic. You can call read_documentation again with a specific path as the subject to read the content."
            })

        # Traverse the path
        parts = subject.strip("/").split("/")
        current = topic_dict
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return self.result(f"Subject '{subject}' not found within topic '{topic}'.", success=False)

        # If we ended up on a dictionary, it's a folder
        if isinstance(current, dict):
            prefix = subject.strip("/")
            subjects = [f"{prefix}/{k}" if prefix else k for k in current.keys()]
            return self.result({
                "subjects": subjects,
                "instructions": "The subjects listed above are paths within this folder. You can call read_documentation again with a specific path as the subject to read the content."
            })
        
        # It's a file, return content
        return current
