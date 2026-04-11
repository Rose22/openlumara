import core
import os
import asyncio
import time
import json
import json_repair
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import BadRequest

class Telegram(core.channel.Channel):
    """
    A Telegram channel with live streaming, command pass-through,
    and pretty-printed tool call visualization.

    Commands are processed immediately to allow /stop to interrupt streams.
    Normal messages are queued to ensure sequential processing.
    """
    running = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            try:
                self.token = core.config.get("channels").get("settings").get("telegram").get("token")
            except (AttributeError, KeyError):
                pass

        self.app = None
        self.auth_storage = core.storage.StorageText("telegram_chat_id")
        self.authorized_chat_id = self._load_authorized_id()
        self._shutting_down = False
        self.message_queue = asyncio.Queue()
        self.queue_task = None

    def _load_authorized_id(self):
        stored_id = self.auth_storage.get()
        if stored_id and stored_id.strip():
            try:
                chat_id = int(stored_id)
                core.log("telegram", f"Restored authorized chat ID: {chat_id}")
                return chat_id
            except ValueError:
                core.log("telegram", "Failed to parse stored chat ID.")
        return None

    async def run(self):
        if not self.token:
            await self._announce("Telegram channel failed: No API token provided.", "error")
            return False

        try:
            self.app = Application.builder().token(self.token).build()
            self.app.add_handler(CommandHandler("start", self._tg_start))
            self.app.add_handler(MessageHandler(filters.TEXT, self._tg_message))

            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling(drop_pending_updates=True)

            self.running = True
            self.queue_task = asyncio.create_task(self._process_queue_worker())
            await self._announce("Telegram channel connected.", "status")

            while self.running and not self._shutting_down:
                await asyncio.sleep(1)

        except Exception as e:
            core.log("telegram", f"Critical Error: {str(e)}")
            return False
        finally:
            if self.queue_task:
                self.queue_task.cancel()
            await self._cleanup()

        return True

    async def _cleanup(self):
        if self.app:
            if self.app.updater.running:
                await self.app.updater.stop()
            if self.app.running:
                await self.app.stop()
            await self.app.shutdown()

    async def shutdown(self):
        await self.announce("Shutting down Telegram channel...", "status")
        self.running = False
        self._shutting_down = True
        return True

    async def _tg_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if self.authorized_chat_id is None:
            self.authorized_chat_id = chat_id
            self.auth_storage.set(str(chat_id))
            await update.message.reply_text("✅ Session started.")
            core.log("telegram", f"Authorized chat ID: {chat_id}")
        elif self.authorized_chat_id != chat_id:
            await update.message.reply_text("⚠️ This bot is already in use.")

    def _format_tool_call(self, tool_data):
        try:
            if hasattr(tool_data, 'function'):
                func_name = getattr(tool_data.function, 'name', 'unknown')
                raw_args = getattr(tool_data.function, 'arguments', '{}')
            elif isinstance(tool_data, dict) and 'function' in tool_data:
                func_name = tool_data['function'].get('name', 'unknown')
                raw_args = tool_data['function'].get('arguments', '{}')
            else:
                return "🔧 Calling tool..."

            if isinstance(raw_args, str):
                try:
                    args_dict = json_repair.loads(raw_args)
                except Exception:
                    args_dict = {}
            elif isinstance(raw_args, dict):
                args_dict = raw_args
            else:
                args_dict = {}

            arg_strs = []
            for k, v in args_dict.items():
                v_str = str(v)
                if len(v_str) > 30:
                    v_str = v_str[:30] + ".."
                v_str = v_str.replace('"', "'")
                arg_strs.append(f'{k}="{v_str}"')

            return f"🔧 {func_name}({', '.join(arg_strs)})"
        except Exception as e:
            core.log("telegram", f"Error formatting tool call: {e}")
            return "🔧 Calling tool..."

    async def _tg_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
        if self.authorized_chat_id and chat_id != self.authorized_chat_id:
            return

        if not self.authorized_chat_id:
            self.authorized_chat_id = chat_id
            self.auth_storage.set(str(chat_id))

        text = update.message.text.strip()
        cmd_prefix = core.config.get("cmd_prefix", "/")

        if text.startswith(cmd_prefix):
            asyncio.create_task(self._process_stream(update, context))
        else:
            await self.message_queue.put((update, context))

    async def _process_queue_worker(self):
        while self.running and not self._shutting_down:
            try:
                update, context = await self.message_queue.get()
                await self._process_stream(update, context)
                self.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                core.log("telegram", f"Queue worker error: {e}")
                await asyncio.sleep(1)

    async def _process_stream(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        user_msg = update.message.text.strip()
        typing_task = asyncio.create_task(self._keep_typing(chat_id))

        message = None
        last_edit_time = 0
        tool_calls_display = []
        response_buffer = []
        shown_reasoning_text = False
        visual_buffer = ""

        try:
            async for token in self.send_stream({"role": "user", "content": user_msg}):
                t_type = token.get("type")
                content = token.get("content", "")

                if t_type == "tool_calls":
                    if content:
                        calls = content if isinstance(content, list) else [content]
                        for tool in calls:
                            tool_calls_display.append(self._format_tool_call(tool))
                elif t_type == "reasoning":
                    if not shown_reasoning_text:
                        visual_buffer = "thinking.."
                        shown_reasoning_text = True
                    else:
                        continue
                elif t_type in ["content", "error"]:
                    response_buffer.append(content)

                # Construct visual state
                tools_text = "".join(tool_calls_display)
                text_part = "".join(response_buffer)

                # Priority: if we have tools, show them. If we have text, append.
                if tools_text and text_part:
                    visual_buffer = f"{tools_text}{text_part}"
                elif tools_text:
                    visual_buffer = tools_text
                else:
                    visual_buffer = text_part if text_part else ("thinking.." if shown_reasoning_text else "")

                # Throttled Updating
                now = time.time()
                if visual_buffer:
                    if message is None:
                        message = await context.bot.send_message(chat_id, visual_buffer[:4000])
                        last_edit_time = now
                    elif now - last_edit_time > 1.5:
                        try:
                            await message.edit_text(visual_buffer[:4000])
                            last_edit_time = now
                        except BadRequest:
                            pass

            # Finalize
            if message and visual_buffer:
                try:
                    await message.edit_text(visual_buffer[:4000])
                except Exception: pass
            elif visual_buffer:
                await context.bot.send_message(chat_id, visual_buffer[:4000])

        except Exception as e:
            core.log("telegram", f"Error processing stream: {e}")
            try:
                await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")
            except Exception: pass
        finally:
            if not typing_task.done():
                typing_task.cancel()

    async def _keep_typing(self, chat_id: int):
        try:
            while True:
                await self.app.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            core.log("telegram", f"Typing indicator error: {e}")

    async def _send_telegram_message(self, text: str):
        if not self.authorized_chat_id or not self.app:
            return
        try:
            await self.app.bot.send_message(self.authorized_chat_id, text, parse_mode="Markdown")
        except Exception:
            try:
                await self.app.bot.send_message(self.authorized_chat_id, text)
            except Exception as e:
                core.log("telegram", f"Failed to send message: {e}")

    async def _announce(self, message: str, msg_type: str = "info"):
        core.log("telegram", f"[{msg_type}] {message}")
        if self.authorized_chat_id and self.app:
            emoji_map = {"error": "🚨", "warning": "⚠️", "status": "ℹ️", "info": "💬"}
            emoji = emoji_map.get(msg_type, "🔔")
            # Basic sanitization for Markdown
            safe_msg = message.replace("*", "").replace("_", "")
            text = f"{emoji} *{msg_type.upper()}:* {safe_msg}"
            asyncio.create_task(self._send_telegram_message(text))
