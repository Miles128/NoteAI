/**
 * CLI tool call 人类可读摘要（NoteAI vault MCP + 常见 CLI 内置工具）
 */
(function() {
    'use strict';

    function t(key, fallback, vars) {
        if (window.t) {
            try { return window.t(key, vars || {}); } catch (_e) { /* ignore */ }
        }
        var s = fallback;
        if (vars) {
            Object.keys(vars).forEach(function(k) {
                s = s.replace('{' + k + '}', vars[k]);
            });
        }
        return s;
    }

    function basename(p) {
        if (!p) return '';
        var s = String(p).replace(/\\/g, '/');
        var i = s.lastIndexOf('/');
        return i >= 0 ? s.slice(i + 1) : s;
    }

    function clip(text, max) {
        var s = String(text || '').replace(/\s+/g, ' ').trim();
        if (!s) return '';
        if (s.length <= max) return s;
        return s.slice(0, max) + '…';
    }

    function normalizeToolName(name) {
        var n = String(name || '').trim();
        if (!n) return 'tool';
        var mcp = n.match(/^mcp__[^_]+__(.+)$/);
        if (mcp) n = mcp[1];
        return n;
    }

    function parseMaybeJson(value) {
        if (value == null) return null;
        if (typeof value === 'object') return value;
        var s = String(value).trim();
        if (!s) return null;
        try { return JSON.parse(s); } catch (_e) { return null; }
    }

    function countLines(text) {
        if (!text) return 0;
        return String(text).split('\n').length;
    }

    var VAULT_CALL = {
        vault_read_note: function(input) {
            return t('cliAgent.tool.readNote', '读取笔记「{name}」', { name: basename(input.file_path) || input.file_path || '?' });
        },
        vault_list_notes: function(input) {
            if (input.topic) {
                return t('cliAgent.tool.listNotesTopic', '列出主题「{topic}」下的笔记', { topic: input.topic });
            }
            return t('cliAgent.tool.listNotes', '列出工作区笔记');
        },
        vault_search_notes: function(input) {
            return t('cliAgent.tool.searchNotes', '搜索笔记「{query}」', { query: input.query || '?' });
        },
        vault_list_topics: function() {
            return t('cliAgent.tool.listTopics', '查看主题体系');
        },
        vault_write_note: function(input) {
            return t('cliAgent.tool.writeNote', '写入笔记「{name}」', { name: basename(input.file_path) || '?' });
        },
        vault_update_frontmatter: function(input) {
            return t('cliAgent.tool.updateMeta', '更新笔记元数据「{name}」', { name: basename(input.file_path) || '?' });
        },
        vault_move_note: function(input) {
            return t('cliAgent.tool.moveNote', '移动笔记「{from}」→「{to}」', {
                from: basename(input.from_path) || input.from_path || '?',
                to: basename(input.to_path) || input.to_path || '?'
            });
        },
        vault_append_log: function(input) {
            return t('cliAgent.tool.appendLog', '写入变更日志');
        },
        vault_raw_archive: function(input) {
            return t('cliAgent.tool.archive', '归档文件「{name}」', { name: basename(input.file_path) || '?' });
        },
        vault_ingest_url: function(input) {
            return t('cliAgent.tool.ingestUrl', '采集网页「{url}」', { url: clip(input.url, 48) || '?' });
        }
    };

    var VAULT_RESULT = {
        vault_read_note: function(input, result) {
            var lines = countLines(result);
            return t('cliAgent.tool.resultRead', '已读取「{name}」（约 {lines} 行）', {
                name: basename(input && input.file_path) || '?',
                lines: lines || '—'
            });
        },
        vault_search_notes: function(input, result) {
            var m = String(result || '').match(/Found (\d+)/i);
            var n = m ? m[1] : '';
            if (n) {
                return t('cliAgent.tool.resultSearchCount', '找到 {count} 条匹配笔记', { count: n });
            }
            return t('cliAgent.tool.resultSearch', '搜索完成');
        },
        vault_list_notes: function(_input, result) {
            var m = String(result || '').match(/Found (\d+)/i);
            if (m) {
                return t('cliAgent.tool.resultListCount', '共 {count} 篇笔记', { count: m[1] });
            }
            return t('cliAgent.tool.resultList', '笔记列表已返回');
        },
        vault_write_note: function(input) {
            return t('cliAgent.tool.resultWrite', '已保存「{name}」', { name: basename(input && input.file_path) || '?' });
        },
        vault_move_note: function(input) {
            return t('cliAgent.tool.resultMove', '已移动到「{name}」', { name: basename(input && input.to_path) || '?' });
        },
        vault_ingest_url: function() {
            return t('cliAgent.tool.resultIngest', '网页已入库');
        }
    };

    var GENERIC_CALL = {
        Read: function(input) {
            return t('cliAgent.tool.readFile', '读取文件「{name}」', { name: basename(input.file_path || input.path) || '?' });
        },
        Write: function(input) {
            return t('cliAgent.tool.writeFile', '写入文件「{name}」', { name: basename(input.file_path || input.path) || '?' });
        },
        Edit: function(input) {
            return t('cliAgent.tool.editFile', '编辑文件「{name}」', { name: basename(input.file_path || input.path) || '?' });
        },
        Bash: function(input) {
            return t('cliAgent.tool.bash', '运行命令：{cmd}', { cmd: clip(input.command || input.cmd, 60) || '…' });
        },
        Grep: function(input) {
            return t('cliAgent.tool.grep', '搜索「{pattern}」', { pattern: clip(input.pattern || input.query, 40) || '?' });
        },
        Glob: function(input) {
            return t('cliAgent.tool.glob', '查找文件「{pattern}」', { pattern: input.pattern || input.glob_pattern || '?' });
        },
        Task: function(input) {
            return t('cliAgent.tool.task', '子任务：{desc}', { desc: clip(input.description || input.prompt, 50) || '…' });
        },
        WebSearch: function(input) {
            return t('cliAgent.tool.webSearch', '联网搜索「{query}」', { query: clip(input.query || input.q, 40) || '?' });
        },
        Skill: function(input) {
            return t('cliAgent.tool.skill', '调用技能「{name}」', { name: input.skill || input.name || '?' });
        }
    };

    function describeCall(toolName, input) {
        var name = normalizeToolName(toolName);
        var args = parseMaybeJson(input) || input || {};
        if (VAULT_CALL[name]) return VAULT_CALL[name](args);
        if (GENERIC_CALL[name]) return GENERIC_CALL[name](args);
        return t('cliAgent.tool.genericCall', '调用工具「{name}」', { name: name });
    }

    function describeResult(toolName, input, result, success) {
        var name = normalizeToolName(toolName);
        var args = parseMaybeJson(input) || input || {};
        var text = '';
        if (typeof result === 'string') {
            text = result;
        } else if (result && typeof result === 'object') {
            if (result.content && Array.isArray(result.content)) {
                text = result.content.map(function(c) { return c && c.text; }).filter(Boolean).join('\n');
            } else if (result.text) {
                text = result.text;
            } else if (result.message) {
                text = result.message;
            }
        }
        if (success === false) {
            return t('cliAgent.tool.resultFailed', '操作失败：{reason}', { reason: clip(text, 80) || t('cliAgent.tool.unknownError', '未知原因') });
        }
        if (VAULT_RESULT[name]) return VAULT_RESULT[name](args, text);
        if (name === 'Read' || name === 'ReadMediaFile') {
            return t('cliAgent.tool.resultRead', '已读取「{name}」（约 {lines} 行）', {
                name: basename(args.file_path || args.path) || '?',
                lines: countLines(text) || '—'
            });
        }
        if (name === 'Bash') {
            return t('cliAgent.tool.resultBash', '命令执行完成');
        }
        if (name === 'Grep' || name === 'Glob') {
            var hits = (text.match(/^-/gm) || []).length;
            if (hits) {
                return t('cliAgent.tool.resultHits', '找到 {count} 条结果', { count: hits });
            }
            return t('cliAgent.tool.resultGeneric', '操作完成');
        }
        if (text.length > 0) {
            return t('cliAgent.tool.resultGeneric', '操作完成');
        }
        return t('cliAgent.tool.resultGeneric', '操作完成');
    }

    function describeRunning(toolName, input) {
        return describeCall(toolName, input) + '…';
    }

    window.CliToolSummary = {
        normalizeToolName: normalizeToolName,
        describeCall: describeCall,
        describeResult: describeResult,
        describeRunning: describeRunning,
        clip: clip
    };
})();
