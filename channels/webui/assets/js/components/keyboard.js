/*
 * Settings -> Keyboard panel.
 * All state lives in $store.keyboard; this component exists only to release
 * the key recorder when the panel (or the settings dialog) goes away.
 */
function keyboardShortcuts() {
    return {
        destroy() {
            Alpine.store('keyboard').stopRecording();
        }
    };
}
