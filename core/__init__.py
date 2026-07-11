import os

quiet = False
debug = False
debug_stream = False

from core.functions import *
import core.exceptions

user_module_path = core.get_path("user_modules", sandbox=False)
if not os.path.exists(user_module_path):
    os.makedirs(user_module_path, exist_ok=True)

user_channel_path = core.get_path("user_channels", sandbox=False)
if not os.path.exists(user_channel_path):
    os.makedirs(user_channel_path, exist_ok=True)

# wtf tiktoken?! apparentely you don't work offline... might need to switch off it ASAP
cache_dir = core.get_path(".tiktoken_cache")
os.makedirs(cache_dir, exist_ok=True)
os.environ["TIKTOKEN_CACHE_DIR"] = cache_dir

import core.config
import core.storage
import core.module
import core.commands
import core.context
import core.toolcalls
import core.chat
import core.channel

import core.modules
import core.api_client

import core.manager
