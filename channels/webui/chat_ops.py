"""
functions/operations that affect chats
"""

async def op_chat_switch(channel, chat_id):
    """loads a chat, cancels any stream, notifies all clients"""
    ws_mgr = channel.websocket_manager
    if ws_mgr.active_stream_task and not ws_mgr.active_stream_task.done():
        ws_mgr.active_stream_task.cancel()

    try:
        success = await channel.context.chat.load(chat_id)
    except Exception as e:
        return False

    if success:
        ws_mgr.active_chat_id = chat_id
        await ws_mgr.broadcast({"type": "chat_switched", "id": chat_id})

    return True

async def op_chat_new(channel, category="general", title=None, tags=None):
    """creates a chat, switches to it, notifies all clients."""
    ws_mgr = channel.websocket_manager
    if ws_mgr.active_stream_task and not ws_mgr.active_stream_task.done():
        ws_mgr.active_stream_task.cancel()

    kwargs = {"category": category}
    if title:
        kwargs["title"] = title

    new_id = await channel.context.chat.new(**kwargs)

    if tags:
        await channel.context.chat.set("tags", list(tags))
        channel.context.chat.data.save()

    ws_mgr.active_chat_id = new_id

    await ws_mgr.broadcast({"type": "chat_switched", "id": new_id})
    return new_id

async def op_chat_delete(channel, chat_id):
    """deletes a chat and points all clients at whatever is loaded now"""
    await channel.context.chat.delete(chat_id)
    await channel.websocket_manager.broadcast({
        "type": "chat_switched",
        "id": channel.context.chat.get("id"),
    })

def validate_category_format(name):
    name = (name or "").strip()

    if not name:
        return "category name cannot be empty", None
    if ":" in name:
        return "':' is reserved for subcategories", None

    return None, name

def validate_category_name(name, chat_store):
    """for explicitly creating a new category"""
    error, name = validate_category_format(name)
    if error:
        return error, None

    existing = [
        (chat.get("category") or "general")
        for chat in chat_store.data
    ]
    if name in existing:
        return f"'{name}' already exists", None

    return None, name

async def op_chat_rename(channel, title, chat_id=None):
    """renames a chat (current chat when no id given), saves, notifies"""
    chat_store = channel.context.chat

    if chat_id:
        index = chat_store._find_index(chat_id)
        if index is None:
            return False
        await chat_store.set("title", title, index=index)
        tags = chat_store.data[index].get("tags") or []
    else:
        await chat_store.set("title", title)
        tags = chat_store.get("tags") or []

    chat_store.data.save()

    await channel.websocket_manager.broadcast({
        "type": "chat_metadata_updated",
        "title": title,
        "tags": tags,
    })
    return True
