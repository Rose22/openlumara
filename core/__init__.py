import os

quiet = False

import core.storage
import core.module
import core.commands
import core.context
import core.toolcalls
import core.chat
import core.channel
from core.functions import *
from core.functions import set_data_path, set_config_path, get_config_path

import core.config
import core.modules
import core.api_client

import core.manager

# Initialize config now that all imports are complete
core.config.initialize_config()
