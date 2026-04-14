// ==============================================
// Status Activity Panel — sidebar event list
// ==============================================
(function () {
    'use strict';

    const panelEl = document.getElementById('sidebarActivity');
    const listEl   = document.getElementById('sidebarActivityList');
    const queueEl  = document.getElementById('sidebarActivityQueue');

    if (!listEl) return;

    const FEED_ENDPOINT = '/api/status/feed';
    const POLL_ACTIVE   = 1000;   // ms — poll interval while active events exist
    const POLL_IDLE     = 10000;  // ms — poll interval when nothing active
    const MAX_SHOWN     = 3;      // max visible at once — extras wait in queue
    const TERMINAL_TTL  = 8 * 1000; // terminal events drop out after 8 s

    const STATE_TTL = {
        seeding:          8 * 1000, // show seeding briefly then yield
        seeding_complete: 8 * 1000,
    };

    const ACTIVE_STATES = new Set([
        'queued', 'found',
        'running', 'downloading', 'audible_downloading',
        'importing', 'converting', 'processing', 'searching',
    ]);

    const CATEGORY_ICONS = {
        download:       'fa-download',
        conversion:     'fa-sync-alt',
        metadata:       'fa-tag',
        import:         'fa-file-import',
        search:         'fa-search',
        system:         'fa-server',
        auth:           'fa-user-shield',
        abs:            'fa-book-open',
        audiobookshelf: 'fa-book-open',
        seeding:        'fa-seedling',
        cleanup:        'fa-broom',
        image_cache:    'fa-images',
    };

    const STATE_LABELS = {
        running:             'Running',
        queued:              'Queued',
        searching:           'Searching',
        found:               'Found',
        downloading:         'Downloading',
        audible_downloading: 'Downloading',
        paused:              'Paused',
        complete:            'Complete',
        converting:          'Converting',
        converted:           'Converted',
        processing:          'Processing',
        importing:           'Importing',
        imported:            'Imported',
        seeding:             'Seeding',
        seeding_complete:    'Seeded',
        completed:           'Done',
        failed:              'Failed',
        cancelled:           'Cancelled',
        warning:             'Warning',
        download_failed:     'Failed',
        conversion_failed:   'Conv. Failed',
        import_failed:       'Import Failed',
        search_failed:       'Search Failed',
    };

    // ── State ─────────────────────────────────
    const eventCache    = new Map();
    const expiryTimers  = new Map(); // eventId → timer handle for auto drop-out
    const terminalEntry = new Map(); // eventId → timestamp when first seen as terminal

    // suppressed uses composite "id:created_at" keys so a server restart (which
    // resets the integer counter) never silently hides brand-new events.
    const SUPPRESS_KEY = 'aa_suppressed_events';
    function suppKey(e) { return e.id + ':' + (e.created_at || ''); }
    function loadSuppressed() {
        try {
            var raw = sessionStorage.getItem(SUPPRESS_KEY);
            return raw ? new Set(JSON.parse(raw)) : new Set();
        } catch (_) {
            // Corrupt data — wipe it
            try { sessionStorage.removeItem(SUPPRESS_KEY); } catch (_) {}
            return new Set();
        }
    }
    function saveSuppressed() {
        try { sessionStorage.setItem(SUPPRESS_KEY, JSON.stringify(Array.from(suppressed))); } catch (_) {}
    }
    const suppressed = loadSuppressed();

    var   allEvents     = [];   // full sorted list
    var   currentEvents = [];   // top MAX_SHOWN for display
    var   pollTimer     = null;

    function parseTs(value) {
        var t = Date.parse(value || '');
        return Number.isFinite(t) ? t : 0;
    }

    function isStaleUpdate(existing, incoming) {
        if (!existing) return false;
        var existingTs = parseTs(existing.updated_at || existing.created_at);
        var incomingTs = parseTs(incoming.updated_at || incoming.created_at);
        if (!existingTs || !incomingTs) return false;
        return incomingTs < existingTs;
    }

    // ── SocketIO ──────────────────────────────
    (function attachSocket() {
        var sock = window._appSocket;
        if (!sock) return;
        sock.on('status:updated', onStatusEvent);
        sock.on('connect', function() {
            console.debug('[activity] socket connected; forcing feed refresh');
            schedulePoll(0);
        });
        sock.on('disconnect', function(reason) {
            console.debug('[activity] socket disconnected', reason || 'unknown');
            // Keep polling aggressively while disconnected so UI still tracks.
            schedulePoll(200);
        });
    })();

    function onStatusEvent(evtData) {
        if (!evtData || typeof evtData.id === 'undefined') {
            schedulePoll(100);
            return;
        }
        var existing = eventCache.get(evtData.id);
        if (isStaleUpdate(existing, evtData)) {
            console.debug('[activity] stale socket update dropped', {
                id: evtData.id,
                incoming: evtData.updated_at,
                existing: existing && existing.updated_at,
            });
            return;
        }
        console.debug('[activity] socket status:updated', { id: evtData.id, state: evtData.state, title: evtData.title });
        var isNew = !eventCache.has(evtData.id);
        eventCache.set(evtData.id, evtData);
        rebuild();
        render();
        if (isNew) schedulePoll(400);
    }

    // ── Polling — safety net ──────────────────
    function schedulePoll(delay) {
        if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
        pollTimer = setTimeout(runPoll, delay);
    }

    async function runPoll() {
        pollTimer = null;
        try {
            var url = FEED_ENDPOINT + (FEED_ENDPOINT.indexOf('?') === -1 ? '?' : '&') + '_ts=' + Date.now();
            var res = await fetch(url, { cache: 'no-store' });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            var data = await res.json();
            if (data.success && Array.isArray(data.events)) {
                // Merge: remove stale entries, upsert fresh ones.
                // Do NOT clear — a socket event may have arrived since the request was sent.
                var pollIds = new Set(data.events.map(function(e) { return e.id; }));
                eventCache.forEach(function(_, id) {
                    if (!pollIds.has(id)) { eventCache.delete(id); }
                });
                data.events.forEach(function(e) {
                    var existing = eventCache.get(e.id);
                    if (!isStaleUpdate(existing, e)) {
                        eventCache.set(e.id, e);
                    }
                });
                console.debug('[activity] poll merged', data.events.length, 'events');
                rebuild();
                render();
            }
        } catch (_) {
            // silently degrade — next poll will retry
        } finally {
            var hasActive = currentEvents.some(function(e) {
                return ACTIVE_STATES.has((e.state || '').toLowerCase());
            });
            schedulePoll(hasActive ? POLL_ACTIVE : POLL_IDLE);
        }
    }

    // ── Build display list from cache ─────────
    function rebuild() {
        var now = Date.now();
        var visible = [];

        eventCache.forEach(function(e) {
            var state = (e.state || '').toLowerCase();
            // If this event is back to active, un-suppress it
            if (ACTIVE_STATES.has(state)) {
                if (suppressed.has(suppKey(e))) { suppressed.delete(suppKey(e)); saveSuppressed(); }
                terminalEntry.delete(e.id);
                // Cancel any pending expiry timer — event is active again
                if (expiryTimers.has(e.id)) {
                    clearTimeout(expiryTimers.get(e.id));
                    expiryTimers.delete(e.id);
                }
                visible.push(e);
            } else {
                // Never show a suppressed event again unless it goes active
                if (suppressed.has(suppKey(e))) return;
                // Include all non-suppressed terminal events
                visible.push(e);
            }
        });

        // Newest first: active states float to top, then by updated_at descending
        visible.sort(function(a, b) {
            var aA = ACTIVE_STATES.has((a.state || '').toLowerCase()) ? 1 : 0;
            var bA = ACTIVE_STATES.has((b.state || '').toLowerCase()) ? 1 : 0;
            if (aA !== bA) return bA - aA;
            return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
        });

        allEvents     = visible;
        currentEvents = visible.slice(0, MAX_SHOWN);

        // Schedule exact drop-out for each visible terminal item.
        // terminalEntry is set HERE (not in the feed loop) so the clock only
        // starts when an item actually enters the visible panel, not while queued.
        currentEvents.forEach(function(e) {
            var state = (e.state || '').toLowerCase();
            if (ACTIVE_STATES.has(state)) return;
            var id  = e.id;
            var key = suppKey(e);
            if (expiryTimers.has(id)) return; // already running
            // First time this item is visible — start the clock now
            if (!terminalEntry.has(id)) terminalEntry.set(id, Date.now());
            var ttl = STATE_TTL[state] !== undefined ? STATE_TTL[state] : TERMINAL_TTL;
            var remaining = ttl - (Date.now() - terminalEntry.get(id));
            if (remaining > 0) {
                expiryTimers.set(id, setTimeout(function() {
                    expiryTimers.delete(id);
                    terminalEntry.delete(id);
                    suppressed.add(key);
                    saveSuppressed();
                    rebuild();
                    render();
                    // Poll immediately so any state transition that arrived
                    // while the item was in a terminal state gets picked up.
                    schedulePoll(200);
                }, remaining));
            } else {
                suppressed.add(key);
                saveSuppressed();
                schedulePoll(200);
            }
        });

        // Cancel timers for events no longer in cache
        expiryTimers.forEach(function(handle, id) {
            if (!eventCache.has(id)) {
                clearTimeout(handle);
                expiryTimers.delete(id);
                terminalEntry.delete(id);
            }
        });
    }

    // ── Render list into sidebar ──────────────
    function render() {
        if (!currentEvents.length) {
            panelEl.style.display = 'none';
            return;
        }
        panelEl.style.display = '';

        // Queue badge — how many are waiting behind the visible 3
        var waiting = allEvents.length - currentEvents.length;
        if (queueEl) {
            if (waiting > 0) {
                queueEl.textContent = '+' + waiting + ' waiting';
                queueEl.style.display = '';
            } else {
                queueEl.style.display = 'none';
            }
        }

        // Reconcile DOM nodes (prepend new items so newest appears at top)
        var existingIds = Array.from(listEl.children).map(function(n) { return n.dataset.evtId; });
        var newIds      = currentEvents.map(function(e) { return String(e.id); });

        // Remove nodes no longer in the list
        Array.from(listEl.children).forEach(function(n) {
            if (newIds.indexOf(n.dataset.evtId) === -1) listEl.removeChild(n);
        });

        // Insert / update in correct order (index 0 = top = newest)
        currentEvents.forEach(function(evt, i) {
            var id  = String(evt.id);
            var existing = listEl.querySelector('[data-evt-id="' + id + '"]');
            var node = buildItem(evt);
            if (existing) {
                listEl.replaceChild(node, existing);
            } else {
                var refNode = listEl.children[i] || null;
                listEl.insertBefore(node, refNode);
            }
        });
    }

    // ── Build a single event row ──────────────
    function buildItem(evt) {
        var cat      = (evt.category || '').toLowerCase();
        var state    = (evt.state    || 'running').toLowerCase();
        var isActive = ACTIVE_STATES.has(state);
        var icon     = CATEGORY_ICONS[cat] || stateIcon(state);
        var label    = STATE_LABELS[state]  || toTitleCase(state);
        var stateKey = state.replace(/_/g, '-');

        var hasProgress = (isActive || state === 'complete') && typeof evt.progress === 'number';
        var pct = hasProgress ? Math.min(100, Math.max(0, evt.progress)) : 0;

        var li = document.createElement('li');
        li.className = 'sidebar-activity-item';
        li.dataset.evtId = String(evt.id);
        li.innerHTML =
            '<div class="activity-row">' +
                '<i class="fas ' + escHtml(icon) + ' activity-icon state-' + stateKey + (isActive ? ' activity-icon--spin' : '') + '"></i>' +
                '<span class="activity-title">' + escHtml(evt.title || 'Task') + '</span>' +
            '</div>' +
            '<div class="activity-meta">' +
                '<span class="activity-badge state-' + stateKey + '">' + escHtml(label) + '</span>' +
            '</div>' +
            (hasProgress
                ? '<div class="activity-progress-track"><div class="activity-progress-fill state-' + stateKey + '" style="width:' + pct + '%"></div></div>'
                : '');
        return li;
    }

    function escHtml(str) {
        return String(str).replace(/[&<>"']/g, function(c) {
            return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
        });
    }

    function stateIcon(state) {
        var MAP = {
            queued:              'fa-clock',
            searching:           'fa-search',
            found:               'fa-check',
            downloading:         'fa-download',
            audible_downloading: 'fa-headphones',
            paused:              'fa-pause-circle',
            complete:            'fa-check-circle',
            converting:          'fa-sync-alt',
            converted:           'fa-check-circle',
            processing:          'fa-cog',
            importing:           'fa-file-import',
            imported:            'fa-check-double',
            seeding:             'fa-seedling',
            seeding_complete:    'fa-leaf',
            completed:           'fa-check-circle',
            warning:             'fa-exclamation-triangle',
            search_failed:       'fa-search-minus',
            download_failed:     'fa-times-circle',
            conversion_failed:   'fa-exclamation-circle',
            import_failed:       'fa-folder-minus',
            failed:              'fa-times-circle',
            cancelled:           'fa-ban',
        };
        return MAP[state] || 'fa-circle-notch';
    }

    function toTitleCase(str) {
        return str.replace(/[_-]/g, ' ').replace(/\b\w/g, function(c) { return c.toUpperCase(); });
    }

    schedulePoll(0);
})();
