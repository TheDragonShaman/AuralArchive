// ==============================================
// Global Status Bar - Live log ticker
// ==============================================
(function () {
    const bar = document.getElementById('statusBar');
    if (!bar) {
        return;
    }

    const levelBadge = document.getElementById('statusBarLevel');
    const messageEl = document.getElementById('statusBarMessage');
    const sourceEl = document.getElementById('statusBarSource');
    const timestampEl = document.getElementById('statusBarTimestamp');

    const POLL_INTERVAL = 2000;
    const DISPLAY_INTERVAL = 5000; // unused when cycling is disabled
    const STATUS_ENDPOINT = '/api/status/feed';
    const LEVEL_CONFIG = {
        success: { alert: 'alert-success', badge: 'badge-success' },
        info: { alert: 'alert-info', badge: 'badge-info' },
        warning: { alert: 'alert-warning', badge: 'badge-warning' },
        error: { alert: 'alert-error', badge: 'badge-error' },
        default: { alert: 'alert-neutral', badge: 'badge-ghost' }
    };

    let currentEvents = [];
    let currentIndex = 0;
    let lastSignature = '';

    function updateLevel(level) {
        const normalized = (level || 'default').toLowerCase();
        const config = LEVEL_CONFIG[normalized] || LEVEL_CONFIG.default;

        Object.values(LEVEL_CONFIG).forEach(({ alert }) => bar.classList.remove(alert));
        Object.values(LEVEL_CONFIG).forEach(({ badge }) => levelBadge.classList.remove(badge));

        bar.classList.add(config.alert);
        levelBadge.classList.add(config.badge);
        levelBadge.textContent = normalized.toUpperCase();
    }

    function formatState(state) {
        if (!state) return null;
        return state.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    }

    function updateContent(entry) {
        if (!entry) {
            messageEl.textContent = 'Standing by for system activity…';
            sourceEl.textContent = 'Status idle';
            timestampEl.textContent = '—';
            updateLevel('default');
            return;
        }

        updateLevel(entry.level);

        const headline = entry.title || entry.message || 'Activity update';
        const detailParts = [];
        if (entry.message && entry.title && entry.message !== entry.title) {
            detailParts.push(entry.message);
        }
        if (typeof entry.progress === 'number') {
            detailParts.push(`${Math.round(entry.progress)}%`);
        }
        const friendlyState = formatState(entry.state);
        if (friendlyState) {
            detailParts.push(friendlyState);
        }

        messageEl.textContent = headline;
        sourceEl.textContent = detailParts.join(' · ') || (entry.origin || entry.source || 'System activity');
        timestampEl.textContent = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    }

    function normalize(entry) {
        if (!entry) return null;
        return {
            id: entry.id ?? entry.entity_id ?? entry.title,
            timestamp: entry.updated_at || entry.timestamp,
            level: entry.level || 'info',
            title: entry.title,
            message: entry.message,
            origin: entry.source || entry.category || 'System',
            progress: entry.progress,
            state: entry.state || 'info'
        };
    }

    function scheduleCycle() {
        // Cycling disabled: always show the most recent event
        if (currentEvents.length > 0) {
            currentIndex = 0;
            updateContent(currentEvents[0]);
        }
    }

    async function poll() {
        try {
            const response = await fetch(STATUS_ENDPOINT);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Status feed error');
            }
            const events = Array.isArray(data.events) ? data.events : [];
            const normalizedEvents = events
                .map(normalize)
                .filter(Boolean)
                .sort((a, b) => new Date(b.timestamp || 0) - new Date(a.timestamp || 0));

            const signature = normalizedEvents
                .map((evt) => `${evt.id}-${evt.timestamp}-${evt.state}`)
                .join('|');

            if (signature !== lastSignature) {
                lastSignature = signature;
                currentEvents = normalizedEvents;
                currentIndex = 0;

                if (currentEvents.length > 0) {
                    updateContent(currentEvents[0]);
                } else {
                    updateContent(null);
                }

                scheduleCycle();
            }

            if (!currentEvents.length) {
                lastSignature = '';
            }
        } catch (error) {
            console.warn('Status bar update failed:', error);
            updateLevel('warning');
            messageEl.textContent = 'Status feed unavailable';
            sourceEl.textContent = error.message;
            timestampEl.textContent = new Date().toLocaleTimeString();
            lastSignature = '';
            currentEvents = [];
            currentIndex = 0;
            scheduleCycle();
        } finally {
            setTimeout(poll, POLL_INTERVAL);
        }
    }

    updateContent(null);
    poll();
})();
