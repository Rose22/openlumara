"""
OpenLumara WebUI - manual rewrite

This is daunting, but i'm rewriting the entire WebUI from the ground up, manually, with minimal AI-generated code, due to high amount of unpredictable bugs in the previous version, and sheer difficulty of maintaining it

The plan is to use FastAPI for the backend again, but manually written, and alpine.js for the frontend, since it's nice and lightweight and not React.

Let's get this WebUI up to the standards of the rest of openlumara, since it's become basically the primary way everyone uses it..

~ Rose22
"""

# openlumara core
import core

# system
import os
import json
import asyncio
import time

# webui stuff
import fastapi, fastapi.templating, fastapi.staticfiles
import starlette, starlette.middleware.sessions
import uvicorn
import base64

# security libraries
import secrets

# --------------------
# Channel class
# --------------------
class Webui(core.channel.Channel):
    """A full-featured, modern webUI for OpenLumara, providing you with a privacy-friendly option that doesn't depend on any external chat providers"""
    version = 2.0

    dependencies = [
        "fastapi",
        "starlette>=1.0.1",
        "itsdangerous",
        "websockets",
        "jinja2",
        "uvicorn",
        "python-multipart"
    ]

    # these settings are taken straight from the previous webUI,
    # and currently, many of the settings don't do anything yet
    # but i plan to support these of course
    settings = {
        "network_mode": {
            "type": "select",
            "options": {
                "local": "Allows only the device OpenLumara is running on to access the WebUI (sets hostname to `localhost`)",
                "internet": "Allows any device to access the WebUI (sets hostname to `0.0.0.0`)",
                "custom": "Use the custom hostname defined below"
            },
            "default": "local"
        },
        "custom_host": {
            "default": None,
            "depends": {"network_mode": "custom"}
        },
        "port": {
            "description": "What port to run the WebUI on. Set this to 80 to be able to access it like a normal website, and anything else to access it on that port (for example http://yourdomain.org:3000)",
            "default": 3000
        },
        "allow_admin_commands": {
            "description": "Whether to allow /commands that control the openlumara server. Turn this off if you expose your openlumara instance to the internet without a login!",
            "default": True
        },
        "enable_chat_header": {
            "description": "Whether to enable the header at the top of a chat. Disabling this removes access to all graphical controls, and strips the interface down to a very basic chat. You might want this for public instances!",
            "default": True
        },
        "enable_title": {
            "default": True,
            "description": "Whether to show a fancy title in the header",
            "depends": "enable_chat_header"
        },
        "title": {
            "default": "OpenLumara",
            "depends": {"enable_chat_header": True, "enable_title": True}
        },
        "enable_chat_titlebar": {
            "description": "Whether to show the name of the chat below the header",
            "default": False
        },
        "enable_streaming_state_display": {
            "description": "Whether to show an indicator in the header that tells you what the AI is currently doing. Very useful! Disabled on mobile due to lack of space.",
            "default": True,
            "depends": "enable_chat_header",
        },
        "enable_sidebar": {
            "description": "Whether to enable the sidebar at the left of the screen. Without it, you can\'t switch chats the graphical way, but you can still use commands like `/chat`!",
            "default": True
        },
        "show_unsafe_settings": {
            "description": "Whether to show unsafe settings. This setting has to be manually toggled via `/config` or by editing the config file, because if you want access to the unsafe features, you hopefully know what you're doing!",
            "default": False,
            "unsafe": True
        },
        "require_login": {
            "description": "Whether to protect the WebUI with a username and password. **Highly recommended if your webui is exposed to the internet!!**",
            "default": False
        },
        "username": {
            "default": "admin",
            "depends": "require_login"
        },
        "password": {
            "default": "admin",
            "depends": "require_login"
        },
        "login_lifetime": {
            "description": "How many days to stay logged in for",
            "default": 30,
            "depends": "require_login"
        }
    }

    async def _verify_credentials(self, username: str, password: str) -> bool:
        """Verify credentials securely using timing-safe comparison."""
        correct_username = self.config.get("username")
        correct_password = self.config.get("password")

        if not secrets.compare_digest(username, correct_username):
            # Dummy comparison to prevent timing attacks
            secrets.compare_digest(password, correct_password)
            return False
        return secrets.compare_digest(password, correct_password)

    async def on_ready(self):
        # paths
        self.path = core.get_path(os.path.join("channels", "webui"))
        self.template_path = os.path.join(self.path, "templates")
        self.assets_path = os.path.join(self.path, "assets")

        # fastapi-specific instances
        self.templates = fastapi.templating.Jinja2Templates(self.template_path)

        # aaand create it
        self.app = await create_fastapi(self)

        # determine network mode
        network_mode = self.config.get("network_mode")
        match network_mode:
            case "local":
                self.host = "127.0.0.1"
            case "internet":
                self.host = "0.0.0.0"
            case "custom":
                self.host = self.config.get("custom_host")
            case _:
                self.host = "127.0.0.1"

        self.port = self.config.get("port")
        self.url = f"http://{self.host}:{self.port}"

        # stores logs from channel.log()
        self.logs = []

        self.username = self.config.get("username", "admin")
        self.password = self.config.get("password", "admin")
        self.login_attempts = {}

        # initialize the websocket manager
        self.websocket_manager = WebSocketManager(self)

    async def run(self):
        self.log("webui", f"Starting WebUI on {self.url}")

        # serve the app using uvicorn
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,

            # this makes it work in situations where https and http content are served mixed
            proxy_headers=True,
            forwarded_allow_ips = "127.0.0.1",

            # only log critical http errors
            log_level="error"
        )
        self.server = uvicorn.Server(config)

        await self.server.serve()

    async def on_push(self, message):
        await self.websocket_manager.broadcast({
            "type": "push",
            "content": message
        })

    def on_log(self, category, message):
        if not hasattr(self, 'websocket_manager'):
            # not initialized yet
            return False

        # Store log in buffer for history
        self.logs.append({"category": category, "message": message})
        
        # Broadcast log messages to all connected webui clients
        # Since on_log is sync but manager.broadcast is async, we schedule it as a task
        log_message = {
            "type": "log",
            "category": category,
            "message": message
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.websocket_manager.broadcast(log_message))
        except RuntimeError:
            # No event loop running - create one for this task
            asyncio.ensure_future(self.websocket_manager.broadcast(log_message))

    async def on_shutdown(self):
        # broadcast first so clients know we're going away
        await self.websocket_manager.broadcast({"type": "shutdown"})
        
        # then properly stop uvicorn
        # this is a flag exposed by uvicorn itself, which causes it to start gracefully shutting down when set
        self.server.should_exit = True

        # wait for uvicorn to actually finish shutting down
        try:
            await asyncio.wait_for(self.server.shutdown(), timeout=5.0)
        except (AttributeError, asyncio.TimeoutError):
            # fallback: just give it a moment to release the socket
            await asyncio.sleep(0.5)

# -------------------
# Helper Functions
# -------------------
def serialize_for_json(obj):
    """Recursively converts non-serializable objects into plain dicts/lists."""
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_for_json(x) for x in obj]
    elif hasattr(obj, 'to_dict'):
        return serialize_for_json(obj.to_dict())
    elif hasattr(obj, '__dict__'):
        return serialize_for_json(obj.__dict__)
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)

def get_recursive_assets(assets_path, ext, skip: list = []):
    """Recursively list asset files with paths relative to server root."""
    files = []
    
    for root, dirs, filenames in os.walk(assets_path):
        # Skip files and directories marked for skipping
        filenames[:] = [f for f in filenames if os.path.basename(f) not in skip]
        dirs[:] = [d for d in dirs if d not in skip]
        
        for filename in filenames:
            if filename.endswith(f".{ext}"):
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, assets_path)
                files.append(rel_path)
    
    return sorted(files)

def inject_indexes_into_messages(lst: list):
    """speaks for itself lol"""
    return [{**dickt, 'index': index} for index, dickt in enumerate(lst)]

def inject_indexes_into_chat(chat):
    """injects indexes into a chat's messages"""
    # copy it so we dont mutate it when injecting indexes
    chat_copy = dict(chat)

    # insert indexes into the messages array
    # so that the UI can track them for things like
    # editing messages, regenerating, deleting, etc
    chat_copy["messages"] = inject_indexes_into_messages(chat["messages"])

    return chat_copy

# -------------------
# FastAPI creator (contains routes and so on)
# -------------------
def api_result(obj = None, success: bool = True):
    if obj is None:
        result = {}
    else:
        result = obj

    return {"data": result, "success": success}

async def create_fastapi(channel):
    app = fastapi.FastAPI()

    # add authorization, cookies, and so on (middleware)
    # auth middleware for all routes
    @app.middleware("http")
    async def auth_middleware(request: fastapi.Request, call_next):
        # Skip auth check if login isn't required
        if not channel.config.get("require_login", False):
            return await call_next(request)
        
        # Skip auth for login page and assets
        if request.url.path in ["/login", "/logout"] or str(request.url.path).startswith("/assets/"):
            return await call_next(request)
        
        # Check session for API and other routes
        if not request.session.get("authenticated", False):
            # For API requests, return 401
            if str(request.url.path).startswith("/api"):
                return fastapi.responses.JSONResponse(
                    status_code=401,
                    content={"detail": "Unauthorized"}
                )
            # For web routes, redirect to login
            if request.url.path != "/login":
                return fastapi.responses.RedirectResponse(url="/login", status_code=303)
        
        return await call_next(request)

    session_lifetime_days = channel.config.get("login_lifetime")
    app.add_middleware(
        starlette.middleware.sessions.SessionMiddleware,
        secret_key=channel.config.get("session_secret", "openlumara-default-session-secret-change-me"),
        max_age=session_lifetime_days * 86400
    )

    # serve asset files (formerly /static) using fastAPI's mount()
    app.mount("/assets", fastapi.staticfiles.StaticFiles(directory=channel.assets_path), name="assets")

    # ------------------
    # Web pages
    # ------------------

    # main page
    @app.get("/")
    async def root(request: fastapi.Request):
        """The main page. This returns HTML, not JSON"""
        css_files = get_recursive_assets(os.path.join(channel.assets_path, "css"), "css", skip=["code-themes"])
        alpine_stores = os.listdir(os.path.join(channel.assets_path, "js", "stores"))
        js_utils = os.listdir(os.path.join(channel.assets_path, "js", "utils"))
        js_files = get_recursive_assets(os.path.join(channel.assets_path, "js"), "js", skip=["init.js", "stores", "libs", "utils"])

        return channel.templates.TemplateResponse(request, "index.html", {
            "version": channel.version,
            "config": channel.config,
            "css_files": css_files,
            "alpine_stores": alpine_stores,
            "js_utils": js_utils,
            "js_files": js_files,
            "login_enabled": channel.config.get("require_login")
        })

    # ---- login
    # -- GET
    @app.get("/login")
    async def login_page(request: fastapi.Request):
        """Shows the login form."""
        if channel.config.get("require_login"):
            return channel.templates.TemplateResponse(request, "login.html", {"error": None})
        else:
            return fastapi.responses.RedirectResponse(url="/", status_code=303)

    # -- POST
    @app.post("/login")
    async def login_submit(request: fastapi.Request):
        """Handles login form submission."""

        # rate limit the request
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        if client_ip in channel.login_attempts:
            # clean old attempts (older than 15 minutes)
            channel.login_attempts[client_ip] = [
                t for t in channel.login_attempts[client_ip] if now - t < 900
            ]

            if len(channel.login_attempts[client_ip]) >= 5:
                return fastapi.responses.JSONResponse(
                    status_code=429,
                    content={"error": "Too many attempts. Try again later."}
                )

        # and now check if the credentials match
        form = await request.form()
        username = form.get("username")
        password = form.get("password")
        
        if await channel._verify_credentials(username, password):
            channel.login_attempts[client_ip] = []
            request.session["authenticated"] = True

            return fastapi.responses.RedirectResponse(url="/", status_code=303)
        
        # on failure, record the login attempt
        if client_ip not in channel.login_attempts:
            channel.login_attempts[client_ip] = []
        channel.login_attempts[client_ip].append(now)
        
        return channel.templates.TemplateResponse(request, "login.html", {"error": "Invalid credentials"})

    # ---- logout
    @app.get("/logout")
    async def logout(request: fastapi.Request):
        """Logs the user out by clearing their session."""
        request.session.pop("authenticated", None)
        return fastapi.responses.RedirectResponse(url="/login", status_code=303)

    # ------------------
    # API routes (/api)
    # ------------------

    # reminder to self: docstrings show up in the autogenerated API docs (/docs), so they are essential

    # --- chats
    # -- GET
    @app.get("/api/chat/load/{chat_id}")
    async def chat_load(chat_id: str, request: fastapi.Request):
        """Loads a specific chat by its id"""
        try:
            success = await channel.context.chat.load(chat_id)
        except Exception as e:
            return api_result(f"error while loading chat: {core.detail_error(e)}", success=False)

        if not success:
            # that likely means this is already the loaded chat
            chat = dict(channel.context.chat.get())
            chat["turn_history"] = await channel.group_history()
            return api_result(chat, success=True)

        # broadcast the switch to any connected clients
        await channel.websocket_manager.broadcast({"type": "chat_switched", "id": chat_id})

        chat = dict(channel.context.chat.get())
        chat["turn_history"] = await channel.group_history()
        return api_result(chat, success=True)

    @app.get("/api/chat/current")
    async def chat_get_current():
        """Gives you the currently loaded chat's data"""

        chat = dict(channel.context.chat.get())
        chat["turn_history"] = await channel.group_history()
        return api_result(chat)

    @app.get("/api/chat/export")
    async def chat_export():
        """Gives you the chat history as a human-readable string, which you can save to a file or do whatever else with"""
        return api_result(await channel.context.chat.export())

    @app.get("/api/chats")
    async def get_chats(request: fastapi.Request):
        """Returns a list of all chats, with pagination"""
        offset = int(request.query_params.get("offset", 0))
        limit = int(request.query_params.get("limit", 50))
        category = request.query_params.get("category", None)

        all_chats = channel.context.chat.get_all()
        if category:
            all_chats = [c for c in all_chats if c.get("category") == category]

        paginated = all_chats[offset:offset + limit]
        has_more = offset + limit < len(all_chats)

        return api_result({"messages": paginated, "has_more": has_more}, success=True)

    @app.get("/api/chats/categories")
    async def get_chat_categories():
        """Returns a list of all existing chat categories"""
        return api_result(channel.context.chat.get_categories(), True)

    @app.post("/api/chats/search")
    async def search_chats(request: fastapi.Request):
        """Searches across all chats for messages matching a query"""
        data = await request.json()
        query = data.get("query", "").strip()
        search_in_content = data.get("search_in_content", True)
        category = data.get("category")

        if not query:
            return api_result([])

        results = await channel.context.chat.search(query)

        # filter by category if provided
        if category and category != 'general':
            results = [r for r in results if r.get('category') == category]
        elif category == 'general':
            results = [r for r in results if not r.get('category') or r.get('category') == 'general']

        return api_result(results)

    @app.get("/api/chat/prompt")
    async def get_prompt():
        sysprompt = await channel.context.get(system_prompt=True, end_prompt=False, history=False)
        if isinstance(sysprompt, core.api.APIError):
            return api_result(sysprompt, success=False)

        return api_result(sysprompt[-1].get("content"))

    # -- POST
    @app.post("/api/chat/new")
    async def chat_new():
        """Creates a new chat"""
        return api_result(await channel.context.chat.new())

    @app.post("/api/chat/rename/{chat_id}")
    async def chat_rename(chat_id: str, request: fastapi.Request):
        """Renames a chat by its ID"""
        try:
            data = await request.json()
            new_title = data.get('title', '').strip()
            if not new_title:
                return api_result("Title cannot be empty", success=False)
            
            # Find the index for this chat ID
            index = channel.context.chat._find_index(chat_id)
            if index is None:
                return api_result("Chat not found", success=False)
            
            # Direct update without loading the chat
            await channel.context.chat.set("title", new_title, index=index)
            
            return api_result(success=True)
        except Exception as e:
            return api_result(str(e), success=False)

    @app.post("/api/chat/delete/{chat_id}")
    async def chat_delete(chat_id: str):
        """Deletes a chat by its ID"""
        await channel.context.chat.delete(chat_id)
        return api_result(success=True)

    # --- Settings
    # -- GET
    @app.get("/api/settings/load")
    async def settings_load():
        """Returns the core's config object as a json object"""
        return api_result(core.config.config)

    @app.get("/api/settings/get_module_info")
    async def get_module_info():
        """Returns the schemas (descriptions, settings schemas, etc) for all modules and core config sections"""
        module_info = {}
        
        # Add module/channel settings schemas
        for module_name, module_data in core.config.get_module_structure().items():
            metadata = module_data.get("metadata", {})
            settings_schema = module_data.get("settings", {})

            if module_name not in module_info.keys():
                module_info[module_name] = {
                    "description": metadata.get("doc", ""),
                    "unsafe": metadata.get("unsafe", False),
                    "settings_schema": settings_schema
                }
        
        # Add core config sections settings schemas
        core_structure = core.config.get_core_settings_structure()
        for section_name, section_data in core_structure.items():
            if section_name not in module_info.keys():
                module_info[section_name] = {
                    "description": section_data.get("metadata", {}).get("doc", ""),
                    "unsafe": section_data.get("metadata", {}).get("unsafe", False),
                    "settings_schema": section_data.get("settings", {})
                }

        return api_result(module_info)

    @app.get("/api/check_connection")
    async def check_connection():
        """returns True if the backend is connected to the AI API, else False"""
        if channel.manager.API.connected:
            return api_result(True, success=True)
        else:
            return api_result("not connected", success=False)

    @app.get("/api/models")
    async def models_get():
        """Returns a list of all available AI models"""
        result = await channel.manager.API.list_models()
        if isinstance(result, core.api.APIError):
            return api_result(str(result), success=False)

        return api_result(result)

    # -- POST
    @app.post("/api/settings/save")
    async def settings_save(request: fastapi.Request):
        """Saves config data to the backend. Accepts a structure that reflects core.config.config exactly (check /api/settings/load to see that structure"""
        data = await request.json()

        changed_modules = list(data.get("changed_modules", []))
        data.pop("changed_modules")

        prev_model = core.config.config.get("model", "name")

        result = core.config.config.load(data=data)
        core.config.config.save()

        if not result:
            return api_result(success=False)

        # If the AI model selection changed and the models module manages load/unload,
        # apply it to VRAM (unload current, then load the newly configured model).
        new_model = core.config.config.get("model", "name")
        if new_model and new_model != prev_model:
            models_module = channel.manager.modules.get("models")
            if (
                models_module is not None
                and getattr(models_module, "apply_config_model", None)
                and models_module.config.get("enable_model_load_unload")
            ):
                await models_module.apply_config_model()
                channel.log(
                    self.name,
                    f"Model changed to '{new_model}': unloading previous model and loading {new_model}",
                )

        # Reload modules that had their settings changed
        if changed_modules:
            for module_name in changed_modules:
                try:
                    await channel.manager.reload_module(module_name)
                except Exception as e:
                    channel.log(self.name, f"Error reloading module {module_name}: {core.detail_error(e)}")

        return api_result(success=True)
    
    @app.post("/api/reconnect")
    async def reconnect():
        """Disconnects and then reconnects the API."""
        result = await channel.manager.API.reconnect()
        if isinstance(result, core.api.APIError):
            return api_result(str(result), success=False)

        return api_result(success=True)

    # ----------------------------
    # System.. stuff
    # ----------------------------
    # -- GET
    @app.get("/api/system/data")
    async def get_data():
        """returns any relevant data for the webUI to use"""
        data = {
            "max_context": core.config.get("api", "max_context")
        }

        return api_result(data)
    @app.get("/api/system/logs")
    async def get_logs():
        return api_result(channel.logs)

    # -- POST
    @app.post("/api/system/restart")
    async def restart_server():
        await channel.manager.restart()

    # ----------------------------
    # Theme API endpoints
    # ----------------------------
    @app.get("/api/themes")
    async def get_themes():
        """Returns a list of available theme families with their supported modes (dark/light)"""
        themes_dir = os.path.join(channel.path, "themes")
        theme_list = []

        for f in os.listdir(themes_dir):
            if f.endswith('.json') and f != 'base.json':
                family_name = f[:-5]
                filepath = os.path.join(themes_dir, f)
                try:
                    with open(filepath, 'r', encoding='utf-8') as fh:
                        theme_data = json.load(fh)
                        theme_list.append({
                            "name": family_name,
                            "dark": "dark" in theme_data,
                            "light": "light" in theme_data
                        })
                except Exception as e:
                    channel.log(channel.name, f"failed to read theme {filepath}: {e}")

        theme_list.sort(key=lambda x: x["name"])
        return theme_list

    @app.get("/api/themes/{family_name}")
    async def get_theme(family_name: str):
        """Returns full theme data for a specific family"""
        themes_dir = os.path.join(channel.path, "themes")
        filepath = os.path.join(themes_dir, f"{family_name}.json")
        
        if not os.path.exists(filepath):
            return api_result(f"Theme family '{family_name}' not found", success=False)

        try:
            with open(filepath, 'r', encoding='utf-8') as fh:
                theme_data = json.load(fh)
            return theme_data
        except Exception as e:
            channel.log(channel.name, f"failed to load theme {filepath}: {e}")
            return api_result(f"Failed to load theme: {str(e)}", success=False)

    def generate_cache_version():
        # generate an sw.js cache version based on this file's last modified time
        # because bumping sw.js's version manually each time i update the webui
        # is a total pain and i don't want to deal with it

        webui_folder = core.get_path("channels/webui")

        # Get the latest modification time among all files in the folder
        latest_mtime = os.path.getmtime(__file__)  # fallback to this file

        for root, dirs, files in os.walk(webui_folder):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime > latest_mtime:
                        latest_mtime = file_mtime
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    pass

        return f"v{int(latest_mtime)}"

    @app.get('/sw.js')
    async def service_worker():
        base_path = core.get_path("channels/webui")
        static_base = os.path.join(base_path, 'static')

        files_to_cache = []
        for subdir in ['js', 'css']:
            dir_path = os.path.join(static_base, subdir)
            if os.path.isdir(dir_path):
                for root, _, files in os.walk(dir_path):
                    for filename in files:
                        full_path = os.path.join(root, filename)
                        rel_path = os.path.relpath(full_path, static_base)
                        files_to_cache.append('/static/' + rel_path)
        files_to_cache.sort()

        sw_template_path = os.path.join(base_path, 'sw.js')
        with open(sw_template_path) as f:
            sw_code = f.read()

        version = generate_cache_version()

        file_list = ',\n    '.join(f'"{f}"' for f in files_to_cache)
        sw_code = sw_code.replace('{{VERSION}}', version)
        sw_code = sw_code.replace('{{FILE_LIST}}', f'{file_list}\n')

        return fastapi.Response(
            content=sw_code,
            media_type='application/javascript',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
            }
        )

    @app.get('/manifest.json')
    async def manifest():
        """Serve the PWA manifest."""
        with open(os.path.join(channel.path, "manifest.json")) as f:
            manifest_data = json.loads(f.read())
        return manifest_data

    @app.get('/icon-192.png')
    async def icon_192():
        """Serve the 192x192 icon for PWA."""
        return fastapi.responses.FileResponse(os.path.join(channel.path, "icon-192.png"))

    @app.get('/icon-512.png')
    async def icon_512():
        """Serve the 512x512 icon for PWA."""
        return fastapi.responses.FileResponse(os.path.join(channel.path, "icon-512.png"))

    @app.get('/favicon.ico')
    async def favicon():
        """Serve the favicon for the web interface."""
        return fastapi.responses.FileResponse(os.path.join(channel.path, "favicon.ico"))

    # ------------------
    # WebSocket endpoint
    # ------------------
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: fastapi.WebSocket):
        # WebSocket auth check
        if channel.config.get("require_login", False):
            session_cookie = websocket.cookies.get("session")
            if not session_cookie:
                # check if rate limited
                client_ip = websocket.client.host if websocket.client else "unknown"
                now = time.time()

                if client_ip in channel.login_attempts:
                    channel.login_attempts[client_ip] = [
                        t for t in channel.login_attempts[client_ip] if now - t < 900
                    ]
                    if len(channel.login_attempts[client_ip]) >= 5:
                        await websocket.close(code=4001, reason="Rate limited")
                        return

                # failure
                await websocket.close(code=4001, reason="Unauthorized")
                return

        ws_mgr = channel.websocket_manager
        await ws_mgr.connect(websocket)

        try:
            while True:
                data_text = await websocket.receive_text()

                try:
                    data = json.loads(data_text)
                    msg_type = data.get("type")

                    match msg_type:
                        case "stop":
                            if channel:
                                await channel.manager.API.cancel()
                        case "reload_messages":
                            await ws_mgr.broadcast({
                                "type": "sync"
                            })
                        case "rename":
                            new_title = data.get("title")
                            if channel and new_title:
                                await channel.context.chat.set("title", new_title)
                                await ws_mgr.broadcast({
                                    "type": "chat_metadata_updated",
                                    "title": new_title,
                                    "tags": channel.context.chat.get("tags") or []
                                })
                        case "switch_chat":
                            new_chat_id = data.get("chat_id")
                            if new_chat_id:
                                if ws_mgr.active_stream_task and not ws_mgr.active_stream_task.done():
                                    ws_mgr.active_stream_task.cancel()


                                try:
                                    await channel.context.chat.load(new_chat_id)
                                except Exception as e:
                                    await ws_mgr.broadcast({"type": "error", "content": f"Failed to load chat: {e}"})

                                ws_mgr.active_chat_id = new_chat_id

                                await ws_mgr.broadcast({
                                    "type": "chat_switched",
                                    "chat_id": new_chat_id,
                                })
                        case "new_chat":
                            if ws_mgr.active_stream_task and not ws_mgr.active_stream_task.done():
                                ws_mgr.active_stream_task.cancel()

                            new_id = await channel.context.chat.new()
                            ws_mgr.active_chat_id = new_id

                            await ws_mgr.broadcast({
                                "type": "chat_switched",
                                "chat_id": new_id,
                                "buffer": []
                            })
                        case "chat_delete":
                            chat_id = data.get("chat_id")
                            if not chat_id:
                                return False

                            await channel.context.chat.delete(chat_id)
                            await ws_mgr.broadcast({
                                "type": "chat_switched",
                                "chat_id": channel.context.chat.get("id"),
                                "buffer": []
                            })
                        case "user_message":
                            text = data.get("content")
                            files_data = data.get("files")

                            if not text and not files:
                                break

                            files_dict = None
                            if files_data:
                                files_dict = {
                                    f["name"]: base64.b64decode(f["data"])
                                    for f in files_data
                                }

                            chat_id = channel.context.chat.get("id") or "default"
                            await ws_mgr.start_stream(channel, chat_id, message=text, files=files_dict)
                        case "message_edit":
                            index = data.get("index")
                            if index < 0:
                                return False

                            message = await channel.context.chat.messages.get(index)
                            message["content"] = data.get("content")
                            await channel.context.chat.messages.edit(index, message)

                            await ws_mgr.broadcast({
                                "type": "sync"
                            })
                        case "message_delete":
                            index = data.get("index")
                            if index < 0:
                                return False

                            await channel.context.chat.messages.delete_from(index)
                            await ws_mgr.broadcast({
                                "type": "sync"
                            })
                        case "message_regenerate":
                            index = data.get("index")

                            if index is not None and channel:
                                last_user_message_index = await channel.context.chat.messages.get_last_message_with_role("user", cutoff_index=index)

                                if last_user_message_index == -1:
                                    await ws_mgr.broadcast({
                                        "type": "error",
                                        "error": "Could not regenerate message (no preceding user message found)"
                                    })
                                    return

                                user_message = await channel.context.chat.messages.get(last_user_message_index)

                                # delete_from deletes all messages AFTER the target, so we need to do index-1
                                # max(0, index) clamps it so that it never goes below 0
                                await channel.context.chat.messages.delete_from(max(0, last_user_message_index))

                                await ws_mgr.broadcast({"type": "sync"})
                                await ws_mgr.start_stream(channel, channel.context.chat.get("id"), user_message.get("content"))
                        case _:
                            channel.log(channel.name, f"Unknown websocket command received: {msg_type}")

                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    channel.log(channel.name, f"WebSocket command error: {core.detail_error(e)}")

        except fastapi.WebSocketDisconnect:
            ws_mgr.disconnect(websocket)
        except Exception as e:
            channel.log(channel.name, f"WebSocket error: {core.detail_error(e)}")
            ws_mgr.disconnect(websocket)

    return app

# -------------------
# Websocket Manager
# -------------------
class WebSocketManager:
    def __init__(self, channel):
        self.channel = channel

        self.active_connections = []

        self.active_stream_task = None
        self.webui_ready = False

    async def connect(self, websocket: fastapi.WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        current_chat_id = self.channel.context.chat.get("id")

        if current_chat_id:
            await websocket.send_json({
                "type": "ready"
            })

        asyncio.create_task(self.queue_ready_signal())

    def disconnect(self, websocket: fastapi.WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def queue_ready_signal(self):
        while not self.webui_ready:
            await asyncio.sleep(0.1)
        await self.broadcast({"type": "ready"})

    def send_ready_signal(self):
        self.webui_ready = True

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                if connection.client_state == starlette.websockets.WebSocketState.CONNECTED:
                    await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)

    async def _stream_task(self, message: str, index, files: list = None):
        user_message_confirmed = False

        try:
            async for partial in self.channel.turncollector.group_stream(
                    self.channel.send_stream(
                        message=message,
                        files=files,
                        commands_authorized=self.channel.config.get("allow_admin_commands")
                    )
                ):
                payload = serialize_for_json(partial)

                if partial.get("type") == "token":
                    token = partial.get("content")
                    token_type = token.get("type")
                    match token_type:
                        case "user_message":
                            try:
                                user_msg_payload = token.copy()
                                user_msg_payload['index'] = index
                                await self.broadcast({
                                    "type": "user_message_added",
                                    "message": user_msg_payload,
                                })
                            except Exception as e:
                                self.channel.log(self.channel.name, f"error sending user message: {core.detail_error(e)}")
                                return
                        case "error":
                            # for an error, just force a chat reload so that it shows up (core/channel takes care of adding it to context)
                            await self.broadcast({
                                "type": "user_message_confirmed",
                                "index": index
                            })
                            await self.broadcast({
                                "type": "sync"
                            })
                            return
                        case _:
                            if not user_message_confirmed:
                                user_message_confirmed = True
                                await self.broadcast({
                                    "type": "user_message_confirmed",
                                    "index": index
                                })

                            await self.broadcast({
                                "type": "token",
                                "content": token
                            })

                elif partial.get("type") == "turn":
                    await self.broadcast({
                        "type": "turn_stream",
                        "turns": partial.get("content")
                    })
        finally:
            # always finalize the stream, no matter what
            await self.broadcast({
                "type": "stream_complete"
            })

    async def start_stream(self, channel, chat_id: str, message: str, files: list = None):
        if self.active_stream_task and not self.active_stream_task.done():
            self.active_stream_task.cancel()

        next_index = len(await channel.context.chat.messages.get())

        try:
            self.active_stream_task = asyncio.create_task(self._stream_task(message, next_index, files=files))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            channel.log(channel.name, f"Background stream error: {core.detail_error(e)}")

