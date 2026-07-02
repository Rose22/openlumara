import core
import os
import json
import yaml
import msgpack

TEMPORARY = False

class StorageList(list):
    """subclassed list that handles storage of data. supports a variety of storage formats."""
    def __init__(self, name: str, type: str, manager=None, path=None, autoload=True, *args):
        super().__init__(*args)

        # default to openlumara data folder if no path specified
        if not path:
            path = core.get_data_path()

        self.path = core.sandbox_path(path, name)
        self.name = os.path.basename(self.path)
        self.binary = False

        # cache for change detection
        self._last_modified = 0.0

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
            if autoload and not TEMPORARY:
                self.load()
        else:
            self.save()

    def _write(self, content):
        try:
            write_mode = "wb" if self.binary else "w"
            encoding = "utf-8" if not self.binary else None

            with open(self.path, write_mode, encoding=encoding) as f:
                f.write(content)
        except Exception as e:
            core.log("error", f"error writing {self.name}: {e}")
            return False

        return True
    def _read(self):
        try:
            result = None
            read_mode = "rb" if self.binary else "r"
            encoding = "utf-8" if not self.binary else None
            with open(self.path, read_mode, encoding=encoding) as f:
                result = f.read()
            return result
        except Exception as e:
            core.log("error", f"error reading {self.name}: {e}")
            return False

    def _file_changed(self):
        """check if the file on disk has changed"""
        try:
            current_mtime = os.path.getmtime(self.path)
            return current_mtime != self._last_modified
        except OSError:
            return True

    def _update_mtime(self):
        """update the cached modification time"""
        try:
            self._last_modified = os.path.getmtime(self.path)
        except OSError:
            pass

    def save(self):
        """save content to file"""
        if TEMPORARY:
            return True

        match self.type:
            case "json":
                self._write(json.dumps(self, indent=2))
            case "yaml":
                self._write(yaml.safe_dump(self, default_flow_style=False, sort_keys=False, allow_unicode=True))
            case "msgpack":
                self._write(msgpack.packb(self))
            case "text":
                if len(self) > 0:
                    self._write("\n".join(self))

        # update mtime after saving so we know our cache is fresh
        self._update_mtime()

    def load(self, data=None):
        """load content from file or data argument"""
        if data:
            self.clear()
            self.extend(data)
            return self

        # skip reload if file hasn't changed on disk
        if not self._file_changed():
            self._update_mtime()
            return self

        self.clear()

        data = self._read()
        if not data:
            return None

        match self.type:
            case "json":
                self.extend(json.loads(data))
            case "yaml":
                self.extend(yaml.safe_load(data))
            case "msgpack":
                self.extend(msgpack.unpackb(data))
            case "text":
                self.extend(data.split("\n"))

        # update mtime after loading
        self._update_mtime()

    def get(self, *args, **kwargs):
        if not TEMPORARY:
            self.load()

        return super().get(*args)

class StorageDict(dict):
    """subclassed dict that handles storage of data. supports a variety of storage formats."""
    def __init__(self, name: str, type: str, manager=None, path=None, autoload=True, override_temporary=False, *args):
        super().__init__(*args)

        # default to openlumara data folder if no path specified
        if not path:
            path = core.get_data_path()

        self.path = core.sandbox_path(path, name)

        self.name = os.path.basename(self.path)
        self.binary = False

        # this is mainly for the config, so that we can still make changes in temporary mode
        # but who knows what it might be needed for in the future
        self.override_temporary = override_temporary

        # cache for change detection
        self._last_modified = 0.0

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
            if autoload and not (TEMPORARY and not self.override_temporary):
                self.load()
        else:
            self.save()

    def _write(self, content):
        try:
            write_mode = "wb" if self.binary else "w"
            encoding = "utf-8" if not self.binary else None
            with open(self.path, write_mode, encoding=encoding) as f:
                f.write(content)
        except Exception as e:
            core.log("error", f"error writing {self.name}: {e}")
            return False

        return True

    def _read(self):
        try:
            result = None
            read_mode = "rb" if self.binary else "r"
            encoding = "utf-8" if not self.binary else None
            with open(self.path, read_mode, encoding=encoding) as f:
                result = f.read()
            return result
        except Exception as e:
            core.log("error", f"error reading {self.name}: {e}")
            return False

    def _file_changed(self):
        """check if the file on disk has changed"""
        try:
            current_mtime = os.path.getmtime(self.path)
            return current_mtime != self._last_modified
        except OSError:
            return True

    def _update_mtime(self):
        """update the cached modification time"""
        try:
            self._last_modified = os.path.getmtime(self.path)
        except OSError:
            pass

    def _parse_nested_keys(self, flat_dict):
        """Convert flat keys like 'ideas/openlumara/topic' into nested dict structure."""
        result = {}
        for key, value in flat_dict.items():
            # normalize separators to / to handle Windows-style paths
            parts = key.replace("\\", "/").split("/")
            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        return result

    def _flatten_nested_keys(self, nested_dict, prefix=""):
        """Convert nested dict into flat keys like 'ideas/openlumara/topic'."""
        result = {}
        for key, value in nested_dict.items():
            full_key = f"{prefix}/{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten_nested_keys(value, full_key))
            else:
                result[full_key] = value

        return result

    def _delete_nested_key(self, flat_key):
        """Delete a key from the nested dict structure."""
        # normalize the key to ensure consistent splitting
        parts = flat_key.replace("\\", "/").split("/")

        current = self
        # traverse down to the parent dictionary of the target key
        for part in parts[:-1]:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                # the path doesn't exist, nothing to delete
                return

        # delete the target key from the parent dictionary
        if isinstance(current, dict) and parts[-1] in current:
            del current[parts[-1]]

    def save(self):
        """save content to file"""
        if TEMPORARY and not self.override_temporary:
            return True

        match self.type:
            case "json":
                self._write(json.dumps(dict(self), indent=2))
            case "yaml":
                self._write(yaml.safe_dump(dict(self), default_flow_style=False, sort_keys=False, allow_unicode=True))
            case "markdown":
                # NOTE to readers: i suck at recursive programming, so this is where i heavily use AI assistance. ~Rose22

                # recursive file structure
                # keys like "ideas/openlumara/topic" become nested directories
                if not os.path.exists(self.path):
                    os.makedirs(self.path, exist_ok=True)

                # flatten nested dict to path keys
                flat_items = self._flatten_nested_keys(dict(self))
                failed_keys = []

                for key, content in list(flat_items.items()):
                    try:
                        name = core.sandbox_path(self.path, f"{key}.md")
                    except ValueError as e:
                        # if validation fails, delete the key from the in-memory dicts to keep them clean.
                        self._delete_nested_key(key)
                        del flat_items[key]
                        failed_keys.append((key, str(e)))

                        continue  # Skip saving this file

                    file_dir = os.path.dirname(name)

                    if not os.path.exists(file_dir):
                        os.makedirs(file_dir, exist_ok=True)

                    with open(name, "w", encoding="utf-8") as f:
                        f.write(content)

                # Raise an error if any keys were skipped due to validation failure
                if failed_keys:
                    error_msg = "Failed to save the following keys due to validation errors:\n" + "\n".join([f"- {k}: {e}" for k, e in failed_keys])
                    raise ValueError(error_msg)

                # remove files that were deleted
                for root, dirs, files in os.walk(self.path, topdown=False):
                    for filename in files:
                        if filename.endswith(".md"):
                            full_path = os.path.join(root, filename)
                            rel_path = os.path.relpath(full_path, self.path)

                            # remove the .md extension
                            path_no_ext = rel_path[:-3]

                            # normalize path to make it cross-platform
                            normalized = os.path.normpath(path_no_ext)
                            logical_key = "/".join(normalized.split(os.sep))

                            if logical_key not in flat_items:
                                os.remove(full_path)

                    # remove empty directories
                    if root != self.path and not os.listdir(root):
                        os.rmdir(root)
            case "msgpack":
                self._write(msgpack.packb(dict(self)))
            case "text":
                if len(self) > 0:
                    self._write("\n".join(dict(self)))

        # update mtime after saving so we know our cache is fresh
        self._update_mtime()

    def load(self, data=None):
        """load content from file or data argument"""
        if data:
            self.clear()
            self.update(data)
            return True

        # skip reload if file hasn't changed on disk
        if self.type not in ["markdown"] and not self._file_changed():
            self._update_mtime()
            return True

        self.clear()

        if self.type not in ["markdown"]:
            data = self._read()
            if not data:
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
                            rel_path = os.path.relpath(os.path.join(root, filename), self.path)

                            # remove .md extension
                            path_without_ext = rel_path[:-3]

                            # normalize path to make it cross-platform
                            normalized_path = os.path.normpath(path_without_ext)
                            key = "/".join(normalized_path.split(os.sep))

                            with open(full_path, "r", encoding="utf-8") as f:
                                flat_dict[key] = str(f.read())

                # convert flat path keys to nested dict structure
                nested_dict = self._parse_nested_keys(flat_dict)
                self.update(nested_dict)
            case "msgpack":
                self.update(msgpack.unpackb(data))
            case "text":
                self.update(data.split("\n"))

        # update mtime after loading
        self._update_mtime()
        return True

    def get(self, *args, **kwargs):
        if not TEMPORARY and not self.override_temporary:
            self.load()

        return super().get(*args)

class StorageText:
    """simple class that saves its content to a text file"""
    def __init__(self, name: str, manager=None, path=None, autoload=True, *args):
        super().__init__(*args)

        # default to openlumara data folder if no path specified
        if not path:
            path = core.get_data_path()

        self.path = core.sandbox_path(path, name)

        self._data = ""

        # cache for change detection
        self._last_modified = 0.0

        if os.path.exists(self.path):
            if autoload and not TEMPORARY:
                self.load()
        else:
            self.save()

    def __str__(self, *args, **kwargs):
        return self.get()

    def set(self, new_data: str):
        self._data = str(new_data)
        self.save()
    def get(self):
        if not TEMPORARY:
            self.load()
        return str(self._data)

    def load(self):
        # skip reload if file hasn't changed on disk
        if not self._file_changed():
            self._update_mtime()
            return self

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self._data = f.read()
        except Exception as e:
            core.log("error", f"error while loading text storage: {e}")

        # update mtime after loading
        self._update_mtime()
        return self

    def save(self):
        if TEMPORARY:
            return self

        with open(self.path, "w", encoding="utf-8") as f:
            f.write(self._data)

        # update mtime after saving so we know our cache is fresh
        self._update_mtime()
        return self

    def _file_changed(self):
        """check if the file on disk has changed"""
        try:
            current_mtime = os.path.getmtime(self.path)
            return current_mtime != self._last_modified
        except OSError:
            return True

    def _update_mtime(self):
        """update the cached modification time"""
        try:
            self._last_modified = os.path.getmtime(self.path)
        except OSError:
            pass
