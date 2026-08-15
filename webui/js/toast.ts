(function() {
    'use strict';

    // updateStatus / updateProgress 的全库唯一实现（workspace.js、app.js 的重复定义已移除）。
    // 由 main.mjs 在最早批次 import，保证所有使用点调用时已挂载 window。
    function updateStatus(text: any) {
        if (window.StatusbarModule && window.StatusbarModule.updateMessage) {
            window.StatusbarModule.updateMessage(text || '');
            return;
        }
        const el = document.getElementById('status-bar') || document.getElementById('statusbar-message');
        if (el) {
            el.textContent = text;
        }
    }

    function updateProgress(elementId: any, progress: any, text: any) {
        const fill = document.getElementById(elementId + '-fill');
        const statusEl = document.getElementById(elementId.replace('progress', 'status'));

        if (fill) {
            fill.style.width = (progress * 100) + '%';
        }
        if (statusEl) {
            statusEl.textContent = text;
        }

        // 下载弹窗使用并行的 modal-* 进度条元素，需同步更新（原 workspace.js 版本的能力）
        const modalFillEl = document.getElementById('modal-' + elementId + '-fill');
        const modalStatusEl = document.getElementById('modal-' + elementId.replace('progress', 'status'));
        const modalProgressContainer = document.getElementById('modal-progress-container');

        if (modalProgressContainer) {
            if (progress > 0 || text) {
                modalProgressContainer.style.display = 'block';
            }
        }

        if (modalFillEl) {
            modalFillEl.style.width = (progress * 100) + '%';
        }
        if (modalStatusEl) {
            modalStatusEl.textContent = text;
        }
    }

    window.toast = {
        updateStatus,
        updateProgress
    };

    window.updateStatus = updateStatus;
    window.updateProgress = updateProgress;

    // ToastModule：cli-agent.js 等模块依赖的轻量 toast 通知（index.html 已含 #toast-container）。
    function showToast(message: any, type: any) {
        const container = document.getElementById('toast-container');
        if (!container) {
            window.updateStatus(message);
            return;
        }
        const el = document.createElement('div');
        el.className = 'toast' + (type ? ' toast-' + type : '');
        el.textContent = message;
        container.appendChild(el);
        setTimeout(function() {
            el.classList.add('hiding');
            setTimeout(function() { el.remove(); }, 350);
        }, 3500);
    }

    window.ToastModule = {
        show: showToast,
        error: function(message: any) { showToast(message, 'error'); },
        info: function(message: any) { showToast(message, 'info'); },
        success: function(message: any) { showToast(message, 'success'); }
    };
})();

