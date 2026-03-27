import core
import os
import json
import yaml
import msgpack

class StorageList(list):
    """subclassed list that handles storage of data. supports a variety of storage formats."""
    def __init__(self, file_path, type: str, manager=None, data_dir=None, autoreload=True, *args):
        super().__init__(*args)

        if not data_dir:
            data_dir = "data"

        # ensure it's relative to the opticlaw root directory
        data_dir = core.get_path(data_dir)

        if not os.path.exists(data_dir):
            os.mkdir(data_dir)

        self.path = core.get_path(os.path.join(data_dir, file_path))
        self.name = os.path.basename(self.path)
        self.binary = False

        # lets not overwrite a builtin
        file_type = type
        if not type:
            # default to json
            file_type = "json"

        file_ext = None
        match file_type:
            case "text":
                file_ext = "txt"
            case "json":
                file_ext = "json"
            case "yaml":
                file_ext = "yml"
            case "msgpack":
                file_ext = "mp"
                self.binary = True

        self.type = file_type
        self.ext = file_ext
        self.autoreload = autoreload

        self.path += f".{self.ext}"

        if manager:
            self.manager = manager

        if os.path.exists(self.path):
            self.load()
        else:
            self.save()

    def _write(self, content):
        try:
            write_mode = "wb" if self.binary else "w"
            with open(self.path, write_mode) as f:
                f.write(content)
        except Exception as e:
            core.log("error", f"error writing {self.name}: {e}")
            return False

        return True
    def _read(self):
        try:
            result = None
            read_mode = "rb" if self.binary else "r"
            with open(self.path, read_mode) as f:
                result = f.read()
            return result
        except Exception as e:
            core.log("error", f"error reading {self.name}: {e}")
            return False

    def save(self):
        """save content to file"""

        match self.type:
            case "json":
                self._write(json.dumps(self, indent=2))
            case "yaml":
                self._write(yaml.dump(self, default_flow_style=False, sort_keys=False))
            case "msgpack":
                self._write(msgpack.packb(self))
            case "text":
                if len(self) > 0:
                    self._write("\n".join(self))

    def load(self, data=None):
        """load content from file or data argument"""
        self.clear()

        if data:
            self.extend(data)
            return self

        data = self._read()
        if not data:
            return None

        match self.type:
            case "json":
                self.extend(json.loads(data))
            case "yaml":
                self.extend(yaml.load(data))
            case "msgpack":
                self.extend(msgpack.unpackb(data))
            case "text":
                self.extend(data.split("\n"))

    def get(self, *args, **kwargs):
        if self.autoreload:
            self.load()

        return super().get(*args, **kwargs)

class StorageDict(dict):
    """subclassed dict that handles storage of data. supports a variety of storage formats."""
    def __init__(self, file_path, type: str, manager=None, data_dir=None, autoreload=True, *args):
        super().__init__(*args)

        if not data_dir:
            data_dir = "data"

        # ensure it's relative to the opticlaw root directory
        data_dir = core.get_path(data_dir)

        if not os.path.exists(data_dir):
            os.mkdir(data_dir)

        self.path = core.get_path(os.path.join(data_dir, file_path))
        self.name = os.path.basename(self.path)
        self.binary = False
        self.autoreload = autoreload

        # lets not overwrite a builtin
        file_type = type
        if not type:
            # default to json
            file_type = "json"

        file_ext = None
        match file_type:
            case "text":
                file_ext = "txt"
            case "json":
                file_ext = "json"
            case "yaml":
                file_ext = "yml"
            case "markdown":
                file_ext = "md"
            case "msgpack":
                file_ext = "mp"
                self.binary = True

        self.type = file_type
        self.ext = file_ext

        if file_type not in ["markdown"]:
            self.path += f".{self.ext}"

        if manager:
            self.manager = manager

        if os.path.exists(self.path):
            self.load()
        else:
            self.save()

    def _write(self, content):
        try:
            write_mode = "wb" if self.binary else "w"
            with open(self.path, write_mode) as f:
                f.write(content)
        except Exception as e:
            core.log("error", f"error writing {self.name}: {e}")
            return False

        return True

    def _read(self):
        try:
            result = None
            read_mode = "rb" if self.binary else "r"
            with open(self.path, read_mode) as f:
                result = f.read()
            return result
        except Exception as e:
            core.log("error", f"error reading {self.name}: {e}")
            return False

    def _parse_nested_keys(self, flat_dict):
        """Convert flat keys like 'ideas/opticlaw/topic' into nested dict structure."""
        result = {}
        for key, value in flat_dict.items():
            parts = key.split("/")
            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return result

    def _flatten_nested_keys(self, nested_dict, prefix=""):
        """Convert nested dict into flat keys like 'ideas/opticlaw/topic'."""
        result = {}
        for key, value in nested_dict.items():
            full_key = f"{prefix}/{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten_nested_keys(value, full_key))
            else:
                result[full_key] = value
        return result

    def save(self):
        """save content to file"""

        match self.type:
            case "json":
                self._write(json.dumps(dict(self), indent=2))
            case "yaml":
                self._write(yaml.dump(dict(self), default_flow_style=False, sort_keys=False))
            case "markdown":
                # recursive file structure
                # keys like "ideas/opticlaw/topic" become nested directories
                if not os.path.exists(self.path):
                    os.makedirs(self.path, exist_ok=True)

                # flatten nested dict to path keys
                flat_items = self._flatten_nested_keys(dict(self))

                for key, content in flat_items.items():
                    file_path = os.path.join(self.path, f"{key}.md")
                    file_dir = os.path.dirname(file_path)

                    if not os.path.exists(file_dir):
                        os.makedirs(file_dir, exist_ok=True)

                    with open(file_path, "w") as f:
                        f.write(content)

                # remove files that were deleted
                for root, dirs, files in os.walk(self.path, topdown=False):
                    for filename in files:
                        if filename.endswith(".md"):
                            rel_path = os.path.relpath(os.path.join(root, filename), self.path)
                            key = rel_path[:-3]  # remove .md extension
                            if key not in flat_items:
                                os.remove(os.path.join(root, filename))

                    # remove empty directories
                    if root != self.path and not os.listdir(root):
                        os.rmdir(root)
            case "msgpack":
                self._write(msgpack.packb(dict(self)))
            case "text":
                if len(self) > 0:
                    self._write("\n".join(dict(self)))

    def load(self, data=None):
        """load content from file or data argument"""
        self.clear()

        if data:
            self.update(data)
            return True

        data = self._read()
        if self.type not in ["markdown"] and not data:
            return None

        match self.type:
            case "json":
                self.update(json.loads(data))
            case "yaml":
                self.update(yaml.safe_load(data))
            case "markdown":
                # recursive file structure
                flat_dict = {}
                for root, dirs, files in os.walk(self.path):
                    for filename in files:
                        if filename.endswith(".md"):
                            full_path = os.path.join(root, filename)
                            rel_path = os.path.relpath(full_path, self.path)
                            key = rel_path[:-3]  # remove .md extension

                            with open(full_path, "r") as f:
                                flat_dict[key] = str(f.read())

                # convert flat path keys to nested dict structure
                nested_dict = self._parse_nested_keys(flat_dict)
                self.update(nested_dict)
            case "msgpack":
                self.update(msgpack.unpackb(data))
            case "text":
                self.update(data.split("\n"))

        return True

    def get(self, *args, **kwargs):
        if self.autoreload:
            self.load()

        return super().get(*args, **kwargs)

class StorageText:
    """simple class that saves its content to a text file"""
    def __init__(self, file_path, manager=None, data_dir=None, autoreload=True, *args):
        super().__init__(*args)

        if not data_dir:
            data_dir = "data"

        # ensure it's relative to the opticlaw root directory
        data_dir = core.get_path(data_dir)

        if not os.path.exists(data_dir):
            os.mkdir(data_dir)

        self._data = ""
        self.autoreload = autoreload

        self.path = core.get_path(os.path.join(data_dir, file_path))
        if os.path.exists(self.path):
            self.load()
        else:
            self.save()

    def __str__(self, *args, **kwargs):
        return self._data

    def set(self, new_data: str):
        self._data = str(new_data)
        self.save()
    def get(self):
        if self.autoreload:
            self.load()
        return str(self._data)

    def load(self):
        try:
            with open(self.path, "r") as f:
                self._data = f.read()
        except Exception as e:
            core.log("error", f"error while loading text storage: {e}")
        return self

    def save(self):
        with open(self.path, "w") as f:
            f.write(self._data)

        return self
