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

    settings =  {
        "token": "TOKEN_HERE",
        "announce_startup": False,
        "announce_shutdown": False
    }

    async def run(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            try:
                self.token = self.config.get("token")
            except AttributeError:
                pass

        self.app = None

        # Initialize StorageText to handle the authorized chat ID
        self.auth_storage = core.storage.StorageText("telegram_chat_id")

        # Load the stored chat ID from disk
        stored_id = self.auth_storage.get()
        self.authorized_chat_id = None
        if stored_id and stored_id.strip():
            try:
                self.authorized_chat_id = int(stored_id)
                core.log("telegram", f"Restored authorized chat ID: {self.authorized_chat_id}")
            except ValueError:
                core.log("telegram", "Failed to parse stored chat ID.")

        self._shutting_down = False

        # Queue for sequential processing of standard messages
        self.message_queue = asyncio.Queue()
        self.queue_task = None

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

            # Start the queue processor worker
            self.queue_task = asyncio.create_task(self._process_queue_worker())

            if self.config.get("announce_startup"):
                await self._announce("Telegram channel connected.", "status")

            while self.running and not self._shutting_down:
                await asyncio.sleep(1)

        except Exception as e:
            core.log("telegram", f"Critical Error: {str(e)}")
            return False
        finally:
            # Clean up the queue task
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

    async def on_shutdown(self):
        if self.config.get("announce_shutdown"):
            await self.announce("Shutting down Telegram channel...", "status")
            self.running = False
            self._shutting_down = True
            return True

    async def _tg_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id

        if self.authorized_chat_id is None:
            self.authorized_chat_id = chat_id
            self.auth_storage.set(str(chat_id))
            await update.message.reply_text("✅ Session started.\n")
            core.log("telegram", f"Authorized chat ID: {chat_id}")
        elif self.authorized_chat_id != chat_id:
            await update.message.reply_text("⚠️ This bot is already in use.")

    async def _tg_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Routes incoming messages:
        - Commands (/stop, /help) -> Process immediately (concurrently).
        - Normal text -> Add to queue (sequentially).
        """
        if not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
        if self.authorized_chat_id and chat_id != self.authorized_chat_id:
            return

        if not self.authorized_chat_id:
            self.authorized_chat_id = chat_id
            self.auth_storage.set(str(chat_id))

        text = update.message.text.strip()
        cmd_prefix = core.config.get("core").get("cmd_prefix", "/")

        # Check if it is a command
        if text.startswith(cmd_prefix):
            # Execute commands immediately in a separate task to allow interruption
            # This allows /stop to cancel an ongoing stream processed by the queue worker
            asyncio.create_task(self._process_stream(update, context))
        else:
            # Queue normal messages for sequential processing
            await self.message_queue.put((update, context))

    async def _process_queue_worker(self):
        """
        Worker that processes messages from the queue one by one.
        This ensures normal messages don't overlap.
        """
        while self.running and not self._shutting_down:
            try:
                # Wait for a message from the queue
                update, context = await self.message_queue.get()

                # Process the message (this waits for the stream to finish)
                await self._process_stream(update, context)

                # Mark the task as done
                self.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                core.log("telegram", f"Queue worker error: {e}")
                await asyncio.sleep(1) # Prevent tight loop on error

    async def _process_stream(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Contains the logic for streaming AI responses to the user.
        """
        chat_id = update.effective_chat.id
        user_msg = update.message.text.strip()

        # 1. Start Typing Indicator
        typing_task = asyncio.create_task(self._keep_typing(chat_id))

        message = None
        last_edit_time = 0
        tool_calls_display = []
        response_buffer = []
        shown_reasoning_text = False

        try:
            # 2. Consume the stream
            async for token in self.send_stream({"role": "user", "content": user_msg}):
                t_type = token.get("type")
                content = token.get("content", "")
                visual_buffer = None

                if t_type == "tool_calls":
                    if content:
                        if isinstance(content, list):
                            for tool in content:
                                tool_calls_display.append(self.tc_manager.display_call(tool))
                        else:
                            tool_calls_display.append(self.tc_manager.display_call(content))
                elif t_type == "reasoning":
                    if not shown_reasoning_text:
                        visual_buffer = "thinking.."
                        shown_reasoning_text = True
                    else:
                        continue
                elif t_type in ["content", "error"]:
                    response_buffer.append(content)

                # 3. Construct the visual message
                tools_text = "\n".join(tool_calls_display)
                text_part = "".join(response_buffer)

                if not visual_buffer:
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

            # 5. Finalize
            if message:
                try:
                    await message.edit_text(visual_buffer[:4000])
                except: pass
            elif visual_buffer:
                await context.bot.send_message(chat_id, visual_buffer)

        except Exception as e:
            core.log("telegram", f"Error processing stream: {e}")
            try:
                await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")
            except:
                pass
        finally:
            if not typing_task.done():
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

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
            text = f"{emoji} *{type.upper()}:* {safe_msg}"
            asyncio.create_task(self._send_telegram_message(text))
