# NoteAI 前端架构设计文档

## 1. 项目概述

NoteAI 是一个基于 PySide6 QtWebEngine 的桌面应用，采用 HTML/CSS/JS 前端技术栈。本文档记录了前端架构的重构方案，包括模块化拆分、pywebview 兼容层清理等内容。

### 1.1 重构前的问题

- **单文件过大**：原 `index.html` 超过 4200 行，包含 CSS、JS 和 HTML，难以维护
- **pywebview 兼容层冗余**：JS 端有 pywebview stub，Python 端有 FileDialog 兼容判断
- **API 调用不统一**：没有统一的 HTTP 调用封装，错误处理和超时控制分散
- **状态管理分散**：API 配置、UI 配置、主题偏好等状态分散在各处

### 1.2 重构目标

1. 删除 pywebview 兼容层（JS + Python）
2. 模块化拆分 CSS 和 JS
3. 统一 API 调用封装（超时、错误处理）
4. 集中状态管理
5. 编写测试用例验证

---

## 2. 架构变更

### 2.1 删除 pywebview 兼容层

#### JS 端（已删除）

原 `index.html` 第 8-124 行的 pywebview stub 已删除：

```javascript
// 已删除的代码：
(function() {
    var is_initialized = false;
    var http_port = null;
    var api_methods = [...];
    // ... pywebview 兼容层代码
})();
```

#### Python 端（已清理）

已删除/简化的代码：

| 原代码 | 处理方式 |
|--------|----------|
| `FileDialog` 枚举类 | 已删除，改用字符串常量 |
| `FileDialog.FOLDER` | 改为 `'folder'` |
| `FileDialog.OPEN_FILES` | 改为 `'open_files'` |
| `attributes` 属性 | 已删除（pywebview 风格） |
| `set_fullscreen` 方法 | 已删除 |
| `create_file_dialog` 中的兼容判断 | 简化为只支持字符串 |

### 2.2 通信机制

**当前（以仓库为准）**：Tauri `invoke('py_call')` → Python sidecar（`python/main.py`，stdin/stdout JSON）。  
**已废弃**：`webui/app.py` 提供的本地 HTTP + `/api/`（仅供历史脚本，勿再扩展）。

历史文档曾描述 Qt/pywebview 下的：

```
JS (fetch POST) → Python (HTTP API) → JS (QWebEnginePage.runJavaScript)
```

该路径已不再作为正式架构。

---

## 3. 模块化方案

### 3.1 文件结构

```
webui/
├── index.html              # 骨架 HTML（约 490 行）
├── test-modules.html       # 模块测试页面
├── css/
│   ├── variables.css       # CSS 变量和主题
│   ├── layout.css          # 布局样式
│   ├── components.css      # 组件样式
│   ├── tree.css            # 文件树样式
│   ├── editor.css          # 编辑器样式
│   └── preview.css         # 预览面板样式
└── js/
    ├── utils.js            # 工具函数
    ├── api.js              # API 调用封装
    ├── state.js            # 状态管理
    ├── toast.js            # 通知系统
    ├── tabs.js             # Tab 切换
    ├── theme.js            # 主题切换
    ├── tree.js             # 文件树
    ├── preview.js          # 文件预览
    ├── editor.js           # Markdown 编辑器
    ├── workspace.js        # 工作区管理
    ├── downloader.js       # 网页下载
    ├── converter.js        # 文件转换
    ├── integrator.js       # 笔记整合
    ├── settings.js         # 设置面板
    └── app.js              # 入口初始化
```

### 3.2 加载顺序

```html
<!-- CSS 模块 -->
<link rel="stylesheet" href="css/variables.css">
<link rel="stylesheet" href="css/layout.css">
<link rel="stylesheet" href="css/components.css">
<link rel="stylesheet" href="css/tree.css">
<link rel="stylesheet" href="css/editor.css">
<link rel="stylesheet" href="css/preview.css">

<!-- 核心 JS 模块（基础依赖） -->
<script src="js/utils.js"></script>
<script src="js/api.js"></script>
<script src="js/state.js"></script>
<script src="js/toast.js"></script>
<script src="js/tabs.js"></script>

<!-- 业务 JS 模块 -->
<script src="js/theme.js"></script>
<script src="js/tree.js"></script>
<script src="js/preview.js"></script>
<script src="js/editor.js"></script>
<script src="js/workspace.js"></script>
<script src="js/downloader.js"></script>
<script src="js/converter.js"></script>
<script src="js/integrator.js"></script>
<script src="js/settings.js"></script>

<!-- 入口模块（最后加载） -->
<script src="js/app.js"></script>
```

---

## 4. 核心模块说明

### 4.1 utils.js - 工具函数

提供通用工具函数，封装在 `window.utils` 对象中。

```javascript
window.utils = {
    escapeHtml,           // HTML 转义
    formatFileSize,       // 文件大小格式化
    formatFileSizeForTree, // 文件树专用格式化
    formatModifiedTime    // 时间戳格式化
};
```

### 4.2 api.js - API 调用封装

统一 HTTP API 调用，包含超时控制、错误处理。

#### 主要功能

1. **端口检测**：从 URL 参数或 `window.location.port` 获取端口
2. **统一调用**：`invokeApi(methodName, args, timeout)`
3. **超时控制**：默认 10 秒超时
4. **错误处理**：网络错误、HTTP 错误、JSON 解析错误

#### API 方法列表

通过 `window.api` 对象暴露：

```javascript
window.api = {
    // 窗口控制
    move_window, minimize_window, maximize_window, close_window,
    
    // 工作区
    get_workspace_status, check_workspace_path_valid, clear_saved_workspace,
    update_window_title, open_workspace,
    
    // API 配置
    get_api_config, save_api_config,
    
    // UI 配置
    get_ui_config, save_ui_config,
    
    // 文件操作
    browse_folder, add_files,
    
    // 状态通知
    update_status, update_progress, show_message,
    
    // 网页下载
    start_web_download,
    
    // 文件转换
    start_file_conversion,
    
    // 笔记整合
    extract_topics, start_note_integration,
    
    // 主题
    get_theme_preference, save_theme_preference,
    
    // 文件树
    get_workspace_tree, on_file_selected,
    
    // 文件预览
    get_file_preview, can_preview_file,
    
    // 编辑器
    save_file_content,
    
    // 其他
    show_about, refresh_log
};
```

#### 调用示例

```javascript
// 基础调用
const result = await window.api.open_workspace();

// 带参数
const files = await window.api.add_files();

// 错误处理
try {
    const result = await window.api.start_web_download(urls, options);
} catch (error) {
    console.error('下载失败:', error);
    showToast('下载失败: ' + error.message);
}
```

### 4.3 state.js - 状态管理

集中管理应用状态，支持状态监听。

#### 状态内容

```javascript
// 内部状态
_state = {
    apiConfig: null,        // API 配置
    uiConfig: null,         // UI 配置
    themePreference: null,  // 主题偏好
    workspacePath: null,    // 工作区路径
    _subscribers: []        // 订阅者列表
};
```

#### 暴露的全局变量

为了兼容现有代码，同时暴露以下全局变量：

```javascript
window.apiConfig        // getter，返回 _state.apiConfig
window.uiConfig         // getter，返回 _state.uiConfig
window.themePreference  // getter，返回 _state.themePreference
```

#### 暴露的函数

```javascript
window.state = {
    get,              // 获取状态副本
    subscribe,        // 订阅状态变化
    loadAllConfig,    // 加载所有配置
    loadApiConfig,    // 加载 API 配置
    loadUiConfig,     // 加载 UI 配置
    loadThemePreference, // 加载主题偏好
    saveApiConfig,    // 保存 API 配置
    saveUiConfig,     // 保存 UI 配置
    saveThemePreference, // 保存主题偏好
    setWorkspacePath  // 设置工作区路径
};

// 兼容函数
window.subscribeToState   // 等同于 window.state.subscribe
window.notifyStateChange  // 触发状态通知
```

### 4.4 toast.js - 通知系统

提供状态更新和进度显示功能。

```javascript
// 更新状态栏文本
updateStatus(message);

// 更新进度条
updateProgress(progress, message);
// progress: 0-100 或特殊值
//   -1: 隐藏进度条
//   -2: 仅显示文本（无限进度）
```

### 4.5 tabs.js - Tab 切换

管理三个功能 Tab 的切换。

```javascript
// 切换 Tab
switchTab(tabIndex);
// tabIndex: 0=下载, 1=转换, 2=整合

// 初始化 Tab（DOMContentLoaded 时自动调用）
initTabs();
```

---

## 5. 业务模块说明

### 5.1 theme.js - 主题管理

```javascript
window.ThemeModule = {
    toggleTheme,           // 切换深色/浅色
    setTheme,              // 设置指定主题 ('light'|'dark'|'system')
    applySystemTheme,      // 应用系统主题
    initSystemThemeListener, // 初始化系统主题监听
    applyTheme,            // 应用主题
    restoreSidebarWidth,   // 恢复侧边栏宽度
    initResizer,           // 初始化侧边栏调整器
    initPreviewResizer,    // 初始化预览面板调整器
    showAboutPanel,        // 显示关于面板
    hideAboutPanel         // 隐藏关于面板
};

// 全局函数（兼容现有代码）
toggleTheme(), setTheme(), showAbout(), closeAboutPanel()
```

### 5.2 tree.js - 文件树

```javascript
window.TreeModule = {
    loadWorkspaceTree,     // 加载工作区树
    renderTree,            // 渲染树结构
    toggleFolder,          // 切换文件夹展开/折叠
    selectFile,            // 选择文件
    refreshTree,           // 刷新树
    expandAll,             // 展开所有
    collapseAll,           // 折叠所有
    saveExpandedState,     // 保存展开状态
    restoreExpandedState   // 恢复展开状态
};

// 全局函数
onFileSelected(), handleFileSelection()
```

### 5.3 preview.js - 文件预览

```javascript
window.PreviewModule = {
    showPreviewPanel,      // 显示预览面板
    closePreviewPanel,     // 关闭预览面板
    loadFilePreview,       // 加载文件预览
    renderMarkdownPreview, // 渲染 Markdown 预览
    renderCodePreview,     // 渲染代码预览
    renderImagePreview,    // 渲染图片预览
    renderPdfPreview,      // 渲染 PDF 预览
    renderGenericPreview   // 渲染通用预览
};

// 全局函数
closePreviewPanel(), toggleEditMode()
```

### 5.4 editor.js - Markdown 编辑器

```javascript
window.EditorModule = {
    initEditor,            // 初始化编辑器
    loadContent,           // 加载内容
    getContent,            // 获取内容
    saveContent,           // 保存内容
    updateEditorTheme,     // 更新编辑器主题
    syncScroll,            // 同步滚动
    updatePreview          // 更新预览
};

// 全局函数
toggleEditMode(), saveEditorContent()
```

### 5.5 workspace.js - 工作区管理

```javascript
window.WorkspaceModule = {
    openWorkspace,         // 打开工作区
    checkWorkspaceStatus,  // 检查工作区状态
    setupWorkspaceUI       // 设置工作区 UI
};

// 全局函数
openWorkspace(), browse_folder(), add_files()
```

### 5.6 downloader.js - 网页下载

```javascript
window.DownloaderModule = {
    startWebDownload,      // 开始网页下载
    updateWebAIStatus,     // 更新 AI 状态
    updateWebImageStatus   // 更新图片状态
};

// 全局函数
startWebDownload(), updateWebAIStatus(), updateWebImageStatus()
```

### 5.7 converter.js - 文件转换

```javascript
window.ConverterModule = {
    startFileConversion,   // 开始文件转换
    updateConvAIStatus     // 更新 AI 状态
};

// 全局函数
startFileConversion(), updateConvAIStatus()
```

### 5.8 integrator.js - 笔记整合

```javascript
window.IntegratorModule = {
    extractTopics,         // 提取主题
    startNoteIntegration,  // 开始笔记整合
    updateIntegrateBtnState // 更新整合按钮状态
};

// 全局函数
extractTopics(), startNoteIntegration(), updateIntegrateBtnState()
```

### 5.9 settings.js - 设置面板

```javascript
window.SettingsModule = {
    showSettingsPanel,     // 显示设置面板
    closeSettingsPanel,    // 关闭设置面板
    loadSettings,          // 加载设置
    saveApiConfig,         // 保存 API 配置
    showLogPanel,          // 显示日志面板
    closeLogPanel,         // 关闭日志面板
    refreshLog             // 刷新日志
};

// 全局函数
showSettings(), closeSettingsPanel(), saveApiConfig()
showLog(), closeLogPanel(), refreshLog()
```

### 5.10 app.js - 入口模块

应用初始化入口，在 `DOMContentLoaded` 时执行：

```javascript
// 初始化顺序
1. applyTheme()           // 应用主题
2. initResizer()          // 初始化侧边栏调整器
3. initPreviewResizer()   // 初始化预览面板调整器
4. initTabs()             // 初始化 Tab
5. initSystemThemeListener() // 初始化系统主题监听
6. checkWorkspaceStatus() // 检查工作区状态
7. state.loadAllConfig()  // 加载所有配置
```

---

## 6. CSS 模块说明

### 6.1 variables.css - CSS 变量和主题

定义浅色/深色/系统主题的 CSS 变量。

```css
/* 浅色主题变量 */
:root {
    --bg: #f5f5f7;
    --sidebar-bg: rgba(246, 246, 248, 0.88);
    --surface: rgba(255, 255, 255, 0.92);
    --text: #1d1d1f;
    --text-muted: #86868b;
    --primary: #007AFF;
    /* ... 更多变量 */
}

/* 深色主题变量 */
[data-theme="dark"] {
    --bg: #1c1c1e;
    --sidebar-bg: rgba(28, 28, 30, 0.88);
    --surface: rgba(44, 44, 46, 0.92);
    --text: #f5f5f7;
    /* ... 更多变量 */
}
```

### 6.2 layout.css - 布局样式

```css
/* 标题栏 */
.custom-titlebar { ... }
.titlebar-drag { ... }
.titlebar-controls { ... }

/* 主容器 */
.app-container { ... }

/* 侧边栏 */
.sidebar { ... }
.sidebar-left { ... }

/* 内容区域 */
.right-area { ... }
.content-panel { ... }

/* 预览面板 */
.preview-panel { ... }

/* 调整器 */
.resizer { ... }
```

### 6.3 components.css - 组件样式

```css
/* 按钮 */
.btn { ... }
.btn-primary { ... }
.btn-secondary { ... }

/* 卡片 */
.card { ... }
.card-title { ... }

/* 表单 */
.form-input { ... }
.form-textarea { ... }
.form-label { ... }

/* 进度条 */
.progress-bar { ... }
.progress-fill { ... }

/* 主题选择 */
.theme-option { ... }
.theme-preview { ... }

/* 滚动条 */
::-webkit-scrollbar { ... }
```

### 6.4 tree.css - 文件树样式

```css
/* 文件树容器 */
.file-tree-container { ... }

/* 树节点 */
.tree-item { ... }
.tree-folder { ... }
.tree-file { ... }

/* 图标 */
.tree-icon { ... }
.folder-icon { ... }
.file-icon { ... }

/* 通知系统 */
.toast { ... }
.toast-success { ... }
.toast-error { ... }
.toast-warning { ... }

/* 弹窗 */
.modal-overlay { ... }
.modal { ... }
```

### 6.5 editor.css - 编辑器样式

```css
/* 编辑器容器 */
.editor-container { ... }
.cm-editor-container { ... }

/* 分栏编辑 */
.editor-split-container { ... }
.editor-pane { ... }
.editor-pane-header { ... }

/* 预览内容 */
.editor-preview-scroll { ... }
.markdown-preview { ... }
```

### 6.6 preview.css - 预览面板样式

```css
/* 预览面板 */
.preview-panel { ... }
.preview-header { ... }
.preview-content { ... }

/* 空状态 */
.preview-empty { ... }

/* 文件信息 */
.preview-info { ... }
```

---

## 7. 测试方案

### 7.1 测试页面

已创建 `test-modules.html` 测试页面，包含以下测试项目：

#### 1. 工具函数测试 (utils.js)
- `escapeHtml()` - HTML 转义
- `formatFileSize()` - 文件大小格式化
- `formatModifiedTime()` - 时间格式化

#### 2. 状态管理测试 (state.js)
- API 配置初始化
- UI 配置初始化
- 主题偏好
- 状态监听

#### 3. Tab 切换测试 (tabs.js)
- Tab 初始化
- Tab 切换

#### 4. 通知系统测试 (toast.js)
- `updateStatus()` - 状态更新
- `updateProgress()` - 进度更新

#### 5. API 兼容层测试 (api.js)
- `window.api` 存在性
- API 方法列表
- 端口检测

#### 6. 业务模块测试
- EditorModule
- ThemeModule
- TreeModule
- PreviewModule
- WorkspaceModule
- DownloaderModule
- ConverterModule
- IntegratorModule
- SettingsModule
- App 入口

### 7.2 运行测试

```bash
cd webui
python3 -m http.server 8080
```

然后访问 `http://localhost:8080/test-modules.html`，点击"运行所有测试"按钮。

---

## 8. 重构前后对比

| 指标 | 重构前 | 重构后 |
|------|--------|--------|
| index.html 行数 | ~4221 行 | ~490 行 |
| CSS 行数 | ~1850 行（内联） | 拆分到 6 个文件 |
| JS 行数 | ~1760 行（内联） | 拆分到 16 个文件 |
| pywebview 兼容层 | JS 端 + Python 端 | 已删除 |
| API 调用封装 | 无 | 统一封装（超时+错误处理） |
| 状态管理 | 分散 | 集中管理（state.js） |
| 测试覆盖 | 无 | 有（test-modules.html） |

---

## 9. 注意事项

### 9.1 向后兼容

为了确保现有代码能正常工作，以下兼容层已保留：

1. **全局变量暴露**：`window.apiConfig`、`window.uiConfig`、`window.themePreference`
2. **全局函数暴露**：`switchTab()`、`toggleTheme()`、`openWorkspace()` 等
3. **`window.api` 对象**：保留所有 API 方法的封装

### 9.2 模块依赖关系

```
utils.js → api.js → state.js → toast.js → tabs.js
     ↓           ↓           ↓
theme.js    workspace.js  settings.js
tree.js     downloader.js
preview.js  converter.js
editor.js   integrator.js
     ↓
    app.js（入口）
```

### 9.3 后续优化建议

1. **使用 ES Modules**：将 JS 模块改为 ES Modules，使用 `import`/`export`
2. **添加构建工具**：使用 Vite 或 Webpack 进行打包
3. **TypeScript**：考虑迁移到 TypeScript 获得类型安全
4. **单元测试**：添加更完善的单元测试（使用 Jest 或 Mocha）

---

## 10. 相关文件

### 10.1 新建文件

```
webui/
├── css/
│   ├── variables.css
│   ├── layout.css
│   ├── components.css
│   ├── tree.css
│   ├── editor.css
│   └── preview.css
├── js/
│   ├── utils.js
│   ├── api.js
│   ├── state.js
│   ├── toast.js
│   ├── tabs.js
│   ├── theme.js
│   ├── tree.js
│   ├── preview.js
│   ├── editor.js
│   ├── workspace.js
│   ├── downloader.js
│   ├── converter.js
│   ├── integrator.js
│   ├── settings.js
│   └── app.js
└── test-modules.html
```

### 10.2 修改文件

| 文件 | 修改内容 |
|------|----------|
| `webui/index.html` | 重构为骨架形式，删除内联 CSS/JS，引入模块 |
| `webui/app.py` | 删除 FileDialog 类、attributes 属性、set_fullscreen 方法，简化 create_file_dialog |

---

**文档版本**: v1.0  
**创建日期**: 2026-04-26  
**最后更新**: 2026-04-26
