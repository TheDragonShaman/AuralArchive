document.addEventListener('DOMContentLoaded', () => {
    const importAuthorButton = document.querySelector('.js-import-author');
    if (importAuthorButton) {
        importAuthorButton.addEventListener('click', () => {
            const authorName = importAuthorButton.dataset.author;
            if (!authorName) {
                showNotification('Author name missing for import.', 'error');
                return;
            }

            const confirmMessage = `Import all catalog titles for ${authorName}?`;
            if (!window.confirm(confirmMessage)) {
                return;
            }

            handleImportRequest(
                '/authors/api/import-author',
                { author_name: authorName },
                importAuthorButton
            );
        });
    }

    const seriesButtons = document.querySelectorAll('.js-import-series');
    seriesButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const authorName = button.dataset.author;
            const seriesName = button.dataset.series;

            if (!authorName || !seriesName) {
                showNotification('Series import metadata is incomplete.', 'error');
                return;
            }

            const confirmMessage = `Import every title from series "${seriesName}"?`;
            if (!window.confirm(confirmMessage)) {
                return;
            }

            handleImportRequest(
                '/authors/api/import-series',
                { author_name: authorName, series_name: seriesName },
                button
            );
        });
    });

    const standaloneButton = document.querySelector('.js-import-standalone');
    if (standaloneButton) {
        standaloneButton.addEventListener('click', () => {
            const authorName = standaloneButton.dataset.author;
            if (!authorName) {
                showNotification('Author name missing for import.', 'error');
                return;
            }

            const confirmMessage = `Import standalone titles for ${authorName}?`;
            if (!window.confirm(confirmMessage)) {
                return;
            }

            handleImportRequest(
                '/authors/api/import-standalone',
                { author_name: authorName },
                standaloneButton
            );
        });
    }

    const standaloneBookButtons = document.querySelectorAll('.js-import-book');
    standaloneBookButtons.forEach((button) => {
        button.addEventListener('click', () => {
            const authorName = button.dataset.author;
            const asin = button.dataset.asin;

            if (!authorName || !asin) {
                showNotification('Missing data for book import.', 'error');
                return;
            }

            const confirmMessage = `Import this title (ASIN: ${asin}) into your library?`;
            if (!window.confirm(confirmMessage)) {
                return;
            }

            handleImportRequest(
                '/authors/api/import-book',
                { author_name: authorName, asin },
                button
            );
        });
    });
});

async function handleImportRequest(url, payload, button) {
    setLoadingState(button, true);

    try {
        const data = await sendImportRequest(url, payload);

        if (data.success) {
            showNotification(data.message || 'Import complete.', 'success');
        } else {
            let warningMessage = data.error || 'No titles imported.';

            const skippedMessages = [];
            if (Number(data.language_skipped) > 0) {
                skippedMessages.push(`${data.language_skipped} filtered by language`);
            }
            if (Number(data.missing_raw) > 0) {
                skippedMessages.push(`${data.missing_raw} skipped due to missing metadata`);
            }

            if (skippedMessages.length) {
                warningMessage += ` (${skippedMessages.join(', ')})`;
            }

            showNotification(warningMessage, 'warning');
        }
    } catch (error) {
        showNotification(error.message || 'Import failed.', 'error');
    } finally {
        setLoadingState(button, false);
    }
}

async function sendImportRequest(url, payload) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
    });

    let data = {};
    try {
        data = await response.json();
    } catch (error) {
        // Ignore JSON parsing errors; they will be surfaced as generic failures below
    }

    if (!response.ok) {
        const message = data.error || `Request failed (${response.status})`;
        throw new Error(message);
    }

    return data;
}

function setLoadingState(button, isLoading) {
    if (!button) {
        return;
    }

    if (isLoading) {
        button.disabled = true;
        button.classList.add('loading');
        button.setAttribute('aria-busy', 'true');
    } else {
        button.disabled = false;
        button.classList.remove('loading');
        button.removeAttribute('aria-busy');
    }
}
