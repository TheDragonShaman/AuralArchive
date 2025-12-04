"use strict";

(function () {
    const CLIENT_DEFINITIONS = {
        qbittorrent: {
            label: "qBittorrent",
            defaults: {
                enabled: true,
                auto_download: false,
                host: "127.0.0.1",
                port: 8080,
                username: "",
                password: "",
                category: "auralarchive",
                path_mappings: [],
                download_path_remote: "",
                download_path_local: ""
            }
        },
        deluge: {
            label: "Deluge",
            defaults: {
                enabled: true,
                auto_download: false,
                host: "127.0.0.1",
                port: 8112,
                password: ""
            }
        },
        transmission: {
            label: "Transmission",
            defaults: {
                enabled: true,
                auto_download: false,
                host: "127.0.0.1",
                port: 9091,
                username: "transmission",
                password: ""
            }
        },
        sabnzbd: {
            label: "SABnzbd",
            defaults: {
                enabled: true,
                auto_download: false,
                host: "127.0.0.1",
                port: 8080,
                username: "",
                password: "",
                api_key: ""
            }
        },
        nzbget: {
            label: "NZBGet",
            defaults: {
                enabled: true,
                auto_download: false,
                host: "127.0.0.1",
                port: 6789,
                username: "",
                password: ""
            }
        }
    };

    const CLIENT_ORDER = Object.keys(CLIENT_DEFINITIONS);
    const MAX_PATH_MAPPINGS = 5;

    const INDEXER_TYPE_LABELS = {
        jackett: "Jackett",
        prowlarr: "Prowlarr",
        nzbhydra2: "NZBHydra2",
        direct: "Direct"
    };

    const DEFAULT_INDEXER_PRIORITY = 100;

    const state = {
        config: {},
        downloadClients: {},
        indexers: {},
        namingTemplates: [],
        mediaSettings: {},
        downloadSettings: {},
        absLibraries: [],
        selectedClientKey: null,
        selectedIndexerKey: null,
        addingIndexer: false,
        lastLoaded: null,
        audible: {
            serviceStatus: null,
            accountStatus: null,
            stats: null,
            setupInfo: null,
            pendingSessionId: null,
            lastUpdated: null
        }
    };

    function maskApiKey(value) {
        const apiKey = (value || "").trim();
        if (!apiKey) {
            return "";
        }
        if (apiKey.length <= 4) {
            return apiKey;
        }
        return `${apiKey.slice(0, 4)}${"*".repeat(apiKey.length - 4)}`;
    }

    function isDirectIndexerType(type) {
        return (type || "").toLowerCase() === "direct";
    }

    function updateIndexerFieldVisibility(typeValue) {
        const isDirect = isDirectIndexerType(typeValue);
        document.querySelectorAll('[data-indexer-field="standard"]').forEach((element) => {
            element.classList.toggle("hidden", isDirect);
        });
        document.querySelectorAll('[data-indexer-field="direct"]').forEach((element) => {
            element.classList.toggle("hidden", !isDirect);
        });
    }

    function parseCategoriesList(rawValue) {
        if (!rawValue) {
            return [];
        }
        if (Array.isArray(rawValue)) {
            return rawValue.map((entry) => entry.toString().trim()).filter(Boolean);
        }
        return rawValue
            .toString()
            .split(',')
            .map((entry) => entry.trim())
            .filter(Boolean);
    }

    function hydrateIndexersFromConfig() {
        if (!state.config || typeof state.config !== "object") {
            return;
        }

        Object.entries(state.config).forEach(([section, values]) => {
            if (!section.toLowerCase().startsWith("indexer:") || !values || typeof values !== "object") {
                return;
            }

            const key = section.split(':', 2)[1];
            if (!key || state.indexers[key]) {
                return;
            }

            const name = values.name || key.replace(/_/g, ' ');
            const feedUrl = values.feed_url || values.url || "";
            const baseUrl = values.base_url || "";
            const sessionId = values.session_id || "";
            const apiKey = values.api_key || values.key || "";
            const type = (values.type || inferIndexerType(key, values.protocol)).toLowerCase();
            const protocol = (values.protocol || (type === "nzbhydra2" ? "newznab" : "torznab")).toLowerCase();
            const priority = toNumeric(values.priority, DEFAULT_INDEXER_PRIORITY);
            const categories = parseCategoriesList(values.categories);
            const verifySsl = values.verify_ssl != null ? toBoolean(values.verify_ssl) : true;
            const timeout = toNumeric(values.timeout, 30);
            const rateLimitRps = toNumeric(values.rate_limit_requests_per_second || values["rate_limit.request_per_second"], 1);
            const rateLimitConcurrent = toNumeric(values.rate_limit_max_concurrent || values["rate_limit.max_concurrent"], 1);
            const enabled = values.enabled != null ? toBoolean(values.enabled) : false;
            const isDirect = isDirectIndexerType(type);
            const configured = isDirect ? Boolean(baseUrl && sessionId) : Boolean(feedUrl && apiKey);

            state.indexers[key] = {
                key,
                name,
                enabled,
                feed_url: feedUrl,
                base_url: baseUrl,
                api_key: apiKey,
                api_key_masked: maskApiKey(apiKey),
                session_id: sessionId,
                session_id_masked: maskApiKey(sessionId),
                type,
                protocol,
                priority,
                categories,
                verify_ssl: verifySsl,
                timeout,
                rate_limit: {
                    requests_per_second: rateLimitRps,
                    max_concurrent: rateLimitConcurrent
                },
                configured,
                has_api_key: Boolean(apiKey),
                has_session_id: Boolean(sessionId)
            };
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        attachFormHandlers();
        initializeAudibleSection();
        loadAllData();
        refreshAudibleStatus();

        const typeSelect = document.getElementById("indexer_type");
        if (typeSelect) {
            updateIndexerFieldVisibility(typeSelect.value);
        }

        const refreshButton = document.getElementById("refreshSettings");
        if (refreshButton) {
            refreshButton.addEventListener("click", (event) => {
                event.preventDefault();
                loadAllData({ showToast: true });
            });
        }
    });

    function attachFormHandlers() {
        safeAddFormHandler("generalForm", handleGeneralSubmit);
        safeAddFormHandler("absForm", handleAbsSubmit);
        safeAddFormHandler("downloadClientForm", handleDownloadClientSubmit);
        safeAddFormHandler("indexerForm", handleIndexerSubmit);
        safeAddFormHandler("mediaManagementForm", handleMediaManagementSubmit);
        safeAddFormHandler("audibleAuthForm", handleAudibleAuthSubmit);
        safeAddFormHandler("audibleOtpForm", handleAudibleOtpSubmit);

        safeAddEventListener("mm_naming_template", "change", handleNamingTemplateChange);
        safeAddEventListener("download_client_type", "change", handleClientTypeChange);
        safeAddEventListener("downloadClientAddButton", "click", () => openDownloadClientEditor());
        safeAddEventListener("downloadClientDeleteButton", "click", handleDownloadClientDelete);
        safeAddEventListener("downloadClientTestButton", "click", handleDownloadClientTest);
        safeAddEventListener("indexerAddButton", "click", () => openIndexerEditor());
        safeAddEventListener("indexerDeleteButton", "click", handleIndexerDelete);
        safeAddEventListener("indexerRefreshButton", "click", refreshIndexersList);
        safeAddEventListener("indexerTestButton", "click", handleIndexerTest);
        safeAddEventListener("indexer_name", "input", handleIndexerNameInput);
        safeAddEventListener("indexer_custom_key", "input", handleIndexerKeyInput);
        safeAddEventListener("indexer_type", "change", handleIndexerTypeChange);
        safeAddEventListener("absTestButton", "click", handleAbsTestConnection);
        safeAddEventListener("absRefreshLibraries", "click", handleAbsRefreshLibraries);
        safeAddEventListener("absManualSync", "click", handleAbsManualSync);
        safeAddEventListener("qbPathMappingAdd", "click", handleQbPathMappingAdd);

        safeAddEventListener("audibleRefreshButton", "click", (event) => {
            event.preventDefault();
            refreshAudibleStatus({ showToast: true });
        });
        safeAddEventListener("audibleSyncFullButton", "click", handleAudibleSyncFull);
        safeAddEventListener("audibleSyncQuickButton", "click", handleAudibleSyncQuick);
        safeAddEventListener("audibleSetupButton", "click", handleAudibleSetupInfo);
        safeAddEventListener("audibleAuthenticateButton", "click", openAudibleAuthModal);
        safeAddEventListener("audibleRevokeButton", "click", handleAudibleRevoke);
        safeAddEventListener("audibleRefreshLibraryButton", "click", handleAudibleLibraryRefresh);
    safeAddEventListener("audibleDownloadAllButton", "click", handleAudibleDownloadAll);
        safeAddEventListener("audibleExportButton", "click", handleAudibleExport);
        safeAddEventListener("audibleStatsButton", "click", handleAudibleStatsLoad);
        safeAddEventListener("audibleStatsRefreshButton", "click", handleAudibleStatsLoad);
        safeAddEventListener("audibleValidateButton", "click", handleAudibleValidate);
        safeAddEventListener("app_theme", "change", handleThemeSelectionPreview);

        const qbPathMappings = document.getElementById("qbPathMappings");
        if (qbPathMappings) {
            qbPathMappings.addEventListener("click", handleQbPathMappingRemove);
        }

        const clientList = document.getElementById("downloadClientsList");
        if (clientList) {
            clientList.addEventListener("click", (event) => {
                const target = event.target.closest("[data-client-key]");
                if (target) {
                    event.preventDefault();
                    openDownloadClientEditor(target.dataset.clientKey);
                }
            });
        }

        const indexerList = document.getElementById("indexersList");
        if (indexerList) {
            indexerList.addEventListener("click", (event) => {
                const target = event.target.closest("[data-indexer-key]");
                if (target) {
                    event.preventDefault();
                    openIndexerEditor(target.dataset.indexerKey);
                }
            });
        }
    }

    async function loadAllData(options = {}) {
        const { showToast = false, silent = false } = options;

        if (!silent) {
            toggleRefreshButton(true);
        }

        try {
            const [configPayload, indexersPayload, templatesPayload, mediaPayload, downloadPayload] = await Promise.all([
                fetchJson("/settings/config"),
                fetchJson("/settings/api/indexers"),
                fetchJson("/settings/audiobookshelf/naming-templates"),
                fetchJson("/settings/api/media-management"),
                fetchJson("/settings/api/download-management")
            ]);

            state.config = configPayload.config || {};
            setIndexersState(indexersPayload.indexers || {});
            state.namingTemplates = templatesPayload.templates || [];
            state.mediaSettings = mediaPayload.config || {};
            state.downloadSettings = downloadPayload.config || {};
            buildDownloadClientsState();
            state.lastLoaded = new Date();
            state.addingIndexer = false;

            populateForms();

            if (showToast) {
                showNotification("Configuration refreshed", "success");
            }
        } catch (error) {
            console.error(error);
            showNotification(`Failed to load configuration: ${error.message}`, "error");
        } finally {
            if (!silent) {
                toggleRefreshButton(false);
            }
        }
    }

    function setIndexersState(indexersMap) {
        state.indexers = {};

        if (!indexersMap || typeof indexersMap !== "object") {
            hydrateIndexersFromConfig();
            return;
        }

        Object.entries(indexersMap).forEach(([key, details]) => {
            if (!details || typeof details !== "object") {
                return;
            }
            state.indexers[key] = { key, ...details };
        });

        if (!Object.keys(state.indexers).length) {
            hydrateIndexersFromConfig();
        }
    }

    function populateForms() {
        populateGeneralForm();
        populateAbsForm();
        renderDownloadClientsList();
        renderIndexerList();
        populateMediaManagementForm();
        updateTimestamp();
    }

    function populateGeneralForm() {
        const generalConfig = state.config.application || {};
        const autoSearchConfig = state.config.auto_search || {};

        setSelectValue("app_log_level", (generalConfig.log_level || "INFO").toUpperCase());
        setNumericInput("quality_threshold", autoSearchConfig.quality_threshold, 5);
        setCheckboxValue("auto_download_enabled", autoSearchConfig.auto_download_enabled);

        const themeSelect = document.getElementById("app_theme");
        if (themeSelect) {
            const storedTheme = generalConfig.theme || getStoredThemePreference();
            if (storedTheme) {
                themeSelect.value = storedTheme;
            }
        }
    }

    function populateAbsForm() {
        const absConfig = state.config.audiobookshelf || {};

        setInputValue("abs_host", absConfig.abs_host || absConfig.server_url || "");
        setInputValue("abs_api_key", absConfig.abs_api_key || absConfig.api_key || "");
        setInputValue("abs_sync_frequency", absConfig.abs_sync_frequency || absConfig.sync_interval_hours || "30min");
        setCheckboxValue("abs_enabled", absConfig.abs_enabled);
        setCheckboxValue("abs_sync_metadata", absConfig.abs_sync_metadata);
        setCheckboxValue("abs_sync_only_owned", absConfig.abs_sync_only_owned);
        setCheckboxValue("abs_auto_sync", absConfig.abs_auto_sync || absConfig.abs_auto_sync_enabled);

        const libraryId = absConfig.abs_library_id || absConfig.library_id || "";
        populateAbsLibrarySelect(libraryId);
        setSelectValue("abs_library_id", libraryId);
    }

    function populateAbsLibrarySelect(selectedId) {
        const select = document.getElementById("abs_library_id");
        if (!select) {
            return;
        }

        const helper = document.getElementById("absLibraryHelper");
        select.innerHTML = "";

        if (!state.absLibraries.length) {
            const placeholder = document.createElement("option");
            placeholder.value = selectedId || "";
            placeholder.textContent = selectedId ? `Current library (${selectedId})` : "Select a library";
            if (!selectedId) {
                placeholder.disabled = true;
            }
            placeholder.selected = true;
            select.appendChild(placeholder);

            if (helper) {
                helper.textContent = "Test the connection and refresh libraries to load available options.";
            }
            return;
        }

        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = "Select a library";
        select.appendChild(defaultOption);

        state.absLibraries.forEach((library) => {
            const option = document.createElement("option");
            option.value = library.id;
            option.textContent = library.name;
            if (library.id === selectedId) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        if (helper) {
            helper.textContent = `${state.absLibraries.length} libraries available.`;
        }
    }

    function buildDownloadClientsState() {
        const clients = {};

        CLIENT_ORDER.forEach((type) => {
            const section = state.config[type];
            if (!section || typeof section !== "object") {
                return;
            }

            const defaults = CLIENT_DEFINITIONS[type].defaults;
            const normalized = { ...defaults };

            switch (type) {
                case "qbittorrent":
                    normalized.enabled = toBoolean(section.enabled);
                    normalized.auto_download = toBoolean(section.auto_download);
                    normalized.host = section.qb_host || section.host || defaults.host;
                    normalized.port = toNumeric(section.qb_port, defaults.port);
                    normalized.username = section.qb_username || section.username || defaults.username;
                    normalized.password = stripQuotes(section.qb_password || section.password || defaults.password);
                    normalized.category = section.category || section.qb_category || defaults.category;
                    let pathMappings = extractSectionPathMappings(section);

                    if (!pathMappings.length) {
                        pathMappings = parsePathMappings(section.path_mappings);
                    }

                    if (!pathMappings.length) {
                        const legacyRemote = (
                            section.download_path ||
                            section.download_path_remote ||
                            section.save_path ||
                            ""
                        )
                            .toString()
                            .trim();
                        const legacyLocal = (section.download_path_local || section.local_save_path || "")
                            .toString()
                            .trim();

                        if (legacyRemote || legacyLocal) {
                            pathMappings = [
                                {
                                    remote: legacyRemote,
                                    local: legacyLocal
                                }
                            ];
                        }
                    }

                    normalized.path_mappings = pathMappings;
                    normalized.download_path_remote =
                        (
                            pathMappings[0]?.remote ||
                            section.download_path_remote ||
                            section.download_path ||
                            section.save_path ||
                            ""
                        )
                            .toString()
                            .trim();
                    normalized.download_path_local =
                        (pathMappings[0]?.local || section.download_path_local || section.local_save_path || "")
                            .toString()
                            .trim();
                    break;
                case "deluge":
                    normalized.enabled = toBoolean(section.enabled);
                    normalized.auto_download = toBoolean(section.auto_download);
                    normalized.host = section.host || defaults.host;
                    normalized.port = toNumeric(section.port, defaults.port);
                    normalized.password = stripQuotes(section.password || defaults.password);
                    break;
                case "transmission":
                    normalized.enabled = toBoolean(section.enabled);
                    normalized.auto_download = toBoolean(section.auto_download);
                    normalized.host = section.transmission_host || section.host || defaults.host;
                    normalized.port = toNumeric(section.transmission_port || section.port, defaults.port);
                    normalized.username = section.transmission_username || section.username || defaults.username;
                    normalized.password = stripQuotes(section.transmission_password || section.password || defaults.password);
                    break;
                case "sabnzbd":
                    normalized.enabled = toBoolean(section.enabled);
                    normalized.auto_download = toBoolean(section.auto_download);
                    normalized.host = section.host || defaults.host;
                    normalized.port = toNumeric(section.port, defaults.port);
                    normalized.username = section.username || defaults.username;
                    normalized.password = stripQuotes(section.password || defaults.password);
                    normalized.api_key = section.api_key || defaults.api_key;
                    break;
                case "nzbget":
                    normalized.enabled = toBoolean(section.enabled);
                    normalized.auto_download = toBoolean(section.auto_download);
                    normalized.host = section.host || defaults.host;
                    normalized.port = toNumeric(section.port, defaults.port);
                    normalized.username = section.username || defaults.username;
                    normalized.password = stripQuotes(section.password || defaults.password);
                    break;
                default:
                    break;
            }

            clients[type] = normalized;
        });

        state.downloadClients = clients;
    }

    function renderDownloadClientsList() {
        const list = document.getElementById("downloadClientsList");
        const emptyCard = document.getElementById("downloadClientEmptyState");
        const editor = document.getElementById("downloadClientEditor");

        if (!list || !emptyCard || !editor) {
            return;
        }

        list.innerHTML = "";

        CLIENT_ORDER.forEach((type) => {
            const definition = CLIENT_DEFINITIONS[type];
            const button = document.createElement("button");
            button.type = "button";
            button.dataset.clientKey = type;
            button.className = `btn btn-sm w-full justify-between ${state.selectedClientKey === type ? "btn-primary" : "btn-outline"}`;

            const name = document.createElement("span");
            name.textContent = definition.label;

            const status = document.createElement("span");
            const configured = Boolean(state.downloadClients[type]);
            status.textContent = configured ? "Configured" : "Not configured";
            status.className = `text-xs ${configured ? "text-success" : "text-base-content/60"}`;

            button.append(name, status);
            list.appendChild(button);
        });

        if (!state.selectedClientKey) {
            emptyCard.classList.remove("hidden");
            editor.classList.add("hidden");
        }
    }

    function openDownloadClientEditor(clientKey) {
        const editor = document.getElementById("downloadClientEditor");
        const emptyCard = document.getElementById("downloadClientEmptyState");
        const heading = document.getElementById("downloadClientHeading");
        const helper = document.getElementById("downloadClientHelper");
        const deleteButton = document.getElementById("downloadClientDeleteButton");
        const typeSelect = document.getElementById("download_client_type");
        const statusTarget = document.getElementById("downloadClientStatus");

        if (!editor || !emptyCard || !heading || !helper || !deleteButton || !typeSelect || !statusTarget) {
            return;
        }

        state.selectedClientKey = clientKey || null;
        statusTarget.textContent = "";
        typeSelect.disabled = Boolean(clientKey);

        if (clientKey) {
            typeSelect.value = clientKey;
            heading.textContent = CLIENT_DEFINITIONS[clientKey].label;
            helper.textContent = "Update the connection details and save to apply changes.";
            deleteButton.classList.remove("hidden");
            populateClientFields(clientKey, state.downloadClients[clientKey]);
        } else {
            const nextType = findNextAvailableClientType();
            typeSelect.disabled = false;
            typeSelect.value = nextType;
            heading.textContent = "New Client";
            helper.textContent = "Choose a client type, fill in the connection details, and save.";
            deleteButton.classList.add("hidden");
            populateClientFields(nextType, CLIENT_DEFINITIONS[nextType].defaults);
        }

        showClientPanel(typeSelect.value);
        emptyCard.classList.add("hidden");
        editor.classList.remove("hidden");
        renderDownloadClientsList();
    }

    function populateClientFields(clientType, data = {}) {
        setCheckboxValue("download_client_enabled", data.enabled);
        setCheckboxValue("download_client_auto", data.auto_download);

        switch (clientType) {
            case "qbittorrent":
                setInputValue("qb_host", data.host);
                setNumericInput("qb_port", data.port, CLIENT_DEFINITIONS.qbittorrent.defaults.port);
                setInputValue("qb_username", data.username);
                setInputValue("qb_password", data.password);
                setInputValue("qb_category", data.category);
                renderQbPathMappings(data.path_mappings || []);
                break;
            case "deluge":
                setInputValue("deluge_host", data.host);
                setNumericInput("deluge_port", data.port, CLIENT_DEFINITIONS.deluge.defaults.port);
                setInputValue("deluge_password", data.password);
                renderQbPathMappings();
                break;
            case "transmission":
                setInputValue("transmission_host", data.host);
                setNumericInput("transmission_port", data.port, CLIENT_DEFINITIONS.transmission.defaults.port);
                setInputValue("transmission_username", data.username);
                setInputValue("transmission_password", data.password);
                renderQbPathMappings();
                break;
            case "sabnzbd":
                setInputValue("sabnzbd_host", data.host);
                setNumericInput("sabnzbd_port", data.port, CLIENT_DEFINITIONS.sabnzbd.defaults.port);
                setInputValue("sabnzbd_username", data.username);
                setInputValue("sabnzbd_password", data.password);
                setInputValue("sabnzbd_api_key", data.api_key);
                renderQbPathMappings();
                break;
            case "nzbget":
                setInputValue("nzbget_host", data.host);
                setNumericInput("nzbget_port", data.port, CLIENT_DEFINITIONS.nzbget.defaults.port);
                setInputValue("nzbget_username", data.username);
                setInputValue("nzbget_password", data.password);
                renderQbPathMappings();
                break;
            default:
                renderQbPathMappings();
                break;
        }
    }

    function parsePathMappings(rawValue) {
        if (!rawValue) {
            return [];
        }

        if (Array.isArray(rawValue)) {
            return rawValue
                .map((item) => ({
                    remote: (item.remote || item.qb_path || "").toString().trim(),
                    local: (item.local || item.host_path || "").toString().trim()
                }))
                .filter((item) => item.remote || item.local);
        }

        if (typeof rawValue === "string") {
            return rawValue
                .split(";")
                .map((entry) => entry.trim())
                .filter(Boolean)
                .map((entry) => {
                    const [remote = "", local = ""] = entry.split("|");
                    return { remote: remote.trim(), local: local.trim() };
                })
                .filter((item) => item.remote || item.local);
        }

        return [];
    }

    function extractSectionPathMappings(section = {}) {
        if (!section || typeof section !== "object") {
            return [];
        }

        const buckets = new Map();
        Object.entries(section).forEach(([key, value]) => {
            if (typeof key !== "string") {
                return;
            }
            const normalizedKey = key.toLowerCase();
            const match = normalizedKey.match(/^path_mapping_(\d+)_(qb_path|host_path|remote|local)$/);
            if (!match) {
                return;
            }

            const index = Number.parseInt(match[1], 10);
            if (Number.isNaN(index)) {
                return;
            }

            const bucket = buckets.get(index) || { remote: "", local: "" };
            const trimmedValue = (value || "").toString().trim();

            if (match[2] === "qb_path" || match[2] === "remote") {
                bucket.remote = trimmedValue;
            } else {
                bucket.local = trimmedValue;
            }

            buckets.set(index, bucket);
        });

        if (buckets.size) {
            return Array.from(buckets.entries())
                .sort((a, b) => a[0] - b[0])
                .map(([, mapping]) => mapping)
                .filter((mapping) => mapping.remote || mapping.local);
        }

        const legacyValue = section.path_mappings || section.path_mapping;
        return parsePathMappings(legacyValue);
    }

    function renderQbPathMappings(mappings = []) {
        const container = document.getElementById("qbPathMappings");
        if (!container) {
            updateQbPathMappingAddState(0);
            return;
        }

        let rows = Array.isArray(mappings) && mappings.length ? mappings : [{ remote: "", local: "" }];

        if ((!mappings || !mappings.length) && rows.length === 1 && !rows[0].remote && !rows[0].local) {
            const defaultLocal =
                state.downloadClients?.qbittorrent?.path_mappings?.[0]?.local ||
                state.downloadClients?.qbittorrent?.download_path_local ||
                "";
            rows = [{ remote: "", local: defaultLocal }];
        }

        container.innerHTML = "";

        rows.forEach((mapping, index) => {
            const row = document.createElement("div");
            row.className = "grid gap-2 md:grid-cols-[1fr_1fr_auto] qb-path-mapping-row";
            row.dataset.index = String(index);

            const remoteWrapper = document.createElement("div");
            remoteWrapper.className = "form-control";
            const remoteLabel = document.createElement("label");
            remoteLabel.className = "label pb-1";
            const remoteText = document.createElement("span");
            remoteText.className = "label-text text-xs uppercase tracking-wide text-base-content/60";
            remoteText.textContent = "qB path";
            remoteLabel.appendChild(remoteText);
            const remoteInput = document.createElement("input");
            remoteInput.type = "text";
            remoteInput.className = "input input-bordered w-full qb-path-remote";
            remoteInput.placeholder = "/downloads/torrent_downloads";
            remoteInput.value = mapping.remote || "";
            remoteWrapper.append(remoteLabel, remoteInput);

            const localWrapper = document.createElement("div");
            localWrapper.className = "form-control";
            const localLabel = document.createElement("label");
            localLabel.className = "label pb-1";
            const localText = document.createElement("span");
            localText.className = "label-text text-xs uppercase tracking-wide text-base-content/60";
            localText.textContent = "Host path";
            localLabel.appendChild(localText);
            const localInput = document.createElement("input");
            localInput.type = "text";
            localInput.className = "input input-bordered w-full qb-path-local";
            localInput.placeholder = "/media/...";
            localInput.value = mapping.local || "";
            localWrapper.append(localLabel, localInput);

            const actionsWrapper = document.createElement("div");
            actionsWrapper.className = "flex justify-end md:justify-center items-center mt-2 md:mt-6";
            const removeButton = document.createElement("button");
            removeButton.type = "button";
            removeButton.className = `btn btn-outline btn-error btn-xs${rows.length === 1 ? " hidden" : ""}`;
            removeButton.dataset.qbPathRemove = String(index);
            const removeIcon = document.createElement("i");
            removeIcon.className = "fas fa-trash";
            removeButton.appendChild(removeIcon);
            actionsWrapper.appendChild(removeButton);

            row.append(remoteWrapper, localWrapper, actionsWrapper);
            container.appendChild(row);
        });

        updateQbPathMappingAddState(rows.length);
    }

    function collectQbPathMappings(includeEmpty = false) {
        const container = document.getElementById("qbPathMappings");
        if (!container) {
            return [];
        }

        const rows = container.querySelectorAll(".qb-path-mapping-row");
        const mappings = Array.from(rows).map((row) => {
            const remote = row.querySelector(".qb-path-remote")?.value.trim() || "";
            const local = row.querySelector(".qb-path-local")?.value.trim() || "";
            return { remote, local };
        });

        if (includeEmpty) {
            return mappings;
        }

        return mappings.filter((mapping) => mapping.remote && mapping.local);
    }

    function handleQbPathMappingAdd(event) {
        event.preventDefault();

        const currentMappings = collectQbPathMappings(true);
        if (currentMappings.length >= MAX_PATH_MAPPINGS) {
            return;
        }

        currentMappings.push({ remote: "", local: "" });
        renderQbPathMappings(currentMappings);
    }

    function handleQbPathMappingRemove(event) {
        const button = event.target.closest("[data-qb-path-remove]");
        if (!button) {
            return;
        }

        event.preventDefault();
        const index = Number(button.dataset.qbPathRemove);
        if (Number.isNaN(index)) {
            return;
        }

        const currentMappings = collectQbPathMappings(true);
        currentMappings.splice(index, 1);
        renderQbPathMappings(currentMappings);
    }

    function updateQbPathMappingAddState(count) {
        const addButton = document.getElementById("qbPathMappingAdd");
        if (!addButton) {
            return;
        }

        const disabled = count >= MAX_PATH_MAPPINGS;
        addButton.disabled = disabled;
        addButton.classList.toggle("btn-disabled", disabled);
    }

    function handleClientTypeChange(event) {
        const newType = event.target.value;
        showClientPanel(newType);
        populateClientFields(newType, CLIENT_DEFINITIONS[newType].defaults);
    }

    function findNextAvailableClientType() {
        const firstUnconfigured = CLIENT_ORDER.find((type) => !state.downloadClients[type]);
        return firstUnconfigured || CLIENT_ORDER[0];
    }

    async function handleDownloadClientSubmit(form) {
        const statusTarget = document.getElementById("downloadClientStatus");
        const submitButton = form.querySelector("button[type=\"submit\"]");
        const typeSelect = document.getElementById("download_client_type");

        if (!statusTarget || !submitButton || !typeSelect) {
            return;
        }

        const clientType = typeSelect.value;

        let payload;
        try {
            payload = getClientPayload(clientType);
        } catch (validationError) {
            statusTarget.textContent = validationError.message;
            statusTarget.className = "text-xs text-error";
            showNotification(validationError.message, "error");
            return;
        }

        statusTarget.textContent = "Saving client…";
        statusTarget.className = "text-xs text-info";
        submitButton.classList.add("loading");
        submitButton.disabled = true;

        try {
            const response = await fetchJson(`/settings/api/clients/${clientType}`, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const message = response.message || `${CLIENT_DEFINITIONS[clientType].label} saved.`;
            statusTarget.textContent = "Saved";
            statusTarget.className = "text-xs text-success";
            showNotification(message, "success");

            state.selectedClientKey = clientType;
            await loadAllData({ silent: true });
            openDownloadClientEditor(clientType);
        } catch (error) {
            console.error(error);
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`Failed to save client: ${error.message}`, "error");
        } finally {
            submitButton.classList.remove("loading");
            submitButton.disabled = false;
        }
    }

    async function handleDownloadClientDelete(event) {
        event.preventDefault();

        if (!state.selectedClientKey) {
            showNotification("Select a client before deleting.", "warning");
            return;
        }

        const statusTarget = document.getElementById("downloadClientStatus");
        const deleteButton = document.getElementById("downloadClientDeleteButton");

        if (!statusTarget || !deleteButton) {
            return;
        }

        statusTarget.textContent = "Deleting client…";
        statusTarget.className = "text-xs text-info";
        deleteButton.classList.add("loading");
        deleteButton.disabled = true;

        try {
            const clientType = state.selectedClientKey;
            const response = await fetchJson(`/settings/api/clients/${clientType}`, {
                method: "DELETE"
            });

            const message = response.message || `${CLIENT_DEFINITIONS[clientType].label} deleted.`;
            showNotification(message, "success");

            state.selectedClientKey = null;
            await loadAllData({ silent: true });
            renderDownloadClientsList();
        } catch (error) {
            console.error(error);
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`Failed to delete client: ${error.message}`, "error");
        } finally {
            deleteButton.classList.remove("loading");
            deleteButton.disabled = false;
        }
    }

    async function handleDownloadClientTest(event) {
        event.preventDefault();

        const typeSelect = document.getElementById("download_client_type");
        const statusTarget = document.getElementById("downloadClientStatus");

        if (!typeSelect || !statusTarget) {
            return;
        }

        const clientType = typeSelect.value;

        let payload;
        try {
            payload = getClientPayload(clientType);
        } catch (validationError) {
            statusTarget.textContent = validationError.message;
            statusTarget.className = "text-xs text-error";
            showNotification(validationError.message, "error");
            return;
        }

        statusTarget.textContent = "Testing connection…";
        statusTarget.className = "text-xs text-info";

        try {
            const response = await fetchJson(`/settings/api/clients/${clientType}/test`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const message = response.test_result?.message || response.message || "Connection successful";
            statusTarget.textContent = message;
            statusTarget.className = "text-xs text-success";
            showNotification(message, "success");
        } catch (error) {
            console.error(error);
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`Client test failed: ${error.message}`, "error");
        }
    }

    function getClientPayload(clientType) {
        const payload = {
            enabled: getCheckboxValue("download_client_enabled"),
            auto_download: getCheckboxValue("download_client_auto")
        };

        switch (clientType) {
            case "qbittorrent":
                payload.host = getInputValue("qb_host") || CLIENT_DEFINITIONS.qbittorrent.defaults.host;
                payload.port = toNumeric(getInputValue("qb_port"), CLIENT_DEFINITIONS.qbittorrent.defaults.port);
                payload.username = getInputValue("qb_username");
                payload.password = getInputValue("qb_password");
                payload.category = getInputValue("qb_category") || CLIENT_DEFINITIONS.qbittorrent.defaults.category;
                const rawMappings = collectQbPathMappings(true);
                const incompleteMapping = rawMappings.find((mapping) => (mapping.remote && !mapping.local) || (!mapping.remote && mapping.local));
                if (incompleteMapping) {
                    throw new Error("Complete both qB and host paths for each mapping entry.");
                }
                payload.path_mappings = rawMappings.filter((mapping) => mapping.remote && mapping.local);
                break;
            case "deluge":
                payload.host = getInputValue("deluge_host") || CLIENT_DEFINITIONS.deluge.defaults.host;
                payload.port = toNumeric(getInputValue("deluge_port"), CLIENT_DEFINITIONS.deluge.defaults.port);
                payload.password = getInputValue("deluge_password");
                break;
            case "transmission":
                payload.host = getInputValue("transmission_host") || CLIENT_DEFINITIONS.transmission.defaults.host;
                payload.port = toNumeric(getInputValue("transmission_port"), CLIENT_DEFINITIONS.transmission.defaults.port);
                payload.username = getInputValue("transmission_username");
                payload.password = getInputValue("transmission_password");
                break;
            case "sabnzbd":
                payload.host = getInputValue("sabnzbd_host") || CLIENT_DEFINITIONS.sabnzbd.defaults.host;
                payload.port = toNumeric(getInputValue("sabnzbd_port"), CLIENT_DEFINITIONS.sabnzbd.defaults.port);
                payload.username = getInputValue("sabnzbd_username");
                payload.password = getInputValue("sabnzbd_password");
                payload.api_key = getInputValue("sabnzbd_api_key");
                break;
            case "nzbget":
                payload.host = getInputValue("nzbget_host") || CLIENT_DEFINITIONS.nzbget.defaults.host;
                payload.port = toNumeric(getInputValue("nzbget_port"), CLIENT_DEFINITIONS.nzbget.defaults.port);
                payload.username = getInputValue("nzbget_username");
                payload.password = getInputValue("nzbget_password");
                break;
            default:
                break;
        }

        return payload;
    }

    function renderIndexerList() {
        const list = document.getElementById("indexersList");
        const emptyCard = document.getElementById("indexerEmptyState");
        const editor = document.getElementById("indexerEditor");

        if (!list || !emptyCard || !editor) {
            return;
        }

        list.innerHTML = "";

        const entries = Object.entries(state.indexers || {}).sort((a, b) => {
            const priorityDiff = (a[1].priority ?? DEFAULT_INDEXER_PRIORITY) - (b[1].priority ?? DEFAULT_INDEXER_PRIORITY);
            if (priorityDiff !== 0) {
                return priorityDiff;
            }
            return a[0].localeCompare(b[0]);
        });

        if (!entries.length) {
            const placeholder = document.createElement("div");
            placeholder.className = "rounded-lg border border-dashed border-base-300 p-4 text-sm text-base-content/60";
            placeholder.textContent = "No indexers configured yet.";
            list.appendChild(placeholder);
        } else {
            entries.forEach(([key, indexer]) => {
                const button = document.createElement("button");
                button.type = "button";
                button.dataset.indexerKey = key;
                button.className = `btn btn-sm w-full justify-between ${state.selectedIndexerKey === key ? "btn-primary" : "btn-outline"}`;

                const feedUrl = typeof indexer.feed_url === "string"
                    ? indexer.feed_url.trim()
                    : String(indexer.feed_url || "").trim();
                const hasApiKey = typeof indexer.api_key === "string"
                    ? Boolean(indexer.api_key.trim())
                    : Boolean(indexer.has_api_key);
                const baseUrl = typeof indexer.base_url === "string" ? indexer.base_url.trim() : "";
                const hasSessionId = typeof indexer.session_id === "string"
                    ? Boolean(indexer.session_id.trim())
                    : Boolean(indexer.has_session_id);
                const isDirect = isDirectIndexerType(indexer.type);
                const isConfigured = isDirect ? Boolean(baseUrl && hasSessionId) : Boolean(feedUrl && hasApiKey);

                const label = document.createElement("span");
                label.textContent = indexer.name || key;
                const tooltipBits = [];
                const typeLabel = INDEXER_TYPE_LABELS[indexer.type] || indexer.type;
                if (typeLabel) {
                    tooltipBits.push(typeLabel);
                }
                if (Number.isFinite(indexer.priority)) {
                    tooltipBits.push(`Priority ${indexer.priority}`);
                }
                if (tooltipBits.length) {
                    button.title = tooltipBits.join(" · ");
                }

                const status = document.createElement("span");
                let statusText = "Not configured";
                let statusClass = "text-xs text-base-content/60";

                if (isConfigured && indexer.enabled) {
                    statusText = "Configured";
                    statusClass = "text-xs text-success";
                } else if (isConfigured) {
                    statusText = "Disabled";
                    statusClass = "text-xs text-base-content/60";
                }

                status.textContent = statusText;
                status.className = statusClass;

                button.append(label, status);
                list.appendChild(button);
            });
        }

        if (!state.selectedIndexerKey && !state.addingIndexer) {
            emptyCard.classList.remove("hidden");
            editor.classList.add("hidden");
        }
    }

    function openIndexerEditor(indexerKey) {
        const editor = document.getElementById("indexerEditor");
        const emptyCard = document.getElementById("indexerEmptyState");
        const heading = document.getElementById("indexerHeading");
        const helper = document.getElementById("indexerHelper");
        const deleteButton = document.getElementById("indexerDeleteButton");
        const typeSelect = document.getElementById("indexer_type");
        const keyInput = document.getElementById("indexer_custom_key");
        const statusTarget = document.getElementById("indexerStatus");

        if (!editor || !emptyCard || !heading || !helper || !deleteButton || !typeSelect || !keyInput || !statusTarget) {
            return;
        }

        const isNewIndexer = !indexerKey;
        state.selectedIndexerKey = isNewIndexer ? null : indexerKey;
        state.addingIndexer = isNewIndexer;
        statusTarget.textContent = "";

        if (!isNewIndexer) {
            const indexer = state.indexers[indexerKey] || {};
            heading.textContent = indexer.name || indexerKey;
            const helperBits = [];
            if (isDirectIndexerType(indexer.type)) {
                helperBits.push(indexer.base_url ? "Base URL configured" : "Base URL missing");
            } else {
                helperBits.push(indexer.feed_url ? "Feed URL configured" : "Feed URL missing");
                helperBits.push(indexer.has_api_key ? `API key set (${indexer.api_key_masked || "hidden"})` : "API key missing");
            }
            helper.textContent = helperBits.filter(Boolean).join(" · ") || "Update the feed URL, API key, priority, or categories and save to apply changes.";
            deleteButton.classList.remove("hidden");
            keyInput.value = indexerKey;
            keyInput.disabled = true;
            keyInput.dataset.locked = "true";
            typeSelect.value = indexer.type || inferIndexerType(indexerKey, indexer.protocol);
            setCheckboxValue("indexer_enabled", indexer.enabled);
            setInputValue("indexer_name", indexer.name || "");
            setInputValue("indexer_feed_url", indexer.feed_url || "");
            setInputValue("indexer_api_key", indexer.api_key || "");
            setInputValue("indexer_base_url", indexer.base_url || "");
            setInputValue("indexer_session_id", indexer.session_id || "");
            setNumericInput("indexer_priority", indexer.priority, DEFAULT_INDEXER_PRIORITY);
            setInputValue("indexer_categories", (indexer.categories || []).join(", "));
        } else {
            heading.textContent = "New Indexer";
            helper.textContent = isDirectIndexerType(typeSelect.value)
                ? "Provide the base URL and session ID for your direct provider. Priority determines search order."
                : "Provide the torznab/newznab endpoint and API key. Priority determines search order.";
            deleteButton.classList.add("hidden");
            keyInput.value = generateSuggestedIndexerKey(typeSelect.value);
            keyInput.disabled = false;
            keyInput.dataset.locked = "false";
            typeSelect.value = typeSelect.value || "jackett";
            setCheckboxValue("indexer_enabled", true);
            setInputValue("indexer_name", "");
            setInputValue("indexer_feed_url", "");
            setInputValue("indexer_api_key", "");
            setInputValue("indexer_base_url", "");
            setInputValue("indexer_session_id", "");
            setNumericInput("indexer_priority", DEFAULT_INDEXER_PRIORITY, DEFAULT_INDEXER_PRIORITY);
            setInputValue("indexer_categories", "3030");
        }

        emptyCard.classList.add("hidden");
        editor.classList.remove("hidden");
        updateIndexerFieldVisibility(typeSelect.value);
        renderIndexerList();
    }

    function handleIndexerNameInput(event) {
        if (state.selectedIndexerKey) {
            return;
        }

        const keyInput = document.getElementById("indexer_custom_key");
        const typeSelect = document.getElementById("indexer_type");

        if (!keyInput || keyInput.disabled || keyInput.dataset.locked === "true") {
            return;
        }

        const slug = slugify(event.target.value);
        if (slug) {
            keyInput.value = slug;
        } else if (!keyInput.value) {
            keyInput.value = generateSuggestedIndexerKey(typeSelect ? typeSelect.value : "indexer");
        }
    }

    function handleIndexerKeyInput() {
        const keyInput = document.getElementById("indexer_custom_key");
        if (keyInput && !keyInput.disabled) {
            keyInput.dataset.locked = "true";
        }
    }

    function handleIndexerTypeChange(event) {
        const typeValue = event.target.value;
        updateIndexerFieldVisibility(typeValue);

        if (!state.selectedIndexerKey) {
            const helper = document.getElementById("indexerHelper");
            if (helper) {
                helper.textContent = isDirectIndexerType(typeValue)
                    ? "Provide the base URL and session ID for your direct provider. Priority determines search order."
                    : "Provide the torznab/newznab endpoint and API key. Priority determines search order.";
            }
        }

        if (state.selectedIndexerKey) {
            return;
        }

        const keyInput = document.getElementById("indexer_custom_key");
        if (!keyInput || keyInput.disabled || keyInput.dataset.locked === "true") {
            return;
        }

        keyInput.value = generateSuggestedIndexerKey(typeValue);
    }

    function inferIndexerType(key, protocol) {
        if (protocol === "newznab") {
            return "nzbhydra2";
        }
        if (key && key.toLowerCase().includes("prowlarr")) {
            return "prowlarr";
        }
        return "jackett";
    }

    async function handleIndexerSubmit(form) {
        const statusTarget = document.getElementById("indexerStatus");
        const submitButton = form.querySelector("button[type=\"submit\"]");

        if (!statusTarget || !submitButton) {
            return;
        }

        const keyInput = document.getElementById("indexer_custom_key");
        const nameInput = document.getElementById("indexer_name");
        const typeSelect = document.getElementById("indexer_type");

        if (!keyInput || !nameInput || !typeSelect) {
            return;
        }

        let indexerKey = state.selectedIndexerKey;
        if (!indexerKey) {
            indexerKey = slugify(keyInput.value || nameInput.value);
        }

        if (!indexerKey) {
            statusTarget.textContent = "Indexer key cannot be empty.";
            statusTarget.className = "text-xs text-error";
            return;
        }

        const existingIndexer = state.indexers[indexerKey];

        const typeValue = (typeSelect.value || "jackett").toLowerCase();
        const payload = {
            name: nameInput.value.trim() || indexerKey,
            type: typeValue,
            enabled: getCheckboxValue("indexer_enabled"),
            priority: toNumeric(getInputValue("indexer_priority"), DEFAULT_INDEXER_PRIORITY),
            categories: getInputValue("indexer_categories").split(",").map((value) => value.trim()).filter(Boolean)
        };

        if (isDirectIndexerType(typeValue)) {
            payload.base_url = getInputValue("indexer_base_url");
            payload.session_id = getInputValue("indexer_session_id");
            payload.feed_url = "";
            payload.api_key = "";
        } else {
            payload.feed_url = getInputValue("indexer_feed_url");
            payload.api_key = getInputValue("indexer_api_key");
            payload.base_url = "";
            payload.session_id = "";
        }

        if (existingIndexer) {
            if (existingIndexer.protocol) {
                payload.protocol = existingIndexer.protocol;
            } else if (isDirectIndexerType(typeValue)) {
                payload.protocol = "direct";
            } else {
                payload.protocol = payload.type === "nzbhydra2" ? "newznab" : "torznab";
            }
        } else {
            if (isDirectIndexerType(typeValue)) {
                payload.protocol = "direct";
            } else {
                payload.protocol = payload.type === "nzbhydra2" ? "newznab" : "torznab";
            }
        }

        if (existingIndexer && Object.prototype.hasOwnProperty.call(existingIndexer, "verify_ssl")) {
            payload.verify_ssl = existingIndexer.verify_ssl;
        }

        if (existingIndexer && Object.prototype.hasOwnProperty.call(existingIndexer, "timeout")) {
            payload.timeout = existingIndexer.timeout;
        }

        if (existingIndexer && existingIndexer.rate_limit) {
            payload.rate_limit = existingIndexer.rate_limit;
        }

        statusTarget.textContent = "Saving indexer…";
        statusTarget.className = "text-xs text-info";
        submitButton.classList.add("loading");
        submitButton.disabled = true;

        try {
            const response = await fetchJson(`/settings/api/indexers/${indexerKey}`, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            const message = response.message || "Indexer saved.";
            statusTarget.textContent = "Saved";
            statusTarget.className = "text-xs text-success";
            showNotification(message, "success");

            state.selectedIndexerKey = indexerKey;
            state.addingIndexer = false;
            await refreshIndexersList();
            openIndexerEditor(indexerKey);
        } catch (error) {
            console.error(error);
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`Failed to save indexer: ${error.message}`, "error");
        } finally {
            submitButton.classList.remove("loading");
            submitButton.disabled = false;
        }
    }

    async function handleIndexerDelete(event) {
        event.preventDefault();

        if (!state.selectedIndexerKey) {
            showNotification("Select an indexer before deleting.", "warning");
            return;
        }

        const statusTarget = document.getElementById("indexerStatus");
        const deleteButton = document.getElementById("indexerDeleteButton");

        if (!statusTarget || !deleteButton) {
            return;
        }

        statusTarget.textContent = "Deleting indexer…";
        statusTarget.className = "text-xs text-info";
        deleteButton.classList.add("loading");
        deleteButton.disabled = true;

        try {
            const key = state.selectedIndexerKey;
            const response = await fetchJson(`/settings/api/indexers/${key}`, {
                method: "DELETE"
            });

            const message = response.message || "Indexer deleted.";
            showNotification(message, "success");

            state.selectedIndexerKey = null;
            state.addingIndexer = false;
            await refreshIndexersList();
        } catch (error) {
            console.error(error);
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`Failed to delete indexer: ${error.message}`, "error");
        } finally {
            deleteButton.classList.remove("loading");
            deleteButton.disabled = false;
        }
    }

    async function refreshIndexersList(event) {
        if (event) {
            event.preventDefault();
        }

        try {
            const payload = await fetchJson("/settings/api/indexers");
            setIndexersState(payload.indexers || {});
            state.addingIndexer = false;
            renderIndexerList();

            if (state.selectedIndexerKey) {
                if (state.indexers[state.selectedIndexerKey]) {
                    openIndexerEditor(state.selectedIndexerKey);
                } else {
                    state.selectedIndexerKey = null;
                }
            }

            if (!state.selectedIndexerKey && !state.addingIndexer) {
                const emptyCard = document.getElementById("indexerEmptyState");
                const editor = document.getElementById("indexerEditor");
                if (emptyCard && editor) {
                    emptyCard.classList.remove("hidden");
                    editor.classList.add("hidden");
                }
            }
        } catch (error) {
            console.error(error);
            showNotification(`Failed to reload indexers: ${error.message}`, "error");
        }
    }

    async function handleIndexerTest(event) {
        event.preventDefault();

        if (!state.selectedIndexerKey) {
            showNotification("Select an indexer before testing.", "warning");
            return;
        }

        const statusTarget = document.getElementById("indexerStatus");
        if (!statusTarget) {
            return;
        }

        statusTarget.textContent = "Testing connection…";
        statusTarget.className = "text-xs text-info";

        try {
            const response = await fetchJson(`/settings/api/indexers/${state.selectedIndexerKey}/test`, {
                method: "POST"
            });

            const message = response.message || "Indexer connection successful";
            statusTarget.textContent = message;
            statusTarget.className = "text-xs text-success";
            showNotification(message, "success");
        } catch (error) {
            console.error(error);
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`Indexer test failed: ${error.message}`, "error");
        }
    }

    function generateSuggestedIndexerKey(type) {
        const base = slugify(type || "indexer");
        if (!base) {
            return `indexer_${Date.now()}`;
        }

        let candidate = base;
        let counter = 1;

        while (state.indexers[candidate]) {
            candidate = `${base}_${counter}`;
            counter += 1;
            if (counter > 999) {
                candidate = `${base}_${Date.now()}`;
                break;
            }
        }

        return candidate;
    }

    function populateMediaManagementForm() {
        const templateSelect = document.getElementById("mm_naming_template");
        const previewList = document.getElementById("mmNamingPreviewList");

        if (templateSelect) {
            templateSelect.innerHTML = "";
            if (state.namingTemplates.length) {
                state.namingTemplates.forEach((template) => {
                    const option = document.createElement("option");
                    option.value = template.name;
                    option.textContent = template.label || template.name;
                    templateSelect.appendChild(option);
                });
                templateSelect.disabled = false;
            } else {
                const option = document.createElement("option");
                option.value = "";
                option.textContent = "No templates available";
                templateSelect.appendChild(option);
                templateSelect.disabled = true;
            }
            const currentTemplate = state.mediaSettings.naming_template || "standard";
            templateSelect.value = currentTemplate;
        }

        if (previewList) {
            previewList.innerHTML = "";
        }

    setInputValue("mm_library_path", state.mediaSettings.library_path || "/mnt/audiobooks");
    setInputValue("mm_import_directory", state.mediaSettings.import_directory || "/downloads/import");

        setCheckboxValue("dm_seeding_enabled", state.downloadSettings.seeding_enabled);
        setCheckboxValue("dm_keep_torrent_active", state.downloadSettings.keep_torrent_active);
        setCheckboxValue("dm_wait_for_completion", state.downloadSettings.wait_for_seeding_completion);
        setCheckboxValue("dm_delete_source", state.downloadSettings.delete_source_after_import);
        setCheckboxValue("dm_delete_temp", state.downloadSettings.delete_temp_files);
        setCheckboxValue("dm_auto_process_queue", state.downloadSettings.auto_process_queue);
        setCheckboxValue("dm_auto_start_monitoring", state.downloadSettings.auto_start_monitoring);
        setCheckboxValue("dm_monitor_seeding", state.downloadSettings.monitor_seeding);

        setNumericInput("dm_retention_days", state.downloadSettings.retention_days, 7);
        setInputValue("dm_temp_download_path", state.downloadSettings.temp_download_path || "");
        setInputValue("dm_temp_conversion_path", state.downloadSettings.temp_conversion_path || "");
        setInputValue("dm_temp_failed_path", state.downloadSettings.temp_failed_path || "");
        setNumericInput("dm_max_concurrent_downloads", state.downloadSettings.max_concurrent_downloads, 3);
        setNumericInput("dm_queue_priority", state.downloadSettings.queue_priority_default, 5);
        setNumericInput("dm_monitor_interval", state.downloadSettings.monitoring_interval, 2);
        setNumericInput("dm_retry_search", state.downloadSettings.retry_search_max, 3);
        setNumericInput("dm_retry_download", state.downloadSettings.retry_download_max, 2);
        setNumericInput("dm_retry_conversion", state.downloadSettings.retry_conversion_max, 1);
        setNumericInput("dm_retry_import", state.downloadSettings.retry_import_max, 2);
        setNumericInput("dm_retry_backoff", state.downloadSettings.retry_backoff_minutes, 30);

        const audibleDefaults = state.mediaSettings.audible_downloads || {};
        setSelectValue("audible_format", audibleDefaults.format || "aaxc");
        setSelectValue("audible_quality", audibleDefaults.quality || "best");
        setCheckboxValue("audible_aax_fallback", audibleDefaults.aax_fallback !== undefined ? audibleDefaults.aax_fallback : true);
        setCheckboxValue("audible_save_voucher", audibleDefaults.save_voucher !== undefined ? audibleDefaults.save_voucher : true);
        setCheckboxValue("audible_include_cover", audibleDefaults.include_cover);
        setCheckboxValue("audible_include_chapters", audibleDefaults.include_chapters);
        setCheckboxValue("audible_include_pdf", audibleDefaults.include_pdf);
        setNumericInput("audible_concurrent_downloads", audibleDefaults.concurrent_downloads, 1);

        const currentTemplate = templateSelect ? templateSelect.value : "standard";
        renderNamingPreview(currentTemplate);
    }

    function handleNamingTemplateChange(event) {
        renderNamingPreview(event.target.value);
    }

    function renderNamingPreview(templateName) {
        const previewList = document.getElementById("mmNamingPreviewList");
        if (!previewList) {
            return;
        }

        previewList.innerHTML = "";
        const template = state.namingTemplates.find((entry) => entry.name === templateName);

        if (template && Array.isArray(template.examples) && template.examples.length) {
            template.examples.forEach((example) => {
                const item = document.createElement("li");
                item.className = "text-sm";
                const title = document.createElement("span");
                title.className = "font-medium";
                title.textContent = example.title || "Sample";
                const path = document.createElement("code");
                path.className = "ml-2 text-xs";
                path.textContent = example.preview || example.path || "";
                item.append(title, document.createTextNode(" → "), path);
                previewList.appendChild(item);
            });
        } else {
            fetchNamingPreview(templateName);
        }
    }

    async function fetchNamingPreview(templateName) {
        const previewList = document.getElementById("mmNamingPreviewList");
        if (!previewList) {
            return;
        }

        const loadingItem = document.createElement("li");
        loadingItem.className = "text-sm text-base-content/60 italic";
        loadingItem.textContent = "Generating preview…";
        previewList.appendChild(loadingItem);

        try {
            const response = await fetchJson("/settings/api/media-management/preview", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ template: templateName })
            });

            previewList.innerHTML = "";
            if (Array.isArray(response.examples) && response.examples.length) {
                response.examples.forEach((example) => {
                    const item = document.createElement("li");
                    item.className = "text-sm";
                    const title = document.createElement("span");
                    title.className = "font-medium";
                    title.textContent = example.title || "Sample";
                    const path = document.createElement("code");
                    path.className = "ml-2 text-xs";
                    path.textContent = example.path || "";
                    item.append(title, document.createTextNode(" → "), path);
                    previewList.appendChild(item);
                });
            } else {
                const emptyItem = document.createElement("li");
                emptyItem.className = "text-sm text-base-content/60 italic";
                emptyItem.textContent = "No preview examples available.";
                previewList.appendChild(emptyItem);
            }
        } catch (error) {
            console.error(error);
            previewList.innerHTML = "";
            const errorItem = document.createElement("li");
            errorItem.className = "text-sm text-error";
            errorItem.textContent = `Failed to generate preview: ${error.message}`;
            previewList.appendChild(errorItem);
        }
    }

    async function handleMediaManagementSubmit(form) {
        const statusTarget = document.getElementById("mediaStatus");
        const submitButton = form.querySelector("button[type=\"submit\"]");

        if (!statusTarget || !submitButton) {
            return;
        }

        const templateValue = getInputValue("mm_naming_template") || "standard";
        const mediaPayload = {
            library_path: getInputValue("mm_library_path") || state.mediaSettings.library_path || "/mnt/audiobooks",
            import_directory: getInputValue("mm_import_directory") || state.mediaSettings.import_directory || "/downloads/import",
            naming_template: templateValue,
            verify_after_import: Boolean(state.mediaSettings.verify_after_import),
            create_backup_on_error: Boolean(state.mediaSettings.create_backup_on_error),
            delete_source_after_import: Boolean(state.mediaSettings.delete_source_after_import)
        };

        const downloadPayload = {
            seeding_enabled: getCheckboxValue("dm_seeding_enabled"),
            keep_torrent_active: getCheckboxValue("dm_keep_torrent_active"),
            wait_for_seeding_completion: getCheckboxValue("dm_wait_for_completion"),
            delete_source_after_import: getCheckboxValue("dm_delete_source"),
            delete_temp_files: getCheckboxValue("dm_delete_temp"),
            auto_process_queue: getCheckboxValue("dm_auto_process_queue"),
            auto_start_monitoring: getCheckboxValue("dm_auto_start_monitoring"),
            monitor_seeding: getCheckboxValue("dm_monitor_seeding"),
            retention_days: toNumeric(getInputValue("dm_retention_days"), state.downloadSettings.retention_days || 7),
            temp_download_path: getInputValue("dm_temp_download_path"),
            temp_conversion_path: getInputValue("dm_temp_conversion_path"),
            temp_failed_path: getInputValue("dm_temp_failed_path"),
            max_concurrent_downloads: toNumeric(getInputValue("dm_max_concurrent_downloads"), state.downloadSettings.max_concurrent_downloads || 3),
            queue_priority_default: toNumeric(getInputValue("dm_queue_priority"), state.downloadSettings.queue_priority_default || 5),
            monitoring_interval: toNumeric(getInputValue("dm_monitor_interval"), state.downloadSettings.monitoring_interval || 2),
            retry_search_max: toNumeric(getInputValue("dm_retry_search"), state.downloadSettings.retry_search_max || 3),
            retry_download_max: toNumeric(getInputValue("dm_retry_download"), state.downloadSettings.retry_download_max || 2),
            retry_conversion_max: toNumeric(getInputValue("dm_retry_conversion"), state.downloadSettings.retry_conversion_max || 1),
            retry_import_max: toNumeric(getInputValue("dm_retry_import"), state.downloadSettings.retry_import_max || 2),
            retry_backoff_minutes: toNumeric(getInputValue("dm_retry_backoff"), state.downloadSettings.retry_backoff_minutes || 30)
        };

        const audiblePayload = {
            format: getInputValue("audible_format") || (state.mediaSettings.audible_downloads?.format || "aaxc"),
            quality: getInputValue("audible_quality") || (state.mediaSettings.audible_downloads?.quality || "best"),
            aax_fallback: getCheckboxValue("audible_aax_fallback"),
            save_voucher: getCheckboxValue("audible_save_voucher"),
            include_cover: getCheckboxValue("audible_include_cover"),
            include_chapters: getCheckboxValue("audible_include_chapters"),
            include_pdf: getCheckboxValue("audible_include_pdf"),
            concurrent_downloads: toNumeric(getInputValue("audible_concurrent_downloads"), state.mediaSettings.audible_downloads?.concurrent_downloads || 1)
        };

        statusTarget.textContent = "Saving media management settings…";
        statusTarget.className = "text-xs text-info";
        submitButton.classList.add("loading");
        submitButton.disabled = true;

        try {
            await Promise.all([
                fetchJson("/settings/api/media-management", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        ...mediaPayload,
                        audible_downloads: audiblePayload
                    })
                }),
                fetchJson("/settings/api/download-management", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(downloadPayload)
                })
            ]);

            statusTarget.textContent = "Saved";
            statusTarget.className = "text-xs text-success";
            showNotification("Media management settings saved.", "success");

            await loadAllData({ silent: true });
        } catch (error) {
            console.error(error);
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`Failed to save media settings: ${error.message}`, "error");
        } finally {
            submitButton.classList.remove("loading");
            submitButton.disabled = false;
        }
    }

    function populateAbsLibrariesFromResponse(payload) {
        state.absLibraries = payload.libraries || [];
        populateAbsLibrarySelect(getInputValue("abs_library_id"));
    }

    async function handleAbsTestConnection(event) {
        event.preventDefault();

        const statusTarget = document.getElementById("absConnectionStatus");
        if (!statusTarget) {
            return;
        }

        statusTarget.textContent = "Testing connection…";
        statusTarget.className = "text-xs text-info";

        try {
            const payload = await fetchJson("/settings/audiobookshelf/test", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    host: getInputValue("abs_host"),
                    api_key: getInputValue("abs_api_key")
                })
            });

            const message = payload.message || "Connection successful";
            statusTarget.textContent = message;
            statusTarget.className = "text-xs text-success";
            showNotification(message, "success");
        } catch (error) {
            console.error(error);
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`AudioBookShelf test failed: ${error.message}`, "error");
        }
    }

    async function handleAbsRefreshLibraries(event) {
        event.preventDefault();

        const statusTarget = document.getElementById("absConnectionStatus");
        if (statusTarget) {
            statusTarget.textContent = "Loading libraries…";
            statusTarget.className = "text-xs text-info";
        }

        const url = new URL("/settings/audiobookshelf/libraries", window.location.origin);
        const host = getInputValue("abs_host");
        const apiKey = getInputValue("abs_api_key");

        if (host) {
            url.searchParams.set("host", host);
        }
        if (apiKey) {
            url.searchParams.set("api_key", apiKey);
        }

        try {
            const payload = await fetchJson(url.toString());
            populateAbsLibrariesFromResponse(payload);
            if (statusTarget) {
                statusTarget.textContent = `Loaded ${payload.count || payload.libraries?.length || 0} libraries.`;
                statusTarget.className = "text-xs text-success";
            }
            showNotification("Libraries refreshed.", "success");
        } catch (error) {
            console.error(error);
            if (statusTarget) {
                statusTarget.textContent = error.message;
                statusTarget.className = "text-xs text-error";
            }
            showNotification(`Failed to load libraries: ${error.message}`, "error");
        }
    }

    async function handleAbsManualSync(event) {
        event.preventDefault();

        const statusTarget = document.getElementById("absConnectionStatus");
        if (statusTarget) {
            statusTarget.textContent = "Triggering manual sync…";
            statusTarget.className = "text-xs text-info";
        }

        try {
            const payload = await fetchJson("/settings/audiobookshelf/manual-sync", {
                method: "POST"
            });

            const message = payload.message || "Manual sync triggered.";
            if (statusTarget) {
                statusTarget.textContent = message;
                statusTarget.className = "text-xs text-success";
            }
            showNotification(message, "success");
        } catch (error) {
            console.error(error);
            if (statusTarget) {
                statusTarget.textContent = error.message;
                statusTarget.className = "text-xs text-error";
            }
            showNotification(`Manual sync failed: ${error.message}`, "error");
        }
    }

    function updateTimestamp() {
        const target = document.getElementById("configUpdatedAt");
        if (!target) {
            return;
        }

        if (!state.lastLoaded) {
            target.textContent = "Configuration not yet loaded";
            return;
        }

        target.textContent = `Configuration loaded ${state.lastLoaded.toLocaleString()}`;
    }

    async function handleGeneralSubmit(form) {
        const selectedTheme = getInputValue("app_theme") || "dark";
        const updates = {
            application: {
                log_level: getInputValue("app_log_level"),
                theme: selectedTheme
            },
            auto_search: {
                auto_download_enabled: getCheckboxValue("auto_download_enabled"),
                quality_threshold: toNumeric(getInputValue("quality_threshold"), 5)
            }
        };

        const wasSaved = await submitConfigUpdates({ updates }, form, "General settings saved.");
        if (wasSaved) {
            applyThemePreference(selectedTheme);
        }
    }

    function handleAbsSubmit(form) {
        const updates = {
            audiobookshelf: {
                abs_host: getInputValue("abs_host"),
                abs_library_id: getInputValue("abs_library_id"),
                abs_api_key: getInputValue("abs_api_key"),
                abs_sync_frequency: getInputValue("abs_sync_frequency"),
                abs_enabled: getCheckboxValue("abs_enabled"),
                abs_sync_metadata: getCheckboxValue("abs_sync_metadata"),
                abs_sync_only_owned: getCheckboxValue("abs_sync_only_owned"),
                abs_auto_sync: getCheckboxValue("abs_auto_sync"),
                abs_auto_sync_enabled: getCheckboxValue("abs_auto_sync")
            }
        };

        submitConfigUpdates({ updates }, form, "AudioBookShelf settings saved.");
    }

    async function submitConfigUpdates(payload, form, successMessage) {
        const statusTarget = form.dataset.statusTarget ? document.getElementById(form.dataset.statusTarget) : null;
        const submitButton = form.querySelector("button[type=\"submit\"]");

        if (statusTarget) {
            statusTarget.textContent = "Saving…";
            statusTarget.className = "text-xs text-info";
        }

        if (submitButton) {
            submitButton.classList.add("loading");
            submitButton.disabled = true;
        }

        try {
            const response = await fetchJson("/settings/config/update", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            if (statusTarget) {
                const message = response.message || "Saved";
                statusTarget.textContent = message;
                statusTarget.className = "text-xs text-success";
            }

            showNotification(successMessage || "Settings saved", "success");
            await loadAllData({ silent: true });
            return true;
        } catch (error) {
            console.error(error);
            if (statusTarget) {
                statusTarget.textContent = error.message;
                statusTarget.className = "text-xs text-error";
            }
            showNotification(`Unable to save settings: ${error.message}`, "error");
            return false;
        } finally {
            if (submitButton) {
                submitButton.classList.remove("loading");
                submitButton.disabled = false;
            }
        }
    }

    function handleThemeSelectionPreview(event) {
        const theme = event && event.target ? event.target.value : null;
        if (!theme) {
            return;
        }
        if (typeof setTheme === "function") {
            setTheme(theme, { persist: false });
        } else {
            document.documentElement.setAttribute("data-theme", theme);
        }
    }

    function applyThemePreference(theme) {
        if (typeof setTheme === "function") {
            setTheme(theme);
        } else {
            document.documentElement.setAttribute("data-theme", theme || "dark");
            try {
                localStorage.setItem("theme", theme || "dark");
            } catch (storageError) {
                console.warn("Unable to persist theme preference:", storageError);
            }
        }
    }

    function getStoredThemePreference() {
        try {
            return localStorage.getItem("theme") || "dark";
        } catch (_err) {
            return "dark";
        }
    }

    function showClientPanel(clientType) {
        const sections = document.querySelectorAll("[data-client-panel]");
        sections.forEach((section) => {
            if (section.dataset.clientPanel === clientType) {
                section.classList.remove("hidden");
            } else {
                section.classList.add("hidden");
            }
        });

        const mappingSection = document.querySelector("[data-qb-path-mappings]");
        if (mappingSection) {
            mappingSection.classList.toggle("hidden", clientType !== "qbittorrent");
        }
    }

    function toggleRefreshButton(isLoading) {
        const button = document.getElementById("refreshSettings");
        if (!button) {
            return;
        }

        if (isLoading) {
            button.classList.add("loading");
            button.disabled = true;
        } else {
            button.classList.remove("loading");
            button.disabled = false;
        }
    }

    async function fetchJson(url, options = {}) {
        const response = await fetch(url, options);
        const payload = await response.json();

        if (!response.ok || payload.success === false) {
            const message = payload.error || payload.message || `Request failed (${response.status})`;
            throw new Error(message);
        }

        return payload;
    }

    function safeAddFormHandler(id, handler) {
        const form = document.getElementById(id);
        if (form) {
            form.addEventListener("submit", (event) => {
                event.preventDefault();
                handler(form);
            });
        }
    }

    function safeAddEventListener(targetOrId, eventName, handler) {
        const element = typeof targetOrId === "string" ? document.getElementById(targetOrId) : targetOrId;
        if (element) {
            element.addEventListener(eventName, handler);
        }
    }

    function setInputValue(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.value = value == null ? "" : value;
        }
    }

    function setSelectValue(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.value = value == null || value === "" ? element.value : value;
        }
    }

    function setNumericInput(id, value, fallback) {
        const element = document.getElementById(id);
        if (!element) {
            return;
        }

        const numeric = toNumeric(value, fallback);
        element.value = Number.isFinite(numeric) ? numeric : fallback || "";
    }

    function setCheckboxValue(id, value) {
        const element = document.getElementById(id);
        if (element) {
            element.checked = toBoolean(value);
        }
    }

    function getInputValue(id) {
        const element = document.getElementById(id);
        if (!element) {
            return "";
        }
        return element.value.trim();
    }

    function getCheckboxValue(id) {
        const element = document.getElementById(id);
        return element ? element.checked : false;
    }

    function toBoolean(value) {
        if (typeof value === "boolean") {
            return value;
        }
        if (value == null) {
            return false;
        }
        const normalized = String(value).trim().toLowerCase();
        return ["true", "1", "yes", "on"].includes(normalized);
    }

    function toNumeric(value, fallback = 0) {
        if (value === "" || value === null || value === undefined) {
            return fallback;
        }
        const numeric = Number(value);
        return Number.isFinite(numeric) ? numeric : fallback;
    }

    function stripQuotes(value) {
        if (typeof value !== "string") {
            return value;
        }
        return value.replace(/^"|"$/g, "");
    }

    function slugify(value) {
        return (value || "")
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "_")
            .replace(/^_+|_+$/g, "")
            .slice(0, 60);
    }

    function initializeAudibleSection() {
        wireModalCloseButtons();
        resetAudibleAuthForms();
        renderAudibleStatus();
        renderAudibleStatsContent();
    }

    function wireModalCloseButtons() {
        const buttons = document.querySelectorAll("[data-modal-close]");
        buttons.forEach((button) => {
            if (button.dataset.modalBound === "true") {
                return;
            }
            button.addEventListener("click", (event) => {
                event.preventDefault();
                const targetId = button.dataset.modalClose;
                if (targetId) {
                    closeModal(targetId);
                }
            });
            button.dataset.modalBound = "true";
        });
    }

    async function refreshAudibleStatus(options = {}) {
        const { showToast = false, skipButtonState = false } = options;
        const helper = document.getElementById("audibleStatusHelper");
        if (helper) {
            helper.textContent = "Refreshing Audible status…";
        }
        if (!skipButtonState) {
            toggleButtonLoading("audibleRefreshButton", true);
        }

        try {
            const [serviceResponse, accountResponse] = await Promise.all([
                fetchJson("/api/audible/library/status"),
                fetchJson("/api/audible/auth/status")
            ]);

            state.audible.serviceStatus = serviceResponse.data || null;
            state.audible.accountStatus = accountResponse || null;
            state.audible.lastUpdated = new Date();
            renderAudibleStatus();

            if (showToast) {
                showNotification("Audible status refreshed.", "success");
            }
        } catch (error) {
            console.error(error);
            if (helper) {
                helper.textContent = `Failed to load status: ${error.message}`;
            }
            showNotification(`Failed to load Audible status: ${error.message}`, "error");
        } finally {
            if (!skipButtonState) {
                toggleButtonLoading("audibleRefreshButton", false);
            }
        }
    }

    function renderAudibleStatus() {
        const helper = document.getElementById("audibleStatusHelper");
        const status = state.audible.serviceStatus;

        if (!status) {
            if (helper) {
                helper.textContent = "Load status to view authentication and sync details.";
            }
            const authenticated = renderAudibleAuthenticationCard(null, state.audible.accountStatus);
            renderAudibleCacheCard(null);
            renderAudibleCapabilitiesList(null);
            toggleAudibleRevoke(authenticated);
            return;
        }

        if (helper) {
            helper.textContent = state.audible.lastUpdated
                ? `Status updated ${formatDateTime(state.audible.lastUpdated)}`
                : "Audible status loaded.";
        }

        const authenticated = renderAudibleAuthenticationCard(status.authentication, state.audible.accountStatus);
        renderAudibleCacheCard(status.cached_library);
        renderAudibleCapabilitiesList(status.capabilities);
        toggleAudibleRevoke(authenticated);
    }

    function renderAudibleAuthenticationCard(authData, accountPayload) {
        const headline = document.getElementById("audibleAuthHeadline");
        const details = document.getElementById("audibleAuthDetails");
        const summary = document.getElementById("audibleAccountSummary");
        const badgeId = "audibleAuthBadge";

        const accountWrapper = accountPayload && typeof accountPayload === "object" ? accountPayload : {};
        const account = accountWrapper.account && typeof accountWrapper.account === "object"
            ? accountWrapper.account
            : {};

        const isAuthenticated = Boolean((authData && authData.authenticated) || accountWrapper.authenticated);

        if (headline) {
            headline.textContent = isAuthenticated ? "Connected" : "Not Connected";
        }

        const message = authData?.message || accountWrapper?.message || (isAuthenticated ? "Audible authentication is ready." : "Authenticate to enable Audible features.");
        if (details) {
            details.textContent = message;
        }

        const summaryLines = [];
        if (account?.name) {
            summaryLines.push(`<p><span class="font-semibold">Name:</span> ${escapeHtml(account.name)}</p>`);
        }
        if (account?.marketplace) {
            summaryLines.push(`<p><span class="font-semibold">Marketplace:</span> ${escapeHtml(account.marketplace)}</p>`);
        }
        if (Array.isArray(authData?.auth_files) && authData.auth_files.length) {
            summaryLines.push(`<p class="mt-2 text-xs text-base-content/60">Auth files:</p>`);
            summaryLines.push(`<ul class="list-disc pl-4 text-xs text-base-content/60">${authData.auth_files
                .slice(0, 4)
                .map((file) => `<li>${escapeHtml(file)}</li>`)
                .join("")}</ul>`);
        }

        if (summary) {
            if (summaryLines.length) {
                summary.innerHTML = summaryLines.join("");
                summary.classList.remove("hidden");
            } else {
                summary.innerHTML = "";
                summary.classList.add("hidden");
            }
        }

        setBadge(badgeId, isAuthenticated ? "success" : "warning", isAuthenticated ? "Connected" : "Required");
        return isAuthenticated;
    }

    function renderAudibleCacheCard(cacheStatus) {
        const headline = document.getElementById("audibleCacheHeadline");
        const details = document.getElementById("audibleCacheDetails");
        const summary = document.getElementById("audibleExportSummary");

        if (!cacheStatus) {
            if (headline) {
                headline.textContent = "Unknown";
            }
            if (details) {
                details.textContent = "Awaiting cache information.";
            }
            if (summary) {
                summary.textContent = "";
            }
            setBadge("audibleCacheBadge", "neutral", "-");
            return;
        }

        const available = toBoolean(cacheStatus.available);
        const count = cacheStatus.book_count ?? cacheStatus.books ?? 0;
        const timestamp = cacheStatus.last_updated || cacheStatus.lastUpdated;

        if (headline) {
            headline.textContent = available ? `${formatNumber(count)} titles` : "Not Cached";
        }

        if (details) {
            details.textContent = available
                ? timestamp
                    ? `Last refreshed ${formatDateTime(timestamp)}.`
                    : "Cache is ready."
                : "Cache has not been generated yet.";
        }

        if (summary) {
            summary.textContent = available
                ? `Export includes ${formatNumber(count)} titles${timestamp ? ` (updated ${formatDateTime(timestamp)})` : "."}`
                : "";
        }

        setBadge("audibleCacheBadge", available ? "success" : "warning", available ? "Ready" : "Empty");
    }

    function renderAudibleCapabilitiesList(capabilities) {
        const list = document.getElementById("audibleCapabilitiesList");
        if (!list) {
            return;
        }

        list.innerHTML = "";

        const entries = capabilities
            ? Object.entries(capabilities).filter(([key]) => key && !key.toLowerCase().includes("cli"))
            : [];

        if (!entries.length) {
            const item = document.createElement("li");
            item.textContent = "Capability data unavailable. Run a sync after authenticating to populate details.";
            list.appendChild(item);
            return;
        }

        entries.forEach(([key, enabled]) => {
            const item = document.createElement("li");
            item.className = "flex items-center justify-between";

            const label = document.createElement("span");
            label.textContent = formatCapabilityLabel(key);

            const state = document.createElement("span");
            state.className = enabled ? "text-xs text-success" : "text-xs text-base-content/50";
            state.textContent = enabled ? "Available" : "Unavailable";

            item.append(label, state);
            list.appendChild(item);
        });
    }

    function toggleAudibleRevoke(isAuthenticated) {
        const button = document.getElementById("audibleRevokeButton");
        if (!button) {
            return;
        }
        button.classList.toggle("hidden", !isAuthenticated);
    }

    function renderAudibleStatsContent() {
        const container = document.getElementById("audibleStatsContent");
        if (!container) {
            return;
        }

        const statsPayload = state.audible.stats;
        if (!statsPayload || !statsPayload.stats) {
            container.textContent = "Statistics have not been loaded yet.";
            return;
        }

        const stats = statsPayload.stats;
        const summaryParts = [
            `<p><span class="font-semibold">Total titles:</span> ${formatNumber(stats.total_books ?? statsPayload.book_count ?? 0)}</p>`,
            `<p><span class="font-semibold">Hours owned:</span> ${formatNumber(stats.total_duration_hours ?? 0, 1)}</p>`,
            `<p><span class="font-semibold">Average length:</span> ${formatMinutesToHours(stats.average_duration_minutes)}</p>`,
            `<p><span class="font-semibold">Average rating:</span> ${stats.average_rating ? formatNumber(stats.average_rating, 2) : "N/A"}</p>`,
            `<p><span class="font-semibold">Titles with ratings:</span> ${formatNumber(stats.books_with_ratings ?? 0)}</p>`
        ];

        const diversityParts = [
            `<p><span class="font-semibold">Unique authors:</span> ${formatNumber(stats.unique_authors ?? 0)}</p>`,
            `<p><span class="font-semibold">Unique narrators:</span> ${formatNumber(stats.unique_narrators ?? 0)}</p>`,
            `<p><span class="font-semibold">Unique genres:</span> ${formatNumber(stats.unique_genres ?? 0)}</p>`,
            `<p><span class="font-semibold">Unique series:</span> ${formatNumber(stats.unique_series ?? 0)}</p>`
        ];

        let distributionSection = "";
        if (stats.rating_distribution && Object.keys(stats.rating_distribution).length) {
            distributionSection = `<div><p class="text-xs font-semibold uppercase tracking-wide text-base-content/60 mb-1">Rating Distribution</p><ul class="space-y-1 text-sm">${Object.entries(stats.rating_distribution)
                .map(([range, count]) => `<li class="flex items-center justify-between"><span>${escapeHtml(range)}</span><span class="text-xs text-base-content/60">${formatNumber(count)}</span></li>`)
                .join("")}</ul></div>`;
        }

        const secondColumnSections = [`<div class="space-y-1">${diversityParts.join("")}</div>`];
        if (distributionSection) {
            secondColumnSections.push(distributionSection);
        }

        let html = `<div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm"><div class="space-y-1">${summaryParts.join("")}</div><div class="space-y-3">${secondColumnSections.join("")}</div></div>`;

        const topLists = [
            renderAudibleTopList("Top Authors", stats.top_authors),
            renderAudibleTopList("Top Narrators", stats.top_narrators),
            renderAudibleTopList("Top Genres", stats.top_genres)
        ].filter(Boolean);

        if (topLists.length) {
            html += `<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">${topLists.join("")}</div>`;
        }

        container.innerHTML = html;
    }

    function renderAudibleTopList(title, entries) {
        if (!Array.isArray(entries) || !entries.length) {
            return "";
        }

        const items = entries.slice(0, 5).map(([name, count]) => {
            const label = name ? escapeHtml(String(name)) : "Unknown";
            return `<li class="flex items-center justify-between"><span>${label}</span><span class="text-xs text-base-content/60">${formatNumber(count)}</span></li>`;
        });

        return `<div><p class="text-xs font-semibold uppercase tracking-wide text-base-content/60 mb-1">${escapeHtml(title)}</p><ul class="space-y-1 text-sm">${items.join("")}</ul></div>`;
    }

    function renderAudibleSetupInfo(setupInfo = {}) {
        const sections = [];

        if (setupInfo.description) {
            sections.push(`<p class="text-sm">${escapeHtml(setupInfo.description)}</p>`);
        }

        if (Array.isArray(setupInfo.requirements) && setupInfo.requirements.length) {
            sections.push(`<div><p class="text-xs font-semibold uppercase tracking-wide text-base-content/60 mb-1">Requirements</p><ul class="list-disc space-y-1 pl-4 text-sm">${setupInfo.requirements.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`);
        }

        if (Array.isArray(setupInfo.steps) && setupInfo.steps.length) {
            sections.push(`<div><p class="text-xs font-semibold uppercase tracking-wide text-base-content/60 mb-1">Steps</p><ol class="list-decimal space-y-1 pl-4 text-sm">${setupInfo.steps
                .map((step) => {
                    const title = step.title ? escapeHtml(step.title) : `Step ${escapeHtml(String(step.step || ""))}`;
                    const description = step.description ? ` - ${escapeHtml(step.description)}` : "";
                    const command = step.command ? `<br><code class="text-xs">${escapeHtml(step.command)}</code>` : "";
                    return `<li><span class="font-medium">${title}</span>${description}${command}</li>`;
                })
                .join("")}</ol></div>`);
        }

        if (Array.isArray(setupInfo.security_notes) && setupInfo.security_notes.length) {
            sections.push(`<div><p class="text-xs font-semibold uppercase tracking-wide text-base-content/60 mb-1">Security Notes</p><ul class="list-disc space-y-1 pl-4 text-sm">${setupInfo.security_notes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`);
        }

        if (Array.isArray(setupInfo.troubleshooting) && setupInfo.troubleshooting.length) {
            sections.push(`<div><p class="text-xs font-semibold uppercase tracking-wide text-base-content/60 mb-1">Troubleshooting</p><ul class="list-disc space-y-1 pl-4 text-sm">${setupInfo.troubleshooting.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></div>`);
        }

        if (!sections.length) {
            sections.push(
                `<p class="text-sm">Use the in-app authentication flow to connect your Audible account. The entire process happens inside AuralArchive—no external CLI required.</p>`
            );
            sections.push(
                `<div><p class="text-xs font-semibold uppercase tracking-wide text-base-content/60 mb-1">Steps</p><ol class="list-decimal space-y-1 pl-4 text-sm"><li><span class="font-medium">Start authentication</span> - Click <em>Authenticate</em> in the Audible tab.</li><li><span class="font-medium">Enter your Audible credentials</span> - Provide the email and password you use with Audible.</li><li><span class="font-medium">Verify the one-time passcode</span> - Enter the OTP sent by Audible to complete sign-in.</li><li><span class="font-medium">Run a library sync</span> - Launch a Quick or Full sync to pull your owned titles.</li></ol></div>`
            );
            sections.push(
                `<p class="text-xs text-base-content/60">Tokens are stored securely. You can revoke access at any time using the <em>Revoke</em> button.</p>`
            );
        }

        return sections.join("");
    }

    function openAudibleAuthModal(event) {
        if (event) {
            event.preventDefault();
        }
        resetAudibleAuthForms();
        openModal("audibleAuthModal");
    }

    function resetAudibleAuthForms() {
        setInputValue("audible_auth_email", "");
        setInputValue("audible_auth_password", "");
        setInputValue("audible_auth_otp", "");
        setElementText("audibleAuthFormStatus", "");
        setElementText("audibleOtpFormStatus", "");
        state.audible.pendingSessionId = null;
    }

    async function handleAudibleAuthSubmit(form) {
        const statusTarget = document.getElementById("audibleAuthFormStatus");
        const submitButton = form.querySelector("button[type=\"submit\"]");

        if (!statusTarget || !submitButton) {
            return;
        }

        const email = getInputValue("audible_auth_email");
        const password = getInputValue("audible_auth_password");
        const countrySelect = document.getElementById("audible_auth_country");
        const country = countrySelect ? countrySelect.value : "us";

        if (!email || !password) {
            statusTarget.textContent = "Email and password are required.";
            statusTarget.className = "text-xs text-error";
            return;
        }

        statusTarget.textContent = "Starting authentication…";
        statusTarget.className = "text-xs text-info";
        submitButton.classList.add("loading");
        submitButton.disabled = true;

        try {
            const payload = await fetchJson("/api/audible/auth/start", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    username: email,
                    password,
                    country_code: country
                })
            });

            if (payload.requires_otp) {
                state.audible.pendingSessionId = payload.session_id;
                statusTarget.textContent = "One-time password required. Enter the code to continue.";
                statusTarget.className = "text-xs text-info";
                closeModal("audibleAuthModal");
                openModal("audibleOtpModal");
            } else {
                state.audible.pendingSessionId = null;
                closeModal("audibleAuthModal");
                setAudibleSuccessModal(payload.account || {});
                openModal("audibleSuccessModal");
                showNotification("Audible authentication completed.", "success");
                await refreshAudibleStatus({ showToast: true, skipButtonState: true });
            }
        } catch (error) {
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`Audible authentication failed: ${error.message}`, "error");
        } finally {
            submitButton.classList.remove("loading");
            submitButton.disabled = false;
            setInputValue("audible_auth_password", "");
        }
    }

    function setAudibleSuccessModal(account = {}) {
        setElementText("audibleSuccessAccount", account.name || account.email || "—");
        setElementText("audibleSuccessMarketplace", account.marketplace || "—");
    }

    async function handleAudibleOtpSubmit(form) {
        const statusTarget = document.getElementById("audibleOtpFormStatus");
        const submitButton = form.querySelector("button[type=\"submit\"]");

        if (!statusTarget || !submitButton) {
            return;
        }

        if (!state.audible.pendingSessionId) {
            statusTarget.textContent = "Session expired. Restart authentication.";
            statusTarget.className = "text-xs text-error";
            return;
        }

        const otpValue = getInputValue("audible_auth_otp");
        if (!otpValue) {
            statusTarget.textContent = "Enter the OTP code to continue.";
            statusTarget.className = "text-xs text-error";
            return;
        }

        statusTarget.textContent = "Verifying code…";
        statusTarget.className = "text-xs text-info";
        submitButton.classList.add("loading");
        submitButton.disabled = true;

        try {
            const payload = await fetchJson("/api/audible/auth/submit-otp", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    session_id: state.audible.pendingSessionId,
                    otp_code: otpValue
                })
            });

            state.audible.pendingSessionId = null;
            closeModal("audibleOtpModal");
            setAudibleSuccessModal(payload.account || {});
            openModal("audibleSuccessModal");
            showNotification("Audible authentication completed.", "success");
            await refreshAudibleStatus({ showToast: true, skipButtonState: true });
        } catch (error) {
            statusTarget.textContent = error.message;
            statusTarget.className = "text-xs text-error";
            showNotification(`OTP verification failed: ${error.message}`, "error");
        } finally {
            submitButton.classList.remove("loading");
            submitButton.disabled = false;
            setInputValue("audible_auth_otp", "");
        }
    }

    async function handleAudibleRevoke(event) {
        if (event) {
            event.preventDefault();
        }

        toggleButtonLoading("audibleRevokeButton", true);

        try {
            const payload = await fetchJson("/api/audible/auth/revoke", {
                method: "POST"
            });

            showNotification(payload.message || "Audible authentication revoked.", "success");
            state.audible.accountStatus = { authenticated: false };
            await refreshAudibleStatus({ skipButtonState: true });
        } catch (error) {
            console.error(error);
            showNotification(`Failed to revoke authentication: ${error.message}`, "error");
        } finally {
            toggleButtonLoading("audibleRevokeButton", false);
        }
    }

    async function handleAudibleSetupInfo(event) {
        if (event) {
            event.preventDefault();
        }

        toggleButtonLoading("audibleSetupButton", true);

        try {
            const payload = await fetchJson("/api/audible/library/setup-info");
            const info = payload.data || payload;
            state.audible.setupInfo = info;
            updateAudibleInfoPanel(renderAudibleSetupInfo(info));
            showNotification("Setup guide loaded.", "success");
        } catch (error) {
            console.error(error);
            showNotification(`Failed to load setup guide: ${error.message}`, "error");
        } finally {
            toggleButtonLoading("audibleSetupButton", false);
        }
    }

    async function handleAudibleSyncFull(event) {
        if (event) {
            event.preventDefault();
        }

        toggleButtonLoading("audibleSyncFullButton", true);
        const helper = document.getElementById("audibleStatusHelper");
        if (helper) {
            helper.textContent = "Starting full library sync…";
        }

        try {
            const payload = await fetchJson("/api/audible/library/sync/full", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({})
            });

            const data = payload.data || payload;
            const message = data.message || "Full sync started.";
            showNotification(message, "success");
            if (helper) {
                helper.textContent = `${message} (${formatDateTime(new Date())})`;
            }
            await refreshAudibleStatus({ skipButtonState: true });
        } catch (error) {
            console.error(error);
            showNotification(`Full sync failed: ${error.message}`, "error");
            if (helper) {
                helper.textContent = `Full sync failed: ${error.message}`;
            }
        } finally {
            toggleButtonLoading("audibleSyncFullButton", false);
        }
    }

    async function handleAudibleSyncQuick(event) {
        if (event) {
            event.preventDefault();
        }

        toggleButtonLoading("audibleSyncQuickButton", true);
        const helper = document.getElementById("audibleStatusHelper");
        if (helper) {
            helper.textContent = "Starting quick library sync…";
        }

        try {
            const payload = await fetchJson("/api/audible/library/sync/quick", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({})
            });

            const data = payload.data || payload;
            const message = data.message || "Quick sync started.";
            showNotification(message, "success");
            if (helper) {
                helper.textContent = `${message} (${formatDateTime(new Date())})`;
            }
            await refreshAudibleStatus({ skipButtonState: true });
        } catch (error) {
            console.error(error);
            showNotification(`Quick sync failed: ${error.message}`, "error");
            if (helper) {
                helper.textContent = `Quick sync failed: ${error.message}`;
            }
        } finally {
            toggleButtonLoading("audibleSyncQuickButton", false);
        }
    }

    async function handleAudibleLibraryRefresh(event) {
        if (event) {
            event.preventDefault();
        }

        toggleButtonLoading("audibleRefreshLibraryButton", true);
        setElementText("audibleCacheDetails", "Refreshing Audible library cache…");

        try {
            const payload = await fetchJson("/api/audible/library/refresh", {
                method: "POST"
            });

            const data = payload.data || payload;
            const message = data.message || "Library cache refreshed.";
            showNotification(message, "success");
            state.audible.serviceStatus = state.audible.serviceStatus || {};
            state.audible.serviceStatus.cached_library = {
                available: true,
                book_count: data.book_count ?? data.data?.book_count ?? 0,
                last_updated: data.last_updated || new Date().toISOString()
            };
            renderAudibleStatus();
            await refreshAudibleStatus({ skipButtonState: true });
        } catch (error) {
            console.error(error);
            setElementText("audibleCacheDetails", `Refresh failed: ${error.message}`);
            showNotification(`Library cache refresh failed: ${error.message}`, "error");
        } finally {
            toggleButtonLoading("audibleRefreshLibraryButton", false);
        }
    }

    async function handleAudibleDownloadAll(event) {
        if (event) {
            event.preventDefault();
        }

        toggleButtonLoading("audibleDownloadAllButton", true);
        setElementText("audibleBulkDownloadStatus", "Preparing to download entire library…");

        const audibleDefaults = state.mediaSettings?.audible_downloads || {};
        const format = getInputValue("audible_format") || audibleDefaults.format || "aaxc";
        const quality = getInputValue("audible_quality") || audibleDefaults.quality || "best";
        const includePdf = getCheckboxValue("audible_include_pdf");
        const includeCover = getCheckboxValue("audible_include_cover");
        const includeChapters = getCheckboxValue("audible_include_chapters");
        const concurrencyDefault = audibleDefaults.concurrent_downloads || 1;
        const jobs = Math.max(1, toNumeric(getInputValue("audible_concurrent_downloads"), concurrencyDefault || 1));

        try {
            const result = await fetchJson("/api/audible/library/download/all", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    format,
                    quality,
                    include_pdf: includePdf,
                    include_cover: includeCover,
                    include_chapters: includeChapters,
                    jobs
                })
            });

            if (!result.success) {
                throw new Error(result.error || "Bulk download failed to start");
            }

            const summaryParts = [result.message || "Bulk download started."];
            if (result.download_id) {
                summaryParts.push(`ID: ${result.download_id}`);
            }
            if (Array.isArray(result.warnings) && result.warnings.length) {
                summaryParts.push(result.warnings.join(" "));
            }

            const statusMessage = summaryParts.join(" ");
            setElementText("audibleBulkDownloadStatus", statusMessage);
            showNotification(statusMessage, "success");
        } catch (error) {
            console.error(error);
            const message = `Failed to start bulk download: ${error.message}`;
            setElementText("audibleBulkDownloadStatus", message);
            showNotification(message, "error");
        } finally {
            toggleButtonLoading("audibleDownloadAllButton", false);
        }
    }

    async function handleAudibleExport(event) {
        if (event) {
            event.preventDefault();
        }

        toggleButtonLoading("audibleExportButton", true);
        setElementText("audibleExportSummary", "Exporting library…");

        try {
            const payload = await fetchJson("/api/audible/library/export?format=json");
            const data = payload.data || payload;
            const bookCount = data.book_count ?? data.data?.book_count ?? 0;
            const timestamp = data.last_updated || new Date().toISOString();
            setElementText("audibleExportSummary", `Export includes ${formatNumber(bookCount)} titles (generated ${formatDateTime(timestamp)}).`);
            showNotification("Library export completed.", "success");
            await refreshAudibleStatus({ skipButtonState: true });
        } catch (error) {
            console.error(error);
            setElementText("audibleExportSummary", `Export failed: ${error.message}`);
            showNotification(`Library export failed: ${error.message}`, "error");
        } finally {
            toggleButtonLoading("audibleExportButton", false);
        }
    }

    async function handleAudibleStatsLoad(event) {
        if (event) {
            event.preventDefault();
        }

        const triggerId = event?.currentTarget?.id;
        if (triggerId) {
            toggleButtonLoading(triggerId, true);
        }

        const container = document.getElementById("audibleStatsContent");
        if (container) {
            container.textContent = "Loading statistics…";
        }

        try {
            const payload = await fetchJson("/api/audible/library/stats");
            state.audible.stats = payload.data || payload;
            renderAudibleStatsContent();
            showNotification("Library statistics loaded.", "success");
        } catch (error) {
            console.error(error);
            if (container) {
                container.textContent = `Failed to load statistics: ${error.message}`;
            }
            showNotification(`Failed to load statistics: ${error.message}`, "error");
        } finally {
            if (triggerId) {
                toggleButtonLoading(triggerId, false);
            }
        }
    }

    async function handleAudibleValidate(event) {
        if (event) {
            event.preventDefault();
        }

        toggleButtonLoading("audibleValidateButton", true);

        try {
            const payload = await fetchJson("/api/audible/library/validate-credentials");
            const data = payload.data || payload;
            const isValid = Boolean(data.valid);
            const message = data.message || (isValid ? "Credentials validated." : "Credentials require attention.");
            showNotification(message, isValid ? "success" : "warning");

            if (data.instructions) {
                updateAudibleInfoPanel(renderAudibleSetupInfo(data.instructions));
            }
        } catch (error) {
            console.error(error);
            showNotification(`Credential validation failed: ${error.message}`, "error");
        } finally {
            toggleButtonLoading("audibleValidateButton", false);
        }
    }

    function updateAudibleInfoPanel(content) {
        const panel = document.getElementById("audibleInfoPanel");
        if (!panel) {
            return;
        }

        if (content) {
            panel.innerHTML = content;
        } else {
            panel.textContent = "Use the quick actions above to authenticate, run syncs, or refresh your library.";
        }
    }

    function toggleButtonLoading(buttonId, isLoading) {
        if (!buttonId) {
            return;
        }

        const button = document.getElementById(buttonId);
        if (!button) {
            return;
        }

        button.classList.toggle("loading", Boolean(isLoading));
        button.disabled = Boolean(isLoading);
    }

    function setElementText(id, text) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = text == null ? "" : text;
        }
    }

    function setBadge(id, variant, label) {
        const element = document.getElementById(id);
        if (!element) {
            return;
        }

        let variantClass = "badge-ghost";
        switch (variant) {
            case "success":
                variantClass = "badge-success";
                break;
            case "warning":
                variantClass = "badge-warning";
                break;
            case "error":
                variantClass = "badge-error";
                break;
            case "info":
                variantClass = "badge-info";
                break;
            default:
                variantClass = "badge-ghost";
                break;
        }

        element.className = `badge badge-sm ${variantClass}`;
        if (label !== undefined) {
            element.textContent = label;
        }
    }

    function openModal(id) {
        const modal = document.getElementById(id);
        if (modal && typeof modal.showModal === "function" && !modal.open) {
            modal.showModal();
        }
    }

    function closeModal(id) {
        const modal = document.getElementById(id);
        if (modal && typeof modal.close === "function" && modal.open) {
            modal.close();
        }
    }

    function escapeHtml(value) {
        if (value == null) {
            return "";
        }

        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatDateTime(value) {
        if (!value) {
            return "";
        }

        const date = value instanceof Date ? value : new Date(value);
        if (Number.isNaN(date.getTime())) {
            return "";
        }

        return date.toLocaleString();
    }

    function formatNumber(value, fractionDigits = 0) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) {
            return "0";
        }

        return numeric.toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: fractionDigits
        });
    }

    function formatMinutesToHours(minutes) {
        const numeric = Number(minutes);
        if (!Number.isFinite(numeric) || numeric <= 0) {
            return "N/A";
        }

        const totalMinutes = Math.round(numeric);
        const hrs = Math.floor(totalMinutes / 60);
        const mins = totalMinutes % 60;

        if (hrs && mins) {
            return `${hrs}h ${mins}m`;
        }
        if (hrs) {
            return `${hrs}h`;
        }
        return `${mins}m`;
    }

    function formatCapabilityLabel(key) {
        if (!key) {
            return "";
        }

        return key
            .split("_")
            .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
            .join(" ");
    }
})();
