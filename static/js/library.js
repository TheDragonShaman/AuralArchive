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
    }
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
    const cards = document.querySelectorAll('.book-card');
    const visibleCards = [];

    cards.forEach(card => {
        const title = card.dataset.title || '';
        const author = card.dataset.author || '';
        const status = card.dataset.status || '';
        const genre = card.dataset.genre || '';

        // Apply search filter
        const matchesSearch = !LibraryState.currentFilters.search || 
            title.includes(LibraryState.currentFilters.search) ||
            author.includes(LibraryState.currentFilters.search);

        // Apply status filter
        const matchesStatus = !LibraryState.currentFilters.status || 
            status === LibraryState.currentFilters.status;

        // Apply genre filter
        const matchesGenre = !LibraryState.currentFilters.genre || 
            genre === LibraryState.currentFilters.genre;

        if (matchesSearch && matchesStatus && matchesGenre) {
            card.style.display = '';
            visibleCards.push(card);
        } else {
            card.style.display = 'none';
        }
    });

    // Apply sorting
    sortBooks(visibleCards);
}

function sortBooks(cards) {
    const grid = document.getElementById('booksGrid');
    const sortBy = LibraryState.currentFilters.sort;

    cards.sort((a, b) => {
        switch (sortBy) {
            case 'author':
                return (a.dataset.author || '').localeCompare(b.dataset.author || '');
            case 'rating':
                const ratingA = parseFloat(a.querySelector('.fa-star')?.nextElementSibling?.textContent || 0);
                const ratingB = parseFloat(b.querySelector('.fa-star')?.nextElementSibling?.textContent || 0);
                return ratingB - ratingA;
            case 'date':
                // Assuming cards are already in date order from backend
                return 0;
            case 'title':
            default:
                return (a.dataset.title || '').localeCompare(b.dataset.title || '');
        }
    });

    // Reorder in DOM
    cards.forEach(card => grid.appendChild(card));
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
    document.querySelectorAll('.book-card').forEach(card => {
        card.addEventListener('click', (e) => {
            const bookId = card.dataset.bookId;
            
            if (LibraryState.isSelectMode) {
                // Selection mode - toggle selection
                e.preventDefault();
                toggleBookSelection(card, bookId);
            } else {
                // Normal mode - open details modal
                openBookModal(bookId);
            }
        });
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
    
    content.innerHTML = `
        <div class="card card-side bg-base-100">
            <!-- Book Cover -->
            <figure class="w-64 flex-shrink-0 flex items-start" style="border-radius: 0.25rem;">
                ${book.cover_image ? 
                    `<img src="${book.cover_image}" alt="${book.title}" class="w-full h-auto object-contain" style="border-radius: 0.25rem;" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">` :
                    ''
                }
                <div class="w-full aspect-[2/3] bg-base-300 flex flex-col items-center justify-center gap-3 ${book.cover_image ? 'hidden' : ''}" style="border-radius: 0.25rem;">
                    <i class="fas fa-book text-6xl opacity-30"></i>
                    <span class="font-semibold opacity-30 text-sm">AUDIO BOOK</span>
                </div>
            </figure>
            
            <!-- Book Details -->
            <div class="card-body p-6 gap-0">
                <h2 class="card-title text-3xl mb-0.5">${book.title}</h2>
                <p class="text-lg mb-2">by ${book.author}</p>
                
                ${book.series && book.series !== 'N/A' ? 
                    `<p class="mb-0.5"><strong>Series:</strong> ${book.series}</p>` : 
                    ''
                }
                
                ${book.sequence && book.sequence !== 'N/A' && book.sequence !== '' ? 
                    `<p class="mb-0.5"><strong>Book Number:</strong> ${book.sequence}</p>` : 
                    ''
                }
                
                ${book.narrator && book.narrator !== 'Unknown' ? 
                    `<p class="mb-0.5"><strong>Narrator:</strong> ${book.narrator}</p>` : 
                    ''
                }
                
                ${book.runtime ? 
                    `<p class="mb-0.5"><strong>Runtime:</strong> ${book.runtime}</p>` : 
                    ''
                }
                
                ${book.rating && book.rating !== 'N/A' ? 
                    `<p class="mb-0.5">
                        <strong>Rating:</strong> 
                        ${book.rating}
                        ${book.num_ratings && book.num_ratings > 0 ? `(${book.num_ratings.toLocaleString()} ratings)` : ''}
                    </p>` : 
                    ''
                }
                
                ${book.release_date && book.release_date !== 'Unknown' ? 
                    `<p class="mb-0.5"><strong>Release Date:</strong> ${book.release_date}</p>` : 
                    ''
                }
                
                ${book.publisher && book.publisher !== 'Unknown' ? 
                    `<p class="mb-0.5"><strong>Publisher:</strong> ${book.publisher}</p>` : 
                    ''
                }
                
                ${book.language ? 
                    `<p class="mb-0.5"><strong>Language:</strong> ${book.language}</p>` : 
                    ''
                }
                
                ${book.ownership_status || book.status ? 
                    `<p class="mb-0.5"><strong>Status:</strong> 
                        <span>
                            ${book.status || book.ownership_status}
                        </span>
                    </p>` : 
                    ''
                }
                
                <p class="mb-0.5"><strong>Source:</strong> 
                    <span>
                        ${formatSourceLabel(book)}
                    </span>
                </p>
                
                ${book.file_location ? 
                    `<div class="mb-0.5"><strong>File Location:</strong>
                        <code class="block text-xs break-all">${book.file_location}</code>
                    </div>` : 
                    ''
                }
                
                ${book.asin ? 
                    `<p class="mb-0.5"><strong>ASIN:</strong> ${book.asin}</p>` : 
                    ''
                }
                
                ${book.summary ? 
                    `<div class="mt-4">
                        <h4 class="font-bold mb-2">Summary:</h4>
                        <p class="leading-relaxed opacity-80">${book.summary}</p>
                    </div>` : 
                    ''
                }
            </div>
        </div>
    `;
    
    // Update modal action buttons
    const modalActions = modal.querySelector('.modal-action');
    if (modalActions) {
        modalActions.innerHTML = `
            <button class="btn btn-soft btn-primary btn-md" onclick="updateBookMetadata(${book.id})">
                <i class="fas fa-sync"></i> Update Metadata
            </button>
            <button class="btn btn-soft btn-accent btn-md" onclick="searchForBook(${book.id})">
                <i class="fas fa-search"></i> Interactive Download
            </button>
            <button class="btn btn-soft btn-warning btn-md" onclick="autoDownloadBook(${book.id}, this)">
                <i class="fas fa-bolt"></i> Auto Download
            </button>
            <button class="btn btn-soft btn-error btn-md" onclick="deleteBook(${book.id})">
                <i class="fas fa-trash"></i> Delete
            </button>
            <form method="dialog">
                <button class="btn btn-soft btn-md">Close</button>
            </form>
        `;
    }
    
    modal.showModal();
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

    // Implementation for bulk delete
    showNotification('Bulk delete feature coming soon', 'info');
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

async function searchForBook(bookId) {
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
                    <span class="badge ${seeders > 10 ? 'badge-success' : seeders > 0 ? 'badge-warning' : 'badge-error'} badge-sm">
                        ${seeders} <i class="fas fa-arrow-up text-[10px] ml-1"></i>
                    </span>
                    <span class="badge badge-ghost badge-sm">
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
                triggerButton.innerHTML = '<i class="fas fa-check"></i> Queued';
                triggerButton.classList.remove('btn-primary', 'btn-error', 'btn-warning');
                triggerButton.classList.add('btn-soft', 'btn-success');
            }
            if (tableRow) {
                tableRow.classList.add('opacity-70');
            }
            showNotification('Download queued successfully! Check the Downloads page.', 'success');
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

// ==============================================
// View Switching
// ==============================================
function setView(viewType) {
    const booksGrid = document.getElementById('booksGrid');
    const booksTable = document.getElementById('booksTable');
    const booksCompact = document.getElementById('booksCompact');
    const gridViewBtn = document.getElementById('gridViewBtn');
    const listViewBtn = document.getElementById('listViewBtn');
    const compactViewBtn = document.getElementById('compactViewBtn');
    
    // Save preference
    localStorage.setItem('libraryView', viewType);
    
    // Update button states
    [gridViewBtn, listViewBtn, compactViewBtn].forEach(btn => {
        btn.classList.remove('btn-primary');
    });
    
    // Hide all views
    booksGrid.classList.add('hidden');
    booksTable.classList.add('hidden');
    booksCompact.classList.add('hidden');
    
    if (viewType === 'grid') {
        booksGrid.classList.remove('hidden');
        gridViewBtn.classList.add('btn-primary');
    } else if (viewType === 'table') {
        booksTable.classList.remove('hidden');
        listViewBtn.classList.add('btn-primary');
    } else if (viewType === 'compact') {
        booksCompact.classList.remove('hidden');
        compactViewBtn.classList.add('btn-primary');
    }
}

// Load saved view preference on page load
document.addEventListener('DOMContentLoaded', () => {
    const savedView = localStorage.getItem('libraryView') || 'grid';
    setView(savedView);
});

// Make functions available globally
window.updateBookMetadata = updateBookMetadata;
window.searchForBook = searchForBook;
window.deleteBook = deleteBook;
window.setView = setView;
window.downloadResult = downloadResult;
window.autoDownloadBook = autoDownloadBook;
