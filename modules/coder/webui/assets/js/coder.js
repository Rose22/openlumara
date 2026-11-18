/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   coder sidebar (sandbox dropdown + lazy file tree) and file edit modal.
   Talks to /api/ext/coder/. the tree is kept flat (rows with depth) so
   alpine renders it with one x-for; children lazy-load on first expand. */

/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   the file edit modal is CodeMirror 5, vendored under assets/vendor/.
   vendor/ deliberately sits OUTSIDE assets/css + assets/js so the webui
   channel's auto-discovery never force-loads it on every page: the
   library is lazy-loaded (sequentially - addons depend on the core, some
   modes/addons on others) the first time a file is opened, then kept
   warm for the rest of the page's life. */
const CM_BASE = "/ext-assets/coder/vendor/codemirror/";

const CM_CSS = [
    "lib/codemirror.css",
    "addon/dialog/dialog.css",
    "addon/fold/foldgutter.css",
    "addon/search/matchesonscrollbar.css",
    "addon/lint/lint.css",
];

const CM_JS = [
    "lib/codemirror.js",
    "addon/comment/comment.js",
    "addon/dialog/dialog.js",
    "addon/search/searchcursor.js",
    "addon/search/search.js",
    "addon/search/match-highlighter.js",
    "addon/scroll/annotatescrollbar.js",
    "addon/search/matchesonscrollbar.js",
    "addon/edit/matchbrackets.js",
    "addon/edit/closebrackets.js",
    "addon/edit/closetag.js",
    "addon/edit/continuelist.js",
    "addon/edit/trailingspace.js",
    "addon/selection/active-line.js",
    "addon/fold/foldcode.js",
    "addon/fold/foldgutter.js",
    "addon/fold/brace-fold.js",
    "addon/fold/comment-fold.js",
    "addon/fold/indent-fold.js",
    "addon/fold/xml-fold.js",
    "addon/fold/markdown-fold.js",
    "addon/lint/lint.js",
    "mode/xml/xml.js",
    "mode/css/css.js",
    "mode/javascript/javascript.js",
    "mode/htmlmixed/htmlmixed.js",
    "mode/jinja2/jinja2.js",
    "mode/markdown/markdown.js",
    "mode/python/python.js",
    "mode/shell/shell.js",
    "mode/yaml/yaml.js",
    "mode/toml/toml.js",
    "mode/properties/properties.js",
    // tag pairing reads metadata the xml mode registers, so it goes last
    "addon/edit/matchtags.js",
];

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// keymap files (vim ~100KB, emacs/sublime ~10KB each) are only meaningful
// when the module setting asks for them, so they stay out of the main list
// and are fetched on demand (presence then cached by the browser like
// everything else). vim is verified via CodeMirror.Vim; the others register
// themselves as CodeMirror.keyMap.<name>.
function coderLoadKeymap(mode) {
    // nano has no vendor file; it's hand-rolled below (coderDefineNanoKeymap)
    if (mode === "nano") {
        if (window.CodeMirror) coderDefineNanoKeymap();
        return Promise.resolve();
    }

    const file = { vim: "keymap/vim.js", emacs: "keymap/emacs.js", sublime: "keymap/sublime.js" }[mode];
    if (!file || !window.CodeMirror) return Promise.resolve();
    const present = mode === "vim" ? !!CodeMirror.Vim : !!CodeMirror.keyMap[mode];
    if (present) return Promise.resolve();
    return coderLoadScript(CM_BASE + file);
}

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// GNU nano emulation. nano is modeless (always typing) and ctrl-driven:
//   ctrl-f/b/n/p move, ctrl-a/e line start/end, ctrl-d delete forward,
//   ctrl-k cut (repeating appends to the cut buffer, like nano does),
//   ctrl-u uncut, ctrl-y/v page up/down, ctrl-w find, ctrl-\ replace,
//   ctrl-t go to line, ctrl-o save, ctrl-x exit, alt-u/e undo/redo.
// the cut buffer only grows while nothing was typed between cuts and the
// next cut starts exactly where the previous one left off (isClean check,
// same trick the emacs keymap's kill ring uses).
let nanoCutBuffer = "";
let nanoLastCut = null; // { pos, gen } right after a cut

function coderDefineNanoKeymap() {
    if (!window.CodeMirror || CodeMirror.keyMap.nano) return;
    const cmds = CodeMirror.commands;
    const Pos = CodeMirror.Pos;

    cmds.nanoCut = function (cm) {
        let text;
        let from;

        if (cm.somethingSelected()) {
            from = cm.getCursor("from");
            text = cm.getSelection() + "\n";
            cm.replaceSelection("", null, "cut");
        } else {
            // whole current line, newline included (deliberate deviation
            // from real nano, which cuts cursor->end of line: rosie wants
            // the whole line gone). the very last line swallows its own
            // preceding newline instead so no blank line is left behind.
            const line = cm.getCursor().line;
            const last = cm.lastLine();
            let to;
            if (line < last) {
                from = Pos(line, 0);
                to = Pos(line + 1, 0);
            } else if (last > 0) {
                from = Pos(line - 1, 0);
                to = Pos(last, cm.getLine(last).length);
            } else {
                from = Pos(0, 0);
                to = Pos(0, cm.getLine(0).length);
            }
            if (CodeMirror.cmpPos(from, to) === 0) { nanoLastCut = null; return; }
            text = cm.getRange(from, to);
            cm.replaceRange("", from, to, "+cut");
        }

        const repeat = !!nanoLastCut
            && CodeMirror.cmpPos(nanoLastCut.pos, cm.getCursor()) === 0
            && cm.isClean(nanoLastCut.gen);

        nanoCutBuffer = repeat ? nanoCutBuffer + text : text;
        nanoLastCut = { pos: cm.getCursor(), gen: cm.changeGeneration() };
    };

    cmds.nanoUncut = function (cm) {
        if (!nanoCutBuffer) return;
        cm.replaceSelection(nanoCutBuffer.replace(/\n$/, ""), "end", "paste");
        nanoLastCut = null;
    };

    CodeMirror.keyMap.nano = CodeMirror.normalizeKeyMap({
        "Ctrl-F": "goCharRight",
        "Ctrl-B": "goCharLeft",
        "Ctrl-N": "goLineDown",
        "Ctrl-P": "goLineUp",
        "Ctrl-A": "goLineStart",
        "Ctrl-E": "goLineEnd",
        "Ctrl-D": "deleteChar",
        "Ctrl-K": "nanoCut",
        "Ctrl-U": "nanoUncut",
        "Ctrl-Y": "pageUp",
        "Ctrl-V": "pageDown",
        "Ctrl-W": "findPersistent",
        "Ctrl-\\": "replace",
        "Alt-R": "replace",
        "Ctrl-T": coderJumpToLine,
        "Ctrl-O": function () { CODER_PANEL.save(); },
        "Ctrl-X": function () { CODER_PANEL.closeEditor(); },
        "Alt-U": "undo",
        "Alt-E": "redo",
        "fallthrough": "default",
    });
}

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// bindings that must win over every keymap (extraKeys always beat keymaps
// in CM5). the find/replace cluster is skipped for nano: there ctrl-f and
// ctrl-h belong to movement, and nano brings its own find (ctrl-w) and
// replace (ctrl-\ / alt-r) from the keymap. as a pragmatic fallback we
// hand nano ctrl-g for find: nano itself only uses that key for help, and
// the browser swallows ctrl-w before the page ever sees it.
function coderExtraKeys(keyMapName, panel) {
    const keys = {
        "Ctrl-S": () => panel.save(),
        "Cmd-S": () => panel.save(),
        "Ctrl-Alt-G": coderJumpToLine,
        "Cmd-Alt-G": coderJumpToLine,
        // jump between diff points when the file was opened from
        // the git sidebar's diff view (no-ops otherwise)
        "F8": () => panel.diffJump(1),
        "Shift-F8": () => panel.diffJump(-1),
        "Ctrl-/": "toggleComment",
        "Cmd-/": "toggleComment",
        // markdown keeps its lists going (that command falls back
        // to newlineAndIndent on its own outside lists); line
        // comments continue their prefix; everything else a plain
        // newline. CM5 has NO continue-comment command (that was
        // CM4), hence the hand-rolled helper below. must
        // execCommand directly: CM5 treats a function binding's
        // return value as "handled", not as a command.
        "Enter": (editor) => {
            if (String(editor.getOption("mode")) === "markdown") {
                editor.execCommand("newlineAndIndentContinueMarkdownList");
            } else if (!coderContinueLineComment(editor)) {
                editor.execCommand("newlineAndIndent");
            }
        },
    };

    if (keyMapName === "nano") {
        keys["Ctrl-G"] = "find";
    } else {
        Object.assign(keys, {
            "Ctrl-F": "find",
            "Cmd-F": "find",
            "F3": "findNext",
            "Shift-F3": "findPrev",
            "Ctrl-G": "findNext",
            "Cmd-G": "findNext",
            "Shift-Ctrl-G": "findPrev",
            "Shift-Cmd-G": "findPrev",
            "Ctrl-H": "replace",
            "Cmd-Alt-F": "replace",
        });
    }

    return keys;
}

// the live editor instance lives OUTSIDE the Alpine store on purpose:
// a reactive proxy wrapped around a whole CodeMirror would be a world
// of hurt, and nothing in the templates needs to read it.
let CODER_CM = null;

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// one-time guard for registering the :w / :wq Ex commands on the global
// CodeMirror.Vim object (vim.js ships no built-ins for these).
let CODER_VIM_EX = false;
let CODER_CM_LOAD = null;

/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   diff-point state (marks handed over by the git sidebar's diff view, and
   since 2026-10-14 by the deslop review: spec.kind "deslop").
   CodeMirror line handles live OUTSIDE the Alpine store, same reasoning
   as CODER_CM: reactive proxies around editor internals are a bad time.
   spec = { adds: [1-based lines], dels: [...], label, kind }; adds/dels hold
   the applied line handles; points holds the nav handles (sorted); addClass
   is the background class applied (so clearing removes the right one). */
let CODER_DIFF = { spec: null, adds: [], dels: [], points: [], addClass: null, kind: "" };

function coderLoadScript(src) {
    return new Promise((resolve, reject) => {
        const s = document.createElement("script");
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error("failed to load " + src));
        document.head.appendChild(s);
    });
}

function coderLoadCss(href) {
    return new Promise((resolve, reject) => {
        const l = document.createElement("link");
        l.rel = "stylesheet";
        l.href = href;
        l.onload = resolve;
        l.onerror = () => reject(new Error("failed to load " + href));
        document.head.appendChild(l);
    });
}

function coderLoadCodeMirror() {
    if (!CODER_CM_LOAD) {
        CODER_CM_LOAD = (async () => {
            await Promise.all(CM_CSS.map((f) => coderLoadCss(CM_BASE + f)));
            // sequential: script order IS dependency order here
            for (const f of CM_JS) {
                await coderLoadScript(CM_BASE + f);
            }
            return window.CodeMirror;
        })().catch((e) => {
            CODER_CM_LOAD = null; // allow a retry on the next open
            throw e;
        });
    }
    return CODER_CM_LOAD;
}

// theme classes defined in coder.css, palette-matched to the
// github-dark/light code themes the chat uses
function coderThemeName() {
    const theme = Alpine.store("theme");
    return theme && theme.mode === "light" ? "lumara-light" : "lumara";
}

// maximized is a persisted preference (localStorage, same pattern as
// coder_sandbox): once you go big, every later open stays big
function coderMaxStored() {
    try { return localStorage.getItem("coder_editor_maximized") === "1"; } catch (e) { return false; }
}

/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   live lint: hands the buffer to the coder module's treesitter check
   (the same one that gates saves) and maps its diagnostics onto CM
   annotations. the lint addon debounces this; positions are clamped to
   the current document because typing between request and response can
   move the edges. */
// async getAnnotations signature per addon/lint/lint.js:
// (text, updateCallback, linterOptions, cm). in async mode the addon also
// drops responses when the doc changed while the request was in flight.
function coderLint(text, update, linterOptions, cm) {
    const panel = Alpine.store("coderPanel");
    if (!panel || !panel.editor.path) return update([]);

    simpleApiPost("/api/ext/coder/lint", {
        sandbox: panel.sandbox,
        path: panel.editor.path,
        content: text,
    }).then((data) => {
        const anns = (data && data.annotations) || [];
        update(anns.map((a) => coderLintAnnotation(cm, a)));
    }).catch(() => update([]));
}

function coderLintAnnotation(cm, a) {
    const lastLine = cm.lastLine();
    const line = Math.min(Math.max((a.line || 1) - 1, 0), lastLine);
    const ch = Math.min(Math.max((a.col || 1) - 1, 0), Math.max(0, cm.getLine(line).length - 1));

    let endLine = Math.min(Math.max((a.end_line || a.line || 1) - 1, 0), lastLine);
    let endCh = Math.max((a.end_col || (a.col || 1)) - 1, ch + 1);
    if (endCh > cm.getLine(endLine).length) {
        endLine = line;
        endCh = Math.max(cm.getLine(line).length, ch + 1);
    }

    return {
        from: CodeMirror.Pos(line, ch),
        to: CodeMirror.Pos(endLine, endCh),
        message: a.message || "syntax error",
        severity: "error",
    };
}

/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   continue a line comment across newlines: "# foo" + Enter -> "# foo\n# ".
   the cursor must sit after a line-comment marker that the mode actually
   tokenises as a comment (so a "#" inside a string doesn't count). returns
   false when nothing applies and the caller should do a plain newline.
   block comments are left alone on purpose. */
function coderContinueLineComment(cm) {
    if (cm.getOption("readOnly")) return false;
    const mode = cm.getMode();
    const lc = mode && mode.lineComment;
    if (!lc) return false;

    const ranges = cm.listSelections();
    const replacements = [];
    for (const r of ranges) {
        if (!r.empty()) return false;
        const line = cm.getLine(r.head.line) || "";
        const idx = line.lastIndexOf(lc, r.head.ch - lc.length);
        if (idx === -1) return false;
        const type = String(cm.getTokenTypeAt({ line: r.head.line, ch: idx + 1 }));
        if (!/(^|\s)comment/.test(type)) return false;
        replacements.push("\n" + line.slice(0, idx) + lc + " ");
    }
    cm.replaceSelections(replacements, "end", "+");
    return true;
}

// ctrl+alt+g: prompt for a line number via the dialog addon
function coderJumpToLine(cm) {
    cm.openDialog('jump to line: <input type="text" style="width: 6em">', (val) => {
        const n = parseInt(val, 10);
        if (!n) return;

        const line = Math.min(Math.max(n - 1, 0), cm.lastLine());
        cm.setCursor({ line: line, ch: 0 });
        cm.scrollIntoView({ line: line, ch: 0 }, 120);
        cm.focus();
    }, {
        value: String(cm.getCursor().line + 1),
        selectValueOnOpen: true,
    });
}

function coderVimState(cm) {
    const vim = cm && cm.state && cm.state.vim;
    if (!vim) return { mode: "normal", subMode: "" };

    if (vim.visualMode) {
        return {
            mode: "visual",
            subMode: vim.visualLine ? "linewise" : vim.visualBlock ? "blockwise" : "",
        };
    }

    if (vim.insertMode) {
        return {
            mode: cm.getOption("overwrite") ? "replace" : "insert",
            subMode: "",
        };
    }

    return { mode: "normal", subMode: "" };
}

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// recently-opened files, persisted to localStorage as
// [{ sandbox, path, at }] newest-first. lives on the panel store so the
// welcome panel (templates/chat/welcome.html) and the sidebar share one
// list. entries pointing at deleted/moved files aren't checked against
// the disk: openFile surfaces the read error, and deleting an entry
// prunes the list (see deleteRow).
const CODER_RECENTS_KEY = "coder_recent_files";
const CODER_RECENTS_MAX = 10;

function coderLoadRecents() {
    try {
        const raw = JSON.parse(localStorage.getItem(CODER_RECENTS_KEY));
        if (!Array.isArray(raw)) return [];
        return raw.filter((r) => r && r.sandbox && r.path).slice(0, CODER_RECENTS_MAX);
    } catch (e) {
        return [];
    }
}

function coderSaveRecents(list) {
    try {
        localStorage.setItem(CODER_RECENTS_KEY, JSON.stringify(list));
    } catch (e) {}
}

function coderPushRecent(sandbox, path) {
    if (!sandbox || !path) return;
    const list = coderLoadRecents().filter((r) => !(r.sandbox === sandbox && r.path === path));
    list.unshift({ sandbox: sandbox, path: path, at: Date.now() });
    coderSaveRecents(list.slice(0, CODER_RECENTS_MAX));
}



// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// pinned files: same shape as recents but never expire and cap higher.
// pinned first, newest pin first (togglePin unshifts).
const CODER_PINNED_KEY = "coder_pinned_files";
const CODER_PINNED_MAX = 20;

function coderLoadPinned() {
    try {
        const raw = JSON.parse(localStorage.getItem(CODER_PINNED_KEY));
        if (!Array.isArray(raw)) return [];
        return raw.filter((r) => r && r.sandbox && r.path).slice(0, CODER_PINNED_MAX);
    } catch (e) {
        return [];
    }
}

function coderSavePinned(list) {
    try {
        localStorage.setItem(CODER_PINNED_KEY, JSON.stringify(list));
    } catch (e) {}
}

function coderSetPinned(sandbox, path, on) {
    const list = coderLoadPinned().filter((r) => !(r.sandbox === sandbox && r.path === path));
    if (on) list.unshift({ sandbox: sandbox, path: path, at: Date.now() });
    coderSavePinned(list.slice(0, CODER_PINNED_MAX));
}

// rename/move: rewrite the path in BOTH lists in place (keeps order and
// pin status) instead of dropping the entry
function coderMoveEntry(sandbox, src, dst) {
    const fix = (list) => list.map((r) => {
        if (r.sandbox !== sandbox) return r;
        if (r.path === src) return { ...r, path: dst };
        if (r.path.startsWith(src + "/")) return { ...r, path: dst + r.path.slice(src.length) };
        return r;
    });
    coderSaveRecents(fix(coderLoadRecents()));
    coderSavePinned(fix(coderLoadPinned()));
}

// delete: drop the entry (and, for folders, everything under it) from both lists
function coderDropEntry(sandbox, path) {
    const keep = (list) => list.filter((r) => !(r.sandbox === sandbox && (r.path === path || r.path.startsWith(path + "/"))));
    coderSaveRecents(keep(coderLoadRecents()));
    coderSavePinned(keep(coderLoadPinned()));
}

// "just now" / "5m ago" / "3h ago" / "4d ago"
function coderTimeAgo(ts) {
    const s = Math.max(0, Math.floor((Date.now() - (ts || 0)) / 1000));
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
}

const CODER_PANEL = {
    sandboxes: [],
    sandbox: "",
    recents: coderLoadRecents(),
    pinned: coderLoadPinned(),
    // git snapshot of the active sandbox root, for the welcome card's
    // git strip (see loadGit / the git_recent + git_status routes)
    git: { is_repo: false, branch: "", dirty: 0, log: [], subpath: "", loaded: false },
    read_only: false,
    editor_mode: "standard", // mirrors the module setting: standard | vim | emacs | sublime (gated by enable_webui_extension)
    autosave_interval: 0, // seconds; 0 = disabled
    _autosaveTimer: null,
    markdown_preview: false,
    rows: [],
    expanded: {},
    children: {},
    rootEntries: null,
    loading: false,
    loaded: false,
    error: "",
    editor: { path: "", content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: false, maximized: false, vimMode: "normal", vimSubMode: "" },
    caretLine: 1,
    caretCol: 1,
    selLen: 0,
    // diff points opened from the git sidebar or deslop review (see CODER_DIFF above)
    diff: { active: false, count: 0, idx: -1, label: "", kind: "" },
    _reveal: 0, // line to jump to once the loaded file is in the editor
    _silent: false, // set while swapping files in (keeps change events from dirtying)

    // right-click menu + small name-prompt modal (create/rename/move)
    menu: { open: false, x: 0, y: 0, row: null },
    prompt: { mode: "", title: "", hint: "", value: "", submitting: false, error: "", row: null, parent: "" },

    // in-sidebar recursive search (replaces the tree view while active)
    search: { active: false, query: "", regex: false, running: false, results: [], truncated: false, error: "", done: false },

    // fuzzy quick-open (ctrl+p)
    quick: { query: "", idx: 0, files: [], filesLoadedFor: "" },

    // drag & drop moving
    dragPath: "",
    dropTarget: null,

    async refresh(force = false) {
        if (!this.sandboxes.length || force) {
            await this.loadSandboxes();
        }

        if (this.sandbox && (force || !this.loaded)) {
            await this.loadRoot();
        }

        // welcome card's git strip (fire-and-forget: never gates the tree)
        this.loadGit();
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       branch + dirty count + the 5 most recent commits for the active
       sandbox, shown in the welcome card's git strip. sandboxes are NOT
       assumed to be repos: repos are discovered inside them (git_repos),
       and the pick mirrors the git sidebar - a saved choice wins,
       otherwise the first repo found. status + recent commits are fetched
       in parallel for that repo; in-flight guard because sidebar mount and
       welcome card can both kick this at once. */
    async loadGit() {
        if (!this.sandbox || this._gitLoading) return;
        this._gitLoading = true;
        try {
            const repos = await simpleApiFetch(`/api/ext/coder/git_repos?sandbox=${encodeURIComponent(this.sandbox)}`)
                .then((d) => d.repos || [])
                .catch(() => []);

            let sub = localStorage.getItem("git_repo::" + this.sandbox) || "";
            if (!repos.includes(sub)) sub = repos[0] || "";

            if (!repos.length) {
                this.git = { is_repo: false, branch: "", dirty: 0, log: [], subpath: "", loaded: true };
                return;
            }

            const q = `sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(sub)}`;
            const [st, recent] = await Promise.all([
                simpleApiFetch("/api/ext/coder/git_status?" + q).catch(() => null),
                simpleApiFetch(`/api/ext/coder/git_recent?${q}&n=5`).catch(() => null),
            ]);

            this.git = {
                is_repo: !!(st && st.is_repo),
                branch: (st && st.branch) || (recent && recent.branch) || "",
                dirty: st && st.changes ? st.changes.length : 0,
                log: (recent && recent.log) || [],
                subpath: sub,
                loaded: true,
            };
        } finally {
            this._gitLoading = false;
        }
    },

    async loadSandboxes() {
        try {
            const data = await simpleApiFetch("/api/ext/coder/sandboxes") || {};
            this.sandboxes = data.sandboxes || [];
            this.read_only = !!data.read_only;
            this.editor_mode = data.editor_mode || "standard";
            this.autosave_interval = parseInt(data.autosave_interval) || 0;
        } catch (e) {
            this.sandboxes = [];
        }

        // selection vanished (sandbox removed from config): fall back
        if (this.sandbox && !this.sandboxes.includes(this.sandbox)) {
            this.sandbox = "";
        }

        if (!this.sandbox && this.sandboxes.length) {
            // prefer the sandbox chosen before a page reload over the
            // plain first entry
            const saved = localStorage.getItem("coder_sandbox") || "";
            this.sandbox = this.sandboxes.includes(saved) ? saved : this.sandboxes[0];
        }
    },

    async onSandboxChange() {
        try { localStorage.setItem("coder_sandbox", this.sandbox); } catch (e) {}
        await this.resetTree();
    },

    // drop every cached tree/quick-open/search state and refetch the root.
    // shared by the sidebar dropdown and switchSandbox (welcome panel)
    async resetTree() {
        this.expanded = {};
        this.children = {};
        this.rootEntries = null;
        this.rows = [];
        this.loaded = false;
        this.quick.filesLoadedFor = "";
        this.quick.files = [];
        this.clearSearch();

        if (this.sandbox) {
            await this.loadRoot();
            this.loadGit();
        }
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       welcome-panel helpers (templates/chat/welcome.html) ---- */

    // switch sandboxes programmatically (x-model doesn't fire on assignment)
    async switchSandbox(name) {
        if (!this.sandboxes.includes(name) || name === this.sandbox) return;
        this.sandbox = name;
        await this.onSandboxChange();
    },

    // jump to another sidebar tab (the git strip's "changed"/"git" links).
    // the core sidebar keeps sidebarTab in the shell's local Alpine scope,
    // which the chat area can't reach - so drive the tab button directly.
    // for the git tab, hand over the strip's repo pick first: the git
    // sidebar restores git_repo::<sandbox> on its first refresh.
    openGitSidebar() {
        if (this.sandbox && this.git.subpath !== undefined) {
            try { localStorage.setItem("git_repo::" + this.sandbox, this.git.subpath || ""); } catch (e) {}
        }
        const btn = document.querySelector('.sidebar-tab[data-tab="coder/git"]');
        if (btn) btn.click();
    },

    async openRecent(r) {
        if (r.sandbox !== this.sandbox) await this.switchSandbox(r.sandbox);
        if (this.sandbox !== r.sandbox) return; // sandbox vanished mid-switch
        this.openFile({ path: r.path });
    },

    clearRecents() {
        this.recents = [];
        coderSaveRecents([]);
    },

    /* ---- pinned files (file modal header button + welcome card) ---- */
    isPinned() {
        if (!this.editor.path) return false;
        return this.pinned.some((r) => r.sandbox === this.sandbox && r.path === this.editor.path);
    },

    togglePin() {
        if (!this.editor.path) return;
        const on = !this.isPinned();
        coderSetPinned(this.sandbox, this.editor.path, on);
        this.pinned = coderLoadPinned();
    },

    unpin(r) {
        coderSetPinned(r.sandbox, r.path, false);
        this.pinned = coderLoadPinned();
    },

    basename(path) {
        return String(path).split("/").pop() || path;
    },

    dirname(path) {
        const parts = String(path).split("/");
        parts.pop();
        return parts.join("/");
    },

    timeAgo(ts) {
        return coderTimeAgo(ts);
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       breadcrumbs: split the current file path into clickable segments.
       clicking a folder segment expands that path in the tree sidebar. # */
    breadcrumbs() {
        if (!this.editor.path) return [];
        const parts = this.editor.path.split("/");
        const crumbs = [];
        for (let i = 0; i < parts.length; i++) {
            crumbs.push({
                name: parts[i],
                path: parts.slice(0, i + 1).join("/"),
                is_file: i === parts.length - 1,
            });
        }
        return crumbs;
    },

    crumbClick(crumb) {
        if (crumb.is_file) return;
        // expand the folder in the tree and scroll to it
        this.clearSearch();
        const expandTo = async (path) => {
            const parts = path.split("/");
            let current = "";
            for (const seg of parts) {
                current = current ? current + "/" + seg : seg;
                if (!this.expanded[current]) {
                    const row = this.rows.find(r => r.path === current);
                    if (row && row.is_dir) await this.toggle(row);
                }
            }
        };
        expandTo(crumb.path);
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       markdown preview: renders the editor content into a preview pane
       using the globally-loaded marked.js + DOMPurify. toggled from the
       editor header. only available for .md files. # */
    isMarkdown() {
        const ext = this.editor.path ? this.editor.path.split(".").pop().toLowerCase() : "";
        return ext === "md" || ext === "markdown";
    },

    toggleMarkdownPreview() {
        this.markdown_preview = !this.markdown_preview;
    },

    renderMarkdownPreview(host) {
        if (!host || !this.markdown_preview || !CODER_CM) return;
        const raw = CODER_CM.getValue();
        try {
            const html = typeof marked !== "undefined" ? marked.parse(raw) : "<p>" + raw.replace(/</g, "&lt;") + "</p>";
            host.innerHTML = typeof DOMPurify !== "undefined" ? DOMPurify.sanitize(html) : html;
        } catch (e) {
            host.innerHTML = "<p style='color:#ff5f7a'>preview error</p>";
        }
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       autosave: debounced auto-save after the configured interval.
       triggered from the CodeMirror change handler. # */
    _scheduleAutosave() {
        if (!this.autosave_interval || this.read_only) return;
        clearTimeout(this._autosaveTimer);
        this._autosaveTimer = setTimeout(() => {
            if (this.editor.dirty && !this.editor.saving) this.save();
        }, this.autosave_interval * 1000);
    },

    _cancelAutosave() {
        clearTimeout(this._autosaveTimer);
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       OS drag-and-drop file upload: handles files dragged from the
       operating system's file manager into the sidebar tree. # */
    onOsDragOver(event) {
        // only intercept if dragging files from outside the browser
        if (this.dragPath) return; // internal drag, let normal handlers work
        if (event.dataTransfer && event.dataTransfer.types.includes("Files")) {
            event.preventDefault();
            event.stopPropagation();
            this.dropTarget = "__os_upload__";
        }
    },

    async onOsDrop(event, targetDir) {
        if (this.dragPath) return; // internal drag
        event.preventDefault();
        event.stopPropagation();
        this.dropTarget = null;

        if (this.read_only) return;
        const files = event.dataTransfer && event.dataTransfer.files;
        if (!files || !files.length) return;

        for (const file of files) {
            await this._uploadFile(file, targetDir || "");
        }
    },

    async _uploadFile(file, targetDir) {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = async () => {
                const b64 = reader.result.split(",")[1];
                try {
                    await simpleApiPost("/api/ext/coder/upload", {
                        sandbox: this.sandbox,
                        path: targetDir,
                        filename: file.name,
                        content: b64,
                    });
                    await this.reloadAfterChange([targetDir]);
                } catch (e) {
                    this.error = this.errorText(e);
                }
                resolve();
            };
            reader.onerror = () => resolve();
            reader.readAsDataURL(file);
        });
    },

    async loadRoot() {
        this.loading = true;
        this.error = "";

        try {
            const data = await simpleApiFetch(`/api/ext/coder/tree?sandbox=${encodeURIComponent(this.sandbox)}&path=`);
            this.rootEntries = data.entries || [];
            this.loaded = true;
            this.rebuild();
        } catch (e) {
            this.error = this.errorText(e);
            this.rootEntries = [];
            this.rebuild();
        } finally {
            this.loading = false;
        }
    },

    rebuild() {
        const out = [];

        const walk = (entries, depth) => {
            for (const entry of entries) {
                out.push({
                    path: entry.path,
                    name: entry.name,
                    is_dir: entry.is_dir,
                    hidden: entry.hidden,
                    blacklisted: entry.blacklisted,
                    depth: depth,
                });

                if (entry.is_dir && this.expanded[entry.path] && this.children[entry.path]) {
                    walk(this.children[entry.path], depth + 1);
                }
            }
        };

        walk(this.rootEntries || [], 0);
        this.rows = out;
    },

    async toggle(row) {
        if (this.children[row.path] == null) {
            this.loading = true;
            try {
                const data = await simpleApiFetch(`/api/ext/coder/tree?sandbox=${encodeURIComponent(this.sandbox)}&path=${encodeURIComponent(row.path)}`);
                this.children[row.path] = data.entries || [];
            } catch (e) {
                this.error = this.errorText(e);
                this.children[row.path] = [];
            } finally {
                this.loading = false;
            }
        }

        if (this.expanded[row.path]) {
            delete this.expanded[row.path];
            delete this.children[row.path];
        } else {
            this.expanded[row.path] = true;
        }

        this.rebuild();
    },

    // marks: optional { adds, dels, label } diff-point spec handed over by
    // the git sidebar's "edit" button (see git.js editFile)
    async openFile(row, line, marks) {
        const path = row.path;
        coderPushRecent(this.sandbox, path);
        this.recents = coderLoadRecents();
        this.editor = { path: path, content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: !!CODER_CM, maximized: coderMaxStored(), vimMode: "normal", vimSubMode: "" };
        this.clearDiffMarks();
        if (marks) CODER_DIFF.spec = marks;
        this._reveal = line && line > 1 ? line : 0;
        this.caretLine = this._reveal || 1;
        this.caretCol = 1;
        this.selLen = 0;

        // always (re-)open: no-op when already mounted, and cancels a close
        // requested in the same tick (quick-open calls closeModal then
        // openFile; if Alpine flushed the unmount in between, the new file
        // would otherwise have no modal to open in)
        Alpine.store("ui").openModal("coder_file");

        try {
            const data = await simpleApiFetch(`/api/ext/coder/read?sandbox=${encodeURIComponent(this.sandbox)}&path=${encodeURIComponent(path)}`);
            const content = data.content || "";
            this.editor.content = content;
            this.editor.mode = this.detectLang(path, content);
            this.loadFileIntoCm(content);
            this.revealPending();
            this.applyDiffMarks();
        } catch (e) {
            this.editor.error = this.errorText(e);
        }
    },

    // swap a freshly-fetched file into a live editor (modal was already open)
    loadFileIntoCm(content) {
        if (!CODER_CM) return;

        this._silent = true;
        CODER_CM.setValue(content);
        CODER_CM.setOption("mode", this.editor.mode || null);
        CODER_CM.clearHistory();
        this._silent = false;
    },

    // jump to the pending line (search results / reveal requests)
    revealPending() {
        if (!CODER_CM || !this._reveal) return;

        // still fetching: an empty editor would clamp the request to the
        // top and eat it. openFile calls back into here once content lands
        if (!this.editor.content && !this.editor.error) return;

        const line = Math.max(0, Math.min(this._reveal - 1, CODER_CM.lineCount() - 1));
        CODER_CM.setCursor({ line: line, ch: 0 });
        CODER_CM.scrollIntoView({ line: line, ch: 0 }, 120);
        CODER_CM.focus();
        this._reveal = 0;
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       diff points (git sidebar -> editor). added lines get a green
       background, deletion sites a red bar in a gutter that only exists
       while marks are active. everything keyed on LINE HANDLES, not line
       numbers, so the marks follow their line when edits shift the text
       above them. called from openFile (content just landed) and
       initEditor (editor just came up); both guard on the other half. */
    applyDiffMarks() {
        if (!CODER_CM || !CODER_DIFF.spec) return;
        // still fetching: same guard as revealPending
        if (!this.editor.content && !this.editor.error) return;

        const cm = CODER_CM;
        const spec = CODER_DIFF.spec;
        this.clearDiffMarks();
        CODER_DIFF.spec = spec; // clearDiffMarks wiped it; we're re-applying

        const last = cm.lastLine();
        const clamp = (n) => Math.max(0, Math.min(n - 1, last));

        // deslop markers get their own amber highlight instead of the git green
        const isDeslop = spec.kind === "deslop";
        const addClass = isDeslop ? "cm-deslop-add" : "cm-diff-add";
        CODER_DIFF.addClass = addClass;
        CODER_DIFF.kind = spec.kind || "git";

        for (const n of new Set((spec.adds || []).map(clamp))) {
            const h = cm.getLineHandle(n);
            cm.addLineClass(h, "background", addClass);
            CODER_DIFF.adds.push(h);
        }

        if (spec.dels && spec.dels.length) {
            if (cm.getOption("gutters").indexOf("cm-diff-gutter") === -1) {
                cm.setOption("gutters", cm.getOption("gutters").concat("cm-diff-gutter"));
            }
            for (const n of new Set(spec.dels.map(clamp))) {
                const h = cm.getLineHandle(n);
                const el = document.createElement("div");
                el.className = "cm-diff-del-mark";
                el.title = "line(s) deleted here";
                cm.setGutterMarker(h, "cm-diff-gutter", el);
                CODER_DIFF.dels.push(h);
            }
        }

        // navigation points: every deletion site + the start of each
        // contiguous run of added lines, sorted. deslop markers are
        // individual review targets, so there every marker line becomes its
        // own point (adjacent markers must stay separately reachable, and
        // the side panel relies on point index == marker index).
        const nums = new Set((spec.dels || []).map(clamp));
        const addNums = [...new Set((spec.adds || []).map(clamp))].sort((a, b) => a - b);
        if (isDeslop) {
            for (const n of addNums) nums.add(n);
        } else {
            let prev = -2;
            for (const n of addNums) {
                if (n !== prev + 1) nums.add(n);
                prev = n;
            }
        }

        CODER_DIFF.points = [...nums].sort((a, b) => a - b).map((n) => cm.getLineHandle(n));
        this.diff = {
            active: CODER_DIFF.points.length > 0,
            count: CODER_DIFF.points.length,
            idx: -1,
            label: spec.label || (isDeslop ? "deslop markers" : "changes"),
            kind: spec.kind || "git",
        };
    },

    clearDiffMarks() {
        this.diff = { active: false, count: 0, idx: -1, label: "", kind: "" };

        const old = CODER_DIFF;
        CODER_DIFF = { spec: null, adds: [], dels: [], points: [], addClass: null, kind: "" };

        if (!CODER_CM) return;
        const addClass = old.addClass || "cm-diff-add";
        for (const h of old.adds) {
            try { CODER_CM.removeLineClass(h, "background", addClass); } catch (e) {}
        }
        for (const h of old.dels) {
            try { CODER_CM.setGutterMarker(h, "cm-diff-gutter", null); } catch (e) {}
        }
        if (old.dels.length && CODER_CM.getOption("gutters").indexOf("cm-diff-gutter") !== -1) {
            CODER_CM.setOption("gutters", CODER_CM.getOption("gutters").filter((g) => g !== "cm-diff-gutter"));
        }
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25)
       swap the diff/marker spec on a LIVE editor without reloading the
       buffer: deslop re-marks its file after every save so highlights and
       F8 points follow marker deletions/edits in place (a full openFile
       would throw away the caret position and undo history). pass null to
       just strip the marks. */
    setDiffMarks(marks) {
        this.clearDiffMarks();
        if (!marks) return;
        CODER_DIFF.spec = marks;
        this.applyDiffMarks();
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       cycle through the diff points (F8 / shift+F8 / header buttons).
       NOTE: CM5 line handles have NO live .line property - the number is
       computed by walking the line's parent tree, exposed as
       cm.getLineNumber(handle), which returns null once the line has been
       deleted. So resolve every handle through that API and skip the dead
       ones instead of reading handle.line. */
    diffJump(dir) {
        const cm = CODER_CM;
        const pts = CODER_DIFF.points;
        const n = pts ? pts.length : 0;
        if (!cm || !n) return;

        let idx = this.diff.idx;
        let line = null;
        for (let step = 0; step < n; step++) {
            idx += dir;
            if (idx >= n) idx = 0;
            else if (idx < 0) idx = n - 1;

            line = cm.getLineNumber(pts[idx]);
            if (line != null) break;
        }
        if (line == null) return; // every point's line is gone

        this.diff.idx = idx;
        const pos = { line: line, ch: 0 };
        cm.setCursor(pos);
        cm.scrollIntoView(pos, 120);
        cm.focus();
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-14
       jump straight to a navigation point by index (used by the deslop
       side panel's marker list; F8/shift+F8 keep cycling instead). */
    diffGoTo(idx) {
        const cm = CODER_CM;
        const pts = CODER_DIFF.points;
        const n = pts ? pts.length : 0;
        if (!cm || !n) return;

        idx = Math.max(0, Math.min(idx, n - 1));
        const line = cm.getLineNumber(pts[idx]);
        if (line == null) return; // that point's line is gone

        this.diff.idx = idx;
        const pos = { line: line, ch: 0 };
        cm.setCursor(pos);
        cm.scrollIntoView(pos, 120);
        cm.focus();
    },

    diffLabel() {
        const d = this.diff;
        if (!d.active) return "";
        return d.idx < 0 ? d.count + " " + d.label : (d.idx + 1) + " / " + d.count;
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       CodeMirror mode for a file: extension map first, then a confident
       highlightAuto guess (hljs is already loaded globally) mapped onto the
       vendored modes, else plaintext. resolved ONCE on open. */
    detectLang(path, code) {
        const map = {
            py: "python", pyw: "python",
            js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "javascript",
            json: "javascript", jsonl: "javascript",
            html: "htmlmixed", htm: "htmlmixed",
            xml: "xml", svg: "xml", xsl: "xml", rss: "xml", atom: "xml",
            j2: "jinja2", jinja: "jinja2",
            css: "css", scss: "css",
            md: "markdown", markdown: "markdown",
            yml: "yaml", yaml: "yaml",
            sh: "shell", bash: "shell", zsh: "shell",
            toml: "toml",
            ini: "properties", cfg: "properties", properties: "properties", env: "properties",
            txt: "",
        };

        const ext = path.includes(".") ? path.split(".").pop().toLowerCase() : "";
        if (map[ext] !== undefined) return map[ext];

        const guessMap = {
            python: "python", javascript: "javascript", json: "javascript",
            xml: "xml", html: "htmlmixed", css: "css", scss: "css",
            markdown: "markdown", yaml: "yaml", shell: "shell", bash: "shell",
            ini: "properties", toml: "toml",
        };

        if (typeof hljs === "undefined" || !code) return "";

        try {
            const res = hljs.highlightAuto(code);
            if (res.language && res.relevance >= 8 && guessMap[res.language]) {
                return guessMap[res.language];
            }
        } catch (e) {}

        return "";
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       CodeMirror lifecycle. initEditor runs from the modal's x-init once
       the lazy library load resolves (guarded against the modal closing
       mid-load); destroyEditor runs from the x-data destroy() hook Alpine
       calls on unmount.
       everything CodeMirror does natively now: line numbers (wrap-aware),
       active line, bracket matching/closing, folding, incremental search
       (ctrl+f/ctrl+h via the dialog addon), comment toggling, undo. */
    async initEditor(host) {
        try {
            await coderLoadCodeMirror();
        } catch (e) {
            this.editor.error = "could not load the code editor (" + this.errorText(e) + ")";
            return;
        }

        // closed while the library was loading
        if (!host.isConnected) return;

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
        // keybinding scheme from the module setting
        // (standard|vim|emacs|sublime|nano). keymap fetched on demand BEFORE
        // the editor exists, so a mid-load modal close can never strand a
        // dead instance. extraKeys still win over any keymap, so the shared
        // bindings (ctrl+s, F8, Enter..) keep working everywhere; coderExtra
        // Keys drops the find cluster for nano so its movement keys survive.
        let keyMapName = "standard";
        const wantedKeymap = this.editor_mode;
        if (wantedKeymap === "vim" || wantedKeymap === "emacs"
            || wantedKeymap === "sublime" || wantedKeymap === "nano") {
            try {
                await coderLoadKeymap(wantedKeymap);
                const ok = wantedKeymap === "vim" ? !!CodeMirror.Vim : !!CodeMirror.keyMap[wantedKeymap];
                if (ok) keyMapName = wantedKeymap;
            } catch (e) {}
            if (!host.isConnected) return;
            // if the keymap failed to load, keep the UI honest: no keymap
            // means no vim mode line, and escape should close the modal.
            if (keyMapName === "standard") this.editor_mode = "standard";
        }
        const vimOn = keyMapName === "vim";

        const cm = CodeMirror(host, {
            value: this.editor.content,
            mode: this.editor.mode || null,
            theme: coderThemeName(),
            keyMap: keyMapName === "standard" ? "default" : keyMapName,
            lineNumbers: true,
            lineWrapping: true,
            styleActiveLine: true,
            matchBrackets: true,
            autoCloseBrackets: !this.read_only,
            autoCloseTags: !this.read_only,
            showTrailingSpace: !this.read_only,
            indentUnit: 4,
            tabSize: 4,
            smartIndent: true,
            readOnly: !!this.read_only,
            foldGutter: true,
            gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter", "CodeMirror-lint-markers"],
            // highlight every occurrence of the word under the caret (or
            // of the current selection). scrollbar annotation stays off:
            // the find addon already owns that lane
            highlightSelectionMatches: { showToken: /\w/, annotateScrollbar: false },
            matchTags: { bothTags: true },
            lint: { getAnnotations: coderLint, async: true, delay: 800, tooltips: true },
            extraKeys: coderExtraKeys(keyMapName, this),
        });

        CODER_CM = cm;
        this.editor.cmReady = true;

        if (vimOn) {
            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
            // real :w / :wq support. :w saves; :wq saves and closes, but
            // only when the save actually stuck (a syntax-check rejection
            // keeps editor.dirty true, so the modal stays open on the
            // error). read-only sandboxes: save() no-ops, and closeEditor
            // still confirms if anything is unsaved.
            if (!CODER_VIM_EX) {
                CODER_VIM_EX = true;
                const panel = this;
                CodeMirror.Vim.defineEx("write", "w", async function () {
                    await panel.save();
                });
                CodeMirror.Vim.defineEx("wq", "wq", async function () {
                    await panel.save();
                    if (!panel.editor.dirty) panel.closeEditor();
                });
                // :q closes (closeEditor itself confirms when dirty, like
                // vim's E370 prompt); :q! skips the confirm. vim.js has no
                // bang concept, but the raw input is preserved in params.
                CodeMirror.Vim.defineEx("quit", "q", function (cm, params) {
                    const bang = !!(params && params.input && params.input.indexOf("!") !== -1);
                    panel.closeEditor(bang);
                });
            }

            const applyVimState = (event) => {
                const state = event && (event.mode || event.subMode !== undefined)
                    ? { mode: event.mode || "normal", subMode: event.subMode || "" }
                    : coderVimState(cm);
                this.editor.vimMode = state.mode;
                this.editor.vimSubMode = state.subMode;
            };

            applyVimState();

            // CodeMirror's custom vim-mode-change signal passes the event
            // object directly. Some CodeMirror event helpers pass (cm, event),
            // so accept both shapes.
            cm.on("vim-mode-change", (...args) => {
                applyVimState(args.length > 1 ? args[1] : args[0]);
            });
        }

        cm.on("change", () => {
            if (!this._silent && !this.editor.dirty) this.editor.dirty = true;
            if (!this._silent) this._scheduleAutosave();
            // update markdown preview live
            if (this.markdown_preview && this.isMarkdown()) {
                const host = document.querySelector(".coder-md-preview");
                if (host) this.renderMarkdownPreview(host);
            }
        });

        cm.on("cursorActivity", (c) => {
            const cur = c.getCursor();
            this.caretLine = cur.line + 1;
            this.caretCol = cur.ch + 1;
            this.selLen = c.somethingSelected() ? c.getSelection().length : 0;

            /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-14
               deslop: keep the side panel's marker selection in sync with
               the caret. the active point is the last one at or above the
               caret; index changes are broadcast so deslop.js can repaint. */
            if (this.diff.active && this.diff.kind === "deslop") {
                let idx = -1;
                for (let i = 0; i < CODER_DIFF.points.length; i++) {
                    const l = c.getLineNumber(CODER_DIFF.points[i]);
                    if (l == null) continue;
                    if (l <= cur.line) idx = i;
                    else break;
                }
                if (idx !== this.diff.idx) {
                    this.diff.idx = idx;
                    window.dispatchEvent(new CustomEvent("deslop-caret", { detail: { idx: idx } }));
                }
            }

            // fallback for vim mode: some mode transitions are easiest to
            // catch from the live vim state when the cursor/selection moves.
            if (vimOn) {
                const vimState = coderVimState(c);
                this.editor.vimMode = vimState.mode;
                this.editor.vimSubMode = vimState.subMode;
            }
        });

        // follow dark/light switches while the modal stays open
        const onTheme = () => cm.setOption("theme", coderThemeName());
        window.addEventListener("theme-changed", onTheme);
        cm._coderThemeOff = () => window.removeEventListener("theme-changed", onTheme);

        this.revealPending();
        this.applyDiffMarks();
        cm.focus();
    },

    destroyEditor() {
        this._cancelAutosave();
        this.markdown_preview = false;
        if (CODER_CM) {
            try {
                CODER_CM._coderThemeOff();
            } catch (e) {}
            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
            // sync the latest text back into the store before letting go,
            // so unsaved edits survive a modal swap (ctrl+p quick-open
            // unmounts the file modal; closeQuick reopens it from here)
            try {
                this.editor.content = CODER_CM.getValue();
            } catch (e) {}
            // the editor's DOM goes away with the modal unmount; dropping the
            // reference is all the teardown a GC'd CodeMirror needs
            CODER_CM = null;
        }
        // CODER_CM is gone; this just drops the state + handle references
        this.clearDiffMarks();
        this.editor.cmReady = false;
    },

    /* ---- right-click context menu ---- */
    openMenu(event, row) {
        if (this.read_only) return;

        // both entry types now show nearly the same item count; use the
        // taller estimate so the menu never overflows the viewport edge
        const menuH = 300;
        this.menu = {
            open: true,
            x: Math.max(4, Math.min(event.clientX, window.innerWidth - 190)),
            y: Math.max(4, Math.min(event.clientY, window.innerHeight - menuH)),
            row: row,
        };
    },

    closeMenu() {
        this.menu.open = false;
    },

    menuAction(fn) {
        const row = this.menu.row;
        this.closeMenu();
        if (row) fn(row);
    },

    /* ---- small prompt modal (new file / new folder / rename / move) ---- */
    openPrompt(mode, row) {
        const parent = row.is_dir ? row.path : row.path.split("/").slice(0, -1).join("/");
        let title = "", value = "", hint = "";

        // where the new entry will actually land (files: their parent folder)
        const inPath = parent ? `${this.sandbox}/${parent}` : this.sandbox;

        if (mode === "new_file") { title = `New file in ${inPath}`; hint = "filename, e.g. notes.py"; }
        if (mode === "new_folder") { title = `New folder in ${inPath}`; hint = "folder name"; }
        if (mode === "rename") { title = `Rename ${row.name}`; value = row.name; hint = "new name"; }
        if (mode === "move") { title = `Move ${row.name}`; value = row.path; hint = "new path within the sandbox"; }

        this.prompt = { mode, title, hint, value, submitting: false, error: "", row: row, parent };
        Alpine.store("ui").openModal("coder_prompt");
    },

    closePrompt() {
        this.prompt = { mode: "", title: "", hint: "", value: "", submitting: false, error: "", row: null, parent: "" };
        Alpine.store("ui").closeModal();
    },

    async submitPrompt() {
        const p = this.prompt;
        if (!p.mode || p.submitting) return;

        const name = (p.value || "").trim();
        if (!name) { p.error = "name can't be empty"; return; }
        if (name === "." || name === "..") { p.error = "nice try"; return; }
        if ((p.mode === "new_file" || p.mode === "new_folder" || p.mode === "rename") && name.includes("/")) {
            p.error = "just a plain name here, no path separators";
            return;
        }

        p.submitting = true;
        p.error = "";

        try {
            if (p.mode === "new_file" || p.mode === "new_folder") {
                const target = p.parent ? p.parent + "/" + name : name;
                await simpleApiPost("/api/ext/coder/create", { sandbox: this.sandbox, path: target, is_dir: p.mode === "new_folder" });
                if (p.parent) this.expanded[p.parent] = true;
                await this.reloadAfterChange([p.parent]);
            } else if (p.mode === "rename") {
                const parent = p.row.path.split("/").slice(0, -1).join("/");
                const target = parent ? parent + "/" + name : name;
                await simpleApiPost("/api/ext/coder/move", { sandbox: this.sandbox, src: p.row.path, dst: target });
                if (this.editor.path === p.row.path) this.editor.path = target;
                coderMoveEntry(this.sandbox, p.row.path, target);
                this.recents = coderLoadRecents();
                this.pinned = coderLoadPinned();
                await this.reloadAfterChange([parent]);
            } else if (p.mode === "move") {
                const oldParent = p.row.path.split("/").slice(0, -1).join("/");
                const dst = name.replace(/^\/+/, "").replace(/\/+$/, "");
                const newParent = dst.includes("/") ? dst.split("/").slice(0, -1).join("/") : "";
                await simpleApiPost("/api/ext/coder/move", { sandbox: this.sandbox, src: p.row.path, dst });
                if (this.editor.path === p.row.path) this.editor.path = dst;
                coderMoveEntry(this.sandbox, p.row.path, dst);
                this.recents = coderLoadRecents();
                this.pinned = coderLoadPinned();
                await this.reloadAfterChange([oldParent, newParent]);
            }

            this.closePrompt();
        } catch (e) {
            p.error = this.errorText(e);
        } finally {
            p.submitting = false;
        }
    },

    async deleteRow(row) {
        const what = row.is_dir ? "folder" : "file";
        const extra = row.is_dir ? " Everything inside it will be removed too." : "";
        if (!window.confirm(`Delete ${what} ${row.path}?${extra}`)) return;

        try {
            await simpleApiPost("/api/ext/coder/delete", { sandbox: this.sandbox, path: row.path });

            // keep the welcome panel's lists honest (folders: their children too)
            coderDropEntry(this.sandbox, row.path);
            this.recents = coderLoadRecents();
            this.pinned = coderLoadPinned();

            if (this.editor.path === row.path || this.editor.path.startsWith(row.path + "/")) {
                this.editor = { path: "", content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: false, maximized: false, vimMode: "normal", vimSubMode: "" };
                if (Alpine.store("ui").currentModal === "coder_file") Alpine.store("ui").closeModal();
            }

            await this.reloadAfterChange([row.path.split("/").slice(0, -1).join("/")]);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    // targeted tree refresh after a filesystem change: re-fetch the given
    // folders' children, then rebuild from the root. expansion state is
    // preserved; unaffected cached folders keep their (still valid) children.
    async reloadAfterChange(forceFolders) {
        for (const folder of forceFolders || []) {
            if (!folder) continue;
            try {
                const data = await simpleApiFetch(`/api/ext/coder/tree?sandbox=${encodeURIComponent(this.sandbox)}&path=${encodeURIComponent(folder)}`);
                this.children[folder] = data.entries || [];
            } catch (e) {
                this.children[folder] = [];
            }
        }

        await this.loadRoot();
    },

    async save() {
        if (this.editor.saving || this.read_only) return;

        // while the editor is live, CodeMirror holds the true content
        const content = CODER_CM ? CODER_CM.getValue() : this.editor.content;

        this.editor.saving = true;
        this.editor.error = "";

        try {
            await simpleApiPost("/api/ext/coder/save", {
                sandbox: this.sandbox,
                path: this.editor.path,
                content: content,
            });

            this.editor.content = content;
            this.editor.dirty = false;
            this.editor.saved = "saved ✓";

            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25)
            // broadcast the save so watchers (deslop's live marker sync)
            // can re-check what now lives on disk.
            window.dispatchEvent(new CustomEvent("coder-saved", {
                detail: { sandbox: this.sandbox, path: this.editor.path },
            }));
        } catch (e) {
            if (e && typeof e === "object" && e.errors) {
                this.editor.error = (e.message ? e.message + "\n" : "") + e.errors.join("\n");
            } else {
                this.editor.error = this.errorText(e);
            }
        } finally {
            this.editor.saving = false;
        }
    },

    vimModeLabel() {
        const mode = this.editor.vimMode || "normal";
        const sub = this.editor.vimSubMode || "";
        if (mode === "visual" && sub) {
            return "VISUAL " + sub.toUpperCase();
        }
        return mode.toUpperCase();
    },

    // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    // keyboard hints in the status bar, matched to the active keymap.
    // nano advertises ctrl+g for find: its native ctrl-w is a reserved
    // browser shortcut (closes the tab) the page never receives.
    statusHints() {
        let text;
        if (this.editor_mode === "nano") {
            text = "ctrl+o save · ctrl+k cut · ctrl+u uncut · ctrl+g find · ctrl+\\ replace";
        } else {
            text = "ctrl+f find · ctrl+h replace · ctrl+alt+g line · ctrl+/ comment";
        }
        if (this.diff.active) text += " · F8 " + (this.diff.kind === "deslop" ? "markers" : "changes");
        return text;
    },

    toggleMaximize() {
        this.editor.maximized = !this.editor.maximized;
        try { localStorage.setItem("coder_editor_maximized", this.editor.maximized ? "1" : "0"); } catch (e) {}

        // CodeMirror needs to recalculate its scroll/line layout after the
        // modal box changes size. Give the browser one paint to settle first.
        if (CODER_CM) {
            setTimeout(() => {
                if (CODER_CM) CODER_CM.refresh();
            }, 0);
        }
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       revert the current file to its HEAD version. confirms with the user,
       calls the backend, then reloads the content into the editor. # */
    async revertFile() {
        if (!this.editor.path || this.read_only) return;

        const name = this.editor.path.split("/").pop();
        const msg = `Revert "${name}" to the last committed version?\n\nAll local changes (staged and unstaged) will be lost.`;
        if (!window.confirm(msg)) return;

        this.editor.saving = true;
        this.editor.error = "";

        try {
            // find the git repo subpath for this sandbox (same logic as git.js)
            let subpath = localStorage.getItem("git_repo::" + this.sandbox) || "";
            await simpleApiPost("/api/ext/coder/git_revert_file", {
                sandbox: this.sandbox,
                subpath: subpath,
                path: this.editor.path,
            });

            // reload the file content from disk
            const data = await simpleApiFetch(
                `/api/ext/coder/read?sandbox=${encodeURIComponent(this.sandbox)}&path=${encodeURIComponent(this.editor.path)}`
            );
            const content = data.content || "";
            this.editor.content = content;
            this.editor.dirty = false;
            this.editor.saved = "reverted ✓";
            this._cancelAutosave();

            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25)
            // the disk content changed too: same broadcast as save(), so
            // deslop re-checks its markers after a revert as well.
            window.dispatchEvent(new CustomEvent("coder-saved", {
                detail: { sandbox: this.sandbox, path: this.editor.path },
            }));

            // swap into the live editor
            if (CODER_CM) {
                this._silent = true;
                CODER_CM.setValue(content);
                CODER_CM.clearHistory();
                this._silent = false;
            }
        } catch (e) {
            this.editor.error = this.errorText(e);
        } finally {
            this.editor.saving = false;
        }
    },

    // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    // force=true skips the unsaved-changes confirm (used by :q!)
    closeEditor(force) {
        if (!force && this.editor.dirty && !window.confirm("This file has unsaved changes. Close anyway?")) {
            return;
        }

        this.clearDiffMarks();
        this.editor = { path: "", content: "", mode: "", dirty: false, saving: false, error: "", saved: "", cmReady: false, maximized: false, vimMode: "normal", vimSubMode: "" };
        Alpine.store("ui").closeModal();
    },

    /* ---- in-sidebar recursive search ---- */
    async runSearch() {
        const q = this.search.query.trim();
        if (!q) {
            this.clearSearch();
            return;
        }

        this.search.active = true;
        this.search.running = true;
        this.search.error = "";

        try {
            const data = await simpleApiPost("/api/ext/coder/search", {
                sandbox: this.sandbox,
                query: q,
                regex: this.search.regex,
            });
            this.search.results = data.results || [];
            this.search.truncated = !!data.truncated;
        } catch (e) {
            this.search.results = [];
            this.search.error = this.errorText(e);
        } finally {
            this.search.running = false;
            this.search.done = true;
        }
    },

    clearSearch() {
        this.search.active = false;
        this.search.query = "";
        this.search.results = [];
        this.search.truncated = false;
        this.search.error = "";
        this.search.done = false;
    },

    openResult(r) {
        this.openFile({ path: r.file }, r.line);
    },

    /* ---- fuzzy quick-open (ctrl+p) ---- */
    async openQuickOpen(event) {
        // works with the coder sidebar closed too: the modal lives in the
        // core modal area. ctrl+p is now ours everywhere in the app (print
        // loses); the store self-bootstraps via loadSandboxes when the
        // sidebar never refreshed.
        if (event) event.preventDefault();

        const prev = this.sandbox;
        if (!this.sandboxes.length) await this.loadSandboxes();
        if (!this.sandbox) return;

        // sidebar never mounted (or was showing another sandbox): keep the
        // tree caches in sync so opening a file lands in a consistent state
        if (this.sandbox !== prev) await this.resetTree();

        if (this.quick.filesLoadedFor !== this.sandbox) {
            try {
                const data = await simpleApiFetch(`/api/ext/coder/files?sandbox=${encodeURIComponent(this.sandbox)}`);
                this.quick.files = data.files || [];
                this.quick.filesLoadedFor = this.sandbox;
            } catch (e) {
                this.quick.files = [];
            }
        }

        this.quick.query = "";
        this.quick.idx = 0;
        Alpine.store("ui").openModal("coder_quick");
    },

    quickMatches() {
        const q = (this.quick.query || "").trim().toLowerCase();
        const files = this.quick.files;

        if (!q) return files.slice(0, 40);

        const scored = [];
        for (const f of files) {
            const s = coderFuzzyScore(f.toLowerCase(), q);
            if (s > 0) scored.push([s, f]);
        }

        scored.sort((a, b) => b[0] - a[0]);
        return scored.slice(0, 40).map((x) => x[1]);
    },

    quickNav(delta) {
        const max = this.quickMatches().length - 1;
        this.quick.idx = Math.max(0, Math.min(this.quick.idx + delta, max));

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
        // keep the active row visible: rAF fires after Alpine's reactive
        // DOM update, so the .active class has already moved
        requestAnimationFrame(() => {
            const el = document.querySelector(".coder-quick-list .coder-quick-item.active");
            if (el) el.scrollIntoView({ block: "nearest" });
        });
    },

    quickEnter() {
        const f = this.quickMatches()[this.quick.idx];
        if (f) this.quickOpenFile(f);
    },

    quickOpenFile(path) {
        Alpine.store("ui").closeModal();
        this.quick.files = [];
        this.quick.filesLoadedFor = "";
        this.openFile({ path });
    },

    closeQuick() {
        Alpine.store("ui").closeModal();
        this.quick.files = [];
        this.quick.filesLoadedFor = "";
        if (this.editor.path) Alpine.store("ui").openModal("coder_file");
    },

    /* ---- drag & drop moving ---- */
    onDragStart(event, row) {
        if (this.read_only) {
            event.preventDefault();
            return;
        }

        this.dragPath = row.path;
        event.dataTransfer.setData("text/plain", row.path);
        event.dataTransfer.effectAllowed = "move";
    },

    onDragEnd() {
        this.dragPath = "";
        this.dropTarget = null;
    },

    // single dragover entry point for all rows: folders highlight as drop
    // targets; file rows accept drops too (meaning "move into the file's
    // parent folder"), and both stop propagation so the root highlight
    // doesn't fight with the row highlight
    onRowDragOver(event, row) {
        if (row.is_dir) {
            if (this.canDropInto(this.dragPath, row)) {
                event.preventDefault();
                event.stopPropagation();
                this.dropTarget = row.path;
            }
            return;
        }

        if (this.dragPath && this.dragPath !== row.path) {
            event.preventDefault();
            event.stopPropagation();
            this.dropTarget = null;
        }
    },

    canDropInto(src, targetRow) {
        if (!src || !targetRow || src === targetRow.path) return false;
        if (!targetRow.is_dir) return false;
        if (src.startsWith(targetRow.path + "/")) return false; // into itself
        const name = src.split("/").pop();
        if (targetRow.path + "/" + name === src) return false; // already there
        return true;
    },

    onFolderDrop(event, row) {
        event.preventDefault();
        event.stopPropagation();

        const src = this.dragPath;
        this.dropTarget = null;
        if (!this.canDropInto(src, row)) return;

        this.moveEntry(src, row.path + "/" + src.split("/").pop());
    },

    // dropping on a file row moves into that file's parent folder
    onFileDrop(event, row) {
        event.preventDefault();
        event.stopPropagation();
        this.dropTarget = null;

        const src = this.dragPath;
        const parent = row.path.split("/").slice(0, -1).join("/");
        const dst = (parent ? parent + "/" : "") + src.split("/").pop();
        if (src && dst !== src) this.moveEntry(src, dst);
    },

    onRootDragOver(event) {
        if (!this.dragPath) return;
        event.preventDefault();
        if (this.dragPath.includes("/")) this.dropTarget = "__root__";
    },

    onRootDrop(event) {
        event.preventDefault();
        this.dropTarget = null;

        const src = this.dragPath;
        if (!src || !src.includes("/")) return;

        this.moveEntry(src, src.split("/").pop());
    },

    async moveEntry(src, dst) {
        this.dragPath = "";
        if (!dst || src === dst) return;

        try {
            await simpleApiPost("/api/ext/coder/move", { sandbox: this.sandbox, src, dst });
            if (this.editor.path === src) this.editor.path = dst;
            await this.reloadAfterChange([
                src.split("/").slice(0, -1).join("/"),
                dst.split("/").slice(0, -1).join("/"),
            ]);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    /* ---- extra context-menu actions ---- */
    copyPath(row) {
        const text = this.sandbox + "/" + row.path;
        if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
    },

    async duplicateRow(row) {
        try {
            await simpleApiPost("/api/ext/coder/duplicate", { sandbox: this.sandbox, path: row.path });
            await this.reloadAfterChange([row.path.split("/").slice(0, -1).join("/")]);
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    // prefill (never auto-send) the chat input with a file reference
    askAI(row) {
        const chat = Alpine.store("chat");
        if (!chat) return;

        const line = `look at ${this.sandbox}/${row.path}: `;
        if (chat.user_input && chat.user_input.trim() &&
            !window.confirm("Replace the current chat input?")) {
            return;
        }

        chat.user_input = line;
    },

    errorText(e) {
        if (e && typeof e === "object") return e.message || JSON.stringify(e);
        return String(e);
    }
};

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// strict fuzzy scorer for quick-open. the very first version gave every
// subsequence a positive score, so scattered junk letters matched
// everything. rules:
//  - always scored against the full path (an earlier basename-only rule
//    was reverted: too surprising)
//  - consecutive runs and path-segment starts pay; gaps cost; crossing a
//    "/" costs a little extra but stays possible
//  - hits that land entirely in the filename get a bonus so they rank
//    above deep-path matches
//  - results must end up strictly positive to be shown at all
function coderFuzzyScore(text, q) {
    let ti = 0;
    let score = 0;
    let run = 0;
    let firstFound = -1;

    for (let qi = 0; qi < q.length; qi++) {
        const found = text.indexOf(q[qi], ti);
        if (found === -1) return 0;

        const gap = found - ti;
        if (gap === 0) {
            run++;
            score += 5 + run * 2;
        } else {
            run = 0;
            let crossed = 0;
            for (let i = ti; i < found; i++) {
                if (text[i] === "/") crossed++;
            }
            score += 1 - Math.min(gap, 10) - crossed * 3;
        }

        if (found === 0 || text[found - 1] === "/") score += 6;
        if (firstFound === -1) firstFound = found;
        ti = found + 1;
    }

    // entire match lives in the filename: prefer it over path matches
    if (firstFound > text.lastIndexOf("/")) score += 5;

    // shorter names win ties; junk-scoring matches sink below zero and
    // get filtered out by the s > 0 check in quickMatches
    return score - Math.min(text.length, 60) / 10;
}

document.addEventListener("alpine:init", () => {
    Alpine.store("coderPanel", CODER_PANEL);
});

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// ctrl+p / cmd+p -> fuzzy quick-open, app-wide (the print shortcut loses).
// capture phase so we get the key before the browser or CodeMirror does.
window.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey
        && String(event.key).toLowerCase() === "p") {
        // nano uses ctrl-p to move up: while the caret is inside a nano
        // editor, leave the keystroke to CodeMirror (quick-open still
        // works everywhere else in the panel)
        if (CODER_CM && CODER_CM.getOption("keyMap") === "nano"
            && event.target && event.target.closest
            && event.target.closest(".CodeMirror")) {
            return;
        }
        CODER_PANEL.openQuickOpen(event);
    }
}, true);

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// fresh Proxy per mount (see shell.js shellTermComponent for why x-data
// must never receive the store object directly). the sidebar panel only
// mounts once today, but this keeps it remount-safe like git.js.
function coderPanelComponent() {
    const target = {};
    const src = () => Alpine.store("coderPanel") || CODER_PANEL;

    return new Proxy(target, {
        get(t, key) {
            if (key === Symbol.unscopables) return undefined;
            if (key in t) return t[key];
            const val = src()[key];
            return typeof val === "function" ? val.bind(src()) : val;
        },
        set(t, key, value) {
            if (key in t) {
                t[key] = value;
                return true;
            }
            src()[key] = value;
            return true;
        },
        has(t, key) {
            return key in t || key in src();
        },
        ownKeys() {
            return [...new Set([...Reflect.ownKeys(target), ...Object.keys(src())])];
        },
        getOwnPropertyDescriptor(t, key) {
            if (key in t) return Reflect.getOwnPropertyDescriptor(t, key);
            if (key in src()) {
                return { value: src()[key], enumerable: true, configurable: true, writable: true };
            }
            return undefined;
        },
    });
}
