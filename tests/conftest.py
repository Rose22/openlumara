# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
# run the suite: uv run --extra test --extra modules pytest
"""Shared fixtures. Every test gets its own data folder and config inside tmp_path."""

import copy
import pathlib
import shutil
import sys
import tempfile

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent

# importing core creates these in the checkout. remember which ones it made so we can remove them again.
_IMPORT_ARTIFACTS = ["data/firstrun", "data", "user_modules", "user_channels"]
_created_by_import = [p for p in _IMPORT_ARTIFACTS if not (REPO / p).exists()]

import core  # noqa: E402

# keep the developer's own user_modules/user_channels from being imported during the run
for name in ("user_modules", "user_channels"):
    sys.modules[name].__path__ = []

# some modules scan the schema in their class body, so the cache can be written at collection time
_session_tmp = tempfile.mkdtemp(prefix="openlumara-tests-")
core.config.SCHEMA_CACHE_FILE = str(pathlib.Path(_session_tmp) / "module_cache.json")


def pytest_sessionfinish(session):
    shutil.rmtree(_session_tmp, ignore_errors=True)
    for name in _created_by_import:
        path = REPO / name
        try:
            # rmdir only removes empty dirs, so nothing a user put there is lost
            path.unlink() if path.is_file() else path.rmdir()
        except OSError:
            pass


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """point the data folder, config file and module schema cache at tmp_path"""
    config = core.storage.StorageDict("config", "yaml", path=str(tmp_path), override_temporary=True)
    defaults = copy.deepcopy(core.config.default_config)
    defaults["core"]["data_folder"] = str(tmp_path / "data")
    config.load(defaults)
    config.save()

    monkeypatch.setattr(core.config, "config", config)
    monkeypatch.setattr(core.config, "SCHEMA_CACHE_FILE", str(tmp_path / "module_cache.json"))
    monkeypatch.setattr(core.config, "_registry_cache", None)
    monkeypatch.setattr(core.storage, "TEMPORARY", False)
    monkeypatch.setattr(core.manager, "global_instance", None)
    return tmp_path / "data"


@pytest.fixture
def set_config():
    """merge sections into the test config, e.g. set_config(model={"use_tools": True})"""
    def _set(**sections):
        for key, value in sections.items():
            core.config.config.setdefault(key, {}).update(value)
        core.config.config.save()
    return _set


class FakeAPI:
    """scripted stand-in for core.api.APIClient. queue replies, then inspect .sent"""

    def __init__(self):
        self.connected = True
        self.supports_developer_role = False
        self.cancel_request = False
        self.sent = []
        self.replies = []  # dicts for send(), token lists for send_stream()

    async def connect(self, silent=False):
        return True

    async def attempt_connect(self):
        return True

    async def send(self, context, **kwargs):
        self.sent.append({"context": context, **kwargs})
        return self.replies.pop(0) if self.replies else {"role": "assistant", "content": ""}

    async def send_stream(self, context, **kwargs):
        self.sent.append({"context": context, **kwargs})
        for token in (self.replies.pop(0) if self.replies else []):
            yield token


class FakeManager:
    """the few manager attributes channels and modules touch"""

    def __init__(self):
        self.API = FakeAPI()
        self.modules = {}
        self.channels = {}
        self.channel = None
        self.tools = []
        self.pure_mode = False
        self.broken_modules = []
        self.savedata = {}
        self._async_tasks = set()
        self.logs = []

    def log(self, category, message):
        self.logs.append((category, message))

    def log_error(self, message, e):
        self.logs.append(("error", f"{message}: {e}"))

    def _remove_async_task(self, task):
        self._async_tasks.discard(task)


class TestChannel(core.channel.Channel):
    __module__ = "channels.test"  # get_name() derives the channel name from this

    async def on_push(self, message):
        self.pushed.append(message)


@pytest.fixture
def manager():
    return FakeManager()


@pytest.fixture
async def channel(manager):
    """a real Channel (with real Context, Chat and Messages) on a fake manager"""
    ch = TestChannel(manager)
    ch.pushed = []
    manager.channel = ch  # skips _set_as_active_channel, which wants a real savedata
    await ch.init()
    yield ch
    await ch._shutdown()
