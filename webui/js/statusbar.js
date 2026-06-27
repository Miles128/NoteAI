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
    }

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
        clearStats: clearStats
    };
})();
