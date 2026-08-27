// 主题侧栏树：列表构建与渲染（由 topic.ts 导入）

export interface TopicTreeNode {
    children: Record<string, TopicTreeNode>;
    files: any[];
    name: string;
    label: string;
}

export function _buildTopicTree(topics: any[]): TopicTreeNode {
    var root: TopicTreeNode = { children: {}, files: [], name: '', label: '' };
    topics.forEach(function(topic) {
        var parts = topic.name.split(' > ');
        var node = root;
        for (var i = 0; i < parts.length; i++) {
            var part = parts[i];
            if (!node.children[part]) {
                node.children[part] = { children: {}, files: [], name: parts.slice(0, i + 1).join(' > '), label: part };
            }
            node = node.children[part];
        }
        if (topic.files && topic.files.length > 0) {
            node.files = topic.files;
        }
    });
    return root;
}

export function _renderTopicTree(node: TopicTreeNode, expandedTopics: Record<string, boolean>, depth?: number): string {
    depth = depth || 0;
    var html = '';
    var keys = Object.keys(node.children).sort(function(a, b) {
        return a.toLowerCase().localeCompare(b.toLowerCase());
    });
    keys.forEach(function(key) {
        var child = node.children[key];
        var hasChildren = Object.keys(child.children).length > 0;
        var hasFiles = child.files.length > 0;
        var isExpanded = expandedTopics[child.name] ? ' expanded' : '';
        var indent = depth * 16;
        var totalFiles = _countAllFiles(child);

        html += '<div class="sidebar-tag-group' + isExpanded + '" data-topic-name="' + window.escapeAttr(child.name) + '">';
        html += '<div class="sidebar-tag-row" onclick="window.topicRowClick(this)" data-topic-name="' + window.escapeAttr(child.name) + '" style="padding-left:' + (8 + indent) + 'px">';
        if (hasChildren || hasFiles) {
            html += '<span class="sidebar-tag-toggle" onclick="event.stopPropagation(); this.parentElement.classList.toggle(\'expanded\')">' + window.Icons!.get('chevronDown') + '</span>';
        } else {
            html += '<span class="sidebar-tag-toggle" style="visibility:hidden">' + window.Icons!.get('chevronDown') + '</span>';
        }
        html += '<span class="sidebar-tag-name" data-topic-name="' + window.escapeAttr(child.name) + '">' + window.escapeHtml(child.label) + '</span>';
        if (totalFiles > 0) {
            html += '<span class="sidebar-tag-count">' + totalFiles + '</span>';
        }
        // 一级主题行挂综述状态：开关 / 无综述标记 / 综述预览 / 可更新
        var surveyStaleShown = false;
        if (depth === 0) {
            var ov = (window._surveyOverviewMap || {})[child.name] || {};
            var enabled = ov.enabled !== false;
            if (!enabled) {
                html += '<span class="sidebar-tag-survey sidebar-tag-survey-off" title="' + window.escapeAttr(window.t('topic.surveyOffTitle')) + '">' + window.escapeHtml(window.t('topic.surveyOff')) + '</span>';
            } else if (!ov.has_survey) {
                html += '<span class="sidebar-tag-survey sidebar-tag-survey-missing" title="' + window.escapeAttr(window.t('topic.noSurveyTitle')) + '">' + window.escapeHtml(window.t('topic.noSurvey')) + '</span>';
            } else {
                html += '<span class="sidebar-tag-survey sidebar-tag-survey-ok" onclick="event.stopPropagation(); window.previewTopicSurvey(\'' + window.escapeAttr(child.name) + '\')">' + window.escapeHtml(window.t('topic.surveyDoc')) + '</span>';
                if (ov.stale) {
                    surveyStaleShown = true;
                    html += '<span class="sidebar-tag-survey sidebar-tag-survey-stale" onclick="event.stopPropagation(); window.updateTopicSurvey(\'' + window.escapeAttr(child.name) + '\')" title="' + window.escapeAttr(window.t('topic.surveyUpdateTitle')) + '">' + window.escapeHtml(window.t('topic.surveyStale')) + '</span>';
                }
            }
            // P5：语义知识页（wiki/semantic/*_语义.md）可更新提示，来自 get_topic_tree 的 stale_topics；
            // 综述 stale 徽标已展示同一级主题时不重复展示
            if ((window._topicStaleMap || {})[child.name] && !surveyStaleShown) {
                html += '<span class="sidebar-tag-survey sidebar-tag-survey-stale" onclick="event.stopPropagation(); window.previewSemanticWikiPage(\'' + window.escapeAttr(child.name) + '\')" title="' + window.escapeAttr(window.t('topic.wikiStaleTitle')) + '">' + window.escapeHtml(window.t('topic.wikiStale')) + '</span>';
            }
            html += '<span class="sidebar-tag-survey-toggle' + (enabled ? ' on' : '') + '" onclick="event.stopPropagation(); window.toggleTopicSurvey(\'' + window.escapeAttr(child.name) + '\')" title="' + window.escapeAttr(window.t('topic.surveyToggleTitle')) + '"></span>';
        }
        html += '</div>';

        if (hasChildren) {
            html += '<div class="sidebar-tag-children">';
            html += _renderTopicTree(child, expandedTopics, depth + 1);
            html += '</div>';
        }

        if (hasFiles) {
            html += '<div class="sidebar-tag-files">';
            child.files.forEach(function(f) {
                var display = f.title || window.t('download.unnamed');
                var path = f.path || '';
                if (path) {
                    html += '<div class="sidebar-tag-file tree-item" draggable="true" data-file-path="' + window.escapeAttr(path) + '" onclick="window.TreeModule.selectFile(\'' + window.escapeAttr(path) + '\', \'' + window.escapeAttr(display) + '\')" style="padding-left:' + (24 + indent) + 'px">';
                } else {
                    html += '<div class="sidebar-tag-file tree-item" style="padding-left:' + (24 + indent) + 'px">';
                }
                html += '<span class="tree-name">' + window.escapeHtml(display) + '</span>';
                html += '</div>';
            });
            html += '</div>';
        }

        html += '</div>';
    });
    return html;
}

export function _countAllFiles(node: TopicTreeNode): number {
    var count = node.files.length;
    var keys = Object.keys(node.children);
    for (var i = 0; i < keys.length; i++) {
        count += _countAllFiles(node.children[keys[i]]);
    }
    return count;
}
