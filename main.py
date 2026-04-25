#!/bin/env python

# OpenLumara! A modular, token-efficient AI agent framework.
# Made by Rose22 (https://github.com/Rose22)

# Official github: https://github.com/Rose22/openlumara

 # This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2.0 of the License, or (at your option) any later version.

 # This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

 # You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>. 

import os
import sys
import asyncio
import core
import subprocess
import argparse

async def main(args):
    # the manager class connects everything together
    manager = core.manager.Manager(cmdline_args=args)
    # run main loop
    return await manager.run()

def add_arguments_recursive(parser, config, prefix=""):
    """
    Recursively traverses the config dict and adds arguments to the parser.
    """
    for key, value in config.items():
        # Build the argument name (e.g., --channels.settings.webui.port)
        arg_name = f"{prefix}.{key}" if prefix else key
        arg_flag = f"--{arg_name}"

        if isinstance(value, dict):
            # If it's a dict, we drill down deeper
            add_arguments_recursive(parser, value, prefix=arg_name)
        else:
            # We reached a leaf node (a real value)
            # We try to infer the type from the default value
            arg_type = type(value) if value is not None else str

            # Special handling for lists (like your 'enabled' keys)
            if isinstance(value, list):
                parser.add_argument(arg_flag, type=str, metavar="<multiple,values>", help=f"Comma-separated list for {arg_name}")
            else:
                parser.add_argument(arg_flag, type=arg_type, default=None, metavar=f"<{key.lower()}>")

def override_config_with_args(live_config, args_namespace):
    """
    Walks through the flat argparse namespace and updates the
    nested live_config dictionary in-place, ONLY if the path exists.
    """
    args_dict = vars(args_namespace)

    for flat_key, value in args_dict.items():
        # 1. Skip if the user didn't provide a value
        if value is None:
            continue

        parts = flat_key.split('.')

        # 2. Attempt to traverse the config path
        current_level = live_config
        path_exists = True

        for part in parts[:-1]:
            if isinstance(current_level, dict) and part in current_level:
                current_level = current_level[part]
            else:
                path_exists = False
                break

        # 3. Check if the final target key exists in the current level
        if path_exists and isinstance(current_level, dict) and parts[-1] in current_level:
            target_key = parts[-1]

            # Logic for handling comma-separated lists
            if isinstance(current_level[target_key], list) and isinstance(value, str):
                current_level[target_key] = [item.strip() for item in value.split(',')]
            else:
                current_level[target_key] = value
        else:
            # If it's not in the config, it's likely an app flag (like --pure or --cli)
            # We do nothing and let the rest of the program handle it via 'args'
            continue


# parse the --config arg
arg_pre_parser = argparse.ArgumentParser(add_help=False)
arg_pre_parser.add_argument("--config")
pre_args, _ = arg_pre_parser.parse_known_args(sys.argv[1:])

# load config file, allowing the path to be overridden
config_display_str = "config.yaml" if not pre_args.config else pre_args.config
if not core.quiet:
    core.log("core", f"Loading settings from config {config_display_str}")
core.config.load(pre_args.config)

# parse arguments
arg_parser = argparse.ArgumentParser()

# custom arguments
args_main = arg_parser.add_argument_group("main")
args_main.add_argument("--config", help="specify a specific config file to load", metavar="<path>")
args_main.add_argument("--pure", help="disables all non-essential modules so that system prompt is blank and you're talking to the bare model", action="store_true")
args_main.add_argument("--tmp", help="temporary session, discards all data after shutdown", action="store_true")
args_main.add_argument("--cli", help="CLI-only mode", action="store_true")
args_main.add_argument("--coder", help="enable only the coder module (coding agent mode)", action="store_true")
args_main.add_argument("--quiet", help="surpress logs", action="store_true")
args_main.add_argument("--insecure_tls", help="Disable verification for SSL/TLS certs. Use when your API uses self-signed or unvalid certificates.", action="store_true")
args_main.add_argument("--debug", help="Enable debug mode (display all warnings and errors)", action="store_true")

args_settings = arg_parser.add_argument_group("settings")
add_arguments_recursive(args_settings, core.config.get_schema(
    enabled_channels=core.config.get("channels").get("enabled"),
    enabled_modules=core.config.get("modules").get("enabled"),
    enabled_user_modules=core.config.get("user_modules").get("enabled")
))

# do the arg parsing
args = arg_parser.parse_args(sys.argv[1:])

# override any targeted config values
override_config_with_args(core.config.config, args)

if args.quiet:
    core.quiet = True

if args.tmp:
    core.storage.TEMPORARY = True
    if not args.quiet:
        core.log("core", "Temporary mode activated. Loading/saving of data disabled. Anything you store will not persist!")

if args.debug:
    core.debug = True

while True:
    result = None
    try:
        result = asyncio.run(main(args))
    except KeyboardInterrupt:
        pass

    if result == "restart":
        # run the loop again
        print("-" * 40)
        pass
    else:
        exit()


