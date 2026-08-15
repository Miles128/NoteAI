// ============================================================================
// onboarding.js —— P2 首启引导 wizard
//
// 触发：main.mjs 在 App.init() 完成后调用 OnboardingModule.maybeStart()，
//       workspace 未设置且未完成过引导时打开（完成标记：localStorage 为主，
//       workspace_state.json 的 onboarding_done 为后端镜像）。
// 步骤状态机：
//   Step 0 欢迎 + 工作区（选择/新建 或 示例库）
//   Step 1 API Key（服务商预设 + test_api_config 测试 + save_api_config 保存）
//   Step 2 模型与索引准备（阶段态轮询 get_onboarding_status / rag_index_status，
//          并复用现有 rag_index_built python-event）
//   Step 3 示范提问（仅示例库路径且索引就绪；由 AssistantModule.ask 发起）
// 「跳过」全程可用；wizard 不写任何笔记，凭据仅走 save_api_config 加密存储。
// ============================================================================
(function() { 'use strict';

var STORAGE_KEY = 'noteai.onboardingDone';
var SAMPLE_QUESTION = '这份指南对普通人使用 AI 的核心建议是什么？';
var MODEL_POLL_MS = 3000;
var INDEX_POLL_MS = 5000;
var SAMPLE_POLL_MAX = 40;

var PROVIDER_PRESETS = [
    {
        id: 'deepseek',
        label: 'DeepSeek',
        apiBase: 'https://api.deepseek.com',
        modelName: 'deepseek-chat',
        keyPlaceholder: 'sk-...'
    },
    {
        id: 'openai',
        label: 'OpenAI 兼容',
        apiBase: 'https://api.openai.com/v1',
        modelName: 'gpt-4o',
        keyPlaceholder: 'sk-...'
    },
    {
        id: 'ollama',
        label: 'Ollama（本地）',
        apiBase: 'http://localhost:11434/v1',
        modelName: 'qwen2.5:7b',
        keyPlaceholder: 'ollama-local（本地任意 10 位以上字符）'
    }
];

var state: any = {
    open: false,
    step: 0,
    sampleMode: false,       // Step 0 是否走了示例库路径
    workspacePath: '',
    modelsReady: false,
    indexReady: false,
    indexChunkCount: 0,
    apiTested: false,
    busy: false,
    root: null,
    bodyEl: null,
    dotsEl: null,
    modelTimer: null,
    indexTimer: null,
    unlistenRag: null
};

// ---------------------------------------------------------------------------
// DOM 工具
// ---------------------------------------------------------------------------

function el(tag: any, className: any, text?: any) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
}

function btn(className: any, text: any, onClick?: any, disabled?: any) {
    var b = el('button', className, text);
    b.type = 'button';
    if (onClick) b.addEventListener('click', onClick);
    if (disabled) b.disabled = true;
    return b;
}

function sleep(ms: any) {
    return new Promise(function(resolve) { setTimeout(resolve, ms); });
}

// ---------------------------------------------------------------------------
// 完成标记
// ---------------------------------------------------------------------------

function isDoneLocal() {
    try { return localStorage.getItem(STORAGE_KEY) === '1'; } catch (e) { return false; }
}

function markDoneLocal() {
    try { localStorage.setItem(STORAGE_KEY, '1'); } catch (e) { /* ignore */ }
}

// ---------------------------------------------------------------------------
// 入口：main.mjs 在 App.init() 完成后调用
// ---------------------------------------------------------------------------

async function maybeStart() {
    if (state.open || isDoneLocal()) return;
    var st = null;
    try {
        st = await window.api.getOnboardingStatus();
    } catch (e) {
        console.warn('[Onboarding] get_onboarding_status failed:', e);
        return;
    }
    if (!st) return;
    if (st.onboarding_done) { markDoneLocal(); return; }
    if (st.workspace_set) return; // 触发条件：workspace 未设置且未完成引导
    open();
}

// ---------------------------------------------------------------------------
// 覆盖层骨架
// ---------------------------------------------------------------------------

function open() {
    if (state.open || state.root) return;
    state.open = true;
    state.step = 0;
    state.sampleMode = false;
    state.modelsReady = false;
    state.indexReady = false;
    state.apiTested = false;

    var root = el('div', 'onb-overlay modal-overlay');
    var card = el('div', 'onb-card');

    var header = el('div', 'onb-header');
    header.appendChild(el('div', 'onb-title', '欢迎使用 NoteAI'));
    header.appendChild(btn('onb-skip', '跳过引导', skip));
    card.appendChild(header);

    state.dotsEl = el('div', 'onb-dots');
    card.appendChild(state.dotsEl);

    state.bodyEl = el('div', 'onb-body');
    card.appendChild(state.bodyEl);

    root.appendChild(card);
    document.body.appendChild(root);
    state.root = root;

    _listenRagEvents();
    renderStep();
}

function _destroy() {
    _stopPolling();
    if (state.unlistenRag) {
        try { state.unlistenRag(); } catch (e) { /* ignore */ }
        state.unlistenRag = null;
    }
    if (state.root && state.root.parentNode) {
        state.root.parentNode.removeChild(state.root);
    }
    state.root = null;
    state.bodyEl = null;
    state.dotsEl = null;
    state.open = false;
}

function _renderDots() {
    if (!state.dotsEl) return;
    state.dotsEl.textContent = '';
    var labels = state.sampleMode
        ? ['工作区', 'API Key', '模型准备', '试一试']
        : ['工作区', 'API Key', '模型准备'];
    labels.forEach(function(label, i) {
        var cls = 'onb-dot';
        if (i === state.step) cls += ' active';
        else if (i < state.step) cls += ' done';
        state.dotsEl.appendChild(el('span', cls, label));
    });
}

function _footer(hint: any, primaryLabel: any, onPrimary: any, primaryDisabled: any, showBack: any) {
    var footer = el('div', 'onb-footer');
    footer.appendChild(el('span', 'onb-hint', hint || ''));
    var right = el('div', 'onb-actions-row');
    if (showBack) {
        right.appendChild(btn('onb-btn', '上一步', function() { goStep(state.step - 1); }));
    }
    if (primaryLabel) {
        right.appendChild(btn('onb-btn primary', primaryLabel, onPrimary, !!primaryDisabled));
    }
    footer.appendChild(right);
    return footer;
}

// ---------------------------------------------------------------------------
// 步骤状态机
// ---------------------------------------------------------------------------

function goStep(n: any) {
    if (!state.open) return;
    if (n < 0) n = 0;
    state.step = n;
    renderStep();
}

function renderStep() {
    if (!state.bodyEl) return;
    _stopPolling();
    state.bodyEl.textContent = '';
    _renderDots();
    if (state.step === 0) renderStep0(state.bodyEl);
    else if (state.step === 1) renderStep1(state.bodyEl);
    else if (state.step === 2) renderStep2(state.bodyEl);
    else renderStep3(state.bodyEl);
}

// ---- Step 0：欢迎 + 工作区 -------------------------------------------------

function renderStep0(container: any) {
    container.appendChild(el('div', 'onb-desc',
        'NoteAI 会把你的笔记变成可检索、可对话的知识库。先选择一个工作区开始：'));

    var row = el('div', 'onb-actions-row');

    var chooseBtn = el('button', 'onb-big-btn');
    chooseBtn.type = 'button';
    chooseBtn.appendChild(el('strong', null, '选择 / 新建工作区'));
    chooseBtn.appendChild(el('span', null, '指定一个本地文件夹作为笔记库（推荐已有笔记的用户）'));
    chooseBtn.addEventListener('click', _chooseWorkspace);
    row.appendChild(chooseBtn);

    var sampleBtn = el('button', 'onb-big-btn');
    sampleBtn.type = 'button';
    sampleBtn.appendChild(el('strong', null, '先用示例库体验'));
    sampleBtn.appendChild(el('span', null, '自动创建「普通人的AI指南」示例笔记库，快速体验 AI 问答'));
    sampleBtn.addEventListener('click', _chooseSample);
    row.appendChild(sampleBtn);

    container.appendChild(row);

    var status = el('div', 'onb-status info', '');
    container.appendChild(status);
    state._step0Status = status;
    state._step0Btns = [chooseBtn, sampleBtn];
}

function _step0Busy(busy: any, message: any) {
    state.busy = busy;
    if (state._step0Status) {
        state._step0Status.className = 'onb-status info';
        state._step0Status.textContent = message || '';
    }
    (state._step0Btns || []).forEach(function(b: any) { (b as HTMLButtonElement).disabled = busy; });
}

async function _chooseWorkspace() {
    if (state.busy) return;
    _step0Busy(true, '正在打开文件夹选择…');
    try {
        var result = await window.api.openWorkspace();
        if (result && result.success) {
            state.workspacePath = result.workspace_path || '';
            goStep(1);
            return;
        }
        _step0Busy(false, (result && result.message) || '未选择文件夹');
    } catch (e) {
        _step0Busy(false, '设置工作区失败：' + ((e as Error) && (e as Error).message || e));
    }
}

async function _chooseSample() {
    if (state.busy) return;
    _step0Busy(true, '正在创建示例库…');
    try {
        var result = await window.api.createSampleWorkspace();
        if (!result || !result.success) {
            _step0Busy(false, (result && result.message) || '创建示例库失败');
            return;
        }
        // 创建为同步 RPC，成功即就绪；仍轮询 get_workspace_status 做就绪确认，
        // 期间展示进度文案（阶段态）。
        var phrases = ['正在复制示例笔记…', '正在初始化目录结构…', '正在激活工作区…'];
        for (var i = 0; i < SAMPLE_POLL_MAX; i++) {
            _step0Busy(true, phrases[i % phrases.length]);
            var ws = null;
            try { ws = await window.api.getWorkspaceStatus(); } catch (e) { ws = null; }
            if (ws && ws.is_set) {
                state.sampleMode = true;
                state.workspacePath = ws.workspace_path || result.workspace_path || '';
                goStep(1);
                return;
            }
            await sleep(1500);
        }
        // 轮询超时但创建 RPC 已成功，按就绪处理
        state.sampleMode = true;
        state.workspacePath = result.workspace_path || '';
        goStep(1);
    } catch (e) {
        _step0Busy(false, '创建示例库失败：' + ((e as Error) && (e as Error).message || e));
    }
}

// ---- Step 1：API Key -------------------------------------------------------

function renderStep1(container: any) {
    container.appendChild(el('div', 'onb-desc',
        '配置一个大模型 API Key（本地加密存储）。也可以先用 Ollama 本地模型，或稍后在设置中补充。'));

    var presets = el('div', 'onb-presets');
    PROVIDER_PRESETS.forEach(function(p) {
        var b = btn('onb-preset-btn', p.label, function() { _applyPreset(p, presets); });
        b.setAttribute('data-preset', p.id);
        presets.appendChild(b);
    });
    container.appendChild(presets);

    var fKey = _field('API Key', 'onb-api-key', 'password', 'sk-...');
    var fBase = _field('API Base', 'onb-api-base', 'text', 'https://api.deepseek.com');
    var fModel = _field('模型名称', 'onb-model-name', 'text', 'deepseek-chat');
    container.appendChild(fKey);
    container.appendChild(fBase);
    container.appendChild(fModel);

    var status = el('div', 'onb-status info', '');
    container.appendChild(status);

    var testBtn = btn('onb-btn', '测试连接', function() { _testApi(status, testBtn); });
    var saveBtn = btn('onb-btn primary', '保存并继续', function() { _saveApi(status, saveBtn); }, true);
    var row = el('div', 'onb-actions-row');
    row.appendChild(testBtn);
    row.appendChild(saveBtn);
    container.appendChild(row);

    container.appendChild(_footer('凭据仅保存在本地加密存储中', '', null, true, false));
    state._apiSaveBtn = saveBtn;
    state._apiStatus = status;

    // 已配置过 Key（例如曾在设置页保存）：允许直接继续
    _prefillApiConfig(status, saveBtn);
}

function _field(label: any, inputId: any, type: any, placeholder: any) {
    var wrap = el('div', 'onb-field');
    var lab = el('label', null, label);
    lab.setAttribute('for', inputId);
    var input = document.createElement('input');
    input.type = type;
    input.id = inputId;
    input.placeholder = placeholder || '';
    input.autocomplete = 'off';
    wrap.appendChild(lab);
    wrap.appendChild(input);
    return wrap;
}

function _applyPreset(preset: any, presetsEl: any) {
    var keyInput = document.getElementById('onb-api-key') as HTMLInputElement | null;
    var baseInput = document.getElementById('onb-api-base') as HTMLInputElement | null;
    var modelInput = document.getElementById('onb-model-name') as HTMLInputElement | null;
    if (baseInput) baseInput.value = preset.apiBase;
    if (modelInput) modelInput.value = preset.modelName;
    if (keyInput) keyInput.placeholder = preset.keyPlaceholder || 'sk-...';
    if (presetsEl) {
        Array.prototype.forEach.call(presetsEl.children, function(b: any) {
            b.classList.toggle('active', b.getAttribute('data-preset') === preset.id);
        });
    }
    state.apiTested = false;
    if (state._apiSaveBtn) state._apiSaveBtn.disabled = true;
    if (state._apiStatus) {
        state._apiStatus.className = 'onb-status info';
        state._apiStatus.textContent = preset.id === 'ollama'
            ? '本地 Ollama：请确认服务已启动（ollama serve），API Key 可填任意 10 位以上字符。'
            : '已填入 ' + preset.label + ' 模板，请填写 API Key 后测试连接。';
    }
}

function _readApiForm() {
    var v = function(id: any) {
        var node = document.getElementById(id) as HTMLInputElement | null;
        return node ? node.value.trim() : '';
    };
    return {
        api_key: v('onb-api-key'),
        api_base: v('onb-api-base') || 'https://api.openai.com/v1',
        model_name: v('onb-model-name') || 'gpt-4'
    };
}

async function _testApi(statusEl: any, testBtn: any) {
    var cfg = _readApiForm();
    if (!cfg.api_key) {
        statusEl.className = 'onb-status err';
        statusEl.textContent = '请先填写 API Key';
        return;
    }
    testBtn.disabled = true;
    statusEl.className = 'onb-status info';
    statusEl.textContent = '正在测试连接…';
    try {
        var result = await window.api.testApiConfig(cfg);
        if (result && result.success) {
            state.apiTested = true;
            statusEl.className = 'onb-status ok';
            statusEl.textContent = '连接成功：' + (result.message || 'OK');
            if (state._apiSaveBtn) state._apiSaveBtn.disabled = false;
        } else {
            state.apiTested = false;
            statusEl.className = 'onb-status err';
            statusEl.textContent = '连接失败：' + ((result && result.message) || '未知错误');
        }
    } catch (e) {
        statusEl.className = 'onb-status err';
        statusEl.textContent = '连接测试异常：' + ((e as Error) && (e as Error).message || e);
    } finally {
        testBtn.disabled = false;
    }
}

async function _saveApi(statusEl: any, saveBtn: any) {
    var cfg = _readApiForm();
    if (!cfg.api_key) {
        statusEl.className = 'onb-status err';
        statusEl.textContent = '请先填写 API Key';
        return;
    }
    saveBtn.disabled = true;
    statusEl.className = 'onb-status info';
    statusEl.textContent = '正在保存并验证…';
    try {
        var result = await window.api.saveApiConfig({
            api_key: cfg.api_key,
            api_base: cfg.api_base,
            model_name: cfg.model_name,
            temperature: 0.7,
            max_tokens: 32000,
            max_context_tokens: 128000,
            disable_thinking: true
        });
        if (result && result.success) {
            goStep(2);
        } else {
            statusEl.className = 'onb-status err';
            statusEl.textContent = '保存失败：' + ((result && result.message) || '未知错误');
            saveBtn.disabled = !state.apiTested;
        }
    } catch (e) {
        statusEl.className = 'onb-status err';
        statusEl.textContent = '保存失败：' + ((e as Error) && (e as Error).message || e);
        saveBtn.disabled = !state.apiTested;
    }
}

async function _prefillApiConfig(statusEl: any, saveBtn: any) {
    try {
        var cfg = await window.api.getApiConfig();
        if (cfg && cfg.api_key_configured) {
            var baseInput = document.getElementById('onb-api-base') as HTMLInputElement | null;
            var modelInput = document.getElementById('onb-model-name') as HTMLInputElement | null;
            if (baseInput && cfg.api_base) baseInput.value = cfg.api_base;
            if (modelInput && cfg.model_name) modelInput.value = cfg.model_name;
            statusEl.className = 'onb-status ok';
            statusEl.textContent = '检测到已保存的 API Key，可直接继续，或输入新 Key 覆盖。';
            saveBtn.disabled = false;
        }
    } catch (e) { /* ignore */ }
}

// ---- Step 2：模型与索引准备（阶段态轮询 + rag_index_built 事件） ------------

function renderStep2(container: any) {
    container.appendChild(el('div', 'onb-desc',
        'NoteAI 正在后台预热检索模型并构建知识库索引，完成后 AI 问答效果最佳。你可以等待就绪，也可以直接进入下一步（后台会继续）。'));

    var modelRow = el('div', 'onb-row');
    modelRow.appendChild(el('span', null, '检索模型（向量 + 重排）'));
    var modelState = el('span', 'onb-row-state', '准备中…');
    modelRow.appendChild(modelState);
    container.appendChild(modelRow);

    var indexRow = el('div', 'onb-row');
    indexRow.appendChild(el('span', null, '知识库索引'));
    var indexState = el('span', 'onb-row-state', state.workspacePath ? '构建中…' : '设置工作区后自动构建');
    indexRow.appendChild(indexState);
    container.appendChild(indexRow);

    var hint = state.sampleMode ? '索引就绪后可体验示范提问' : '索引在后台持续构建，可随时使用';
    container.appendChild(_footer(hint, '继续', _onStep2Next, false, false));

    _startModelPolling(modelState);
    if (state.workspacePath) _startIndexPolling(indexState);
}

function _startModelPolling(stateEl: any) {
    async function poll() {
        try {
            var st = await window.api.getOnboardingStatus();
            state.modelsReady = !!(st && st.models_ready);
        } catch (e) { /* 保持上一状态 */ }
        if (state.modelsReady) {
            stateEl.textContent = '已就绪';
            stateEl.classList.add('ready');
            _stopModelPolling();
        } else {
            stateEl.textContent = '';
            var sp = el('span', 'onb-spinner');
            stateEl.appendChild(sp);
            stateEl.appendChild(document.createTextNode('下载 / 加载中…'));
        }
    }
    poll();
    state.modelTimer = setInterval(poll, MODEL_POLL_MS);
}

function _stopModelPolling() {
    if (state.modelTimer) { clearInterval(state.modelTimer); state.modelTimer = null; }
}

function _startIndexPolling(stateEl: any) {
    async function poll() {
        try {
            var st = await window.api.ragIndexStatus();
            if (st && st.success && st.built) {
                _markIndexReady(st.chunk_count || 0, stateEl);
                _stopIndexPolling();
            } else if (stateEl && !state.indexReady) {
                stateEl.textContent = '';
                stateEl.appendChild(el('span', 'onb-spinner'));
                stateEl.appendChild(document.createTextNode('构建中…'));
            }
        } catch (e) { /* ignore */ }
    }
    poll();
    state.indexTimer = setInterval(poll, INDEX_POLL_MS);
}

function _stopIndexPolling() {
    if (state.indexTimer) { clearInterval(state.indexTimer); state.indexTimer = null; }
}

function _stopPolling() {
    _stopModelPolling();
    _stopIndexPolling();
}

function _markIndexReady(chunkCount: any, stateEl: any) {
    state.indexReady = true;
    state.indexChunkCount = chunkCount || 0;
    var target = stateEl || (state.bodyEl ? state.bodyEl.querySelector('.onb-row:nth-child(3) .onb-row-state') : null);
    if (target) {
        target.textContent = '已就绪（' + state.indexChunkCount + ' 个片段）';
        target.classList.add('ready');
    }
}

function _listenRagEvents() {
    if (state.unlistenRag || typeof window.getTauriEventAPI !== 'function') return;
    var eventAPI = window.getTauriEventAPI();
    if (!eventAPI || typeof eventAPI.listen !== 'function') return;
    try {
        eventAPI.listen('python-event', function(event: any) {
            var data = event && event.payload;
            if (!data || data.type !== 'rag_index_built') return;
            var payload = data.data || data;
            if (payload && payload.success) {
                _markIndexReady(payload.chunk_count || 0, null);
                _stopIndexPolling();
            }
        }).then(function(unlisten: any) {
            state.unlistenRag = unlisten;
        }).catch(function() { /* ignore */ });
    } catch (e) { /* ignore */ }
}

function _onStep2Next() {
    // Step 3（示范提问）仅在示例库路径且索引就绪时展示
    if (state.sampleMode && state.indexReady) {
        goStep(3);
    } else {
        finish(false);
    }
}

// ---- Step 3：示范提问 -------------------------------------------------------

function renderStep3(container: any) {
    container.appendChild(el('div', 'onb-desc',
        '示例库已就绪。试试向 AI 提一个关于示例笔记的问题，体验基于你自己知识库的问答：'));

    container.appendChild(el('div', 'onb-sample-q', '「' + SAMPLE_QUESTION + '」'));

    container.appendChild(_footer('将由 AI 助手面板发起提问', '试试看', function() { finish(true); }, false, false));
}

// ---------------------------------------------------------------------------
// 结束
// ---------------------------------------------------------------------------

function skip() {
    finish(false);
}

async function finish(askSample: any) {
    if (!state.open) return;
    _stopPolling();
    markDoneLocal();
    _destroy();
    try {
        await window.api.markOnboardingDone();
    } catch (e) {
        console.warn('[Onboarding] mark_onboarding_done failed:', e);
    }
    // 刷新主界面（工作区展示 / 文件树）
    try {
        if (window.WorkspaceModule && window.WorkspaceModule.checkWorkspaceStatus) {
            window.WorkspaceModule.checkWorkspaceStatus();
        }
        if (window.TreeModule && window.TreeModule.loadFileTree) {
            window.TreeModule.loadFileTree();
        }
    } catch (e) { /* ignore */ }
    if (askSample && window.AssistantModule && window.AssistantModule.ask) {
        var askFn = window.AssistantModule.ask;
        setTimeout(function() {
            try { askFn(SAMPLE_QUESTION); } catch (e) { console.warn('[Onboarding] sample ask failed:', e); }
        }, 400);
    }
}

window.OnboardingModule = {
    maybeStart: maybeStart,
    open: open,
    skip: skip
};

})();
