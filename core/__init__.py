import os
import site
import sys

version = 1.0

firstrun = False
quiet = False
debug = False
debug_stream = False
proceed_migration = False

from core.functions import *
import core.exceptions

home = core.get_home()
os.makedirs(home, exist_ok=True)

# move state left behind by pre-home versions of the app
core.migrate_legacy_state()

# user_modules/user_channels are imported as namespace packages, so home must be importable
if home not in sys.path:
    sys.path.append(home)

# extra site-packages supplied by the packager (e.g. the NixOS module's extraPackages)
for extra in os.environ.get("OPENLUMARA_EXTRA_SITE_PACKAGES", "").split(os.pathsep):
    if extra and os.path.isdir(extra) and extra not in sys.path:
        site.addsitedir(extra)

user_module_path = core.get_home_path("user_modules", sandbox=False)
if not os.path.exists(user_module_path):
    os.makedirs(user_module_path, exist_ok=True)

user_channel_path = core.get_home_path("user_channels", sandbox=False)
if not os.path.exists(user_channel_path):
    os.makedirs(user_channel_path, exist_ok=True)

# wtf tiktoken?! apparentely you don't work offline... might need to switch off it ASAP
# cache_dir = core.get_path(".tiktoken_cache")
# os.makedirs(cache_dir, exist_ok=True)
# os.environ["TIKTOKEN_CACHE_DIR"] = cache_dir

import core.config
import core.storage
import core.search
import core.module
import core.commands
import core.context
import core.tool_loader
import core.toolcalls
import core.messages
import core.chat
import core.turns
import core.channel

import core.modules
import core.module_manager
import core.http_sse
import core.api

# handle first run
firstrun_path = core.get_data_path("firstrun")
if not os.path.exists(firstrun_path):
    firstrun = True
    with open(firstrun_path, 'w', encoding="utf-8") as f:
        f.write("")

import core.manager
