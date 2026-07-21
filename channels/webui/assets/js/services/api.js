/* 
 * --- useful functions for sending/receiving to/from the backend API and websockets
 */
async function simpleApiFetch(url) {
    // fetches something from the API and returns the data extracted from the JSON response
    raw_data = await(
        await fetch(url)
    ).json()

    console.log(raw_data);

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

    if (!raw_data.success) {
        throw raw_data.data;
    }

    console.log(raw_data);

    return raw_data.data;
}

async function simpleSocketSend(data) {
    try {
        return window.socket.send(JSON.stringify(data));
    } catch (e) {
        return false
    }

    return true
}
