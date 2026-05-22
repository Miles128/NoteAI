(function() { 'use strict';

var STEP_COUNT = 5;
var _resolveOpen = null;
var _currentStep = 0;

var DOMAIN_OPTIONS = [
    { id: 'agent', label: 'AI Agent 架构' },
    { id: 'rag', label: 'RAG 与知识检索' },
    { id: 'product', label: 'AI 产品' },
    { id: 'llm', label: '大模型应用' },
    { id: 'tools', label: '工具与效率' },
    { id: 'career', label: '职业与面试' }
];

var DOMAIN_TO_L1 = {
    agent: 'AI Agent',
    rag: 'RAG 与检索',
    product: 'AI 产品',
    llm: '大模型应用',
    tools: '工具与效率',
    career: '职业成长'
};

var state = {
    purpose: 'personal',
    domains: ['agent', 'rag', 'product'],
    depth: '3',
    language: 'zh',
    habits: ['folder_truth', 'pending', 'survey_only', 'auto_convert', 'tags_cn'],
    customDomains: ''
};

function $(id) {
    return document.getElementById(id);
}

function escapeHtml(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function readStateFromDom() {
    var purposeEl = document.querySelector('input[name="schema-purpose"]:checked');
    state.purpose = purposeEl ? purposeEl.value : 'personal';

    state.domains = [];
    document.querySelectorAll('[data-schema-domain]').forEach(function(el) {
        if (el.checked) state.domains.push(el.value);
    });

    var depthEl = document.querySelector('input[name="schema-depth"]:checked');
    state.depth = depthEl ? depthEl.value : '3';

    var langEl = document.querySelector('input[name="schema-language"]:checked');
    state.language = langEl ? langEl.value : 'zh';

    state.habits = [];
    document.querySelectorAll('[data-schema-habit]').forEach(function(el) {
        if (el.checked) state.habits.push(el.value);
    });

    var custom = $('schema-wizard-custom-domains');
    state.customDomains = custom ? custom.value.trim() : '';
}

function getLevel1Topics() {
    var topics = [];
    state.domains.forEach(function(id) {
        if (DOMAIN_TO_L1[id]) topics.push(DOMAIN_TO_L1[id]);
    });
    if (state.customDomains) {
        state.customDomains.split(/[,，、\n]/).forEach(function(t) {
            t = t.trim();
            if (t && topics.indexOf(t) < 0) topics.push(t);
        });
    }
    if (!topics.length) topics = ['AI 知识'];
    return topics;
}

function purposeLabel() {
    if (state.purpose === 'project') return '项目文档库';
    if (state.purpose === 'research') return '研究资料库';
    return '个人知识库';
}

function buildProjectRules() {
    var topics = getLevel1Topics();
    var lines = [
        '# 项目规则',
        '',
        '本工作区：' + purposeLabel() + '。',
        '',
        '## 一级主题（归类时优先使用）',
        ''
    ];
    topics.forEach(function(t) {
        lines.push('- ' + t);
    });
    lines.push('');
    lines.push('## 禁止自动归入');
    lines.push('- 其他');
    lines.push('- 杂项');
    lines.push('- 未分类');
    lines.push('- 资料');
    lines.push('');
    if (state.language === 'zh') {
        lines.push('- 笔记与标签优先使用中文');
    } else {
        lines.push('- 专有名词可保留英文，主题名与标签以中文为主');
    }
    return lines.join('\n');
}

function buildSchemaMarkdown() {
    var topics = getLevel1Topics();
    var l1Examples = topics.map(function(t) { return '`' + t + '`'; }).join('、');
    var maxDepth = state.depth === '2' ? 2 : 3;
    var editNotes = state.habits.indexOf('edit_notes') >= 0;
    var lines = [
        '# NoteAI 工作区 Schema',
        '',
        '> 由工作区引导生成。用途：' + purposeLabel() + '。',
        '',
        '## 1. 目录结构',
        '',
        '- `Notes/`：源稿 Markdown，按主题文件夹（最多 ' + maxDepth + ' 级）',
        '- `wiki/`：WIKI.md、`{叶主题}_综述.md`、`log.md`',
        '- `Raw/`：原件归档',
        '- `.noteai/`：RAG、memory、日志',
        '- `.ai_memory/project_rules.md`：主题细则',
        '',
        '## 2. 主题体系',
        '',
        '- 分隔符：` > `，最多 ' + maxDepth + ' 层',
        '- 路径：`Notes/一级/二级' + (maxDepth >= 3 ? '/三级' : '') + '/标题.md`',
        '- **文件夹为事实来源**；`WIKI.md` 与 `Notes/` 文件夹保持一致',
        '- 一级领域示例：' + l1Examples,
        '- 不确定分类 → `.pending_topics.json`，禁止「其他/杂项/未分类」',
        '',
        '## 3. Frontmatter',
        '',
        '```yaml',
        '---',
        'topic: ' + topics[0] + (topics.length > 1 ? ' > 二级主题' : ''),
        'tags: [标签1, 标签2]',
        'title: 文章标题',
        '---',
        '```',
        '',
        '- 标签 2～5 个' + (state.habits.indexOf('tags_cn') >= 0 ? '，中文优先' : ''),
        '- 文件名与标题一致，禁用 `/ \\ : * ? " < > |`',
        '',
        '## 4. 入库与级联',
        '',
        '- 流水线：转换 → 分类 → 索引 → 级联综述 → 同步 WIKI'
    ];
    if (state.habits.indexOf('auto_convert') >= 0) {
        lines.push('- 支持 PDF/DOCX 等自动转换；`Raw/` 内原件不重复转换');
    }
    if (state.habits.indexOf('survey_only') >= 0) {
        lines.push('- **级联只更新** `wiki/*_综述.md`，不改 `Notes/` 平行笔记正文');
    }
    lines.push('');
    lines.push('## 5. AI 可写范围');
    lines.push('');
    lines.push('```yaml');
    lines.push('ai_may_edit_wiki: true');
    lines.push('ai_may_edit_notes: ' + (editNotes ? 'true' : 'false'));
    lines.push('max_topic_depth: ' + maxDepth);
    lines.push('```');
    lines.push('');
    lines.push('<!-- noteai-schema-version: 2 -->');
    lines.push('<!-- noteai-schema-configured -->');
    return lines.join('\n');
}

function updateProgressUi() {
    var dots = document.querySelectorAll('.schema-wizard-dot');
    dots.forEach(function(dot, i) {
        dot.classList.remove('active', 'done');
        if (i < _currentStep) dot.classList.add('done');
        if (i === _currentStep) dot.classList.add('active');
    });
    document.querySelectorAll('.schema-wizard-step').forEach(function(step, i) {
        step.classList.toggle('active', i === _currentStep);
    });
    var backBtn = $('schema-wizard-back');
    var nextBtn = $('schema-wizard-next');
    var saveBtn = $('schema-wizard-save');
    if (backBtn) backBtn.style.display = _currentStep === 0 ? 'none' : '';
    if (nextBtn) nextBtn.style.display = _currentStep === STEP_COUNT - 1 ? 'none' : '';
    if (saveBtn) saveBtn.style.display = _currentStep === STEP_COUNT - 1 ? '' : 'none';
}

function refreshPreview() {
    readStateFromDom();
    var preview = $('schema-wizard-preview');
    if (preview) preview.value = buildSchemaMarkdown();
}

function bindOptionCards() {
    document.querySelectorAll('.schema-option-card').forEach(function(card) {
        card.addEventListener('click', function(e) {
            if (e.target.tagName === 'INPUT') return;
            var input = card.querySelector('input');
            if (!input) return;
            if (input.type === 'radio') {
                input.checked = true;
            } else {
                input.checked = !input.checked;
            }
            card.classList.toggle('selected', input.checked);
            if (input.type === 'radio') {
                card.parentElement.querySelectorAll('.schema-option-card').forEach(function(c) {
                    var inp = c.querySelector('input');
                    c.classList.toggle('selected', inp && inp.checked);
                });
            }
        });
    });
}

function showModal() {
    var modal = $('schema-wizard-modal');
    if (modal) modal.style.display = 'flex';
    _currentStep = 0;
    updateProgressUi();
    refreshPreview();
}

function hideModal() {
    var modal = $('schema-wizard-modal');
    if (modal) modal.style.display = 'none';
}

async function applyDefaultTemplate() {
    if (!window.api || !window.api.getSchemaTemplate) return false;
    var tpl = await window.api.getSchemaTemplate();
    if (!tpl || !tpl.success) return false;
    await window.api.saveSchema(tpl.content || '');
    await window.api.saveProjectRules(buildProjectRules());
    return true;
}

async function saveWizardResult() {
    readStateFromDom();
    var schema = $('schema-wizard-preview');
    var content = schema ? schema.value : buildSchemaMarkdown();
    if (!window.api || !window.api.saveSchema) {
        throw new Error('saveSchema 不可用');
    }
    await window.api.saveSchema(content);
    if (window.api.saveProjectRules) {
        await window.api.saveProjectRules(buildProjectRules());
    }
}

async function finishWizard() {
    try {
        await saveWizardResult();
        hideModal();
        if (typeof window.updateStatus === 'function') {
            window.updateStatus('工作区 Schema 已保存');
        }
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            await window.TreeModule.loadFileTree(true);
        }
        if (typeof window.runPostWorkspaceSetup === 'function') {
            window.runPostWorkspaceSetup();
        }
        if (_resolveOpen) _resolveOpen(true);
    } catch (e) {
        console.error('[SchemaWizard] save failed:', e);
        if (typeof window.updateStatus === 'function') {
            window.updateStatus('保存 Schema 失败: ' + e.message);
        }
    }
}

function openWizard() {
    return new Promise(function(resolve) {
        _resolveOpen = resolve;
        showModal();
    });
}

async function maybePromptSchemaSetup(flag) {
    if (!flag && window.api && window.api.needsSchemaSetup) {
        try {
            var st = await window.api.needsSchemaSetup();
            flag = st && st.needs_setup;
        } catch (e) {
            console.warn('[SchemaWizard] needs_schema_setup:', e);
            return false;
        }
    }
    if (!flag) return false;
    await openWizard();
    return true;
}

function initSchemaWizard() {
    bindOptionCards();

    var nextBtn = $('schema-wizard-next');
    var backBtn = $('schema-wizard-back');
    var saveBtn = $('schema-wizard-save');
    var defaultBtn = $('schema-wizard-use-default');

    if (nextBtn) {
        nextBtn.addEventListener('click', function() {
            readStateFromDom();
            if (_currentStep === 1 && !state.domains.length && !state.customDomains) {
                if (typeof window.updateStatus === 'function') {
                    window.updateStatus('请至少选择一个知识领域');
                }
                return;
            }
            if (_currentStep < STEP_COUNT - 1) {
                _currentStep += 1;
                if (_currentStep === STEP_COUNT - 1) refreshPreview();
                updateProgressUi();
            }
        });
    }

    if (backBtn) {
        backBtn.addEventListener('click', function() {
            if (_currentStep > 0) {
                _currentStep -= 1;
                updateProgressUi();
            }
        });
    }

    if (saveBtn) {
        saveBtn.addEventListener('click', function() {
            finishWizard();
        });
    }

    if (defaultBtn) {
        defaultBtn.addEventListener('click', async function() {
            try {
                await applyDefaultTemplate();
                hideModal();
                if (typeof window.runPostWorkspaceSetup === 'function') {
                    window.runPostWorkspaceSetup();
                }
                if (_resolveOpen) _resolveOpen(true);
            } catch (e) {
                console.error('[SchemaWizard] default template:', e);
            }
        });
    }

    document.querySelectorAll('[data-schema-domain],[data-schema-habit]').forEach(function(el) {
        el.addEventListener('change', function() {
            var card = el.closest('.schema-option-card');
            if (card) card.classList.toggle('selected', el.checked);
        });
    });
}

window.SchemaWizard = {
    init: initSchemaWizard,
    open: openWizard,
    maybePromptSchemaSetup: maybePromptSchemaSetup,
    buildSchemaMarkdown: buildSchemaMarkdown
};

})();
