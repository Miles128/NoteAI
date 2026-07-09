(function() {
    'use strict';

    var MAX_SELECTION_CHARS = 800;
    var _bar = null;
    var _selectedText = '';
    var _lastRangeRect = null;

    function _t(key, fallback, vars) {
        return window.t ? window.t(key, vars || {}) : fallback;
    }

    function _selectionScope(node) {
        if (!node) return null;
        var el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
        if (!el) return null;
        return el.closest('.preview-content, .tiptap-prose, .tiptap-editor-content');
    }

    function _isIgnoredTarget(target) {
        if (!target || !target.closest) return false;
        return !!target.closest('input, textarea, select, button, .selection-tools-popover, .settings-layout, .graph-panel');
    }

    function _normalizeSelectionText(text) {
        return String(text || '').replace(/\s+/g, ' ').trim();
    }

    function _getSelectionInfo() {
        var sel = window.getSelection ? window.getSelection() : null;
        if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
        var text = _normalizeSelectionText(sel.toString());
        if (text.length < 2) return null;
        if (text.length > MAX_SELECTION_CHARS) {
            text = text.slice(0, MAX_SELECTION_CHARS).trim();
        }
        var anchorScope = _selectionScope(sel.anchorNode);
        var focusScope = _selectionScope(sel.focusNode);
        if (!anchorScope || !focusScope || anchorScope !== focusScope) return null;
        var range = sel.getRangeAt(0);
        var rect = range.getBoundingClientRect();
        if (!rect || (!rect.width && !rect.height)) return null;
        return { text: text, rect: rect };
    }

    function _ensureBar() {
        if (_bar) return _bar;
        _bar = document.createElement('div');
        _bar.className = 'selection-tools-popover';
        _bar.hidden = true;
        _bar.innerHTML = [
            '<button type="button" data-action="rag"></button>',
            '<button type="button" data-action="local"></button>',
            '<button type="button" data-action="web"></button>',
            '<button type="button" data-action="copy"></button>'
        ].join('');
        document.body.appendChild(_bar);
        _bar.addEventListener('mousedown', function(e) {
            e.preventDefault();
        });
        _bar.addEventListener('click', function(e) {
            var btn = e.target.closest('button[data-action]');
            if (!btn) return;
            var action = btn.getAttribute('data-action');
            if (action === 'rag') {
                askKnowledge(_selectedText);
            } else if (action === 'local') {
                searchNotes(_selectedText);
            } else if (action === 'web') {
                webSearch(_selectedText);
            } else if (action === 'copy') {
                copySelection(_selectedText);
            }
            hide();
        });
        return _bar;
    }

    function _labelButtons() {
        var bar = _ensureBar();
        var rag = bar.querySelector('[data-action="rag"]');
        var local = bar.querySelector('[data-action="local"]');
        var web = bar.querySelector('[data-action="web"]');
        var copy = bar.querySelector('[data-action="copy"]');
        if (rag) rag.textContent = _t('selectionTools.askKb', '问知识库');
        if (local) local.textContent = _t('selectionTools.searchNotes', '搜笔记');
        if (web) web.textContent = _t('selectionTools.webSearch', '联网搜索');
        if (copy) copy.textContent = _t('selectionTools.copy', '复制');
    }

    function _positionBar(rect) {
        var bar = _ensureBar();
        var top = Math.max(8, rect.top + window.scrollY - bar.offsetHeight - 10);
        var left = rect.left + window.scrollX + rect.width / 2 - bar.offsetWidth / 2;
        left = Math.max(8, Math.min(left, window.scrollX + window.innerWidth - bar.offsetWidth - 8));
        bar.style.left = left + 'px';
        bar.style.top = top + 'px';
    }

    function show(info) {
        _selectedText = info.text;
        _lastRangeRect = info.rect;
        var bar = _ensureBar();
        _labelButtons();
        bar.hidden = false;
        bar.classList.add('is-visible');
        requestAnimationFrame(function() {
            if (_lastRangeRect) _positionBar(_lastRangeRect);
        });
    }

    function hide() {
        _selectedText = '';
        _lastRangeRect = null;
        if (!_bar) return;
        _bar.hidden = true;
        _bar.classList.remove('is-visible');
    }

    function refreshFromSelection(target) {
        if (_isIgnoredTarget(target)) {
            hide();
            return;
        }
        var info = _getSelectionInfo();
        if (!info) {
            hide();
            return;
        }
        show(info);
    }

    function askKnowledge(text) {
        var selected = _normalizeSelectionText(text);
        if (!selected) return;
        var prompt = _t('selectionTools.ragPrompt', '请基于知识库解释这段内容，并给出引用：{text}', { text: selected });
        if (window.AssistantModule && window.AssistantModule.ask) {
            window.AssistantModule.ask(prompt);
        }
    }

    function webSearch(text) {
        var selected = _normalizeSelectionText(text);
        if (!selected) return;
        var url = 'https://www.google.com/search?q=' + encodeURIComponent(selected);
        try {
            window.open(url, '_blank', 'noopener,noreferrer');
        } catch (e) {
            window.location.href = url;
        }
    }

    function searchNotes(text) {
        var selected = _normalizeSelectionText(text);
        if (!selected) return;
        if (typeof window.openSearchModal === 'function') {
            window.openSearchModal(selected);
        } else if (typeof window.toggleSearchModal === 'function') {
            window.toggleSearchModal();
        }
    }

    function copySelection(text) {
        var selected = _normalizeSelectionText(text);
        if (!selected) return;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(selected).catch(function() {});
        }
    }

    function init() {
        document.addEventListener('mouseup', function(e) {
            setTimeout(function() { refreshFromSelection(e.target); }, 0);
        });
        document.addEventListener('keyup', function(e) {
            if (e.key === 'Escape') {
                hide();
                return;
            }
            if (e.key && e.key.indexOf('Arrow') === 0) {
                refreshFromSelection(e.target);
            }
        });
        document.addEventListener('selectionchange', function() {
            if (!_bar || _bar.hidden) return;
            var info = _getSelectionInfo();
            if (!info) hide();
            else show(info);
        });
        window.addEventListener('scroll', hide, true);
        window.addEventListener('resize', hide);
        _ensureBar();
        _labelButtons();
    }

    window.SelectionToolsModule = {
        init: init,
        hide: hide,
        askKnowledge: askKnowledge,
        searchNotes: searchNotes,
        webSearch: webSearch
    };
})();
