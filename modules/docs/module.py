import core
import channels.webui.api as webui
import os

class Docs(core.module.Module):
    """Allows your AI to grab documentation about anything you want. Has OpenLumara documentation included!"""

    category = "core"

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

    @core.module.tool
    async def get_topics(self):
        return self.result(await self._get_folder_names())

    @core.module.tool
    async def list(self, folder: str, subfolder: str = None):
        try:
            folder_path = await self._get_folder_path(folder)
            if not folder_path:
                return self.result(f"Folder '{folder}' does not exist within the docs module configuration.", success=False)
            
            # remove the folder from the requested path in case the AI decided to double-add it
            if subfolder == folder:
                subfolder = ""
            elif subfolder and subfolder.startswith(folder + os.path.sep):
                subfolder = subfolder[len(folder) + 1:]

            base_path = core.sandbox_path(folder_path, subfolder or "")

            contents = core.sandbox_listdir(folder_path, subfolder or "")

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

    @core.module.tool
    async def read(self, folder: str, path: str):
        folder_path = await self._get_folder_path(folder)
        # remove the folder from the requested path in case the AI decided to double-add it
        if path == folder:
            path = ""
        elif path.startswith(folder + os.path.sep):
            path = path[len(folder) + 1:]

        if not folder_path:
            return self.result(f"Folder '{folder}' does not exist within the docs module configuration.", success=False)
        
        try:
            fd = core.sandbox_open(folder_path, path, os.O_RDONLY)
            with os.fdopen(fd, "r", encoding="utf-8") as f:
                return self.result(f.read())
        except Exception as e:
            return self.result(str(e), success=False)

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # webui extension routes for the docs sidebar browser.
    # private methods are ignored by the tool loader; @webui.route exposes
    # them under /api/ext/docs/<path>.

    @webui.route("folders")
    async def _route_folders(self, body=None, query=None):
        """doc folder basenames for the sidebar dropdown"""
        return await self._get_folder_names()

    @webui.route("list")
    async def _route_list(self, body=None, query=None):
        """one directory level: {subfolders: [...], files: [...]} relative paths"""
        folder = (query or {}).get("folder", "")
        subfolder = (query or {}).get("subfolder", "") or None

        if not folder:
            return self.result("no folder given", success=False)

        folder_path = await self._get_folder_path(folder)
        if not folder_path:
            return self.result(f"folder '{folder}' does not exist", success=False)

        if subfolder == folder:
            subfolder = ""
        elif subfolder and subfolder.startswith(folder + os.path.sep):
            subfolder = subfolder[len(folder) + 1:]

        try:
            base_path = core.sandbox_path(folder_path, subfolder or "")
            contents = core.sandbox_listdir(folder_path, subfolder or "")
        except Exception as e:
            return self.result(str(e), success=False)

        prefix = f"{subfolder}/" if subfolder else ""
        dirs = sorted([f"{prefix}{d}" for d in contents if os.path.isdir(os.path.join(base_path, d))])
        files = sorted([f"{prefix}{f}" for f in contents if os.path.isfile(os.path.join(base_path, f))])

        return {"subfolders": dirs, "files": files}

    @webui.route("read")
    async def _route_read(self, body=None, query=None):
        """raw text of a doc file"""
        folder = (query or {}).get("folder", "")
        path = (query or {}).get("path", "")

        if not folder or not path:
            return self.result("folder and path are both required", success=False)

        folder_path = await self._get_folder_path(folder)
        if not folder_path:
            return self.result(f"folder '{folder}' does not exist", success=False)

        if path == folder:
            path = ""
        elif path.startswith(folder + os.path.sep):
            path = path[len(folder) + 1:]

        try:
            fd = core.sandbox_open(folder_path, path, os.O_RDONLY)
            with os.fdopen(fd, "r", encoding="utf-8") as f:
                return {"path": path, "content": f.read()}
        except Exception as e:
            return self.result(str(e), success=False)
