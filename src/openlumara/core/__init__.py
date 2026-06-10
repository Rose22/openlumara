import os

quiet = False
debug = False

from openlumara.core.functions import *
from openlumara.core import exceptions

# wtf tiktoken?! apparentely you don't work offline... might need to switch off it ASAP
cache_dir = get_path(".tiktoken_cache")
os.makedirs(cache_dir, exist_ok=True)
os.environ["TIKTOKEN_CACHE_DIR"] = cache_dir

from openlumara.core import config
from openlumara.core import storage
from openlumara.core import module
from openlumara.core import commands
from openlumara.core import context
from openlumara.core import toolcalls
from openlumara.core import chat
from openlumara.core import channel

from openlumara.core import modules
from openlumara.core import api_client

from openlumara.core import manager
