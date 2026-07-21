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
        console.log("error");
        throw raw_data.data.error;
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

    // console.log(raw_data.data);

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

/*
 * stuff to access Alpine stuff outside Alpine
 */
function getMain() {
    main = document.getElementById("main");
    return Alpine.$data(main);
}

/*
 * --- formatting stuff
 */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function partialJsonParse(str) {
    if (!str || !str.trim()) return {};

    try {
        return JSON.parse(str);
    } catch (e) {
        let completed = str.trim();
        completed = completed.replace(/,\s*([}\]])/g, '$1');

        let openBraces = (completed.match(/{/g) || []).length;
        let closeBraces = (completed.match(/}/g) || []).length;
        let openBrackets = (completed.match(/\[/g) || []).length;
        let closeBrackets = (completed.match(/]/g) || []).length;

        const openQuotes = (completed.match(/"(?<!\\)"/g) || []).length;
        if (openQuotes % 2 !== 0) {
            completed += '"';
        }

        while (closeBraces < openBraces) { completed += '}'; closeBraces++; }
        while (closeBrackets < openBrackets) { completed += ']'; closeBrackets++; }

        try {
            return JSON.parse(completed);
        } catch (e2) {
            return { _raw: str };
        }
    }
}

/* just.. utils, lol */
async function forceScrollDown(el) {
    // force scroll to the bottom
    el.scrollTop = el.scrollHeight;
}
