// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-11-13) status:pending
// Alpine component behind content management in the settings modal.
// One component, four placements:
//   repoManager('module')  - Your Modules tab (clone bar + installed module cards)
//   repoManager('channel') - Your Channels tab
//   repoManager('skill')   - Your Skills tab (skills pack + skill cards)
//   repoManager('theme')   - Appearance's theme repo section
// Install flow: POST /api/libraries/stage clones a repo into the staging area
// and classifies it -> the review modal reads it (GET /api/libraries/source?token=)
// -> POST /api/libraries/install { token } commits it. Themes skip the modal:
// they are color data and CSS, so a plain confirm is enough there.
// Nothing installed is ever clobbered: skills/themes with existing names are
// skipped, modules/channels with an existing name are refused.
function repoManager(kind) {
    return {
        kind: kind,

        entries: [],
        loading: false,
        newRepoUrl: '',
        staging: false,
        committing: false,

        // live clone progress: unique key handed to /stage, polled while it runs
        cloneKey: null,
        clonePercent: 0,
        cancelling: false,
        _cloneTimer: null,
        // name of the entry currently being updated/uninstalled (null when idle).
        // scalar on purpose: the bundled alpine build sets the disabled attribute
        // for non-boolean (undefined) bind values, so disabled bindings here must
        // all resolve to strict booleans.
        busyName: null,
        message: null,
        messageKind: 'info',

        // staged repo review modal (module/channel/skill installs)
        audit: null,
        auditLineHeight: 19,

        // skills are data, not executed code, so their review dialog uses a
        // friendly single-step confirm; modules/channels get the two-step one
        get auditIsData() { return this.kind === 'skill'; },

        async init() {
            await this.refresh();
        },

        async refresh() {
            this.loading = true;
            try {
                const data = await simpleApiFetch('/api/libraries/status');
                this.entries = (data.modules || []).filter(m => m.type === this.kind);
            } catch (err) {
                this.flash(String(err), 'error');
            } finally {
                this.loading = false;
            }
        },

        flash(text, kind = 'info') {
            this.message = text;
            this.messageKind = kind;
        },

        startCloneProgress() {
            // unique key so the backend can stream this clone's percentage to
            // the poller while the stage request that started it is in flight
            this.cloneKey = 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
            this.clonePercent = 2;
            this._cloneTimer = setInterval(async () => {
                try {
                    const data = await simpleApiFetch('/api/libraries/progress?key=' + encodeURIComponent(this.cloneKey));
                    if (data && typeof data.percent === 'number') this.clonePercent = Math.min(99, data.percent);
                } catch (err) { /* transient poll failures are fine, next tick retries */ }
            }, 400);
        },

        stopCloneProgress() {
            if (this._cloneTimer) {
                clearInterval(this._cloneTimer);
                this._cloneTimer = null;
            }
            this.clonePercent = 0;
            this.cancelling = false;
        },

        async cancelClone() {
            if (!this.cloneKey || this.cancelling) return;
            this.cancelling = true;
            try {
                // the stage request itself fails with "clone cancelled" and
                // reports through the normal error flash; nothing to do here
                // beyond asking the backend to stop the subprocess
                await simpleApiPost('/api/libraries/cancel', { key: this.cloneKey });
            } catch (err) { /* the clone is already gone */ }
        },

        // split an https or ssh git url into { author, repo } (last two path segments)
        parseRepo(url) {
            if (!url) return { author: '', repo: '' };
            let path = '';
            const ssh = url.match(/^[^@/\s]+@[^:\s]+:(.+)$/);
            if (ssh) path = ssh[1];
            else {
                try { path = new URL(url).pathname; } catch (err) { path = url; }
            }
            const parts = path.split('/').filter(Boolean);
            if (parts.length) parts[parts.length - 1] = parts[parts.length - 1].replace(/\.git$/, '');
            if (parts.length >= 2) return { author: parts[parts.length - 2], repo: parts[parts.length - 1] };
            return { author: '', repo: parts[0] || '' };
        },

        repoLabel(m) {
            const parsed = this.parseRepo(m.library);
            return parsed.author ? parsed.author + '/' + parsed.repo : parsed.repo;
        },

        // per-card git helpers: the Your Modules / Your Channels lists render from
        // the settings store (module names) and look git info up by name
        entryFor(name) {
            return this.entries.find(e => e.name === name) || null;
        },

        isGitContent(name) {
            const entry = this.entryFor(name);
            return Boolean(entry && entry.git);
        },

        repoNameOf(name) {
            const entry = this.entryFor(name);
            return entry ? this.repoLabel(entry) : '';
        },

        async updateContent(name) {
            const entry = this.entryFor(name);
            if (entry) await this.updateEntry(entry);
        },

        async uninstallContent(name) {
            const entry = this.entryFor(name);
            if (entry) await this.uninstall(entry);
        },

        async stageAndInstall() {
            const url = (this.newRepoUrl || '').trim();
            if (!url) return;
            if (!(url.includes('://') || url.startsWith('git@'))) {
                this.flash('That does not look like a git URL.', 'error');
                return;
            }

            this.staging = true;
            this.flash(null);
            this.startCloneProgress();
            try {
                const info = await simpleApiPost('/api/libraries/stage', { url: url, progress_key: this.cloneKey });

                const homes = { module: 'Your Modules', channel: 'Your Channels', skill: 'Your Skills', theme: 'Appearance' };
                if (info.kind !== this.kind) {
                    this.flash('That repo is a ' + info.kind + ' repo - install it from ' + homes[info.kind] + '.', 'error');
                    return;
                }

                if (info.kind === 'module' || info.kind === 'channel') {
                    if (info.skipped.length) {
                        this.flash("'" + info.name + "' is already installed - uninstall it first to reinstall.", 'error');
                        return;
                    }
                } else if (!info.entries.length && !info.skipped.length) {
                    this.flash('That repo has no installable ' + (this.kind === 'skill' ? 'skill folders' : 'theme files') + ' at its root.', 'error');
                    return;
                }

                this.newRepoUrl = '';

                if (this.kind === 'theme') {
                    // themes are color data and CSS: no code runs, a plain confirm suffices
                    let text = 'Download themes from\n' + url + '?';
                    if (info.entries.length) text += '\n\nInstall: ' + info.entries.join(', ');
                    if (info.skipped.length) text += '\nAlready installed, will be skipped: ' + info.skipped.join(', ');
                    if (!confirm(text)) return;
                    await this.commit(info.token);
                } else {
                    await this.openAudit(info.token);
                }
            } catch (err) {
                this.flash(String(err), 'error');
            } finally {
                this.stopCloneProgress();
                this.staging = false;
            }
        },

        // ---- staged repo review modal ----
        async openAudit(token) {
            this.audit = {
                token, loading: true, error: null,
                kind: this.kind, url: '', entries: [], skipped: [],
                code: '', files: [], file: '', truncated: false,
                flags: [], warnings: [], focusLine: 0
            };
            await this.fetchAuditSource();
        },

        async fetchAuditSource() {
            const a = this.audit;
            if (!a) return;
            a.loading = true;
            a.error = null;
            try {
                const url = '/api/libraries/source?token=' + encodeURIComponent(a.token)
                    + (a.file ? '&file=' + encodeURIComponent(a.file) : '');
                const data = await simpleApiFetch(url);
                Object.assign(a, data);
                a.loading = false;
            } catch (err) {
                a.error = String(err);
                a.loading = false;
            }
        },

        async auditSelectFile(rel) {
            if (!this.audit || rel === this.audit.file) return;
            this.audit.file = rel;
            this.audit.focusLine = 0;
            await this.fetchAuditSource();
        },

        get auditLineNums() {
            const count = this.audit && this.audit.code ? this.audit.code.split('\n').length : 0;
            return Array.from({ length: count }, (_, i) => i + 1);
        },

        get auditHighlighted() {
            if (!this.audit || !this.audit.code) return '';
            const code = this.audit.code;
            // pick the grammar by file extension: skill packs review .md files too
            const LANG_BY_EXT = { py: 'python', json: 'json', css: 'css', md: 'markdown', yaml: 'yaml', yml: 'yaml', html: 'xml', js: 'javascript' };
            try {
                if (typeof hljs !== 'undefined') {
                    const ext = (this.audit.file || '').split('.').pop().toLowerCase();
                    const lang = LANG_BY_EXT[ext] || (this.audit.kind === 'skill' ? 'markdown' : 'python');
                    // hljs output is escaped markup, safe for x-html (same
                    // sanctioned escape hatch as the coder tool displays)
                    return hljs.getLanguage(lang)
                        ? hljs.highlight(code, { language: lang }).value
                        : hljs.highlightAuto(code).value;
                }
            } catch (err) { /* fall through to plain escaping */ }
            return escapeHtml(code);
        },

        auditJump(line) {
            if (!this.audit) return;
            this.audit.focusLine = line;
            const box = document.getElementById('library-audit-scroll');
            if (box) box.scrollTop = Math.max(0, (line - 1) * this.auditLineHeight - box.clientHeight / 3);
        },

        closeAudit() {
            // rejecting leaves the staging copy untouched; abandoned ones are swept later
            this.audit = null;
        },

        async confirmAudit() {
            const a = this.audit;
            if (!a || a.loading || a.error) return;
            if (!this.auditIsData) {
                const extra = a.warnings.length
                    ? '\n\nHeads up: this code uses shell/exec-style APIs (see the red warnings).'
                    : '';
                if (!confirm('Really install this repo?\n\nInstalled code runs with full access to your host system - only continue if you have read it and trust this source.' + extra)) return;
            }
            const token = a.token;
            this.audit = null;
            await this.commit(token);
        },

        async commit(token) {
            this.committing = true;
            try {
                const data = await simpleApiPost('/api/libraries/install', { token });
                const installed = data.installed || [];
                const skipped = data.skipped || [];

                if (data.restart_required) {
                    // module/channel code loads at boot: restart straight away,
                    // same overlay flow as saving a module toggle in settings
                    await Alpine.store('system').restart('Restarting the server to load ' + (installed.join(', ') || 'your module') + '..');
                    return;
                } else {
                    let msg = 'Installed ' + (installed.join(', ') || 'nothing');
                    if (skipped.length) msg += ' - skipped already installed: ' + skipped.join(', ');
                    this.flash(msg + '. ' + (data.note || ''), 'success');
                }

                // the module/channel cards above come from the settings store
                if (this.kind === 'module' || this.kind === 'channel') {
                    try { await Alpine.store('settings').load(); } catch (err) { /* not fatal */ }
                }
                await this.refresh();
            } catch (err) {
                this.flash(String(err), 'error');
            } finally {
                this.committing = false;
            }
        },

        async updateEntry(m) {
            this.busyName = m.name;
            this.flash(null);
            try {
                const data = await simpleApiPost('/api/libraries/update', { name: m.name });
                if (data.up_to_date) {
                    this.flash(data.message, 'success');
                    await this.refresh();
                } else {
                    // new code came in: reboot straight away, nothing to acknowledge
                    await Alpine.store('system').restart('Restarting the server after updating ' + m.name + '..');
                }
            } catch (err) {
                this.flash(String(err), 'error');
            } finally {
                this.busyName = null;
            }
        },

        async uninstall(m) {
            const tail = this.kind === 'theme' ? '? Its files are removed from your themes folder.'
                : this.kind === 'skill' ? '? The skill folder is removed from disk.'
                : '? Its settings are kept, but dependencies nothing else needs will be removed.';
            if (!confirm('Remove ' + m.name + tail)) return;

            this.busyName = m.name;
            try {
                const data = await simpleApiPost('/api/libraries/uninstall', { name: m.name });
                if (data && data.restart_required) {
                    await Alpine.store('system').restart('Restarting the server after uninstalling ' + m.name + '..');
                    return;
                }
                await this.refresh();
            } catch (err) {
                this.flash(String(err), 'error');
            } finally {
                this.busyName = null;
            }
        },


    };
}
