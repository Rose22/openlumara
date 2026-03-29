#!/bin/env python

# OptiClaw! A modular, token-efficient AI agent framework.
# Made by Rose22 (https://github.com/Rose22)

# Official github: https://github.com/Rose22/opticlaw

 # This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2.0 of the License, or (at your option) any later version.

 # This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

 # You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>. 

import os
import sys
import argparse
import asyncio
import subprocess

# Parse CLI arguments BEFORE importing core
parser = argparse.ArgumentParser(description="OptiClaw - Modular AI Agent Framework")
parser.add_argument("--data-dir", type=str, default=None, help="Path to data directory (default: ./data)")
parser.add_argument("--config", type=str, default=None, help="Path to config.yml file (default: ./config/config.yml)")
args = parser.parse_args()

# Now import core and set overrides
import core
if args.data_dir:
    core.set_data_path(args.data_dir)
if args.config:
    core.set_config_path(args.config)
    core.config.reload_config()  # Re-initialize config with the new path

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


