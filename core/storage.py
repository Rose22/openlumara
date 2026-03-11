import core
import os
import json
import yaml
import msgpack

class StorageList(list):
    """subclassed list that handles storage of data. supports a variety of storage formats."""
    def __init__(self, file_path, type: str, manager=None, data_dir=None, *args):
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

class StorageDict(dict):
    """subclassed dict that handles storage of data. supports a variety of storage formats."""
    def __init__(self, file_path, type: str, manager=None, data_dir=None, *args):
        super().__init__(*args)

        if not data_dir:
            data_dir = "data"

        # ensure it's relative to the opticlaw root directory
        data_dir = core.get_path(data_dir)

        if not os.path.exists(data_dir):
            os.mkdir(data_dir)

        self.path = core.get_path(os.path.join(data_dir, file_path))
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
                self._write(json.dumps(dict(self), indent=2))
            case "yaml":
                self._write(yaml.dump(dict(self), default_flow_style=False, sort_keys=False))
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
            return self

        data = self._read()
        if not data:
            return None

        match self.type:
            case "json":
                self.update(json.loads(data))
            case "yaml":
                self.update(yaml.safe_load(data))
            case "msgpack":
                self.update(msgpack.unpackb(data))
            case "text":
                self.update(data.split("\n"))

class StorageText:
    """simple class that saves its content to a text file"""
    def __init__(self, file_path, manager=None, data_dir=None, *args):
        super().__init__(*args)

        if not data_dir:
            data_dir = "data"

        # ensure it's relative to the opticlaw root directory
        data_dir = core.get_path(data_dir)

        if not os.path.exists(data_dir):
            os.mkdir(data_dir)

        self._data = ""

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
