#!/bin/env python

# OptiClaw! A modular, token-efficient AI agent framework.
# Made by Rose22 (https://github.com/Rose22)

# Official github: https://github.com/Rose22/opticlaw

 # This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 2.0 of the License, or (at your option) any later version.

 # This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

 # You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>. 

import os
import sys
import asyncio
import core

async def main():
    # the manager class connects everything together
    manager = core.manager.Manager()
    # connect to openAI API
    manager.connect(core.config.get("model").get("name"), base_url=core.config.get("api").get("url"), api_key=core.config.get("api").get("key"))
    # run main loop
    await manager.run()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("Shutting down..")
    exit()
