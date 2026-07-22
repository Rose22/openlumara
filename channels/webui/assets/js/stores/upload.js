const UPLOAD_STORE = {
    files: [],

    addFile(event) {
        this.files = Array.from(event.target.files);
        if (this.files.length === 0) return;
        event.target.value = "";
    },

    removeFile(index) {
        this.files.splice(index, 1);
    },

    readFileAsBase64(file) {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.readAsDataURL(file);
        });
    },

    clear() {
        this.files = [];
        this.processed = [];
    }
};
