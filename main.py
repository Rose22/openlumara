#!/bin/env python

# OpenLumara! A modular, token-efficient AI agent framework.
# Made by Rose22 (https://github.com/Rose22)

# Official github: https://github.com/Rose22/openlumara

 # This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2.0 of the License, or (at your option) any later version.

 # This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

 # You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>. 

import os
import asyncio
import core
import subprocess
import argparse
import sys

async def main_loop(arg_list):
    # parse the --config arg
    arg_pre_parser = argparse.ArgumentParser(add_help=False)
    arg_pre_parser.add_argument("--config")
    arg_pre_parser.add_argument("--quiet", help="surpress logs", action="store_true")
    pre_args, _ = arg_pre_parser.parse_known_args(arg_list)

    # load config file, allowing the path to be overridden
    config_display_str = "config.yaml" if not pre_args.config else pre_args.config
    if not pre_args.quiet:
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
    args_main.add_argument("--debug_stream", help="Display debug information for all streamed tokens", action="store_true")
    args_main.add_argument("--disable_auto_installer", help="Disable automatic installation/uninstallation of module/channel dependencies", action="store_true")

    args_settings = arg_parser.add_argument_group("settings")
    module_structure = core.config.get_module_structure()
    add_arguments_recursive(args_settings, core.config.get_schema(), module_structure, main_parser=arg_parser)

    # do the arg parsing
    args, unknown = arg_parser.parse_known_args(arg_list)
    for unknown_arg in unknown:
        if unknown_arg.startswith("--"):
            core.log("core", f"Warning: Unrecognized argument '{unknown_arg}' will be ignored. The module could be disabled or the syntax could be wrong.")

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

    if args.debug_stream:
        core.debug_stream = True

    # the manager class connects everything together
    manager = core.manager.Manager(cmdline_args=args)
    # run main loop
    result = await manager.run()
    del(manager) # wipe it all
    return result

def run_from_args(arg_list: list = []):
    while True:
        result = None
        try:
            result = asyncio.run(main_loop(arg_list))
        except KeyboardInterrupt:
            pass

        if result == "restart":
            # run the loop again
            print("-" * 40, flush=True)
            pass
        else:
            sys.exit(0)

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def add_arguments_recursive(parser, config, module_structure, prefix="", current_group=None, main_parser=None):
    """
    Recursively traverses the config dict and adds arguments to the parser.
    """
    if main_parser is None:
        main_parser = parser

    for key, value in config.items():
        arg_name = f"{prefix}.{key}" if prefix else key
        arg_flag = f"--{arg_name}"

        if isinstance(value, dict):
            # CHECK: Is this a leaf setting? (A dict that contains a 'default' key)
            if "default" in value:
                # We reached a leaf setting.
                target_parser = current_group if current_group else parser
                
                default_val = value.get("default")
                # Priority: description > help > default fallback
                help_text = value.get("description") or None
                
                arg_type = type(default_val) if default_val is not None else str

                if isinstance(default_val, list):
                    target_parser.add_argument(arg_flag, type=str, metavar="<multiple,values>", help=help_text)
                elif arg_type == bool:
                    target_parser.add_argument(arg_flag, type=str2bool, default=None, metavar=default_val or "<value>", help=help_text)
                else:
                    target_parser.add_argument(arg_flag, type=arg_type, default=None, metavar=default_val or "<value>", help=help_text)
            else:
                # It's a nested dict, we drill down deeper
                
                # Check if this is a module/channel level to create a new group
                module_name = None
                if arg_name.startswith("modules.settings."):
                    module_name = arg_name[len("modules.settings."):]
                elif arg_name.startswith("channels.settings."):
                    module_name = arg_name[len("channels.settings."):]
                elif arg_name.startswith("user_modules.settings."):
                    module_name = arg_name[len("user_modules.settings."):]
                
                new_group = current_group
                if module_name and module_name in module_structure:
                    meta = module_structure[module_name].get("metadata", {})
                    doc = meta.get("doc", "")
                    group_title = module_name.capitalize()
                    new_group = main_parser.add_argument_group(group_title)
                elif new_group is None:
                    # If we aren't in a group and didn't find a module, continue with the current parser
                    new_group = parser
                
                add_arguments_recursive(new_group, value, module_structure, prefix=arg_name, current_group=new_group, main_parser=main_parser)
        else:
            # We reached a leaf node (a real value that isn't a dict)
            arg_type = type(value) if value is not None else str

            # Special handling for lists (like your 'enabled' keys)
            if isinstance(value, list):
                parser.add_argument(arg_flag, type=str, metavar="<multiple,values>", help=f"Comma-separated list for {arg_name}")
            elif arg_type == bool:
                parser.add_argument(arg_flag, type=str2bool, default=None, metavar=f"<{key.lower()}>")
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

            core.log("core", f"overrode setting {target_key} with: {value}")
        else:
            # If it's not in the config, it's likely an app flag (like --pure or --cli)
            # We do nothing and let the rest of the program handle it via 'args'
            continue

if __name__ == "__main__":
    import sys
    run_from_args(sys.argv[1:])
