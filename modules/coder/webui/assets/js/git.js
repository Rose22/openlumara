/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
   git sidebar tab for the coder module: status, stage/unstage, commit,
   branch switching, log, and a diff viewer modal. talks to the
   /api/ext/coder/git_* routes. has its own sandbox picker: it does NOT
   follow the coder filetree tab. */
const GIT_PANEL = {
    sandboxes: [],
    sandbox: "",
    subpath: "",
    repos: [],
    _autoPicked: false,
    _didRestore: false,
    read_only: false,
    ready: false,
    loading: false,
    error: "",
    is_repo: false,
    branch: "",
    branches: [],
    changes: [],
    message: "",
    committing: false,
    // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
    // amend mode + the HEAD info it would amend, served by git_status
    amend: false,
    lastCommit: { hash: "", msg: "" },
    _preAmendMsg: "",
    log: [],
    diff: { path: "", staged: false, lines: [], loading: false },
    push: {
        branch: "", remote: "", upstream: "", has_upstream: false, target: "",
        ahead: [], behind: 0, dirty: false, loading: false, pushing: false, error: "",
        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        // review-before-push: files a push would ship + one expanded file diff
        files: [], filesNote: "", reviewPath: "", reviewLines: [], reviewRows: [], reviewLoading: false,
    },
    // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    // fetch/pull state
    pull: { loading: false, incoming: [], error: "", pulling: false },
    // branch management (manage-branches modal state)
    branchModal: { newName: "", confirming: null, submitting: false, error: "" },
    _currentBranch: "",
    // conflicts
    conflicts: [],
    // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-11-24 harness:openlumara
    // branch-vs-branch compare modal: base..head over local + remote refs
    bd: {
        refs: { local: [], remote: [] },
        base: "", head: "",
        files: [], ahead: 0, behind: 0, loading: false, error: "",
        openPath: "", lines: [], rows: [], diffLoading: false,
    },


    async refresh(force = false) {
        // own sandbox picker (header button forces a rescan of both the
        // sandbox list and the repos inside the selected sandbox)
        if (!this.sandboxes.length || force) {
            try {
                const sd = await simpleApiFetch("/api/ext/coder/sandboxes") || {};
                this.sandboxes = sd.sandboxes || [];
            } catch (e) {
                this.sandboxes = [];
            }
        }

        // selection vanished (sandbox removed from config): fall back
        if (this.sandbox && !this.sandboxes.includes(this.sandbox)) {
            this.sandbox = "";
            this.subpath = "";
            this.repos = [];
            this._autoPicked = false;
        }
        if (!this.sandbox && this.sandboxes.length) {
            // prefer the sandbox chosen before a page reload over the
            // plain first entry
            const saved = localStorage.getItem("git_sandbox") || "";
            this.sandbox = this.sandboxes.includes(saved) ? saved : this.sandboxes[0];
        }

        if (!this.sandbox) {
            this.error = "no sandboxes configured";
            this.ready = true;
            return;
        }

        this.loading = true;
        this.error = "";

        // (re)discover repos inside the sandbox: the root itself plus nested
        // folders containing a .git, so 'dev/openlumara_dev' is selectable.
        // the header refresh button (refresh(true)) doubles as the rescan.
        if (!this.repos || !this.repos.length || force) {
            this._autoPicked = false;
            try {
                const rd = await simpleApiFetch(`/api/ext/coder/git_repos?sandbox=${encodeURIComponent(this.sandbox)}`);
                this.repos = rd.repos || [];
            } catch (e) {
                this.repos = [];
            }
        }

        // first load of the page only: restore the repo this sandbox had
        // before the reload (per-sandbox key, root = ""). once per page so
        // later refreshes never undo a manual pick of "(root)".
        if (!this.subpath && !this._didRestore) {
            this._didRestore = true;
            const savedRepo = localStorage.getItem("git_repo::" + this.sandbox) || "";
            if (this.repos.includes(savedRepo)) {
                this.subpath = savedRepo;
                this._autoPicked = true; // a restored choice beats auto-hop
            }
        }

        if (!this.repos || !this.repos.includes(this.subpath)) {
            this.subpath = "";
        }

        try {
            const data = await simpleApiFetch(`/api/ext/coder/git_status?sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}`);
            this.is_repo = !!data.is_repo;

            // sandbox root isn't a repo but the scan found nested ones:
            // hop into the first one automatically, otherwise the panel
            // would sit on "not a repository" with a repo right next to it
            if (!this.is_repo && this.repos.length && !this._autoPicked) {
                this._autoPicked = true;
                this.subpath = this.repos.find(r => r !== "") || this.repos[0];
                return this.refresh();
            }

            this.branch = data.branch || "";
            this._currentBranch = this.branch;
            this.branches = data.branches || [];
            this.changes = data.changes || [];
            this.read_only = !!data.read_only;
            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
            this.lastCommit = data.last_commit || { hash: "", msg: "" };
            if (!this.lastCommit.hash) this.amend = false; // nothing left to amend
        } catch (e) {
            this.error = this.errorText(e);
            this.changes = [];
        } finally {
            // remember the effective selection across page reloads
            this._save("git_sandbox", this.sandbox);
            this._save("git_repo::" + this.sandbox, this.subpath);
            this.loading = false;
            this.ready = true;
            // check for merge conflicts in the background
            this.loadConflicts();
        }
    },

    _save(key, val) {
        try { localStorage.setItem(key, val); } catch (e) {}
    },

    stagedCount() {
        return this.changes.filter(c => c.staged).length;
    },

    // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
    // keep-committed layout: the clean violet rows (file lives only in an
    // unpushed commit, nothing to do until push) sink to a pinned group at
    // the BOTTOM. dirty files - ringed or not - stay in the active group on
    // top, since they still want staging/committing. keys are path-based,
    // so rows survive the regroup when their state changes.
    activeChanges() {
        return this.changes.filter(c => !c.committed_only);
    },
    // a file that is committed AND dirty again exists once per group, so
    // the section header counts unique paths, not rows
    changeCount() {
        return new Set(this.changes.map(c => c.path)).size;
    },
    pendingChanges() {
        return this.changes.filter(c => c.committed_only);
    },

    badge(c) {
        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        // keep-committed mode: files that exist only in unpushed commits,
        // and dirty files whose path is ALSO in one of those commits
        if (c.committed_only) return c.also_dirty ? "committed (also edited again since)" : "committed";
        if (c.untracked) return "new";
        if (c.staged) return c.committed ? "staged (also unpushed-committed)" : "staged";
        return c.committed ? "changed (also unpushed-committed)" : "changed";
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
       amend toggle: turning it on pre-fills the last commit's message so it
       can be extended; turning it off again restores whatever was typed
       before, as long as the message is still the untouched pre-fill. # */
    toggleAmend() {
        if (this.amend) {
            this._preAmendMsg = this.message;
            if (!this.message.trim() && this.lastCommit.msg) this.message = this.lastCommit.msg;
        } else if (this.lastCommit && this.message === this.lastCommit.msg) {
            this.message = this._preAmendMsg || "";
        }
        this.error = "";
    },

    async _gitPost(route, payload) {
        this.error = "";
        try {
            await simpleApiPost(`/api/ext/coder/${route}`, { sandbox: this.sandbox, subpath: this.subpath, ...payload });
            await this.refresh();
            return true;
        } catch (e) {
            this.error = this.errorText(e);
            return false;
        }
    },

    async switchSandbox() {
        // sandbox already bound via x-model. repos are per-sandbox: hop
        // straight back into whatever was last selected for this one
        // (refresh resets the subpath again if it no longer exists)
        this.subpath = localStorage.getItem("git_repo::" + this.sandbox) || "";
        this.repos = [];
        this._autoPicked = false;
        await this.refresh();
    },

    async switchRepo() {
        // subpath already bound via x-model. a manual choice wins from now
        // on: never auto-hop over the user's selection again
        this._autoPicked = true;
        await this.refresh();
    },

    repoLabel(repo) {
        // the sandbox has its own select above, so labels are relative
        if (!repo) return "(root)";
        return repo;
    },

    stage(path) { return this._gitPost("git_stage", { paths: [path] }); },
    unstage(path) { return this._gitPost("git_unstage", { paths: [path] }); },
    // committed-only rows have nothing in the working tree to act on
    // (deleted files would even make `git add` fail): bulk ops skip them
    stageAll() { return this._gitPost("git_stage", { paths: this.changes.filter(c => !c.committed_only).map(c => c.path) }); },
    unstageAll() { return this._gitPost("git_unstage", { paths: this.changes.filter(c => !c.committed_only).map(c => c.path) }); },

    async commit() {
        const msg = (this.message || "").trim();
        if (this.committing) return;
        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        // amend: an empty message means --no-edit, so the only hard
        // requirement is *something* to fold in (message or staged files)
        if (this.amend) {
            if (!msg && !this.stagedCount()) return;
        } else if (!msg) return;

        this.committing = true;
        this.error = "";

        try {
            await simpleApiPost("/api/ext/coder/git_commit", { sandbox: this.sandbox, subpath: this.subpath, message: msg, amend: this.amend });
            this.message = "";
            this.amend = false;
            this._preAmendMsg = "";
            await this.refresh();
            // keep the log modal fresh if it happens to be open
            await this.loadLog();
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.committing = false;
        }
    },

    async switchBranch(name) {
        if (!name || this.read_only) return;
        this.error = "";

        try {
            await simpleApiPost("/api/ext/coder/git_branch", { sandbox: this.sandbox, subpath: this.subpath, name });
        } catch (e) {
            // show the error AFTER refresh so it doesn't get wiped
            await this.refresh(true);
            this.error = this.errorText(e);
            return;
        }

        await this.refresh(true);
    },

    async openLog() {
        await this.loadLog();
        Alpine.store("ui").openModal("git_log");
    },

    closeLog() {
        Alpine.store("ui").closeModal();
    },

    async openPush() {
        // fetch exactly what would be pushed BEFORE showing the confirm
        // modal; errors (no remote, detached HEAD) go to the footer.
        if (this.push.loading || this.push.pushing) return;
        this.push.loading = true;
        this.push.error = "";

        try {
            const data = await simpleApiFetch(`/api/ext/coder/git_ahead?sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}`);
            const ahead = data.ahead || [];
            if (!ahead.length) {
                this.error = "nothing to push: every commit is already on the remote";
                return;
            }
            this.push = { ...this.push, ...data, ahead, loading: false, pushing: false, error: "",
                // fresh review state per push dialog: never show the previous
                // repo/branch's file list while the new one is still loading
                files: [], filesNote: "", reviewPath: "", reviewLines: [], reviewRows: [], reviewLoading: false };
            Alpine.store("ui").openModal("git_push");
            // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
            // fire-and-forget: the commit list renders immediately, the
            // changed-files section fills in when this resolves
            this.loadPendingFiles();
        } catch (e) {
            this.error = this.errorText(e);
        } finally {
            this.push.loading = false;
        }
    },

    closePush() {
        if (this.push.pushing) return; // never close mid-push
        Alpine.store("ui").closeModal();
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
       review-before-push: list the files (with +/- counts) that sit between
       the remote base and HEAD, so Rosie can read the CODE a push ships
       rather than just its commit messages. failures are non-fatal: the
       push dialog stays fully usable without the review section. # */
    async loadPendingFiles() {
        try {
            const d = await simpleApiFetch(`/api/ext/coder/git_pending_files?sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}`);
            this.push.files = d.files || [];
            this.push.filesNote = d.note || "";
        } catch (e) {
            this.push.files = [];
            this.push.filesNote = "could not load changed files: " + this.errorText(e);
        }
    },

    async toggleReview(path) {
        // clicking the open file again collapses it
        if (this.push.reviewPath === path) {
            this.push.reviewPath = "";
            this.push.reviewLines = [];
            this.push.reviewRows = [];
            return;
        }
        this.push.reviewPath = path;
        this.push.reviewLines = [];
        this.push.reviewRows = [];
        this.push.reviewLoading = true;
        try {
            const d = await simpleApiFetch(
                `/api/ext/coder/git_pending_diff?sandbox=${encodeURIComponent(this.sandbox)}` +
                `&subpath=${encodeURIComponent(this.subpath)}&path=${encodeURIComponent(path)}`
            );
            // the user may have switched files (or closed the modal) while
            // this was in flight: drop the response if it is no longer wanted
            if (this.push.reviewPath !== path) return;
            this.push.reviewLines = String(d.diff || "(no changes)").split("\n");
            this.push.reviewRows = d.rows || [];
        } catch (e) {
            if (this.push.reviewPath !== path) return;
            this.push.reviewLines = [this.errorText(e)];
            this.push.reviewRows = [];
        } finally {
            if (this.push.reviewPath === path) this.push.reviewLoading = false;
        }
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
       edit a committed-not-pushed file straight from the push dialog: opens
       it in the coder editor with the push diff highlighted (fetching that
       diff first when the row is still collapsed). edits land in the working
       tree, so the workflow afterwards is commit -> then push. # */
    async editPending(path) {
        const panel = Alpine.store("coderPanel");
        if (!panel) return;

        let lines = [];
        if (this.push.reviewPath === path && this.push.reviewLines.length) {
            lines = this.push.reviewLines;
        } else {
            try {
                const d = await simpleApiFetch(
                    `/api/ext/coder/git_pending_diff?sandbox=${encodeURIComponent(this.sandbox)}` +
                    `&subpath=${encodeURIComponent(this.subpath)}&path=${encodeURIComponent(path)}`
                );
                lines = String(d.diff || "").split("\n");
            } catch (e) {
                lines = []; // no highlights is no reason to refuse opening the file
            }
        }

        // pending paths are repo-relative; the editor wants sandbox-relative
        const full = this.subpath ? this.subpath + "/" + path : path;

        let marks = null;
        const p = this.parseDiffPoints(lines);
        if (p.adds.length || p.dels.length) {
            marks = { adds: p.adds, dels: p.dels, label: "changes in this push" };
        }

        // same sandbox handoff as editFile(): the git tab has its own picker
        if (panel.sandbox !== this.sandbox) {
            panel.sandbox = this.sandbox;
            panel.onSandboxChange();
        }

        panel.openFile({ path: full }, 0, marks);
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       fetch + pull # */
    async doFetch() {
        if (this.pull.loading) return;
        this.pull.loading = true;
        this.pull.error = "";
        try {
            const data = await simpleApiPost("/api/ext/coder/git_fetch", {
                sandbox: this.sandbox, subpath: this.subpath,
            });
            this.pull.incoming = data.incoming || [];
            if (!this.pull.incoming.length) {
                this.error = "already up to date";
            }
            await this.refresh();
        } catch (e) {
            this.pull.error = this.errorText(e);
        } finally {
            this.pull.loading = false;
        }
    },

    async doPull() {
        if (this.pull.pulling) return;
        this.pull.pulling = true;
        this.pull.error = "";
        try {
            const data = await simpleApiPost("/api/ext/coder/git_pull", {
                sandbox: this.sandbox, subpath: this.subpath,
            });
            if (data && data.pull_failed) {
                this.conflicts = data.conflicts || [];
                this.error = "pull finished with conflicts — resolve them below";
                Alpine.store("ui").openModal("git_conflicts");
            } else {
                this.conflicts = [];
                await this.refresh();
            }
        } catch (e) {
            this.pull.error = this.errorText(e);
        } finally {
            this.pull.pulling = false;
        }
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       branch select handler: if "manage branches" is picked, open the
       manager modal and revert the dropdown to the actual current branch. # */
    onBranchSelect() {
        if (this.branch === "__manage__") {
            this.branch = this._currentBranch || "";
            this.openBranchManager();
            return;
        }
        this.switchBranch(this.branch);
    },

    openBranchManager() {
        this._currentBranch = this.branch;
        Alpine.store("ui").openModal("git_branch");
    },

    async closeBranchManager() {
        Alpine.store("ui").closeModal();
        await this.refresh(true);
    },

    async createBranch(name) {
        if (!name || !name.trim()) return;
        this.branchModal.error = "";
        this.branchModal.submitting = true;
        try {
            await simpleApiPost("/api/ext/coder/git_branch_create", {
                sandbox: this.sandbox, subpath: this.subpath, name: name.trim(), checkout: true,
            });
            this.branchModal.newName = "";
            await this.refresh(true);
        } catch (e) {
            this.branchModal.error = this.errorText(e);
        } finally {
            this.branchModal.submitting = false;
        }
    },

    async deleteBranch(name) {
        this.branchModal.error = "";
        this.branchModal.submitting = true;
        try {
            await simpleApiPost("/api/ext/coder/git_branch_delete", {
                sandbox: this.sandbox, subpath: this.subpath, name: name, force: true,
            });
            this.branchModal.confirming = null;
            await this.refresh(true);
        } catch (e) {
            this.branchModal.error = this.errorText(e);
        } finally {
            this.branchModal.submitting = false;
        }
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       conflicts # */
    async loadConflicts() {
        try {
            const params = `sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}`;
            const data = await simpleApiFetch("/api/ext/coder/git_conflicts?" + params);
            this.conflicts = data.conflicts || [];
        } catch (e) {
            this.conflicts = [];
        }
    },

    async resolveConflict(path, strategy) {
        try {
            await simpleApiPost("/api/ext/coder/git_resolve", {
                sandbox: this.sandbox, subpath: this.subpath, path: path, strategy: strategy,
            });
            await this.loadConflicts();
            await this.refresh();
        } catch (e) {
            this.error = this.errorText(e);
        }
    },

    closeConflicts() {
        Alpine.store("ui").closeModal();
    },



    async doPush() {
        if (this.push.pushing) return;
        this.push.pushing = true;
        this.push.error = "";

        try {
            await simpleApiPost("/api/ext/coder/git_push", { sandbox: this.sandbox, subpath: this.subpath });
            Alpine.store("ui").closeModal();
            await this.refresh();
        } catch (e) {
            // keep the modal open so the rejection reason is readable
            this.push.error = this.errorText(e);
        } finally {
            this.push.pushing = false;
        }
    },

    async loadLog() {
        try {
            // n=100: the backend default is only 20, which always fits the
            // modal body - so the list never got a scrollbar and deeper
            // history was unreachable. 100 is the backend's hard cap.
            const data = await simpleApiFetch(`/api/ext/coder/git_log?sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}&n=100`);
            this.log = data.log || [];
        } catch (e) {
            this.log = [];
        }
    },

    openDiff(c) {
        this.diff = { path: c.path, staged: c.staged, untracked: !!c.untracked, committed: !!c.committed_only, lines: ["loading.."], rows: [], loading: true };
        Alpine.store("ui").openModal("git_diff");

        // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        // committed-only rows are clean against HEAD: the only diff worth
        // showing is the one the push would ship (remote base..HEAD), and
        // that route returns unified + split rows in a single response
        if (c.committed_only) {
            const pend = `sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}` +
                `&path=${encodeURIComponent(c.path)}`;
            simpleApiFetch(`/api/ext/coder/git_pending_diff?${pend}`)
                .then(d => {
                    this.diff.lines = String(d.diff || "(no changes)").split("\n");
                    this.diff.rows = d.rows || [];
                })
                .catch(e => {
                    this.diff.lines = [this.errorText(e)];
                    this.diff.rows = [];
                })
                .finally(() => { this.diff.loading = false; });
            return;
        }

        const params = `sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}` +
            `&path=${encodeURIComponent(c.path)}&staged=${c.staged ? 1 : 0}&untracked=${c.untracked ? 1 : 0}`;

        // fetch unified (mobile) and split (desktop) in parallel
        const unified = simpleApiFetch(`/api/ext/coder/git_diff?${params}`)
            .then(d => { this.diff.lines = String(d.diff || "(no changes)").split("\n"); })
            .catch(e => { this.diff.lines = [this.errorText(e)]; });

        const split = simpleApiFetch(`/api/ext/coder/git_split_diff?${params}`)
            .then(d => { this.diff.rows = d.rows || []; })
            .catch(() => { this.diff.rows = []; });

        Promise.all([unified, split]).finally(() => { this.diff.loading = false; });
    },

    closeDiff() {
        Alpine.store("ui").closeModal();
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
       open the changed file in the coder file editor with the diff points
       highlighted and prev/next navigation (F8). the diff modal unmounts
       itself: the ui store only shows one modal at a time. */
    async editFile() {
        const d = this.diff;
        if (!d.path || d.loading) return;

        const panel = Alpine.store("coderPanel");
        if (!panel) return;

        // diff paths are repo-relative; the editor wants sandbox-relative
        const full = this.subpath ? this.subpath + "/" + d.path : d.path;

        // untracked: every line is an addition, so highlighting would paint
        // the whole file and navigation would be pointless. open it clean.
        let marks = null;
        if (!d.untracked) {
            const p = this.parseDiffPoints(d.lines);
            if (p.adds.length || p.dels.length) {
                marks = { adds: p.adds, dels: p.dels, label: d.committed ? "changes in this push" : d.staged ? "staged changes" : "changes" };
            }
        }

        // the git tab has its own sandbox picker; point the coder tab at the
        // same sandbox so the path resolves. the tree reload is
        // fire-and-forget: openFile doesn't need it.
        if (panel.sandbox !== this.sandbox) {
            panel.sandbox = this.sandbox;
            panel.onSandboxChange();
        }

        panel.openFile({ path: full }, 0, marks);
    },

    // parse unified diff text into new-file line numbers (1-based): every
    // added line, plus one entry per deleted run (the line the deletion
    // happened at). hunk headers reseed the counter, context lines advance
    // it, '-' lines don't (they exist only in the old file).
    parseDiffPoints(lines) {
        const adds = [];
        const dels = [];
        let newLine = 0;
        let inHunk = false;
        let delPending = false;

        for (const line of lines) {
            const h = line.match(/^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
            if (h) {
                newLine = parseInt(h[1], 10);
                inHunk = true;
                continue;
            }
            if (!inHunk) continue;
            if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("\\")) continue;

            if (line.startsWith("+")) {
                adds.push(newLine);
                newLine++;
                delPending = false;
            } else if (line.startsWith("-")) {
                // one marker per deletion run, at the line it precedes
                if (!delPending) { dels.push(newLine); delPending = true; }
            } else {
                newLine++;
                delPending = false;
            }
        }

        return { adds, dels };
    },

    /* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-11-24 harness:openlumara
       branch-vs-branch compare: pick any two refs (local or remote) and see
       what differs. The backend re-validates both names and pins them to
       SHAs before diffing (git_branch_files / git_branch_file_diff). # */
    async openBranchDiff() {
        this.bd.error = "";
        try {
            const params = `sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}`;
            const d = await simpleApiFetch("/api/ext/coder/git_refs?" + params);
            this.bd.refs = { local: d.local || [], remote: d.remote || [] };
        } catch (e) {
            this.bd.error = this.errorText(e);
        }

        const all = [...this.bd.refs.local, ...this.bd.refs.remote];
        if (all.length) {
            // keep earlier picks when they still exist; otherwise default to
            // current branch vs its most likely comparison target
            if (!this.bd.head || !all.includes(this.bd.head)) {
                this.bd.head = all.includes(this.branch) ? this.branch : all[0];
            }
            if (!this.bd.base || !all.includes(this.bd.base) || this.bd.base === this.bd.head) {
                const others = all.filter(r => r !== this.bd.head);
                const fav = ["main", "master", "origin/main", "origin/master"];
                this.bd.base =
                    others.find(r => fav.includes(r)) ||
                    others.find(r => !r.includes("/")) ||
                    others[0] ||
                    "";
            }
        }

        Alpine.store("ui").openModal("git_branch_diff");
        if (this.bd.base && this.bd.head && this.bd.base !== this.bd.head) this.loadBranchFiles();
    },

    async loadBranchFiles() {
        this.bd.error = "";
        this.bd.files = [];
        this.bd.ahead = 0;
        this.bd.behind = 0;
        this.bd.openPath = "";
        this.bd.lines = [];
        this.bd.rows = [];
        if (!this.bd.base || !this.bd.head || this.bd.base === this.bd.head) return;

        this.bd.loading = true;
        try {
            const params = `sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}` +
                `&base=${encodeURIComponent(this.bd.base)}&head=${encodeURIComponent(this.bd.head)}`;
            const d = await simpleApiFetch("/api/ext/coder/git_branch_files?" + params);
            this.bd.files = d.files || [];
            this.bd.ahead = d.ahead || 0;
            this.bd.behind = d.behind || 0;
        } catch (e) {
            this.bd.error = this.errorText(e);
        } finally {
            this.bd.loading = false;
        }
    },

    swapBranches() {
        const b = this.bd.base;
        this.bd.base = this.bd.head;
        this.bd.head = b;
        this.loadBranchFiles();
    },

    async toggleBranchFile(path) {
        if (this.bd.openPath === path) {
            this.bd.openPath = "";
            this.bd.lines = [];
            this.bd.rows = [];
            return;
        }
        this.bd.openPath = path;
        this.bd.lines = [];
        this.bd.rows = [];
        this.bd.diffLoading = true;
        try {
            const params = `sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}` +
                `&base=${encodeURIComponent(this.bd.base)}&head=${encodeURIComponent(this.bd.head)}` +
                `&path=${encodeURIComponent(path)}`;
            const d = await simpleApiFetch("/api/ext/coder/git_branch_file_diff?" + params);
            // the user may have switched files or refs mid-flight
            if (this.bd.openPath !== path) return;
            this.bd.lines = String(d.diff || "(no changes)").split("\n");
            this.bd.rows = d.rows || [];
        } catch (e) {
            if (this.bd.openPath !== path) return;
            this.bd.lines = [this.errorText(e)];
            this.bd.rows = [];
        } finally {
            if (this.bd.openPath === path) this.bd.diffLoading = false;
        }
    },

    // open the file in the coder editor with the branch diff highlighted
    // (same handoff as editPending; if the working tree no longer matches
    // either ref, the marks just point at lines that already moved on)
    async openBranchFile(path) {
        const panel = Alpine.store("coderPanel");
        if (!panel) return;

        let lines = [];
        if (this.bd.openPath === path && this.bd.lines.length) {
            lines = this.bd.lines;
        } else {
            try {
                const params = `sandbox=${encodeURIComponent(this.sandbox)}&subpath=${encodeURIComponent(this.subpath)}` +
                    `&base=${encodeURIComponent(this.bd.base)}&head=${encodeURIComponent(this.bd.head)}` +
                    `&path=${encodeURIComponent(path)}`;
                const d = await simpleApiFetch("/api/ext/coder/git_branch_file_diff?" + params);
                lines = String(d.diff || "").split("\n");
            } catch (e) {
                lines = []; // no highlights is no reason to refuse opening the file
            }
        }

        // compare paths are repo-relative; the editor wants sandbox-relative
        const full = this.subpath ? this.subpath + "/" + path : path;

        let marks = null;
        const p = this.parseDiffPoints(lines);
        if (p.adds.length || p.dels.length) {
            marks = { adds: p.adds, dels: p.dels, label: this.bd.base + " \u2192 " + this.bd.head };
        }

        if (panel.sandbox !== this.sandbox) {
            panel.sandbox = this.sandbox;
            panel.onSandboxChange();
        }

        panel.openFile({ path: full }, 0, marks);
    },

    closeBranchDiff() {
        Alpine.store("ui").closeModal();
    },

    errorText(e) {
        if (e && typeof e === "object") return e.message || JSON.stringify(e);
        return String(e);
    }
};

document.addEventListener("alpine:init", () => {
    Alpine.store("gitPanel", GIT_PANEL);
});

// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
// fresh Proxy per mount (see shell.js shellTermComponent for why x-data
// must never receive the store object directly)
function gitPanelComponent() {
    const target = {};
    const src = () => Alpine.store("gitPanel") || GIT_PANEL;

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
