function keyboardShortcuts() {
    return {
        destroy() {
            Alpine.store('keyboard').stopRecording();
        }
    };
}
