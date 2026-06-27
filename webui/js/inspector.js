/**
 * Inspector Module (右侧多 Tab 检查器)
 *
 * 对标 Tolaria 的 Right Inspector 面板，包含三个 Tab：
 * 1. AI - 现有 AI 聊天
 * 2. Properties - 当前笔记的 frontmatter 属性
 * 3. Backlinks - 反向链接（引用当前笔记的其他笔记）
 */
(function() {
    'use strict';

    var _currentTab = 'ai';
    var _currentFilePath = null;

    function _escapeHtml(s) {
        return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    /**
     * 切换 Tab
     */
    function switchTab(tabName) {
        _currentTab = tabName;

        var tabs = document.querySelectorAll('.inspector-tab');
        tabs.forEach(function(tab) {
            if (tab.getAttribute('data-inspector-tab') === tabName) {
                tab.classList.add('is-active');
            } else {
                tab.classList.remove('is-active');
            }
        });

        var contents = document.querySelectorAll('.inspector-tab-content');
        contents.forEach(function(content) {
            var contentTab = content.id.replace('inspector-content-', '');
            if (contentTab === tabName) {
                content.classList.add('is-active');
            } else {
                content.classList.remove('is-active');
            }
        });

        // 切换到非 AI Tab 时刷新数据
        if (tabName === 'properties' && _currentFilePath) {
            loadProperties(_currentFilePath);
        } else if (tabName === 'backlinks' && _currentFilePath) {
            loadBacklinks(_currentFilePath);
        } else if (tabName === 'cli') {
            if (window.CliAgentModule && window.CliAgentModule.loadAgents) {
                window.CliAgentModule.loadAgents().then(function() {
                    if (window.CliAgentModule.renderAgentSelector) {
                        window.CliAgentModule.renderAgentSelector();
                    }
                });
            }
        }
    }

    /**
     * 解析 frontmatter
     */
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
            // 去掉引号
            if ((val.startsWith('"') && val.endsWith('"')) ||
                (val.startsWith("'") && val.endsWith("'"))) {
                val = val.slice(1, -1);
            }
            // 数组格式 [a, b, c]
            if (val.startsWith('[') && val.endsWith(']')) {
                val = val.slice(1, -1).split(',').map(function(s) { return s.trim(); }).filter(Boolean);
            }
            meta[key] = val;
        });

        return { meta: meta, body: body };
    }

    /**
     * 加载属性 Tab
     */
    function loadProperties(filePath) {
        var body = document.getElementById('inspector-properties-body');
        if (!body) return;

        if (!filePath) {
            body.innerHTML = '<div class="inspector-empty">' +
                (window.t ? window.t('inspector.propertiesEmpty') : '选择一篇笔记查看属性') + '</div>';
            return;
        }

        body.innerHTML = '<div class="inspector-empty">' +
            (window.t ? window.t('inspector.loading') : '加载中…') + '</div>';

        if (!window.api || !window.api.readFileRaw) {
            body.innerHTML = '<div class="inspector-empty">API 不可用</div>';
            return;
        }

        window.api.readFileRaw(filePath).then(function(result) {
            if (!result || !result.success) {
                throw new Error((result && result.message) || '读取失败');
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

            var parsed = _parseFrontmatter(text);
            var meta = parsed.meta;
            var html = '';

            // 基本信息
            html += '<div class="inspector-prop-section">';
            html += '<div class="inspector-prop-section-title">' +
                (window.t ? window.t('inspector.basicInfo') : '基本信息') + '</div>';
            var fileName = filePath.split('/').pop() || filePath;
            html += _renderPropRow('文件名', _escapeHtml(fileName));
            html += _renderPropRow('路径', '<span style="word-break:break-all">' + _escapeHtml(filePath) + '</span>');
            html += '</div>';

            // Frontmatter 属性
            var metaKeys = Object.keys(meta);
            if (metaKeys.length > 0) {
                html += '<div class="inspector-prop-section">';
                html += '<div class="inspector-prop-section-title">' +
                    (window.t ? window.t('inspector.frontmatter') : 'Frontmatter') + '</div>';
                metaKeys.forEach(function(key) {
                    var val = meta[key];
                    html += _renderPropRow(_escapeHtml(key), _formatPropValue(key, val));
                });
                html += '</div>';
            }

            // 统计信息
            var bodyText = parsed.body;
            var charCount = bodyText.length;
            var wordCount = bodyText.replace(/\s+/g, ' ').trim().split(' ').length;
            var lineCount = bodyText.split(/\r?\n/).length;
            html += '<div class="inspector-prop-section">';
            html += '<div class="inspector-prop-section-title">' +
                (window.t ? window.t('inspector.stats') : '统计') + '</div>';
            html += _renderPropRow('字符数', String(charCount));
            html += _renderPropRow('词数', String(wordCount));
            html += _renderPropRow('行数', String(lineCount));
            html += '</div>';

            body.innerHTML = html;
        }).catch(function(err) {
            body.innerHTML = '<div class="inspector-empty">' +
                (window.t ? window.t('inspector.loadFailed') : '加载失败') + ': ' + _escapeHtml(err.message || '') + '</div>';
        });
    }

    function _renderPropRow(key, valueHtml) {
        return '<div class="inspector-prop-row">' +
            '<span class="inspector-prop-key">' + key + '</span>' +
            '<span class="inspector-prop-value">' + valueHtml + '</span>' +
            '</div>';
    }

    function _formatPropValue(key, val) {
        if (Array.isArray(val)) {
            return val.map(function(v) {
                return '<span class="inspector-prop-chip">' + _escapeHtml(v) + '</span>';
            }).join('');
        }
        var str = String(val);
        // topic 字段特殊渲染
        if (key === 'topic' || key === '主题') {
            var parts = str.split('>').map(function(s) { return s.trim(); }).filter(Boolean);
            return parts.map(function(p, i) {
                return '<span class="inspector-prop-chip' + (i === 0 ? ' primary' : '') + '">' + _escapeHtml(p) + '</span>';
            }).join('');
        }
        // tags 字段
        if (key === 'tags' || key === '标签') {
            var tags = str.split(',').map(function(s) { return s.trim(); }).filter(Boolean);
            return tags.map(function(t) {
                return '<span class="inspector-prop-chip">#' + _escapeHtml(t) + '</span>';
            }).join('');
        }
        // URL 字段
        if (key === 'url' || key === 'source' || key === '链接') {
            if (str.startsWith('http')) {
                return '<a href="' + _escapeHtml(str) + '" target="_blank" rel="noopener">' + _escapeHtml(str) + '</a>';
            }
        }
        // 日期字段
        if (key === 'date' || key === 'created' || key === 'updated' || key === '日期') {
            return '<span style="font-variant-numeric:tabular-nums">' + _escapeHtml(str) + '</span>';
        }
        return _escapeHtml(str);
    }

    /**
     * 加载 Backlinks Tab
     */
    function loadBacklinks(filePath) {
        var body = document.getElementById('inspector-backlinks-body');
        if (!body) return;

        if (!filePath) {
            body.innerHTML = '<div class="inspector-empty">' +
                (window.t ? window.t('inspector.backlinksEmpty') : '选择一篇笔记查看反向链接') + '</div>';
            return;
        }

        body.innerHTML = '<div class="inspector-empty">' +
            (window.t ? window.t('inspector.loading') : '加载中…') + '</div>';

        if (!window.api || !window.api.getBacklinks) {
            body.innerHTML = '<div class="inspector-empty">API 不可用</div>';
            return;
        }

        window.api.getBacklinks(filePath).then(function(result) {
            if (!result || !result.success) {
                body.innerHTML = '<div class="inspector-empty">' +
                    (window.t ? window.t('inspector.backlinksEmpty') : '暂无反向链接') + '</div>';
                return;
            }

            var backlinks = result.backlinks || result.links || [];
            if (!Array.isArray(backlinks) || backlinks.length === 0) {
                body.innerHTML = '<div class="inspector-empty">' +
                    (window.t ? window.t('inspector.backlinksEmpty') : '暂无反向链接') + '</div>';
                return;
            }

            var html = backlinks.map(function(link) {
                var fromPath = link.from || link.from_path || link.path || '';
                var fromName = link.from_name || link.name || (fromPath ? fromPath.split('/').pop() : '');
                var snippet = link.snippet || link.context || '';
                var topic = link.topic || '';
                return '<div class="backlink-item" data-path="' + _escapeHtml(fromPath) + '" data-name="' + _escapeHtml(fromName) + '">' +
                    '<div class="backlink-item-title">' + _escapeHtml(fromName) + '</div>' +
                    (snippet ? '<div class="backlink-item-snippet">' + _escapeHtml(snippet) + '</div>' : '') +
                    (topic ? '<div class="backlink-item-topic">' + _escapeHtml(topic) + '</div>' : '') +
                    '</div>';
            }).join('');

            body.innerHTML = html;

            var items = body.querySelectorAll('.backlink-item');
            items.forEach(function(item) {
                item.addEventListener('click', function() {
                    var path = this.getAttribute('data-path');
                    var name = this.getAttribute('data-name');
                    if (path && window.TreeModule && window.TreeModule.selectFile) {
                        window.TreeModule.selectFile(path, name);
                    }
                });
            });
        }).catch(function(err) {
            body.innerHTML = '<div class="inspector-empty">' +
                (window.t ? window.t('inspector.loadFailed') : '加载失败') + ': ' + _escapeHtml(err.message || '') + '</div>';
        });
    }

    /**
     * 当选中文件变化时调用
     */
    function onFileSelected(filePath) {
        _currentFilePath = filePath;
        if (_currentTab === 'properties' && filePath) {
            loadProperties(filePath);
        } else if (_currentTab === 'backlinks' && filePath) {
            loadBacklinks(filePath);
        }
    }

    function init() {
        var tabs = document.querySelectorAll('.inspector-tab');
        tabs.forEach(function(tab) {
            tab.addEventListener('click', function() {
                var tabName = this.getAttribute('data-inspector-tab');
                if (tabName) switchTab(tabName);
            });
        });
    }

    window.InspectorModule = {
        switchTab: switchTab,
        onFileSelected: onFileSelected,
        loadProperties: loadProperties,
        loadBacklinks: loadBacklinks,
        init: init,
        getCurrentTab: function() { return _currentTab; }
    };

    document.addEventListener('DOMContentLoaded', function() {
        init();
    });
})();
