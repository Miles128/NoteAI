/**
 * Statusbar Module
 *
 * 底部全局状态栏：显示当前文件、frontmatter 主题/标签、字数统计、光标位置。
 */
(function() {
    'use strict';

    var _currentFilePath = null;

    function _escapeHtml(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function _parseFrontmatter(text) {
        var meta = {};
        var body = String(text || '');
        var match = body.match(/^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n?/);
        if (!match) return { meta: meta, body: body };

        var yaml = match[1];
        body = body.substring(match[0].length);

        yaml.split(/\r?\n/).forEach(function(line) {
            var m = line.match(/^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)$/);
            if (!m) return;
            var key = m[1];
            var val = m[2].trim();
            if ((val.startsWith('"') && val.endsWith('"')) ||
                (val.startsWith("'") && val.endsWith("'"))) {
                val = val.slice(1, -1);
            }
            if (val.startsWith('[') && val.endsWith(']')) {
                val = val.slice(1, -1).split(',').map(function(s) { return s.trim(); }).filter(Boolean);
            }
            meta[key] = val;
        });

        return { meta: meta, body: body };
    }

    function _setText(id, html) {
        var el = document.getElementById(id);
        if (!el) return;
        el.innerHTML = html;
    }

    function _setPlain(id, text) {
        var el = document.getElementById(id);
        if (!el) return;
        el.textContent = text;
    }

    function _renderTopic(topicVal) {
        if (!topicVal) return '';
        var parts = String(topicVal).split('>').map(function(s) { return s.trim(); }).filter(Boolean);
        return parts.map(function(p) {
            return '<span class="statusbar-topic-chip">' + _escapeHtml(p) + '</span>';
        }).join('');
    }

    function _renderTags(tagsVal) {
        if (!tagsVal) return '';
        var tags = [];
        if (Array.isArray(tagsVal)) {
            tags = tagsVal;
        } else {
            tags = String(tagsVal).split(',').map(function(s) { return s.trim(); }).filter(Boolean);
        }
        return tags.map(function(t) {
            return '<span class="statusbar-tag-chip">#' + _escapeHtml(t) + '</span>';
        }).join('');
    }

    function updateFromContent(text, filePath, fileName) {
        var parsed = _parseFrontmatter(text);
        var body = parsed.body;
        var meta = parsed.meta;

        var charCount = body.length;
        var wordCount = body.replace(/\s+/g, ' ').trim().split(' ').length;
        if (body.trim() === '') wordCount = 0;
        var lineCount = body.split(/\r?\n/).length;

        _setPlain('statusbar-filename', fileName || (filePath && filePath.split('/').pop()) || '—');
        document.getElementById('statusbar-filename').title = filePath || '';
        _setText('statusbar-topic', _renderTopic(meta.topic));
        _setText('statusbar-tags', _renderTags(meta.tags));
        _setPlain('statusbar-chars', charCount + ' 字符');
        _setPlain('statusbar-words', wordCount + ' 词');
        _setPlain('statusbar-lines', lineCount + ' 行');
    }

    function clearStats() {
        _setPlain('statusbar-filename', '—');
        document.getElementById('statusbar-filename').title = '';
        _setText('statusbar-topic', '');
        _setText('statusbar-tags', '');
        _setPlain('statusbar-chars', '0 字符');
        _setPlain('statusbar-words', '0 词');
        _setPlain('statusbar-lines', '0 行');
        _setPlain('statusbar-cursor', 'Ln 1, Col 1');
        updateSaveStatus('', '');
        updateMessage('');
        setMetadataToggleVisible(false);
    }

    function updateSaveStatus(status, text) {
        var el = document.getElementById('statusbar-save-status');
        if (!el) return;
        el.className = 'statusbar-item statusbar-save-status' + (status ? ' ' + status : '');
        el.textContent = text || '';
    }

    var _messageTimer = null;

    function updateMessage(text, options) {
        var el = document.getElementById('statusbar-message');
        if (!el) return;
        options = options || {};
        if (_messageTimer) {
            clearTimeout(_messageTimer);
            _messageTimer = null;
        }
        el.className = 'statusbar-item statusbar-message' + (options.className ? ' ' + options.className : '');
        el.textContent = text || '';
        if (text && options.duration) {
            _messageTimer = setTimeout(function() {
                el.textContent = '';
                el.className = 'statusbar-item statusbar-message';
                _messageTimer = null;
            }, options.duration);
        }
    }

    function setRewriting(isRewriting, text) {
        var appBar = document.getElementById('app-statusbar');
        var container = document.getElementById('tiptap-editor-container');
        if (isRewriting) {
            if (appBar) appBar.classList.add('rewriting');
            if (container) container.classList.add('rewriting');
            updateMessage(text || (window.t ? window.t('app.llmRewriting') : ''), { className: 'rewriting' });
        } else {
            if (appBar) appBar.classList.remove('rewriting');
            if (container) container.classList.remove('rewriting');
            updateMessage('');
        }
    }

    function setMetadataToggleVisible(visible) {
        var toggle = document.getElementById('statusbar-metadata-toggle');
        if (!toggle) return;
        toggle.style.display = visible ? '' : 'none';
        toggle.hidden = !visible;
        if (!visible) {
            var panel = document.getElementById('frontmatter-panel');
            if (panel) {
                panel.style.display = 'none';
                panel.hidden = true;
                panel.classList.remove('is-open');
            }
        }
    }

    function bindMetadataToggle() {
        var toggle = document.getElementById('statusbar-metadata-toggle');
        var panel = document.getElementById('frontmatter-panel');
        if (!toggle || !panel || toggle.dataset.bound === 'true') return;
        toggle.dataset.bound = 'true';
        toggle.addEventListener('click', function() {
            var open = !panel.classList.contains('is-open');
            panel.classList.toggle('is-open', open);
            panel.style.display = open ? 'block' : 'none';
            panel.hidden = !open;
            toggle.classList.toggle('is-active', open);
        });
    }

    bindMetadataToggle();

    function updateCursor(line, col) {
        _setPlain('statusbar-cursor', 'Ln ' + (line || 1) + ', Col ' + (col || 1));
    }

    function onFileSelected(filePath) {
        _currentFilePath = filePath;
        if (!filePath) {
            clearStats();
            return;
        }

        if (!window.api || !window.api.readFileRaw) {
            clearStats();
            return;
        }

        window.api.readFileRaw(filePath).then(function(result) {
            if (!result || !result.success) {
                clearStats();
                return;
            }

            var rawContent = result.content || '';
            var text = '';
            try {
                var bin = atob(rawContent);
                var bytes = new Uint8Array(bin.length);
                for (var i = 0; i < bin.length; i++) {
                    bytes[i] = bin.charCodeAt(i);
                }
                text = new TextDecoder('utf-8').decode(bytes);
            } catch (e) {
                text = rawContent;
            }

            var fileName = filePath.split('/').pop() || filePath;
            updateFromContent(text, filePath, fileName);
        }).catch(function() {
            clearStats();
        });
    }

    window.StatusbarModule = {
        onFileSelected: onFileSelected,
        updateFromContent: updateFromContent,
        updateCursor: updateCursor,
        clearStats: clearStats,
        updateSaveStatus: updateSaveStatus,
        updateMessage: updateMessage,
        setRewriting: setRewriting,
        setMetadataToggleVisible: setMetadataToggleVisible
    };
})();
