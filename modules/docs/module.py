import core
import os

class Docs(core.module.Module):
    """Allows your AI to grab documentation about anything you want. Has OpenLumara documentation included!"""

    settings = {
        "folders": {
            "description": "The folders to grab docs from. These folders can contain any plaintext files you want, such as txt, markdown, and so on, and it can be a nested folder structure.",
            "default": ["openlumara_docs"]
        },
        "insert_system_prompt": {
            "description": "Will make your AI aware of all documentation subjects available to it. Stays small in system prompt because it only lists the top-level folders, which are the topics the documentation is about, not the individual pages.",
            "default": True
        }
    }

    async def on_ready(self):
        folders = self.config.get("folders")
        if folders:
            for folder in folders:
                os.makedirs(core.get_path(os.path.expanduser(folder)).rstrip(os.path.sep), exist_ok=True)

        if self.config.get("insert_system_prompt"):
            self.disabled_tools.append("get_topics")

    async def _get_folder_names(self):
        """translates the folder path list into basenames for the AI"""
        folders = self.config.get("folders")
        if not folders:
            return []

        paths = [f.rstrip(os.path.sep) for f in folders]
        return [os.path.basename(f) for f in paths]

    async def _get_folder_path(self, folder: str):
        """resolves a folder basename to its full path"""
        folders = self.config.get("folders")
        if not folders:
            return None

        for f in folders:
            if os.path.basename(f.rstrip(os.path.sep)) == folder.rstrip(os.path.sep):
                return core.get_path(os.path.expanduser(f)).rstrip(os.path.sep)

    async def on_system_prompt(self):
        folders = await self._get_folder_names()
        if not folders:
            return None
        return f"## Documentation can be fetched from these folders:\n{', '.join(folders)}"

    async def get_topics(self):
        return self.result(await self._get_folder_names())

    async def list(self, folder: str, subfolder: str = None):
        try:
            folder_path = await self._get_folder_path(folder)
            if not folder_path:
                return self.result(f"Folder '{folder}' does not exist within the docs module configuration.", success=False)
            
            # remove the folder from the requested path in case the AI decided to double-add it
            if subfolder and subfolder.startswith(folder):
                subfolder = subfolder[len(folder):]

            base_path = core.sandbox_path(folder_path, subfolder or "")
            
            contents = os.listdir(base_path)
            
            prefix = f"{subfolder}/" if subfolder else ""
            dirs = sorted([f"{prefix}{d}" for d in contents if os.path.isdir(os.path.join(base_path, d))])
            files = sorted([f"{prefix}{f}" for f in contents if os.path.isfile(os.path.join(base_path, f))])
            
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result({
            "subfolders": dirs,
            "files": files,
            "instruction": "You can call docs_list again with a subfolder to navigate deeper, or use docs_read to read a file."
        })

    async def read(self, folder: str, path: str):
        folder_path = await self._get_folder_path(folder)
        # remove the folder from the requested path in case the AI decided to double-add it
        if path.startswith(folder):
            path = path[len(folder):]

        if not folder_path:
            return self.result(f"Folder '{folder}' does not exist within the docs module configuration.", success=False)
        
        target_path = core.sandbox_path(folder_path, path)
            
        try:
            with open(target_path, 'r', encoding="utf-8") as f:
                return self.result(f.read())
        except Exception as e:
            return self.result(str(e), success=False)
