/*
 * This function handles the initial send of the user input towards the backend.
 * Other parts of the frontend then pick that up and start interpreting the stream
 */
async function send(text) {
    const uploadStore = Alpine.store("upload");
    await uploadStore.uploadFiles();

    // Build content array with text and file attachments
    let content;

    if (uploadStore.processed.length > 0) {
        // Multimodal message: combine text with file content blocks
        const contentBlocks = [];

        // Add text if present
        if (text && text.trim()) {
            contentBlocks.push({
                "type": "text",
                "text": text.trim()
            });
        }

        // Add file content blocks
        for (const file of uploadStore.processed) {
            if (file.content_block) {
                contentBlocks.push(file.content_block);
            }
        }

        // If no text and only files, add a placeholder
        if (!text?.trim() && contentBlocks.length === 0) {
            contentBlocks.push({
                "type": "text",
                "text": "[Files attached]"
            });
        }

        content = contentBlocks;
        uploadStore.clear();
    } else {
        // Text-only message
        content = text;
    }

    // send it via websocket, and let it be received by websocket events
    const success = await simpleSocketSend({
        "type": "user_message",
        "content": {"role": "user", "content": content}
    })

    await AudioManager.play("send_message");

    if (success) {
        Alpine.store("stream").state = "sending";
    }
}
