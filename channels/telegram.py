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
    """
    running = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            try:
                self.token = core.config.get("channels").get("settings").get("telegram").get("token")
            except AttributeError:
                pass

        self.app = None
        self.authorized_chat_id = None
        self._shutting_down = False

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
            await self._announce("Telegram channel connected.", "status")

            while self.running and not self._shutting_down:
                await asyncio.sleep(1)

        except Exception as e:
            core.log("telegram", f"Critical Error: {str(e)}")
            return False
        finally:
            await self._cleanup()

        return True

    async def _cleanup(self):
        if self.app:
            if self.app.updater.running:
                await self.app.updater.stop()
            if self.app.running:
                await self.app.stop()
            await self.app.shutdown()

    def shutdown(self):
        await self.announce("Shutting down Telegram channel...", "status")
        self.running = False
        self._shutting_down = True
        return True

    async def _tg_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id

        if self.authorized_chat_id is None:
            self.authorized_chat_id = chat_id
            await update.message.reply_text(
                "✅ Session started.\n"
            )
            core.log("telegram", f"Authorized chat ID: {chat_id}")
        elif self.authorized_chat_id != chat_id:
            await update.message.reply_text("⚠️ This bot is already in use.")

    def _format_tool_call(self, tool_data):
        """
        Parses raw tool call data into a friendly string.
        Example: 🔧 scheduler_add_job(action="Remind user...", seconds=5)
        """
        try:
            # Handle OpenAI style pydantic objects
            if hasattr(tool_data, 'function'):
                func_name = getattr(tool_data.function, 'name', 'unknown')
                raw_args = getattr(tool_data.function, 'arguments', '{}')
            # Handle dictionary style
            elif isinstance(tool_data, dict) and 'function' in tool_data:
                func_name = tool_data['function'].get('name', 'unknown')
                raw_args = tool_data['function'].get('arguments', '{}')
            else:
                return "🔧 Calling tool..."

            # Parse arguments safely using json_repair
            if isinstance(raw_args, str):
                try:
                    args_dict = json_repair.loads(raw_args)
                except Exception:
                    args_dict = {}
            elif isinstance(raw_args, dict):
                args_dict = raw_args
            else:
                args_dict = {}

            # Build arg string: key="value", key2="value2"
            arg_strs = []
            for k, v in args_dict.items():
                v_str = str(v)
                # Truncate long values
                if len(v_str) > 30:
                    v_str = v_str[:30] + ".."
                # Escape quotes for display
                v_str = v_str.replace('"', "'")
                arg_strs.append(f'{k}="{v_str}"')

            args_display = ", ".join(arg_strs)
            return f"🔧 {func_name}({args_display})"

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

        user_msg = update.message.text.strip()

        # 1. Start Typing Indicator
        typing_task = asyncio.create_task(self._keep_typing(chat_id))

        message = None
        last_edit_time = 0

        # Buffers for visual formatting
        tool_calls_display = [] # Stores "🔧 func()" strings
        response_buffer = []    # Stores normal text tokens

        try:
            # 2. Consume the stream
            async for token in self.send_stream({"role": "user", "content": user_msg}):
                t_type = token.get("type")
                content = token.get("content", "")

                # Handle Tool Calls: Format and store
                if t_type == "tool_calls":
                    if content:
                        if isinstance(content, list):
                            for tool in content:
                                tool_calls_display.append(self._format_tool_call(tool))
                        else:
                            tool_calls_display.append(self._format_tool_call(content))

                # Handle Content/Errors: Store text
                elif t_type in ["content", "error"]:
                    response_buffer.append(content)

                # 3. Construct the visual message
                # Combine tools + text for the Telegram preview
                tools_text = "\n".join(tool_calls_display)
                text_part = "".join(response_buffer)

                # Add spacing if we have both tools and text
                if tools_text and text_part:
                    visual_buffer = f"{tools_text}\n\n{text_part}"
                else:
                    visual_buffer = tools_text + text_part

                # 4. Throttled Editing
                now = time.time()
                if visual_buffer:
                    if message is None:
                        message = await context.bot.send_message(chat_id, visual_buffer)
                        last_edit_time = now
                    elif now - last_edit_time > 1.5:
                        try:
                            await message.edit_text(visual_buffer[:4000])
                            last_edit_time = now
                        except BadRequest:
                            pass

            # 5. Stop Typing & Finalize
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

            # Final clean edit
            if message:
                try:
                    await message.edit_text(visual_buffer[:4000])
                except: pass
            elif visual_buffer:
                await context.bot.send_message(chat_id, visual_buffer)

        except Exception as e:
            if not typing_task.done():
                typing_task.cancel()
            core.log("telegram", f"Error processing stream: {e}")
            await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")

    async def _keep_typing(self, chat_id: int):
        try:
            while True:
                await self.app.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
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

    async def _announce(self, message: str, type: str = None):
        if not type:
            type = "info"

        core.log("telegram", f"[{type}] {message}")

        if self.authorized_chat_id and self.app:
            emoji_map = {
                "error": "🚨",
                "warning": "⚠️",
                "status": "ℹ️",
                "info": "💬"
            }
            emoji = emoji_map.get(type, "🔔")
            safe_msg = message.replace("*", "").replace("_", "")
            text = f"{emoji} *{type.upper()}*: {safe_msg}"
            asyncio.create_task(self._send_telegram_message(text))
