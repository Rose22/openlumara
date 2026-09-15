/* 
 * --- useful functions for sending/receiving to/from the backend API and websockets
 */
async function simpleApiFetch(url) {
    // fetches something from the API and returns the data extracted from the JSON response
    raw_data = await(
        await fetch(url)
    ).json()

    if (!raw_data.success) {
        throw raw_data.data;
    }

    return raw_data.data;
}
async function simpleApiPost(url, content=null) {
    // posts something to the API and returns the data extracted from the JSON response
    raw_data = await(
        await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(content)
        })
    ).json()

    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
    // removed console.log of every response payload: devtools keeps a hard
    // reference to every logged object until the console is cleared, so
    // this was quietly retaining the full response data of every single api
    // call (including big chat payloads) for the lifetime of the tab.

    if (!raw_data.success) {
        throw raw_data.data;
    }

    return raw_data.data;
}

async function simpleSocketSend(data) {
    // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
    // same as above: logging every outgoing socket payload retained a
    // reference to every sent message (and its base64 attachments) in the
    // console buffer forever.
    try {
        return window.socket.send(JSON.stringify(data));
    } catch (e) {
        return false
    }
}
