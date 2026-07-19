/*
 * This function handles the initial send of the user input towards the backend.
 * Other parts of the frontend then pick that up and start interpreting the stream
 */
async function send(text) {
    // send it via websocket, and let it be received by websocket events
    await simpleSocketSend({
        "type": "user_message",
        "content": {"role": "user", "content": text}
    })

    Alpine.store("stream").state = "sending";

    // add user message to messages array so it renders immediately
    getMain().messages.push({
        role: "user",
        content: text
    });
}

async function stopStream() {
    await simpleSocketSend({
        "type": "stop"
    });

    Alpine.store("stream").state = "idle";
}
