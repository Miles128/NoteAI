# UI 框架分析与模块化重构方案

> 分析日期：2026-04-26
> 适用版本：NoteAI 当前版本
> 目标：理清现状问题、给出可执行的改进方案

---

## 一、现状总览

### 1.1 整体架构

```
PySide6 (QMainWindow, FramelessWindowHint)
  └── QWebEngineView (Chromium 内核)
       └── index.html (4221 行单文件 SPA)
            ├── 内联 CSS (~300 行)
            ├── 内联 JS Bridge (~120 行)
            ├── HTML 结构 (~数百行)
            └── 内联 JS 业务逻辑 (~3000+ 行)

通信路径：
  JS ←→ HTTP API (localhost:port/api/method) ←→ Python Api 类
线程保证：
  JSBridge (Qt Signal/Slot) 确保 JS 执行在主线程（仅用于 Python → JS 的通知）
```

### 1.2 通信机制现状

| 方向 | 实现方式 | 说明 |
|------|---------|------|
| JS → Python | `fetch POST /api/method` + JSON 参数 | `SimpleHTTPRequestHandler` 解析并反射调用 `getattr(self._api, methodName)` |
| Python → JS | `MainWindow.evaluate_js()` → `JSBridge.run_js()` → Signal → `QWebEnginePage.runJavaScript()` | 确保线程安全，用于 `updateStatus`、`updateProgress` 等通知 |

---

## 二、pywebview 残留代码（需清理）

项目已确定使用 **PySide6**，但代码中仍保留完整的 pywebview 兼容层，造成大量无效代码和维护负担。

### 2.1 Python 端残留

| 位置 | 残留内容 | 现状 | 建议 |
|------|---------|------|------|
| `webui/app.py:36-40` | `FileDialog` 类（`OPEN_FILE=0`、`OPEN_FILES=1`、`FOLDER=2` 枚举） | 仅被 `create_file_dialog()` 的兼容判断引用，实际上 `MainWindow.create_file_dialog()` 内部直接调用 `QFileDialog` | **可删除** |
| `webui/app.py:816-846` | `create_file_dialog()` 方法内的 `dialog_type` 兼容判断 | 支持 `'folder' / FileDialog.FOLDER / 2` 三种等价形式 | **简化为只接收字符串** |
| `webui/app.py:788-792` | `MainWindow.x` / `MainWindow.y` / `MainWindow.move()` / `MainWindow.attributes['fullscreen']` 等属性/方法 | 按 pywebview 风格设计，供 JS 端 `move_window/minimize_window/maximize_window` 调用 | **可保留但建议统一接口命名** |

### 2.2 JS 端残留

| 位置 | 残留内容 | 影响 |
|------|---------|------|
| `index.html:10-124` | `setup_pywebview_stub()` 兼容桥接 + `pywebviewready` 事件 | ~100 行死代码，初始化时永远走不到「真实 pywebview」分支 |
| `index.html` 中 60+ 处 | `if (!window.pywebview) return;` 防御检查 | 每处 API 调用前都有冗余判断，降低可读性 |
| `index.html` 中 48+ 处 | `window.pywebview.api.xxx()` 调用形式 | 统一走 HTTP API 后可简化为 `window.api.xxx()` |

### 2.3 具体残留调用点（按功能分类）

#### 窗口控制
- `pywebview.api.move_window(accumDx, accumDy)` —— 标题栏拖拽
- `pywebview.api.minimize_window()` / `maximize_window()` / `close_window()` —— 标题栏按钮

#### 主题与配置
- `pywebview.api.save_theme_preference(...)`
- `pywebview.api.get_ui_config()` / `save_ui_config(...)`
- `pywebview.api.get_api_config()` / `save_api_config(...)`

#### 工作区
- `pywebview.api.get_workspace_status()` / `get_workspace_tree()`
- `pywebview.api.open_workspace()` / `on_file_selected(path)`

#### 业务功能
- `pywebview.api.start_web_download(...)`
- `pywebview.api.start_file_conversion(...)`
- `pywebview.api.extract_topics(...)` / `start_note_integration(...)`
- `pywebview.api.add_files()` / `browse_folder()`
- `pywebview.api.refresh_log()`
- `pywebview.api.get_file_preview(path)`
- `pywebview.api.save_file_content(...)`

### 2.4 清理建议

**目标**：完全移除 pywebview 兼容路径，只保留「PySide6 + HTTP API」这一条路径。

| 步骤 | 动作 |
|------|------|
| 1 | 删除 `index.html` 中 `setup_pywebview_stub()` 与 `pywebviewready` 事件逻辑 |
| 2 | 直接暴露 `window.api = { invoke, getWorkspaceStatus, ... }` 或封装为 `js/api.js` 模块 |
| 3 | 将所有 `window.pywebview.api.xxx()` 替换为 `window.api.xxx()`（或模块调用） |
| 4 | 删除所有 `if (!window.pywebview) return;` 检查 |
| 5 | 删除 `webui/app.py` 中 `FileDialog` 类（或只保留最简字符串常量） |
| 6 | 简化 `MainWindow.create_file_dialog()` 的 `dialog_type` 兼容判断逻辑 |

---

## 三、前后端连接框架问题

### 3.1 当前实现

`webui/app.py:938-1060` 的 `_start_http_server_with_api`：

- 使用 Python 标准库 `http.server.SimpleHTTPRequestHandler`
- `_handle_api_post`：读取 JSON body → `json.loads` → `_call_api_method`
- `_call_api_method`：
  - 禁止 `_` 开头的私有方法
  - `getattr(self._api, method_name)` 反射调用
  - `args` 既支持数组位置参数 `method(*args)`，也支持字典关键字参数 `method(**args)`

### 3.2 存在的问题

| 问题 | 位置 | 风险 |
|------|------|------|
| **无类型校验** | `_call_api_method` | 参数顺序/类型错误只会在运行时报错，且 JS 端难以定位原因 |
| **无统一契约** | JS 与 Python 分散调用 | 新增 API 时容易漏加 `api_methods` 列表或参数不匹配 |
| **错误处理不统一** | JS 端每处 `await ...` 各自写 try/catch | 网络错误、500、业务错误（`success: false`）处理不一致 |
| **超时无统一控制** | JS 端仅 `get_workspace_tree` 有 `Promise.race` 超时 | 其他 API 可能永久 pending |

### 3.3 改进建议

#### 方案：统一 API 封装层

**Python 侧**（可选但推荐）：
- 定义一个 `API_SCHEMA` 字典，描述每个方法的参数名、类型、必填
- `_call_api_method` 按 schema 校验后再调用

**JS 侧**（建议优先做）：
- 新建 `js/api.js`：
  - 统一 `fetch POST /api/method`
  - 统一超时（如 30 秒）
  - 统一错误类型区分：网络错误 / HTTP 500 / 业务错误（`success: false`）
  - 统一弹窗/日志策略

示例接口形态：

```javascript
// js/api.js
window.api = {
  async invoke(methodName, params = {}) {
    // 统一 fetch、超时、错误解析
  },

  // 业务方法（可选，也可以让业务模块直接用 invoke）
  async openWorkspace() { return this.invoke('open_workspace'); },
  async getWorkspaceStatus() { return this.invoke('get_workspace_status'); },
  // ...
};
```

**优点**：
- 所有 API 调用点不再关心「超时、fetch 选项、错误解析」
- 未来要加请求日志、重试策略、mock 都只改一处
- Python 侧参数变化时，JS 侧有统一的适配层

---

## 四、可提取的重复调用与状态

### 4.1 API 调用重复

| 调用模式 | 出现次数 | 提取建议 |
|---------|---------|---------|
| `await window.pywebview.api.xxx()` | ~17 处 | 统一封装进 `js/api.js`，带超时和错误处理 |
| `if (!window.pywebview) return;` | ~60 处 | 清理 pywebview 兼容层后删除 |
| `get_api_config()` / `save_api_config()` | 3 次+ | 封装成 `state.js` 中的 `apiConfig` 模块，带缓存 |
| `get_ui_config()` / `save_ui_config()` | 2 次+ | 同上，封装进 `uiConfig` 模块 |
| `get_workspace_status()` / `get_workspace_tree()` | 多处 | 封装进 `workspace.js` |

### 4.2 全局状态与重复逻辑

| 状态/逻辑 | 位置 | 问题 | 提取建议 |
|-----------|------|------|---------|
| `window.mdEditor` 对象 | `index.html:2464` 开始 | 污染 `window`，与 UI 渲染、预览滚动、保存逻辑耦合在一起 | 提取为 `js/editor.js` 模块，通过事件/回调与外部通信 |
| 文件树展开状态 `treeExpandedState` / `saveTreeState()` | 与 `renderFileTree()` 混在同一作用域 | 状态管理与渲染逻辑不清 | 提取为 `js/tree.js` |
| `updateStatus()` / `updateProgress()` | 散落各处 | UI 通知与业务逻辑混杂 | 提取为 `js/toast.js` 或 `js/ui.js` |
| `escapeHtml()` / `formatFileSize()` / `formatModifiedTime()` | 全局工具函数 | 与业务逻辑混合 | 提取为 `js/utils.js` |

### 4.3 Tab 与视图切换

当前：
- `switchTab(tabIndex)` 负责切换 `tab-btn.active`、`tab-content.active`、`contentPanel/previewPanel` 显示状态、标题文本
- `showContentView()` / `showPreviewView()` 直接操作 `display: flex/none`

问题：
- 切换逻辑与具体 DOM ID 强绑定
- 未来新增「对话面板」「播客面板」等视图时改动成本高

建议：
- 提取 `js/tabs.js` 或 `js/navigation.js`
- 用「视图名/路由名 + 对应 selector」的配置驱动
- 提供 `navigate(viewName)` 统一入口

---

## 五、`index.html` 单文件模块化拆分方案

### 5.1 问题诊断

| 维度 | 现状 | 危害 |
|------|------|------|
| **文件大小** | 4221 行，HTML/CSS/JS 全部内联 | 定位慢、阅读累 |
| **Git diff** | 所有改动都在一个文件 | 冲突风险高、review 困难 |
| **命名空间** | 所有函数/变量在全局作用域 | 容易意外覆盖、难以追踪依赖 |
| **职责边界** | 编辑器、文件树、Tab、API、样式混在一起 | 修改一个功能可能影响不相关代码 |

### 5.2 方案原则

- **不引入构建工具**：PySide6 `QWebEngineView` 支持直接加载本地 `.css` / `.js` 文件，无需 Vite/Webpack
- **渐进式拆分**：先拆大模块，再细拆，避免一次性全量重构
- **保持功能不变**：拆分后行为与拆分前一致，只做结构优化

### 5.3 推荐目录结构

```
webui/
├── index.html                    # 仅 HTML 骨架（约 500-800 行）
├── css/
│   ├── variables.css             # CSS 变量、主题定义（深色/浅色）
│   ├── layout.css                # 整体布局：标题栏、侧边栏、主区域、状态栏
│   ├── components.css            # 通用组件：按钮、卡片、输入框、进度条、弹窗
│   ├── editor.css                # CodeMirror 编辑器与双栏预览专用样式
│   ├── tree.css                  # 文件树样式（缩进、图标、展开/收起）
│   └── tabs.css                  # Tab 切换与视图显示/隐藏相关样式
├── js/
│   ├── utils.js                  # 纯工具：escapeHtml、formatFileSize、formatModifiedTime
│   ├── api.js                    # HTTP API 统一封装（超时、错误处理、参数解析）
│   ├── state.js                  # 全局状态管理：apiConfig、uiConfig、workspaceState
│   ├── tabs.js                   # Tab 与视图切换（可扩展为简单路由）
│   ├── toast.js                  # 统一通知：updateStatus、updateProgress
│   ├── tree.js                   # 文件树：渲染、展开/收起、选中、状态持久化
│   ├── preview.js                # 文件预览：MD/TXT/PDF/DOCX 渲染逻辑
│   ├── editor.js                 # Markdown 编辑器：CodeMirror 初始化、自动保存、滚动同步
│   ├── workspace.js              # 工作区：打开、状态检查、更新显示、刷新树
│   ├── downloader.js             # 网页下载 Tab 逻辑（URL 解析、进度回调、结果展示）
│   ├── converter.js              # 文件转换 Tab 逻辑
│   ├── integrator.js             # 笔记整合 Tab 逻辑（提取主题、开始整合）
│   ├── settings.js               # 设置 Tab 逻辑（API 配置、UI 配置、主题切换、日志）
│   └── app.js                    # 入口：DOM 就绪 → 初始化顺序 → 事件绑定
└── codemirror-bundle.mjs         # 现有资源，无需改动
```

### 5.4 模块职责与依赖关系

按初始化顺序排列：

```
1) utils.js        —— 无依赖，纯函数
2) api.js          —— 依赖 utils（可选），封装 fetch/超时/错误
3) state.js        —— 依赖 api.js，负责加载/保存/订阅配置状态
4) tabs.js         —— 独立或仅依赖 DOM，负责视图切换
5) toast.js        —— 独立或仅依赖 DOM，负责状态通知
6) tree.js         —— 依赖 api.js（获取树数据）、state.js（工作区路径）
7) preview.js      —— 依赖 api.js（get_file_preview）、toast.js（错误提示）
8) editor.js       —— 依赖 api.js（save_file_content）、preview.js（同步预览）、toast.js
9) workspace.js    —— 依赖 api.js、state.js、tree.js
10) downloader.js   —— 依赖 api.js、toast.js、workspace.js（保存路径）
11) converter.js    —— 依赖 api.js、toast.js、workspace.js
12) integrator.js   —— 依赖 api.js、toast.js、workspace.js
13) settings.js     —— 依赖 api.js、state.js、toast.js
14) app.js          —— 依赖所有模块，负责编排初始化顺序、绑定全局事件
```

### 5.5 模块间通信方式（轻量级）

不需要 Redux/Vuex，建议用以下组合：

| 场景 | 方案 |
|------|------|
| **全局配置变更** | `state.js` 提供 `subscribe(fn)`，相关模块监听变化后自行更新 UI |
| **文件选中** | `tree.js` 提供 `onFileSelect(callback)`，或触发自定义事件 `noteai:file-selected` |
| **编辑器保存** | `editor.js` 内部完成保存后，用 `toast.js` 通知或触发事件 |
| **工作区切换** | `workspace.js` 调用 `tree.js.refresh()`、`state.js.save()`，或广播事件 |

自定义事件示例（解耦）：

```javascript
// 发送方
window.dispatchEvent(new CustomEvent('noteai:file-selected', {
  detail: { path, name }
}));

// 接收方
window.addEventListener('noteai:file-selected', (e) => {
  const { path, name } = e.detail;
  preview.js.loadFilePreview(path, name);
});
```

### 5.6 拆分后 `index.html` 骨架形态

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NoteAI</title>

    <!-- 样式加载顺序：变量 → 布局 → 组件 → 各模块专用样式 -->
    <link rel="stylesheet" href="css/variables.css">
    <link rel="stylesheet" href="css/layout.css">
    <link rel="stylesheet" href="css/components.css">
    <link rel="stylesheet" href="css/editor.css">
    <link rel="stylesheet" href="css/tree.css">
    <link rel="stylesheet" href="css/tabs.css">

    <!-- 外部库（如 marked、highlight.js）仍可以 CDN 或本地文件方式引入 -->
</head>
<body>
    <!-- HTML 结构与原来基本一致，只保留 DOM 骨架 -->
    <div class="app-container">
        <div class="custom-titlebar">
            <!-- 标题、工作区按钮、Tab 按钮、窗口控制按钮 -->
        </div>
        <div class="main-layout">
            <div class="sidebar">
                <div id="file-tree"></div>
            </div>
            <div class="content-area">
                <div id="content-panel" class="panel">
                    <!-- 各 Tab 内容容器 -->
                    <div class="tab-content active" data-tab="web">...</div>
                    <div class="tab-content" data-tab="file">...</div>
                    <div class="tab-content" data-tab="note">...</div>
                    <div class="tab-content" data-tab="settings">...</div>
                    <div class="tab-content" data-tab="log">...</div>
                </div>
                <div id="preview-panel" class="panel" style="display:none;">
                    <div id="cm-editor-container"></div>
                    <div id="preview-content"></div>
                </div>
            </div>
        </div>
        <div class="status-bar">
            <span id="status-bar"></span>
        </div>
    </div>

    <!-- JS 加载顺序：工具 → 基础设施 → 业务模块 → 入口 -->
    <script src="js/utils.js"></script>
    <script src="js/api.js"></script>
    <script src="js/state.js"></script>
    <script src="js/tabs.js"></script>
    <script src="js/toast.js"></script>
    <script src="js/tree.js"></script>
    <script src="js/preview.js"></script>
    <script src="js/editor.js"></script>
    <script src="js/workspace.js"></script>
    <script src="js/downloader.js"></script>
    <script src="js/converter.js"></script>
    <script src="js/integrator.js"></script>
    <script src="js/settings.js"></script>
    <script src="js/app.js"></script>
</body>
</html>
```

**关键点**：
- DOM 结构基本不变，减少重构风险
- `<script>` 按依赖顺序同步加载（`app.js` 最后加载并执行初始化）
- 不再需要 `pywebviewready` 事件，直接在 `app.js` 中 `DOMContentLoaded` 初始化

### 5.7 关键模块示例设计

#### 5.7.1 `js/api.js`（统一 HTTP API）

```javascript
// js/api.js
(function() {
    const API_PORT = (new URLSearchParams(window.location.search)).get('port') || window.location.port;
    const BASE_URL = `http://localhost:${API_PORT}`;
    const DEFAULT_TIMEOUT = 30000;

    async function invoke(methodName, args = []) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT);

        try {
            const res = await fetch(`${BASE_URL}/api/${methodName}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(args),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!res.ok) {
                throw new Error(`API 请求失败: ${res.status}`);
            }

            const data = await res.json();
            return data;
        } catch (e) {
            clearTimeout(timeoutId);
            if (e.name === 'AbortError') {
                throw new Error('请求超时');
            }
            throw e;
        }
    }

    // 常用业务方法封装（可选，也可以让各模块直接用 invoke）
    window.api = {
        invoke,
        getWorkspaceStatus: () => invoke('get_workspace_status'),
        openWorkspace: () => invoke('open_workspace'),
        getWorkspaceTree: () => invoke('get_workspace_tree'),
        getApiConfig: () => invoke('get_api_config'),
        saveApiConfig: (config) => invoke('save_api_config', [config]),
        getUiConfig: () => invoke('get_ui_config'),
        saveUiConfig: (cfg) => invoke('save_ui_config', [cfg]),
        getThemePreference: () => invoke('get_theme_preference'),
        saveThemePreference: (theme) => invoke('save_theme_preference', [theme]),
        startWebDownload: (urls, aiAssist, includeImages) =>
            invoke('start_web_download', [urls, aiAssist, includeImages]),
        startFileConversion: (aiAssist) =>
            invoke('start_file_conversion', [aiAssist]),
        extractTopics: (topicCount) =>
            invoke('extract_topics', [topicCount]),
        startNoteIntegration: (autoTopic, topics) =>
            invoke('start_note_integration', [autoTopic, topics]),
        refreshLog: () => invoke('refresh_log'),
        getFilePreview: (path) => invoke('get_file_preview', [path]),
        saveFileContent: (path, content) =>
            invoke('save_file_content', [path, content]),
        addFiles: () => invoke('add_files'),
        browseFolder: () => invoke('browse_folder'),
        onFileSelected: (path) => invoke('on_file_selected', [path]),
        clearSavedWorkspace: () => invoke('clear_saved_workspace'),
        showAbout: () => invoke('show_about'),
    };
})();
```

#### 5.7.2 `js/state.js`（状态管理与订阅）

```javascript
// js/state.js
(function() {
    const state = {
        apiConfig: null,
        uiConfig: null,
        themePreference: null,
        workspacePath: null,
        _subscribers: []
    };

    function subscribe(fn) {
        state._subscribers.push(fn);
        return () => {
            state._subscribers = state._subscribers.filter(s => s !== fn);
        };
    }

    function notify() {
        state._subscribers.forEach(fn => fn(state));
    }

    async function loadAll() {
        const [apiConfig, uiConfig, themePref] = await Promise.all([
            window.api.getApiConfig(),
            window.api.getUiConfig(),
            window.api.getThemePreference()
        ]);
        state.apiConfig = apiConfig;
        state.uiConfig = uiConfig;
        state.themePreference = themePref;
        notify();
    }

    async function saveUiConfig(cfg) {
        const [success, message] = await window.api.saveUiConfig(cfg);
        if (success) {
            state.uiConfig = { ...state.uiConfig, ...cfg };
            notify();
        }
        return { success, message };
    }

    async function saveThemePreference(theme) {
        await window.api.saveThemePreference(theme);
        state.themePreference = theme;
        notify();
    }

    window.state = {
        get: () => ({ ...state }),
        loadAll,
        subscribe,
        saveUiConfig,
        saveThemePreference
    };
})();
```

#### 5.7.3 `js/toast.js`（统一 UI 通知）

```javascript
// js/toast.js
(function() {
    function updateStatus(text) {
        const el = document.getElementById('status-bar');
        if (el) el.textContent = text;
    }

    function updateProgress(elementId, progress, text) {
        const fill = document.getElementById(elementId + '-fill');
        const statusEl = document.getElementById(elementId.replace('progress', 'status'));
        if (fill) fill.style.width = `${progress * 100}%`;
        if (statusEl) statusEl.textContent = text;
    }

    // 可以扩展 toast 弹窗、error modal 等

    window.toast = {
        updateStatus,
        updateProgress
    };
})();
```

#### 5.7.4 `js/workspace.js`（工作区逻辑）

```javascript
// js/workspace.js
(function() {
    async function openWorkspace() {
        const result = await window.api.openWorkspace();
        if (result.success) {
            window.toast.updateStatus(result.message);
            // 通知其他模块刷新（例如通过事件或显式调用 tree/preview）
            window.dispatchEvent(new CustomEvent('noteai:workspace-changed', {
                detail: { workspacePath: result.workspace_path }
            }));
        }
        return result;
    }

    async function checkAndUpdateDisplay() {
        const status = await window.api.getWorkspaceStatus();
        const container = document.getElementById('workspace-container');
        const titleDisplay = document.getElementById('workspace-name-display');

        if (titleDisplay) {
            if (status.is_set && status.workspace_path) {
                const name = status.workspace_path.split(/[/\\]/).pop();
                titleDisplay.textContent = name;
            } else {
                titleDisplay.textContent = '';
            }
        }

        if (container) {
            if (status.is_set && status.workspace_path) {
                container.innerHTML = `
                    <div class="workspace-folder-display">
                        <span class="workspace-path">${escapeHtml(status.workspace_path)}</span>
                    </div>
                `;
            } else {
                // 显示打开工作区按钮（或交给 app.js 绑定事件）
            }
        }
    }

    window.workspace = {
        openWorkspace,
        checkAndUpdateDisplay
    };
})();
```

#### 5.7.5 `js/app.js`（入口初始化）

```javascript
// js/app.js
(function() {
    function initApp() {
        // 1. 初始化主题（可从 state 或 CSS 变量逻辑）
        // 2. 绑定全局事件（Tab 切换、标题栏按钮等）
        // 3. 加载状态与工作区
        // 4. 绑定业务 Tab 按钮事件

        // 示例：恢复工作区与刷新文件树
        window.state.loadAll().then(() => {
            window.workspace.checkAndUpdateDisplay();
            // 触发文件树刷新等
        }).catch(e => {
            console.error('初始化加载状态失败', e);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initApp);
    } else {
        initApp();
    }
})();
```

---

## 六、对 Python 后端的同步调整建议

| 位置 | 现状 | 建议 |
|------|------|------|
| `FileDialog` 类 | 模仿 pywebview 枚举，实际只被 `create_file_dialog` 兼容判断使用 | **删除**或仅保留最简常量（如 `FOLDER='folder'`） |
| `create_file_dialog` 的 `dialog_type` 参数处理 | 支持 `'folder' / FileDialog.FOLDER / 2` 三种等价形式 | 统一为只接收字符串（`'folder'`、`'open_file'`、`'open_files'`） |
| `MainWindow.x` / `MainWindow.y` / `MainWindow.attributes` | 按 pywebview 风格设计的属性访问 | 如无外部依赖可保留；建议将来逐步改为更直接的方法命名 |
| `Api` 类中 `self.window.create_file_dialog` 使用方式 | 与 `MainWindow.create_file_dialog` 强耦合 | 保持现状即可，这层抽象在「窗口/原生对话框」上是合理的 |

**额外建议**：
- 可在 Python 侧增加一个 `api_methods` 或 `API_SCHEMA` 的显式声明，明确哪些方法可被 JS 调用
- 这样 `_call_api_method` 可以拒绝未声明的方法，减少意外暴露风险

---

## 七、实施路线与优先级

### 7.1 阶段划分

| 阶段 | 任务 | 工作量评估 | 预期收益 |
|------|------|-----------|---------|
| **P0 清理** | 删除 pywebview 兼容层（JS 端 stub + 60+ 处检查 + Python `FileDialog` 冗余判断） | 中 | 代码量-15%，可读性显著提升，Git diff 更干净 |
| **P0 封装** | 提取 `js/api.js`（统一 HTTP 调用、超时、错误解析） + 配套 `js/toast.js` | 小 | 消除 `await window.pywebview.api.xxx` 重复模式，统一错误处理 |
| **P1 状态管理** | 提取 `js/state.js`，将 `apiConfig`/`uiConfig`/`theme` 的加载/保存/订阅集中管理 | 小-中 | 不再反复调用 `get_api_config`，新增配置项时改动更集中 |
| **P1 模块化拆分** | 按「工具/树/预览/编辑器/工作区/各 Tab」拆分 CSS 和 JS | 中 | Git diff 干净、职责清晰、可多人协作，新增功能耦合低 |
| **P2 解耦与可扩展性** | 引入轻量事件总线（CustomEvent）、简化 Tab/路由、规范化 API 契约 | 中 | 未来新增「RAG 对话、播客、脑图」等功能时成本大幅降低 |

### 7.2 推荐实施顺序

1. **先做 P0 清理**：pywebview 残留是「技术债中的技术债」，越早清理越不容易在新增功能中继续扩散兼容逻辑
2. **再做 P0 封装**：`api.js` + `toast.js` 可以在不改变行为的前提下，为后续拆分提供稳定的基础设施
3. **再做 P1 状态管理**：`state.js` 可以让各业务模块（下载/转换/整合/设置）不再直接关心「配置怎么加载保存」
4. **最后做模块化拆分**：在稳定的 api/state/toast 之上拆分业务模块，风险更低

### 7.3 验证策略

- 每一步拆分后做「功能回归」：打开工作区、网页下载、文件转换、提取主题、笔记整合、文件预览/编辑保存、主题切换等核心路径
- 注意：`window.mdEditor` 相关逻辑较多，建议最后拆分 `editor.js`，并重点测试「滚动同步、自动保存、CodeMirror 降级 textarea」

---

## 八、总结

当前 UI 框架的核心问题不是「技术选型」（PySide6 + QWebEngineView + HTML/JS 本身是合理的），而是：

1. **pywebview 兼容层残留**：带来大量死代码和防御性检查
2. **API 调用不统一**：超时、错误处理、重复 `get_api_config` 等问题
3. **单文件巨石**：4221 行 `index.html` 导致 Git diff 噪音高、协作困难、命名空间污染

**解决方案要点**：
- **清理兼容层**：彻底走 PySide6 + HTTP API 一条路径
- **统一 API 封装**：`js/api.js` + `js/state.js` + `js/toast.js`
- **模块化拆分**：按职责拆分为多个 `.css` 和 `.js` 文件，不依赖构建工具
- **轻量通信**：CustomEvent 事件总线 + 状态订阅，避免重型状态管理框架

这样改造后：
- 代码量会先增加（拆成多文件），但可读性和可维护性显著提升
- Git diff 会变得更有意义（改哪个模块就改哪个文件）
- 未来加 RAG 对话、播客生成等新功能时，只需新增对应模块文件，不易影响已有逻辑
