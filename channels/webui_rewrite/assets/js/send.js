/*
 * This function handles the initial send of the user input towards the backend.
 * Other parts of the frontend then pick that up and start interpreting the stream
 */
async function send(text) {
    console.log(text);

    // send it via websocket, and let it be received by websocket events
    window.socket.send(JSON.stringify({
        "type": "user_message",
        "content": {"role": "user", "content": text}
    }))
}
