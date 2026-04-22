// ==============================================
// AuralArchive - Library Page JavaScript
// Modern ES6+ with DaisyUI integration
// ==============================================

// Global state
const LibraryState = {
    selectedBooks: new Set(),
    isSelectMode: false,
    currentFilters: {
        search: '',
        status: '',
        genre: '',
        sort: 'title'
    },
    filteredIds: new Set(),
    books: [],
    filteredBooks: []
};

const LazyState = {
    batchSize: 48,
    renderedCount: 0,
    observer: null,
    loading: false,
    cooldownMs: 100,
    pendingTimer: null
};

// ==============================================
// DOM Ready
// ==============================================
document.addEventListener('DOMContentLoaded', () => {
    initializeFilters();
    initializeSelectionMode();
    initializeBookCards();
    initializeBulkActions();
    initializeSizeSlider();
    initializeLazyGrid();

    // Auto-open book detail modal when navigated from dashboard (?book=<id>)
    const params = new URLSearchParams(window.location.search);
    const bookParam = params.get('book');
    if (bookParam) {
        const bookId = parseInt(bookParam, 10);
        if (!isNaN(bookId)) {
            // Wait for lazy grid to finish its first render before opening
            setTimeout(() => openBookModal(bookId), 300);
        }
        // Clean up URL so refreshing doesn't re-open the modal
        history.replaceState(null, '', window.location.pathname);
    }
});

// ==============================================
// Size Slider
// ==============================================
function initializeSizeSlider() {
    const sizeSlider = document.getElementById('sizeSlider');
    const booksGrid = document.getElementById('booksGrid');
    
    if (!sizeSlider || !booksGrid) return;
    
    // Load saved size preference
    const savedSize = localStorage.getItem('libraryCardSize') || '50';
    sizeSlider.value = savedSize;
    applySizeClass(parseInt(savedSize));
    
    // Handle slider changes
    sizeSlider.addEventListener('input', (e) => {
        const value = parseInt(e.target.value);
        applySizeClass(value);
        localStorage.setItem('libraryCardSize', value);
    });
}

function applySizeClass(value) {
    const booksGrid = document.getElementById('booksGrid');
    if (!booksGrid) return;
    
    // Remove all size classes
    booksGrid.classList.remove('size-xs', 'size-sm', 'size-md', 'size-lg', 'size-xl');
    
    // Apply appropriate size class based on slider value
    // 0-20: xs (150px), 21-40: sm (175px), 41-60: md (200px), 61-80: lg (250px), 81-100: xl (300px)
    if (value <= 20) {
        booksGrid.classList.add('size-xs');
    } else if (value <= 40) {
        booksGrid.classList.add('size-sm');
    } else if (value <= 60) {
        booksGrid.classList.add('size-md');
    } else if (value <= 80) {
        booksGrid.classList.add('size-lg');
    } else {
        booksGrid.classList.add('size-xl');
    }
}

// ==============================================
// Filter System
// ==============================================
function initializeFilters() {
    const searchInput = document.getElementById('searchInput');
    const statusFilter = document.getElementById('statusFilter');
    const genreFilter = document.getElementById('genreFilter');
    const sortFilter = document.getElementById('sortFilter');
    const clearBtn = document.getElementById('clearFiltersBtn');

    // Search with debounce
    let searchTimeout;
    searchInput?.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            LibraryState.currentFilters.search = e.target.value.toLowerCase();
            applyFilters();
        }, 300);
    });

    // Status filter
    statusFilter?.addEventListener('change', (e) => {
        LibraryState.currentFilters.status = e.target.value;
        applyFilters();
    });

    // Genre filter
    genreFilter?.addEventListener('change', (e) => {
        LibraryState.currentFilters.genre = e.target.value;
        applyFilters();
    });

    // Sort filter
    sortFilter?.addEventListener('change', (e) => {
        LibraryState.currentFilters.sort = e.target.value;
        applyFilters();
    });

    // Clear filters
    clearBtn?.addEventListener('click', () => {
        searchInput.value = '';
        statusFilter.value = '';
        genreFilter.value = '';
        sortFilter.value = 'title';
        
        LibraryState.currentFilters = {
            search: '',
            status: '',
            genre: '',
            sort: 'title'
        };
        
        applyFilters();
        showNotification('Filters cleared', 'info');
    });
}

function applyFilters() {
    const searchTerm = (LibraryState.currentFilters.search || '').toLowerCase();
    const statusFilter = LibraryState.currentFilters.status || '';
    const genreFilter = LibraryState.currentFilters.genre || '';
    const sortBy = LibraryState.currentFilters.sort;

    LibraryState.filteredIds = new Set();

    const filtered = LibraryState.books.filter(book => {
        const title = book.title_lc || '';
        const author = book.author_lc || '';
        const status = book.ownership_status || 'unknown';
        const genre = book.genre || 'unknown';

        const matchesSearch = !searchTerm || title.includes(searchTerm) || author.includes(searchTerm);
        const matchesStatus = !statusFilter || status === statusFilter;
        const matchesGenre = !genreFilter || genre === genreFilter;

        if (matchesSearch && matchesStatus && matchesGenre) {
            if (book.id !== undefined && book.id !== null) {
                LibraryState.filteredIds.add(String(book.id));
            }
            return true;
        }
        return false;
    });

    filtered.sort((a, b) => {
        switch (sortBy) {
            case 'author':
                return (a.author || '').localeCompare(b.author || '');
            case 'rating':
                return (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0);
            case 'date':
                return 0; // keep backend order for now
            case 'title':
            default:
                return (a.title || '').localeCompare(b.title || '');
        }
    });

    LibraryState.filteredBooks = filtered;
    LazyState.renderedCount = 0;

    const grid = document.getElementById('booksGrid');
    if (grid) {
        grid.innerHTML = '';
    }

    const sentinel = document.getElementById('lazySentinel');
    if (LazyState.observer && sentinel) {
        LazyState.observer.disconnect();
        LazyState.observer.observe(sentinel);
    }

    requestNextBatch(true);
}

function initializeLazyGrid() {
    if (!Array.isArray(window.libraryBooks)) {
        console.error('libraryBooks missing or invalid; falling back to empty array');
        window.libraryBooks = [];
    }

    LibraryState.books = window.libraryBooks.map(book => ({
        ...book,
        title_lc: (book.title || '').toLowerCase(),
        author_lc: (book.author || '').toLowerCase()
    }));
    LibraryState.filteredBooks = LibraryState.books;

    console.debug('Library init', {
        total: LibraryState.books.length,
        sample: LibraryState.books.slice(0, 3)
    });

    const sentinel = document.getElementById('lazySentinel');
    if (sentinel) {
        LazyState.observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    requestNextBatch();
                }
            });
        }, { root: null, rootMargin: '200px', threshold: 0 });
        LazyState.observer.observe(sentinel);
    }

    applyFilters();
}

function requestNextBatch(immediate = false) {
    if (LazyState.loading) return;
    if (LazyState.pendingTimer) return;

    if (immediate) {
        renderNextBatch();
        return;
    }

    LazyState.pendingTimer = setTimeout(() => {
        LazyState.pendingTimer = null;
        renderNextBatch();
    }, LazyState.cooldownMs);
}

function showLoader() {
    const loader = document.getElementById('lazyLoader');
    if (loader) loader.classList.remove('hidden');
}

function hideLoader() {
    const loader = document.getElementById('lazyLoader');
    if (loader) loader.classList.add('hidden');
}

function setEmptyState(visible) {
    const empty = document.getElementById('emptyState');
    const grid = document.getElementById('booksGrid');
    if (empty) {
        if (visible) {
            empty.classList.remove('hidden');
        } else {
            empty.classList.add('hidden');
        }
    }
    if (grid && visible) {
        grid.innerHTML = '';
    }
}

function renderNextBatch() {
    if (LazyState.loading) return;

    const grid = document.getElementById('booksGrid');
    if (!grid) return;

    if (!LibraryState.filteredBooks || LibraryState.filteredBooks.length === 0) {
        setEmptyState(true);
        hideLoader();
        if (LazyState.observer) {
            LazyState.observer.disconnect();
        }
        console.warn('No books to render; filteredBooks length is 0');
        return;
    }

    setEmptyState(false);

    if (LazyState.renderedCount >= LibraryState.filteredBooks.length) {
        hideLoader();
        if (LazyState.observer) {
            LazyState.observer.disconnect();
        }
        return;
    }

    LazyState.loading = true;
    showLoader();

    try {
        const start = LazyState.renderedCount;
        const end = Math.min(start + LazyState.batchSize, LibraryState.filteredBooks.length);
        const frag = document.createDocumentFragment();

        for (let i = start; i < end; i++) {
            const card = createBookCard(LibraryState.filteredBooks[i]);
            if (card) {
                frag.appendChild(card);
            }
        }

        grid.appendChild(frag);
        LazyState.renderedCount = end;
    } catch (err) {
        console.error('Library render error:', err);
        setEmptyState(true);
        if (LazyState.observer) {
            LazyState.observer.disconnect();
        }
    } finally {
        LazyState.loading = false;
        hideLoader();

        if (LazyState.pendingTimer) {
            clearTimeout(LazyState.pendingTimer);
            LazyState.pendingTimer = null;
        }
    }

    if (LazyState.renderedCount >= LibraryState.filteredBooks.length) {
        hideLoader();
        if (LazyState.observer) {
            LazyState.observer.disconnect();
        }
    }
}

function createBookCard(book) {
    if (!book || book.id === undefined || book.id === null) return null;

    const titleLc = book.title_lc || (book.title || '').toLowerCase();
    const authorLc = book.author_lc || (book.author || '').toLowerCase();

    const card = document.createElement('div');
    card.className = 'cursor-pointer book-card group relative';
    card.dataset.bookId = book.id;
    card.dataset.status = book.ownership_status || 'unknown';
    card.dataset.genre = book.genre || 'unknown';
    card.dataset.title = titleLc;
    card.dataset.author = authorLc;

    const rating = book.rating ? Number(book.rating).toFixed(1) : null;
    const numRatings = book.num_ratings ? `(${book.num_ratings})` : '';
    const hasRating = rating && rating !== 'NaN';

    card.innerHTML = `
        <div class="book-cover-container relative bg-base-300 rounded-sm overflow-hidden shadow-md hover:shadow-lg transition-all duration-200 aspect-square">
            ${book.cover_image ? `
                <img src="${escapeHtml(book.cover_image)}" 
                     alt="${escapeHtml(book.title || '')}" 
                     class="w-full h-full object-cover"
                     loading="lazy"
                     decoding="async"
                     width="225"
                     height="225"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                <div class="w-full h-full hidden items-center justify-center text-base-content/30 text-xs font-bold flex-col gap-2" style="display:none;">
                    <i class="fas fa-book text-3xl"></i>
                    <span>NO COVER</span>
                </div>` : `
                <div class="w-full h-full flex items-center justify-center text-base-content/30 text-xs font-bold flex-col gap-2">
                    <i class="fas fa-book text-3xl"></i>
                    <span>NO COVER</span>
                </div>`}

            <div class="absolute top-2 left-2 selection-checkbox hidden">
                <input type="checkbox" class="checkbox checkbox-primary checkbox-sm shadow-lg bg-base-100" aria-label="Select ${escapeHtml(book.title || 'book')}" />
            </div>

            <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex items-end justify-center pb-3">
                <div class="flex gap-1">
                    <button class="btn btn-soft btn-primary btn-xs shadow-lg" onclick="event.stopPropagation(); openBookModal(${book.id})" title="Book Details">
                        <i class="fas fa-info"></i>
                    </button>
                    <button class="btn btn-soft btn-accent btn-xs shadow-lg" onclick="event.stopPropagation(); searchForBook(${book.id}, this.dataset.title, this.dataset.author)" data-title="${escapeHtml(book.title || '')}" data-author="${escapeHtml(book.author || '')}" title="Interactive Download">
                        <i class="fas fa-download"></i>
                    </button>
                    <button class="btn btn-soft btn-warning btn-xs shadow-lg" onclick="event.stopPropagation(); autoDownloadBook(${book.id}, this)" title="Auto Download">
                        <i class="fas fa-bolt"></i>
                    </button>
                </div>
            </div>
        </div>

        <div class="mt-1.5">
            <h3 class="text-sm line-clamp-2 leading-tight font-semibold text-base-content">${escapeHtml(book.title || '')}</h3>
            <p class="text-xs text-base-content/60 line-clamp-1">${escapeHtml(book.author || '')}</p>
            ${hasRating ? `<div class="flex items-center gap-1 mt-0.5 text-xs text-base-content/60">
                <i class="fas fa-star text-warning text-[10px]"></i>
                <span>${escapeHtml(rating)}</span>
                ${numRatings ? `<span class="text-base-content/50">${escapeHtml(numRatings)}</span>` : ''}
            </div>` : ''}
        </div>
    `;

    return card;
}

// ==============================================
// Selection Mode
// ==============================================
function initializeSelectionMode() {
    const selectModeBtn = document.getElementById('selectModeBtn');
    
    selectModeBtn?.addEventListener('click', () => {
        toggleSelectionMode();
    });
}

function toggleSelectionMode() {
    LibraryState.isSelectMode = !LibraryState.isSelectMode;
    const grid = document.getElementById('booksGrid');
    const toolbar = document.getElementById('selectionToolbar');
    const selectModeBtn = document.getElementById('selectModeBtn');

    if (LibraryState.isSelectMode) {
        grid.classList.add('selection-mode');
        toolbar.classList.remove('hidden');
        selectModeBtn.innerHTML = '<i class="fas fa-times"></i> Cancel';
        selectModeBtn.classList.add('btn-error');
        selectModeBtn.classList.remove('btn-primary');
    } else {
        grid.classList.remove('selection-mode');
        toolbar.classList.add('hidden');
        selectModeBtn.innerHTML = '<i class="fas fa-check-square"></i> Select';
        selectModeBtn.classList.remove('btn-error');
        selectModeBtn.classList.add('btn-primary');
        clearSelection();
    }
}

function clearSelection() {
    LibraryState.selectedBooks.clear();
    document.querySelectorAll('.book-card').forEach(card => {
        card.classList.remove('selected');
        const checkbox = card.querySelector('.selection-checkbox input');
        if (checkbox) checkbox.checked = false;
    });
    updateSelectionCount();
}

function updateSelectionCount() {
    const count = LibraryState.selectedBooks.size;
    const countElement = document.getElementById('selectedCount');
    if (countElement) {
        countElement.textContent = `${count} book${count !== 1 ? 's' : ''} selected`;
    }
}

// ==============================================
// Book Cards Interaction
// ==============================================
function initializeBookCards() {
    const grid = document.getElementById('booksGrid');
    if (!grid) return;

    grid.addEventListener('click', (e) => {
        const card = e.target.closest('.book-card');
        if (!card) return;
        const bookId = card.dataset.bookId;

        if (LibraryState.isSelectMode) {
            e.preventDefault();
            toggleBookSelection(card, bookId);
        } else {
            openBookModal(bookId);
        }
    });
}

function toggleBookSelection(card, bookId) {
    const checkbox = card.querySelector('.selection-checkbox input');
    
    if (LibraryState.selectedBooks.has(bookId)) {
        LibraryState.selectedBooks.delete(bookId);
        card.classList.remove('selected');
        if (checkbox) checkbox.checked = false;
    } else {
        LibraryState.selectedBooks.add(bookId);
        card.classList.add('selected');
        if (checkbox) checkbox.checked = true;
    }
    
    updateSelectionCount();
}

async function openBookModal(bookId) {
    try {
        const response = await fetch(`/library/book/${bookId}`);
        const data = await response.json();
        
        if (data.success && data.book) {
            displayBookModal(data.book);
        } else {
            showNotification('Failed to load book details', 'error');
        }
    } catch (error) {
        console.error('Error loading book:', error);
        showNotification('Error loading book details', 'error');
    }
}

function displayBookModal(book) {
    const modal = document.getElementById('bookModal');
    const content = document.getElementById('modalContent');
    const e = escapeHtml;

    // Status → badge class + label + hero tint class
    const rawStatus = (book.status || book.ownership_status || '').toLowerCase();
    const statusMap = {
        downloaded:      ['badge-success', 'Downloaded',      'downloaded'],
        downloading:     ['badge-info',    'Downloading',     'downloading'],
        queued:          ['badge-warning', 'Queued',          'queued'],
        owned:           ['badge-success', 'Owned',           'downloaded'],
        wanted:          ['badge-ghost',   'Wanted',          'wanted'],
        audible_library: ['badge-primary', 'Audible Library', 'wanted'],
    };
    const [statusCls, statusText, tintClass] = statusMap[rawStatus] || ['badge-ghost', book.status || book.ownership_status || '', 'wanted'];
    const statusBadge = statusText
        ? `<span class="badge ${statusCls} badge-sm">${e(statusText)}</span>`
        : '';

    // Cover
    const coverUrl = book.cover_image || '';
    const coverHtml = coverUrl
        ? `<img src="${e(coverUrl)}" alt="${e(book.title || '')}" class="w-full h-full object-cover" onerror="this.style.display='none'" />`
        : `<div class="w-full h-full flex items-center justify-center"><i class="fas fa-book text-5xl opacity-20"></i></div>`;

    // Rating
    const ratingValue = parseFloat(book.rating) || 0;
    const ratingHtml = ratingValue > 0 ? `
        <div class="flex items-center gap-1.5 mt-1.5">
            <i class="fas fa-star text-warning text-xs"></i>
            <span class="text-sm font-bold text-white">${ratingValue.toFixed(1)}</span>
            ${book.num_ratings && book.num_ratings > 0 ? `<span class="text-xs text-white/30">(${Number(book.num_ratings).toLocaleString()} ratings)</span>` : ''}
        </div>` : '';

    // Series
    const hasSeries = book.series && book.series !== 'N/A';
    const seriesText = hasSeries
        ? `${e(book.series)}${book.sequence && book.sequence !== 'N/A' && book.sequence !== '' ? ' #' + e(book.sequence) : ''}`
        : '';

    // Conditional series tab + panel
    const seriesTab = hasSeries && book.series_asin
        ? `<button role="tab" class="tab text-sm" onclick="bookModalSwitchTab('series', this)">
               <i class="fas fa-layer-group mr-1.5 opacity-50 text-xs"></i>Series
           </button>`
        : '';
    const seriesPanel = hasSeries && book.series_asin
        ? `<div id="bookTab-series" class="book-tab-panel tab-scroll overflow-y-auto flex-1 pt-3 space-y-3"
               data-series-asin="${e(book.series_asin)}" data-loaded="false">
               <div class="flex justify-center py-8"><span class="loading loading-spinner loading-md"></span></div>
           </div>`
        : '';

    // Synopsis
    const synopsisHtml = book.summary
        ? `<div>
            <h3 class="text-[10px] font-bold uppercase tracking-widest text-base-content/35 mb-2">Synopsis</h3>
            <div class="text-sm text-base-content/70 leading-relaxed space-y-3">${
                book.summary
                    .split(/<\/?\s*p\s*>/i)
                    .map(s => s.replace(/<[^>]*>/g, '').trim())
                    .filter(s => s.length > 0)
                    .map(s => `<p>${e(s)}</p>`)
                    .join('')
            }</div>
           </div>`
        : `<p class="text-sm text-base-content/40">No synopsis available.</p>`;

    // Files tab
    const filesHtml = book.file_location
        ? `<div class="bg-base-200 border border-base-300 overflow-hidden" style="border-radius:0.25rem;">
               <div class="flex items-start gap-3 p-4">
                   <div class="w-8 h-8 bg-success/10 flex items-center justify-center flex-shrink-0 mt-0.5" style="border-radius:0.25rem;">
                       <i class="fas fa-file-audio text-success text-sm"></i>
                   </div>
                   <div class="min-w-0">
                       <p class="text-[10px] text-base-content/40 uppercase tracking-wider mb-0.5">File Location</p>
                       <p class="text-xs font-mono text-base-content/65 break-all leading-relaxed">${e(book.file_location)}</p>
                   </div>
               </div>
           </div>`
        : `<p class="text-sm text-base-content/40">No file location recorded.</p>`;

    // Fact-card sidebar rows (only show rows with data)
    const factRows = [
        book.narrator && book.narrator !== 'Unknown'
            ? `<div class="fact-card"><dt><i class="fas fa-microphone mr-1.5 opacity-50"></i>Narrator</dt><dd>${e(book.narrator)}</dd></div>` : '',
        book.runtime
            ? `<div class="fact-card"><dt><i class="fas fa-clock mr-1.5 opacity-50"></i>Runtime</dt><dd>${e(book.runtime)}</dd></div>` : '',
        hasSeries
            ? `<div class="fact-card"><dt><i class="fas fa-layer-group mr-1.5 opacity-50"></i>Series</dt><dd>${e(book.series)}</dd></div>` : '',
        hasSeries && book.sequence && book.sequence !== 'N/A' && book.sequence !== ''
            ? `<div class="fact-card"><dt><i class="fas fa-hashtag mr-1.5 opacity-50"></i>Book</dt><dd>#${e(book.sequence)}</dd></div>` : '',
        book.release_date && book.release_date !== 'Unknown'
            ? `<div class="fact-card"><dt><i class="fas fa-calendar mr-1.5 opacity-50"></i>Released</dt><dd>${e(book.release_date)}</dd></div>` : '',
        book.publisher && book.publisher !== 'Unknown'
            ? `<div class="fact-card"><dt><i class="fas fa-building mr-1.5 opacity-50"></i>Publisher</dt><dd>${e(book.publisher)}</dd></div>` : '',
        book.language
            ? `<div class="fact-card"><dt><i class="fas fa-globe mr-1.5 opacity-50"></i>Language</dt><dd>${e(book.language)}</dd></div>` : '',
        book.asin
            ? `<div class="fact-card"><dt><i class="fas fa-fingerprint mr-1.5 opacity-50"></i>ASIN</dt><dd class="font-mono text-[0.65rem]">${e(book.asin)}</dd></div>` : '',
    ].filter(Boolean).join('');

    content.innerHTML = `
        <!-- ════ HERO ════ -->
        <div class="relative overflow-visible flex-shrink-0" style="min-height:188px">
            <div class="hero-blur" id="bookModalHeroBlur"></div>
            <div class="hero-tint ${tintClass}"></div>
            <div class="absolute inset-x-0 bottom-0 h-20 pointer-events-none"
                 style="background:linear-gradient(to bottom, transparent 0%, var(--color-base-100) 100%)"></div>
            <button class="btn btn-circle btn-ghost btn-sm absolute top-3 right-3 z-30 text-white/60 hover:text-white hover:bg-white/10"
                    onclick="document.getElementById('bookModal').close()">
                <i class="fas fa-xmark"></i>
            </button>
            <div class="relative z-10 flex items-end gap-5 px-6 pt-6 pb-0">
                <div class="cover-float shadow-2xl ring-2 ring-white/10 overflow-hidden" style="width:200px;height:200px;border-radius:0.25rem;">
                    ${coverHtml}
                </div>
                <div class="flex-1 min-w-0 pb-3">
                    <div class="flex flex-wrap items-center gap-1.5 mb-1.5">${statusBadge}</div>
                    <h1 class="text-2xl sm:text-[1.65rem] font-bold text-white leading-tight">${e(book.title || '')}</h1>
                    <p class="text-sm text-white/50 mt-0.5">
                        by <a href="/authors/${encodeURIComponent(book.author || '')}" class="text-white/80 hover:text-white hover:underline font-medium">${e(book.author || '')}</a>
                        ${hasSeries ? `<span class="opacity-30 mx-1">&middot;</span><span class="text-white/40">${seriesText}</span>` : ''}
                    </p>
                    ${ratingHtml}
                </div>
                <div class="flex items-center gap-1.5 pb-4 flex-shrink-0">
                    <button class="btn btn-primary btn-sm gap-1.5" onclick="autoDownloadBook(${book.id}, this)">
                        <i class="fas fa-bolt text-xs"></i> Download
                    </button>
                    <button class="btn btn-ghost btn-sm text-white/60 hover:text-white hover:bg-white/10"
                            title="Interactive Search"
                            data-title="${e(book.title || '')}" data-author="${e(book.author || '')}"
                            onclick="searchForBook(${book.id}, this.dataset.title, this.dataset.author)">
                        <i class="fas fa-search text-xs"></i>
                    </button>
                    <button class="btn btn-ghost btn-sm text-white/60 hover:text-white hover:bg-white/10"
                            title="Refresh Metadata"
                            onclick="updateBookMetadata(${book.id})">
                        <i class="fas fa-rotate text-xs"></i>
                    </button>
                    <div class="dropdown dropdown-end">
                        <button tabindex="0" class="btn btn-ghost btn-sm btn-circle text-white/60 hover:text-white hover:bg-white/10">
                            <i class="fas fa-ellipsis-v text-xs"></i>
                        </button>
                        <ul tabindex="0" class="dropdown-content menu menu-sm bg-base-200 shadow-xl w-44 mt-1 z-[100] border border-base-300 p-1" style="border-radius:0.25rem;">
                            <li><a class="text-error text-xs" onclick="deleteBook(${book.id})"><i class="fas fa-trash mr-2"></i>Delete Book</a></li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>

        <!-- ════ BODY ════ -->
        <div class="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-[1fr_260px] bg-base-100 overflow-hidden"
             style="padding-top:108px">

            <!-- Left: Tabs -->
            <div class="flex flex-col min-h-0 border-r border-base-200 px-5 pt-0 pb-4">
                <div role="tablist" class="tabs tabs-border flex-shrink-0 -mx-1 mb-1">
                    <button role="tab" class="tab tab-active text-sm" onclick="bookModalSwitchTab('overview', this)">
                        <i class="fas fa-align-left mr-1.5 opacity-50 text-xs"></i>Overview
                    </button>
                    <button role="tab" class="tab text-sm" onclick="bookModalSwitchTab('files', this)">
                        <i class="fas fa-folder mr-1.5 opacity-50 text-xs"></i>Files
                    </button>
                    ${seriesTab}
                    <button role="tab" class="tab text-sm" onclick="bookModalSwitchTab('history', this)">
                        <i class="fas fa-clock-rotate-left mr-1.5 opacity-50 text-xs"></i>History
                    </button>
                </div>

                <div id="bookTab-overview" class="book-tab-panel book-tab-active tab-scroll overflow-y-auto flex-1 pt-3 space-y-4">
                    ${synopsisHtml}
                </div>

                <div id="bookTab-files" class="book-tab-panel tab-scroll overflow-y-auto flex-1 pt-3 space-y-3">
                    ${filesHtml}
                </div>

                ${seriesPanel}

                <div id="bookTab-history" class="book-tab-panel tab-scroll overflow-y-auto flex-1 pt-4"
                     data-book-id="${book.id}" data-loaded="false">
                    <div class="flex justify-center py-8"><span class="loading loading-spinner loading-md"></span></div>
                </div>
            </div>

            <!-- Right: Details Sidebar -->
            <div class="flex-shrink-0 bg-base-100 px-4 pt-3 pb-4 overflow-y-auto tab-scroll">
                <p class="text-[10px] font-bold uppercase tracking-widest text-base-content/30 mb-3">Details</p>
                <div class="divide-y divide-base-200">
                    ${factRows}
                </div>
            </div>

        </div>
    `;

    // Set hero blur background via JS (avoids CSS injection risk)
    if (coverUrl) {
        const heroBlur = document.getElementById('bookModalHeroBlur');
        if (heroBlur) heroBlur.style.backgroundImage = `url("${coverUrl.replace(/"/g, '%22')}")`;
    }

    modal.showModal();
}

function bookModalSwitchTab(name, btn) {
    document.querySelectorAll('#modalContent .book-tab-panel')
        .forEach(p => p.classList.remove('book-tab-active'));
    document.querySelectorAll('#modalContent [role="tab"]')
        .forEach(t => t.classList.remove('tab-active'));
    document.getElementById('bookTab-' + name).classList.add('book-tab-active');
    btn.classList.add('tab-active');

    if (name === 'series') {
        const panel = document.getElementById('bookTab-series');
        if (panel && panel.dataset.loaded === 'false') {
            bookModalLoadSeriesTab(panel, panel.dataset.seriesAsin);
        }
    }
    if (name === 'history') {
        const panel = document.getElementById('bookTab-history');
        if (panel && panel.dataset.loaded === 'false') {
            bookModalLoadHistoryTab(panel, panel.dataset.bookId);
        }
    }
}

async function bookModalLoadSeriesTab(panel, seriesAsin) {
    const e = escapeHtml;
    try {
        const res = await fetch(`/series/api/${encodeURIComponent(seriesAsin)}/books`);
        const data = await res.json();
        panel.dataset.loaded = 'true';

        if (!data.success) {
            panel.innerHTML = `<p class="text-sm text-error">Failed to load series data.</p>`;
            return;
        }

        const books = Array.isArray(data.books) ? data.books : [];
        const stats = data.statistics || {};
        const importAuthor = data.primary_author || '';

        const rows = books.length ? books.map(book => {
            const isOwned = book.in_library || ['in_library','owned'].includes((book.library_status||'').toLowerCase());
            const isPending = ['wanted','queued','pending'].includes((book.library_status||'').toLowerCase());
            let badge;
            if (isOwned)        badge = '<span class="badge badge-success badge-xs">In Library</span>';
            else if (isPending) badge = '<span class="badge badge-warning badge-xs">Wanted</span>';
            else                badge = '<span class="badge badge-ghost badge-xs">Not Owned</span>';

            const titleCell = isOwned && book.asin
                ? `<button class="text-sm text-left hover:underline text-primary" onclick="openBookModal('${e(book.asin)}')">${e(book.title || 'Unknown')}</button>`
                : `<span class="text-sm">${e(book.title || 'Unknown')}</span>`;

            const bookAuthor = book.author || importAuthor;
            const actionCell = !isOwned && book.asin
                ? `<button class="btn btn-xs btn-soft btn-primary js-series-tab-import"
                       data-asin="${e(book.asin)}" data-author="${e(bookAuthor)}" data-title="${e(book.title || '')}"
                       data-series-asin="${e(seriesAsin)}">
                       <i class="fas fa-download"></i> ${isPending ? 'Queue' : 'Add'}
                   </button>`
                : '';

            return `<tr class="hover">
                <td class="text-xs font-semibold w-10">${e(String(book.sequence || '—'))}</td>
                <td>${titleCell}</td>
                <td>${badge}</td>
                <td class="text-right">
                    ${(book.rating && book.rating !== 'N/A')
                        ? `<span class="text-xs">${e(String(book.rating))} <i class="fas fa-star text-warning text-[10px]"></i></span>`
                        : '<span class="text-xs opacity-40">—</span>'
                    }
                </td>
                <td class="text-right">${actionCell}</td>
            </tr>`;
        }).join('') : `<tr><td colspan="5" class="text-center text-sm text-base-content/40 py-4">No books found.</td></tr>`;

        panel.innerHTML = `
            <div class="space-y-3">
                <div class="flex flex-wrap gap-2 items-center">
                    ${stats.total_books  ? `<span class="badge badge-ghost badge-sm">${stats.total_books} Books</span>` : ''}
                    ${stats.owned_books  ? `<span class="badge badge-success badge-sm">${stats.owned_books} Owned</span>` : ''}
                    ${stats.missing_books > 0 ? `<span class="badge badge-warning badge-sm">${stats.missing_books} Missing</span>` : ''}
                </div>
                <div class="border border-base-300 rounded overflow-hidden">
                    <table class="table table-sm w-full">
                        <thead class="bg-base-200 text-xs uppercase tracking-wide text-base-content/50">
                            <tr><th>#</th><th>Title</th><th>Status</th><th class="text-right">Rating</th><th></th></tr>
                        </thead>
                        <tbody class="text-sm">${rows}</tbody>
                    </table>
                </div>
            </div>`;

        // Wire up import buttons
        panel.querySelectorAll('.js-series-tab-import').forEach(btn => {
            btn.addEventListener('click', async () => {
                const asin = btn.dataset.asin;
                const author = btn.dataset.author;
                const thisSeries = btn.dataset.seriesAsin;
                btn.disabled = true;
                btn.innerHTML = '<span class="loading loading-spinner loading-xs"></span>';
                try {
                    const r = await fetch('/authors/api/import-book', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ author_name: author, asin })
                    });
                    const result = await r.json();
                    if (result.success) {
                        showNotification(result.message || 'Import queued.', 'success');
                        // Reload series tab
                        panel.dataset.loaded = 'false';
                        bookModalLoadSeriesTab(panel, thisSeries);
                    } else {
                        showNotification(result.error || 'Import failed.', 'error');
                        btn.disabled = false;
                        btn.innerHTML = '<i class="fas fa-download"></i> Add';
                    }
                } catch (err) {
                    showNotification('Import request failed.', 'error');
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-download"></i> Add';
                }
            });
        });

    } catch (err) {
        panel.dataset.loaded = 'true';
        panel.innerHTML = `<p class="text-sm text-error">Error loading series: ${e(err.message)}</p>`;
    }
}

async function bookModalLoadHistoryTab(panel, bookId) {
    const e = escapeHtml;
    try {
        const res = await fetch(`/library/book/${encodeURIComponent(bookId)}/history`);
        const data = await res.json();
        panel.dataset.loaded = 'true';

        if (!data.success || !data.events || data.events.length === 0) {
            panel.innerHTML = `<p class="text-sm text-base-content/40">No history recorded for this book.</p>`;
            return;
        }

        const typeMap = {
            success: 'status-success',
            info:    'status-info',
            warning: 'status-warning',
            error:   'status-error',
        };

        const rows = data.events.map((ev, i) => {
            const dot = typeMap[ev.type] || 'status-info';
            const isLast = i === data.events.length - 1;
            const tsDisplay = ev.ts ? new Date(ev.ts).toLocaleString(undefined, {
                month: 'short', day: 'numeric', year: 'numeric',
                hour: 'numeric', minute: '2-digit'
            }) : '';
            return `
            <div class="flex items-start gap-3 py-2.5 ${isLast ? '' : 'border-b border-base-300/50'}">
                <span class="status ${dot} status-xs mt-1.5 flex-shrink-0"></span>
                <div class="min-w-0 flex-1">
                    <p class="text-sm">${e(ev.label)}</p>
                    ${tsDisplay ? `<p class="text-xs text-base-content/40">${e(tsDisplay)}</p>` : ''}
                </div>
            </div>`;
        }).join('');

        panel.innerHTML = `<div class="space-y-0">${rows}</div>`;
    } catch (err) {
        panel.dataset.loaded = 'true';
        panel.innerHTML = `<p class="text-sm text-error">Error loading history: ${e(err.message)}</p>`;
    }
}

function toggleBookSynopsis(btn) {
    const p = document.getElementById('bookModalSynopsis');
    const nowClamped = p.classList.toggle('line-clamp-5');
    btn.textContent = nowClamped ? 'Show more' : 'Show less';
}

function formatSourceLabel(book) {
    const source = (book.source_label || book.source || '').toLowerCase();
    const status = (book.ownership_status || '').toLowerCase();

    if (source === 'audiobookshelf' || source === 'imported_abs' || source === 'abs_import') {
        return 'AudioBookShelf Import';
    }
    if (source === 'audible' && status === 'audible_library') {
        return 'Audible';
    }
    if (source === 'audible_catalog') {
        return 'Audible Catalog';
    }
    if (source === 'manual_import' || source === 'manual' || source === 'manual_override') {
        return 'Manual Import';
    }
    if (source === 'download_manager') {
        return 'Download Manager';
    }
    if (source === 'indexer') {
        return 'Indexer';
    }
    return source ? source.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : 'Unknown';
}

// ==============================================
// Bulk Actions
// ==============================================
function initializeBulkActions() {
    const selectAllBtn = document.getElementById('selectAllBtn');
    const clearSelectionBtn = document.getElementById('clearSelectionBtn');
    const updateMetadataBtn = document.getElementById('updateMetadataBtn');
    const changeStatusBtn = document.getElementById('changeStatusBtn');
    const deleteSelectedBtn = document.getElementById('deleteSelectedBtn');

    selectAllBtn?.addEventListener('click', selectAllBooks);
    clearSelectionBtn?.addEventListener('click', clearSelection);
    updateMetadataBtn?.addEventListener('click', updateSelectedMetadata);
    changeStatusBtn?.addEventListener('click', changeSelectedStatus);
    deleteSelectedBtn?.addEventListener('click', deleteSelectedBooks);
}

function selectAllBooks() {
    const visibleCards = document.querySelectorAll('.book-card:not([style*="display: none"])');
    
    visibleCards.forEach(card => {
        const bookId = card.dataset.bookId;
        LibraryState.selectedBooks.add(bookId);
        card.classList.add('selected');
        const checkbox = card.querySelector('.selection-checkbox input');
        if (checkbox) checkbox.checked = true;
    });
    
    updateSelectionCount();
    showNotification(`Selected ${LibraryState.selectedBooks.size} books`, 'success');
}

async function updateSelectedMetadata() {
    if (LibraryState.selectedBooks.size === 0) {
        showNotification('No books selected', 'warning');
        return;
    }

    const bookIds = Array.from(LibraryState.selectedBooks);
    showProgressModal('Updating Metadata', bookIds.length);

    let processed = 0;
    let successful = 0;
    let failed = 0;
    const errors = [];

    try {
        for (const bookId of bookIds) {
            updateProgressModal(processed, bookIds.length, successful, failed, errors);

            try {
                const response = await fetch(`/library/book/${bookId}/update-metadata`, {
                    method: 'POST'
                });

                const data = await response.json();

                if (data.success) {
                    successful += 1;
                } else {
                    failed += 1;
                    errors.push({ book_id: bookId, error: data.error || 'Unknown error' });
                    if (errors.length > 10) {
                        errors.splice(0, errors.length - 10);
                    }
                }
            } catch (error) {
                failed += 1;
                errors.push({ book_id: bookId, error: error.message || 'Request failed' });
                if (errors.length > 10) {
                    errors.splice(0, errors.length - 10);
                }
            }

            processed += 1;
            updateProgressModal(processed, bookIds.length, successful, failed, errors);

            // Small delay to avoid overwhelming the backend and give UI time to render
            await sleep(250);
        }

        if (successful > 0 && failed === 0) {
            showNotification(`Updated ${successful} books successfully`, 'success');
            setTimeout(() => location.reload(), 1500);
        } else if (successful > 0) {
            showNotification(`Updated ${successful} books; ${failed} failed`, 'warning');
        } else {
            showNotification('Failed to update metadata', 'error');
        }
    } catch (error) {
        console.error('Error updating metadata:', error);
        showNotification('Failed to update metadata', 'error');
    } finally {
        updateProgressModal(processed, bookIds.length, successful, failed, errors);
        document.getElementById('progressCloseBtn')?.classList.remove('hidden');
    }
}

async function changeSelectedStatus() {
    if (LibraryState.selectedBooks.size === 0) {
        showNotification('No books selected', 'warning');
        return;
    }

    // This would open a modal to select new status
    showNotification('Status change feature coming soon', 'info');
}

async function deleteSelectedBooks() {
    if (LibraryState.selectedBooks.size === 0) {
        showNotification('No books selected', 'warning');
        return;
    }

    if (!confirm(`Delete ${LibraryState.selectedBooks.size} selected books?`)) {
        return;
    }

    const bookIds = Array.from(LibraryState.selectedBooks).map(id => Number(id));
    showProgressModal('Deleting Books', bookIds.length);

    try {
        const response = await fetch('/library/books/bulk-delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ book_ids: bookIds })
        });

        const data = await response.json();

        const deletedCount = data.deleted_ids ? data.deleted_ids.length : 0;
        const failedCount = data.failed ? data.failed.length : 0;

        updateProgressModal(bookIds.length, bookIds.length, deletedCount, failedCount, data.failed || []);
        document.getElementById('progressCloseBtn')?.classList.remove('hidden');

        // Remove deleted cards from UI
        (data.deleted_ids || []).forEach(id => {
            const card = document.querySelector(`.book-card[data-book-id="${id}"]`);
            if (card) card.remove();
            LibraryState.selectedBooks.delete(String(id));
        });

        updateSelectionCount();

        if (deletedCount > 0 && failedCount === 0) {
            showNotification(`Deleted ${deletedCount} book(s)`, 'success');
        } else if (deletedCount > 0) {
            showNotification(`Deleted ${deletedCount} book(s); ${failedCount} failed`, 'warning');
        } else {
            showNotification('Failed to delete selected books', 'error');
        }

        // Reload to refresh state if anything changed
        if (deletedCount > 0) {
            setTimeout(() => location.reload(), 800);
        }

    } catch (error) {
        console.error('Bulk delete failed:', error);
        showNotification('Failed to delete selected books', 'error');
        document.getElementById('progressCloseBtn')?.classList.remove('hidden');
    }
}

// ==============================================
// Single Book Actions
// ==============================================
async function updateBookMetadata(bookId) {
    try {
        const response = await fetch(`/library/book/${bookId}/update-metadata`, {
            method: 'POST'
        });

        const data = await response.json();
        
        if (data.success) {
            showNotification('Metadata updated successfully', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification(data.error || 'Update failed', 'error');
        }
    } catch (error) {
        console.error('Error updating metadata:', error);
        showNotification('Failed to update metadata', 'error');
    }
}

async function searchForBook(bookId, bookTitle = '', bookAuthor = '') {
    const modal = document.getElementById('searchModal');
    const loading = document.getElementById('searchLoading');
    const results = document.getElementById('searchResults');
    const noResults = document.getElementById('searchNoResults');
    const error = document.getElementById('searchError');
    
    // Reset modal state
    loading.classList.remove('hidden');
    results.classList.add('hidden');
    noResults.classList.add('hidden');
    error.classList.add('hidden');

    // Show known title/author immediately so the header is correct during loading
    document.getElementById('searchBookTitle').textContent = bookTitle;
    document.getElementById('searchBookAuthor').textContent = bookAuthor;
    
    // Show modal
    modal.showModal();
    
    try {
        const response = await fetch(`/api/search/manual/book/${bookId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || 'Search failed');
        }
        
        // Update book info
        if (data.book_info) {
            document.getElementById('searchBookTitle').textContent = data.book_info.title;
            document.getElementById('searchBookAuthor').textContent = data.book_info.author || '';
        }
        
        loading.classList.add('hidden');
        
        // Show results
        if (data.results && data.results.length > 0) {
            console.log('Search results received:', data.results.length, 'results');
            console.log('First result:', data.results[0]);
            displaySearchResults(data.results, bookId);
            results.classList.remove('hidden');
        } else {
            noResults.classList.remove('hidden');
        }
        
    } catch (err) {
        console.error('Search error:', err);
        loading.classList.add('hidden');
        error.classList.remove('hidden');
        document.getElementById('searchErrorMessage').textContent = err.message;
    }
}

async function autoDownloadBook(bookId, triggerButton = null) {
    if (!bookId) {
        showNotification('Invalid book selected for auto download.', 'error');
        return;
    }

    const numericId = Number.parseInt(bookId, 10);
    if (Number.isNaN(numericId) || numericId <= 0) {
        showNotification('Invalid book identifier provided.', 'error');
        return;
    }

    if (triggerButton?.dataset.loading === 'true') {
        return;
    }

    const button = triggerButton || null;
    const originalHtml = button ? button.innerHTML : '';

    if (button) {
        button.dataset.loading = 'true';
        button.disabled = true;
        button.innerHTML = '<span class="loading loading-spinner loading-xs"></span>';
    }

    try {
        const response = await fetch(`/api/search/automatic/force/${numericId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (!response.ok || data.success === false || data.error) {
            throw new Error(data.error || data.message || 'Automatic search failed');
        }

        showNotification(data.message || 'Automatic search queued', 'success');

        if (button) {
            button.innerHTML = '<i class="fas fa-check"></i>';
            button.classList.remove('btn-warning');
            button.classList.add('btn-success');
            button.title = 'Queued';
        }
    } catch (error) {
        console.error('Auto download error:', error);
        showNotification(error.message || 'Automatic search failed', 'error');

        if (button) {
            button.innerHTML = originalHtml || '<i class="fas fa-bolt"></i>';
            button.disabled = false;
        }
    } finally {
        if (button) {
            delete button.dataset.loading;
            if (!button.classList.contains('btn-success')) {
                button.disabled = false;
            }
        }
    }
}

function displaySearchResults(results, bookId) {
    const tbody = document.getElementById('searchResultsBody');
    const count = document.getElementById('resultsCount');
    
    console.log('displaySearchResults called with', results.length, 'results');
    
    count.textContent = results.length;
    tbody.innerHTML = '';
    
    results.forEach((result, index) => {
        console.log(`Result ${index}:`, result);
        
    const row = document.createElement('tr');

    let downloadType = (result.download_type || result.source || '').toLowerCase();
    let isAudibleDirect = downloadType.includes('audible');

        // Extract quality and confidence from quality_assessment object or top-level
        let quality = 0;
        let confidence = 0;
        
        if (result.quality_assessment) {
            console.log('Has quality_assessment:', result.quality_assessment);
            // Quality is on 0-10 scale, convert to percentage
            quality = (result.quality_assessment.total_score || 0) * 10;
            confidence = result.quality_assessment.confidence || 0;
        } else {
            console.log('No quality_assessment, using fallback');
            // Fallback to top-level fields
            quality = result.quality_score || 0;
            confidence = result.confidence || 0;
        }
        
        console.log(`Extracted values - quality: ${quality}, confidence: ${confidence}`);
        
        // Parse title for cleaner display
        const fullTitle = result.title || 'Unknown';
        let displayTitle = fullTitle;
        let displayAuthor = getAuthorLabel(result);
        let bitrate = '';
        
        // Extract author from "Title - Author" pattern if metadata missing
        if (!displayAuthor) {
            const dashIndex = fullTitle.indexOf(' - ');
            if (dashIndex > 0) {
                displayTitle = fullTitle.substring(0, dashIndex).trim();
                const remainder = fullTitle.substring(dashIndex + 3);
                displayAuthor = remainder.replace(/\[.*?\]/g, '').trim();
            }
        }
        
        // Extract bitrate from title (e.g., "128 kbps")
        const bitrateMatch = fullTitle.match(/(\d+)\s*kbps/i);
        if (bitrateMatch) {
            bitrate = `${bitrateMatch[1]} kbps`;
        }
        
        // Clean title
        displayTitle = displayTitle.replace(/\[.*?\]/g, '').trim();
        
        // Extract format from title or use provided format
        const format = result.format || detectFormat(fullTitle);

        // Indexer flags
        const indexerLabelRaw = (result.indexer || result.source || '').toString();
        const indexerLower = indexerLabelRaw.toLowerCase();
        const isAudiobookBay = indexerLower.includes('audiobookbay');
        
        // Get peers info
        const seeders = result.seeders || 0;
        const peers = result.peers || 0;
        
        // Determine badge classes based on scores (both are 0-100 scale now)
        const qualityClass = quality >= 80 ? 'badge-success' : quality >= 60 ? 'badge-warning' : 'badge-error';
        const confidenceClass = confidence >= 80 ? 'badge-success' : confidence >= 60 ? 'badge-warning' : 'badge-error';
        
        // Use size_bytes for formatting, fallback to size string
        const sizeBytes = result.size_bytes || 0;
        const sizeFormatted = sizeBytes > 0 ? formatSize(sizeBytes) : (result.size || 'Unknown');
        
        // Create title cell with author if extracted
        const titleCell = displayAuthor 
            ? `<div class="max-w-xs">
                 <div class="truncate font-semibold" title="${escapeHtml(fullTitle)}">${escapeHtml(displayTitle)}</div>
                 <div class="text-xs text-base-content/60 truncate">${escapeHtml(displayAuthor)}</div>
               </div>`
            : `<div class="max-w-xs truncate" title="${escapeHtml(fullTitle)}">${escapeHtml(displayTitle)}</div>`;
        
        row.innerHTML = `
            <td>${titleCell}</td>
            <td>
                <span class="badge badge-sm ${isAudibleDirect ? 'badge-primary' : 'badge-outline'}">
                    ${isAudibleDirect ? 'Audible' : format}
                </span>
                ${bitrate ? `<div class="text-xs text-base-content/60 mt-1">${bitrate}</div>` : ''}
            </td>
            <td>${isAudibleDirect ? '—' : sizeFormatted}</td>
            <td>
                <span class="badge ${qualityClass} badge-sm">
                    ${quality > 0 ? quality.toFixed(0) + '%' : isAudibleDirect ? '100%' : 'N/A'}
                </span>
            </td>
            <td>
                <span class="badge ${confidenceClass} badge-sm">
                    ${confidence > 0 ? confidence.toFixed(0) + '%' : isAudibleDirect ? '100%' : 'N/A'}
                </span>
            </td>
            <td>
                <div class="flex items-center gap-2 text-xs">
                    ${isAudibleDirect ? '<span class="badge badge-success badge-sm">owned</span>' : `
                    <span class="badge ${isAudiobookBay ? 'badge-success' : seeders > 10 ? 'badge-success' : seeders > 0 ? 'badge-warning' : 'badge-error'} badge-sm">
                        ${seeders} <i class="fas fa-arrow-up text-[10px] ml-1"></i>
                    </span>
                    <span class="badge ${isAudiobookBay ? 'badge-success' : 'badge-ghost'} badge-sm">
                        ${peers} <i class="fas fa-arrow-down text-[10px] ml-1"></i>
                    </span>`}
                </div>
            </td>
            <td class="text-xs">${escapeHtml(result.indexer || result.source || (isAudibleDirect ? 'Audible Library' : 'Unknown'))}</td>
            <td>
                <button type="button" class="btn ${isAudibleDirect ? 'btn-primary' : 'btn-soft btn-primary'} btn-xs manual-download-btn">
                    <i class="fas fa-download"></i> ${isAudibleDirect ? 'Download from Audible' : 'Download'}
                </button>
            </td>
        `;
        
        const downloadBtn = row.querySelector('.manual-download-btn');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', (event) => {
                event.preventDefault();
                event.stopPropagation();
                downloadResult(bookId, result, downloadBtn, row);
            });
        }

        tbody.appendChild(row);
    });
}

// Helper function to detect format from title
function detectFormat(title) {
    if (!title) return 'M4B';
    const formatMatch = title.match(/\[(M4B|MP3|FLAC|AAC|OGG|WMA|M4A)\]/i);
    return formatMatch ? formatMatch[1].toUpperCase() : 'M4B';
}

function getAuthorLabel(result) {
    if (!result || typeof result !== 'object') {
        return '';
    }

    const candidateKeys = [
        'author',
        'authors',
        'author_name',
        'primary_author',
        'book_author',
    ];

    for (const key of candidateKeys) {
        const value = result[key];
        if (!value) {
            continue;
        }

        if (Array.isArray(value)) {
            const joined = value.filter(Boolean).join(', ').trim();
            if (joined) {
                return joined;
            }
        } else if (typeof value === 'object') {
            const joined = Object.values(value)
                .map(part => (typeof part === 'string' ? part.trim() : ''))
                .filter(Boolean)
                .join(', ');
            if (joined) {
                return joined;
            }
        } else if (typeof value === 'string') {
            const cleaned = value.trim();
            if (cleaned && cleaned.toLowerCase() !== 'unknown author') {
                return cleaned;
            }
        }
    }

    return '';
}

function formatSize(bytes) {
    if (!bytes || bytes === 0) return 'Unknown';
    
    const gb = bytes / (1024 * 1024 * 1024);
    const mb = bytes / (1024 * 1024);
    
    if (gb >= 1) {
        return `${gb.toFixed(2)} GB`;
    } else if (mb >= 1) {
        return `${mb.toFixed(0)} MB`;
    } else {
        return `${bytes} B`;
    }
}

function escapeHtml(text) {
    if (typeof text !== 'string') return text;
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function downloadResult(bookId, result, triggerButton = null, tableRow = null) {
    if (triggerButton?.dataset.loading === 'true') {
        return;
    }

    let originalButtonHtml = null;
    if (triggerButton) {
        originalButtonHtml = triggerButton.innerHTML;
        triggerButton.dataset.loading = 'true';
        triggerButton.disabled = true;
        triggerButton.innerHTML = '<span class="loading loading-spinner loading-xs"></span>';
    }

    try {
        const response = await fetch('/api/search/manual/download', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                book_id: bookId,
                result: result
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (triggerButton) {
                triggerButton.innerHTML = '<i class="fas fa-check"></i> Enqueued';
                triggerButton.classList.remove('btn-primary', 'btn-error', 'btn-warning');
                triggerButton.classList.add('btn-soft', 'btn-success');
            }
            if (tableRow) {
                tableRow.classList.add('opacity-70');
            }
            const jobId = data.job_id ? ` Job: ${data.job_id}` : '';
            showNotification(`Download enqueued successfully.${jobId ? jobId : ''} Check the Downloads page.`, 'success');
            const modal = document.getElementById('searchModal');
            modal?.close();
        } else {
            // Handle duplicate download case
            if (data.duplicate || response.status === 409) {
                if (triggerButton) {
                    triggerButton.innerHTML = '<i class="fas fa-inbox"></i> In Queue';
                    triggerButton.classList.remove('btn-primary', 'btn-error', 'btn-warning');
                    triggerButton.classList.add('btn-soft', 'btn-warning');
                }
                if (tableRow) {
                    tableRow.classList.add('opacity-70');
                }
                showNotification('This book is already in the download queue. Check the Downloads page.', 'warning');
                const modal = document.getElementById('searchModal');
                modal?.close();
            } else {
                showNotification(data.error || 'Download failed', 'error');
                if (triggerButton) {
                    triggerButton.innerHTML = originalButtonHtml;
                    triggerButton.disabled = false;
                }
            }
        }
    } catch (err) {
        console.error('Download error:', err);
        showNotification('Failed to start download', 'error');
        if (triggerButton) {
            triggerButton.innerHTML = originalButtonHtml;
            triggerButton.disabled = false;
        }
    }
    if (triggerButton) {
        delete triggerButton.dataset.loading;
    }
}

async function deleteBook(bookId) {
    if (!confirm('Delete this book?')) {
        return;
    }

    try {
        const response = await fetch(`/library/book/${bookId}`, {
            method: 'DELETE'
        });

        const data = await response.json();
        
        if (data.success) {
            showNotification('Book deleted successfully', 'success');
            setTimeout(() => location.reload(), 1000);
        } else {
            showNotification(data.error || 'Delete failed', 'error');
        }
    } catch (error) {
        console.error('Error deleting book:', error);
        showNotification('Failed to delete book', 'error');
    }
}

// ==============================================
// Progress Modal
// ==============================================
function showProgressModal(title, total) {
    const modal = document.getElementById('progressModal');
    document.getElementById('progressTitle').textContent = title;
    document.getElementById('progressDetails').textContent = 'Starting operation...';
    document.getElementById('progressBar').value = 0;
    document.getElementById('progressCount').textContent = `0 / ${total}`;
    document.getElementById('progressPercent').textContent = '0%';
    document.getElementById('progressSuccess').textContent = '0';
    document.getElementById('progressFailed').textContent = '0';
    document.getElementById('errorsList').classList.add('hidden');
    document.getElementById('progressCloseBtn').classList.add('hidden');
    
    modal.showModal();
}

function updateProgressModal(current, total, success, failed, errors) {
    const progressBar = document.getElementById('progressBar');
    const progressCount = document.getElementById('progressCount');
    const progressPercent = document.getElementById('progressPercent');
    const progressSuccess = document.getElementById('progressSuccess');
    const progressFailed = document.getElementById('progressFailed');
    const progressDetails = document.getElementById('progressDetails');

    if (!progressBar || !progressCount || !progressPercent || !progressSuccess || !progressFailed || !progressDetails) {
        return;
    }

    const safeTotal = total || 1;
    const percent = Math.round((current / safeTotal) * 100);
    const nextIndex = Math.min(current + 1, safeTotal);
    
    progressBar.value = percent;
    progressCount.textContent = `${current} / ${total}`;
    progressPercent.textContent = `${percent}%`;
    progressSuccess.textContent = success;
    progressFailed.textContent = failed;
    progressDetails.textContent = 
        current === total ? 'Operation complete' : `Processing book ${nextIndex} of ${total}...`;
    
    if (errors && errors.length > 0) {
        const errorsList = document.getElementById('errorsList');
        const errorsContent = document.getElementById('errorsContent');
        if (errorsList && errorsContent) {
            errorsContent.innerHTML = errors.map(err => 
                `<div class="text-error"><strong>${err.title || err.book_id}</strong>: ${err.error}</div>`
            ).join('');

            errorsList.classList.remove('hidden');
        }
    } else {
        const errorsList = document.getElementById('errorsList');
        if (errorsList) {
            errorsList.classList.add('hidden');
            const errorsContent = document.getElementById('errorsContent');
            if (errorsContent) {
                errorsContent.innerHTML = '';
            }
        }
    }
    
    if (current === total) {
        document.getElementById('progressCloseBtn').classList.remove('hidden');
    }
}

function sleep(durationMs) {
    return new Promise(resolve => setTimeout(resolve, durationMs));
}

function closeProgressModal() {
    const modal = document.getElementById('progressModal');
    modal.close();
}


// Make functions available globally
window.updateBookMetadata = updateBookMetadata;
window.searchForBook = searchForBook;
window.deleteBook = deleteBook;
window.downloadResult = downloadResult;
window.autoDownloadBook = autoDownloadBook;

// ==============================================
// Real-time sync notifications
// ==============================================
const socket = window._appSocket || null;
if (socket) {
    socket.on('abs_sync_progress', (data) => {
        // Only show notifications when sync completes
        if (data.status === 'completed') {
            const count = data.synced_count || 0;
            const message = count > 0 
                ? `Sync completed! ${count} book${count !== 1 ? 's' : ''} added/updated.`
                : 'Sync completed.';
            
            showSyncCompleteBanner(message, count);
        }
    });
}

function showSyncCompleteBanner(message, count) {
    // Remove existing banner if any
    const existingBanner = document.getElementById('syncCompleteBanner');
    if (existingBanner) {
        existingBanner.remove();
    }
    
    // Only show banner if books were actually added/updated
    if (count === 0) return;
    
    // Create banner
    const banner = document.createElement('div');
    banner.id = 'syncCompleteBanner';
    banner.className = 'alert alert-success shadow-lg mb-4 flex justify-between items-center';
    banner.innerHTML = `
        <div class="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>${message}</span>
        </div>
        <div class="flex gap-2">
            <button onclick="refreshLibrary()" class="btn btn-sm btn-primary">
                Refresh Now
            </button>
            <button onclick="dismissSyncBanner()" class="btn btn-sm btn-ghost">
                Dismiss
            </button>
        </div>
    `;
    
    // Insert at top of page content
    const container = document.querySelector('.container') || document.querySelector('main') || document.body;
    container.insertBefore(banner, container.firstChild);
    
    // Auto-dismiss after 30 seconds
    setTimeout(() => {
        if (document.getElementById('syncCompleteBanner')) {
            dismissSyncBanner();
        }
    }, 30000);
}

function refreshLibrary() {
    window.location.reload();
}

function dismissSyncBanner() {
    const banner = document.getElementById('syncCompleteBanner');
    if (banner) {
        banner.style.transition = 'opacity 0.3s';
        banner.style.opacity = '0';
        setTimeout(() => banner.remove(), 300);
    }
}

window.refreshLibrary = refreshLibrary;
window.dismissSyncBanner = dismissSyncBanner;
