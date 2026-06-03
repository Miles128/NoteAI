(function() { 'use strict';

var _searchVisible = false;
var _searchDebounceTimer = null;

function toggleSearchModal() {
    if (_searchVisible) {
        closeSearchModal();
    } else {
        openSearchModal();
    }
}

function openSearchModal() {
    var overlay = document.getElementById('search-modal');
    var input = document.getElementById('search-input');
    if (!overlay || !input) return;

    overlay.style.display = 'flex';
    _searchVisible = true;

    input.value = '';
    document.getElementById('search-results').innerHTML = '';

    setTimeout(function () {
        input.focus();
    }, 50);
}

function closeSearchModal() {
    var overlay = document.getElementById('search-modal');
    if (overlay) overlay.style.display = 'none';
    _searchVisible = false;

    if (_searchDebounceTimer) {
        clearTimeout(_searchDebounceTimer);
        _searchDebounceTimer = null;
    }
}

function doSearch(query) {
    var resultsEl = document.getElementById('search-results');
    if (!resultsEl) return;

    console.log('[Search] doSearch called, query:', query);

    if (!query || query.trim().length === 0) {
        resultsEl.innerHTML = '';
        return;
    }

    if (!window.api || !window.api.invoke) {
        resultsEl.innerHTML =
            '<div class="search-empty">' + window.t('search.unavailable') + '</div>';
        return;
    }

    resultsEl.innerHTML =
        '<div class="search-loading">' + window.t('search.loading') + '</div>';

    window.api.invoke('search_files', { query: query.trim() })
        .then(function (result) {
            console.log('[Search] result:', JSON.stringify(result).substring(0, 500));
            if (result && result.success) {
                renderSearchResults(result);
            } else {
                resultsEl.innerHTML =
                    '<div class="search-empty">' +
                    (result ? escapeHtml(result.message || window.t('search.failed')) : window.t('search.failed')) +
                    '</div>';
            }
        })
        .catch(function (e) {
            console.error('[Search] error:', e);
            resultsEl.innerHTML =
                '<div class="search-empty">' + window.t('search.error', { message: escapeHtml(e.message || e || window.t('common.unknownError')) }) + '</div>';
        });
}

function renderSearchResults(result) {
    var resultsEl = document.getElementById('search-results');
    if (!resultsEl) return;

    var results = result.results || [];
    var query = result.query || '';

    if (results.length === 0) {
        resultsEl.innerHTML =
            '<div class="search-empty">' + window.t('search.noResults', { query: '<strong>' + escapeHtml(query) + '</strong>' }) + '</div>';
        return;
    }

    var countText = window.t('search.resultCount', { count: results.length });
    if (result.count > 50) {
        countText = window.t('search.resultTruncated', { total: result.count });
    }

    var html = '<div class="search-count">' + countText + '</div>';

    results.forEach(function (r) {
        var highlightedSnippet = highlightMatch(r.snippet || '', query);
        html +=
            '<div class="search-result-item" data-path="' +
            escapeAttr(r.path) +
            '" onclick="onSearchResultClick(this)">' +
            '<div class="search-result-title">' +
            escapeHtml(r.title || r.name) +
            '</div>' +
            '<div class="search-result-path">' +
            escapeHtml(r.path) +
            '</div>' +
            '<div class="search-result-snippet">' +
            highlightedSnippet +
            '</div>' +
            '</div>';
    });

    resultsEl.innerHTML = html;
}

function highlightMatch(text, query) {
    if (!query) return escapeHtml(text);
    var regex = new RegExp('(' + query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    var parts = [];
    var lastIdx = 0;
    var m;
    while ((m = regex.exec(text)) !== null) {
        if (m.index > lastIdx) {
            parts.push(escapeHtml(text.substring(lastIdx, m.index)));
        }
        parts.push('<mark class="search-highlight">' + escapeHtml(m[1]) + '</mark>');
        lastIdx = regex.lastIndex;
    }
    if (lastIdx < text.length) {
        parts.push(escapeHtml(text.substring(lastIdx)));
    }
    return parts.join('');
}

function onSearchResultClick(el) {
    var path = el.getAttribute('data-path');
    var name = el.querySelector('.search-result-title')?.textContent || '';
    if (path) {
        closeSearchModal();
        if (window.TreeModule && window.TreeModule.selectFile) {
            window.TreeModule.selectFile(path, name);
        }
    }
}

document.addEventListener('keydown', function (e) {
    // Cmd+K or Ctrl+K → open search
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (_searchVisible) {
            closeSearchModal();
        } else {
            openSearchModal();
        }
        return;
    }

    // Escape → close
    if (e.key === 'Escape' && _searchVisible) {
        var input = document.getElementById('search-input');
        if (input && document.activeElement === input && input.value.length > 0) {
            // First Esc clears input, second closes
            input.value = '';
            doSearch('');
            return;
        }
        e.preventDefault();
        closeSearchModal();
        return;
    }
});

document.addEventListener('DOMContentLoaded', function() {
    var input = document.getElementById('search-input');
    if (input) {
        input.addEventListener('input', function () {
            if (_searchDebounceTimer) clearTimeout(_searchDebounceTimer);
            _searchDebounceTimer = setTimeout(function () {
                doSearch(input.value);
            }, 200);
        });

        input.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                e.stopPropagation();
            }
        });
    }

    var overlay = document.getElementById('search-modal');
    if (overlay) {
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) {
                closeSearchModal();
            }
        });
    }
});

window.toggleSearchModal = toggleSearchModal;
window.closeSearchModal = closeSearchModal;
window.onSearchResultClick = onSearchResultClick;

})();

