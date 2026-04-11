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

async def main():
    # the manager class connects everything together
    manager = core.manager.Manager()
    # run main loop
    return await manager.run()

def do_restart():
    """cross-platform restart with TTY/console inheritance"""
    script = os.path.abspath(sys.argv[0])
    args = [sys.executable, script] + sys.argv[1:]

    if sys.platform == "win32":
        # windows: spawn new process, inherit same console
        subprocess.Popen(
            args,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        sys.exit(0)
    else:
        # unix: replace process, inherits TTY automatically
        os.execv(sys.executable, args)

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
                parser.add_argument(arg_flag, type=str, metavar="LIST", help=f"Comma-separated list for {arg_name}")
            else:
                parser.add_argument(arg_flag, type=arg_type, default=None, metavar="VALUE")

def override_config_with_args(live_config, args_namespace):
    """
    Walks through the flat argparse namespace and updates the
    nested live_config dictionary in-place.
    """
    # Convert Namespace to dict
    args_dict = vars(args_namespace)

    for flat_key, value in args_dict.items():
        # IMPORTANT: Only override if the user actually provided the argument
        # argparse fills missing args with the 'default' we provided (None)
        if value is None:
            continue

        parts = flat_key.split('.')

        # Traverse the live_config dict to the target location
        current_level = live_config
        try:
            for part in parts[:-1]:
                current_level = current_level[part]

            target_key = parts[-1]

            # Logic for handling comma-separated lists (e.g., --channels.enabled=a,b)
            # We check if the current value in the live config is a list
            if isinstance(current_level.get(target_key), list) and isinstance(value, str):
                current_level[target_key] = [item.strip() for item in value.split(',')]
            else:
                current_level[target_key] = value

        except KeyError as e:
            print(f"Warning: Argument {flat_key} provided, but path not found in config: {e}")

# parse arguments
arg_parser = argparse.ArgumentParser()
add_arguments_recursive(arg_parser, core.config.default_config)

# custom arguments
arg_parser.add_argument("--pure", help="disables all non-essential modules so that system prompt is blank and you're talking to the bare model", action="store_true")
arg_parser.add_argument("--cli", help="CLI-only mode", action="store_true")

# do the arg parsing
args = arg_parser.parse_args(sys.argv[1:])

# by this point, the config is already loaded by core.__init__.py, so we can just override the values
override_config_with_args(core.config.config, args)

if args.pure:
    # mode that lets you easily talk to the bare model
    core.config.config["modules"]["enabled"] = ["context"]
if args.cli:
    core.config.config["channels"]["enabled"] = ["cli"]

while True:
    result = None
    try:
        result = asyncio.run(main())
    except KeyboardInterrupt:
        pass

    if result == "restart":
        do_restart()
    else:
        print("Shutting down..")
        exit()


