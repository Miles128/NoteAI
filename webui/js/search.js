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
    document.getElementById('search-results').innerHTML =
        '<div class="search-empty">输入关键词搜索工作区中的所有笔记</div>';

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

    if (!query || query.trim().length === 0) {
        resultsEl.innerHTML =
            '<div class="search-empty">输入关键词搜索工作区中的所有笔记</div>';
        return;
    }

    if (!window.api || !window.api.pyCall) {
        resultsEl.innerHTML =
            '<div class="search-empty">搜索不可用</div>';
        return;
    }

    resultsEl.innerHTML =
        '<div class="search-loading">搜索中...</div>';

    window.api.pyCall('search_files', { query: query.trim() })
        .then(function (result) {
            if (result && result.success) {
                renderSearchResults(result);
            } else {
                resultsEl.innerHTML =
                    '<div class="search-empty">' +
                    (result ? escapeHtml(result.message || '搜索失败') : '搜索失败') +
                    '</div>';
            }
        })
        .catch(function (e) {
            resultsEl.innerHTML =
                '<div class="search-empty">搜索出错: ' + escapeHtml(e.message || '') + '</div>';
        });
}

function renderSearchResults(result) {
    var resultsEl = document.getElementById('search-results');
    if (!resultsEl) return;

    var results = result.results || [];
    var query = result.query || '';

    if (results.length === 0) {
        resultsEl.innerHTML =
            '<div class="search-empty">未找到匹配 "<strong>' +
            escapeHtml(query) + '</strong>" 的笔记</div>';
        return;
    }

    var countText = results.length + ' 个结果';
    if (result.count > 50) {
        countText = '前 50 个结果（共 ' + result.count + ' 个）';
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
    var escaped = escapeHtml(text);
    var queryEscaped = escapeHtml(query);
    // case-insensitive highlight
    var regex = new RegExp('(' + queryEscaped.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    return escaped.replace(regex, '<mark class="search-highlight">$1</mark>');
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

(function () {
    var input = document.getElementById('search-input');
    if (input) {
        input.addEventListener('input', function () {
            if (_searchDebounceTimer) clearTimeout(_searchDebounceTimer);
            _searchDebounceTimer = setTimeout(function () {
                doSearch(input.value);
            }, 200);
        });

        // Prevent input blur from closing
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') {
                e.stopPropagation();
            }
        });
    }

    // Click overlay background to close
    var overlay = document.getElementById('search-modal');
    if (overlay) {
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) {
                closeSearchModal();
            }
        });
    }
})();
