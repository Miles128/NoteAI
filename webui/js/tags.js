(function() { 'use strict';

var _lastTagsData = null;
var _tagsDragData = { filePath: null, fileName: null };

async function loadTagsView(silent) {
    var container = document.getElementById('sidebar-tags');
    if (!container) return;
    if (!silent) {
        container.innerHTML = '<div class="sidebar-view-loading">加载标签...</div>';
    }

    try {
        await window.api.ensureTagsMd();
        var result = await window.api.getAllTags();

        var dataStr = JSON.stringify(result);
        if (silent && dataStr === _lastTagsData) return;
        _lastTagsData = dataStr;
        window.AppState.lastTagsData = dataStr;

        if (!result || !result.tags || result.tags.length === 0) {
            container.innerHTML = '<div class="sidebar-view-empty">暂无标签</div>';
        } else {
            var expandedTags = {};
            container.querySelectorAll('.sidebar-tag-group.expanded').forEach(function(el) {
                var name = el.getAttribute('data-tag-name');
                if (name) expandedTags[name] = true;
            });

            var html = '<div class="sidebar-tags-list">';
            result.tags.forEach(function(tag) {
                var isExpanded = expandedTags[tag.name] ? ' expanded' : '';
                html += '<div class="sidebar-tag-group' + isExpanded + '" data-tag-name="' + escapeAttr(tag.name) + '">';
                html += '<div class="sidebar-tag-row" onclick="this.parentElement.classList.toggle(\'expanded\')" data-tag-name="' + escapeAttr(tag.name) + '">';
                html += '<span class="sidebar-tag-toggle">' + window.Icons.get('chevronDown') + '</span>';
                html += '<span class="sidebar-tag-name">' + escapeHtml(tag.name) + '</span>';
                html += '<span class="sidebar-tag-count">' + tag.count + '</span>';
                html += '</div>';
                html += '<div class="sidebar-tag-files">';
                tag.files.forEach(function(file) {
                    var fileName = file.split('/').pop();
                    html += '<div class="sidebar-tag-file tree-item" draggable="true" data-file-path="' + escapeAttr(file) + '" data-file-name="' + escapeAttr(fileName) + '" onclick="window.TreeModule.selectFile(\'' + escapeAttr(file) + '\', \'' + escapeAttr(fileName) + '\')">';
                    html += '<span class="tree-indent-unit"></span>';
                    html += '<span class="tree-name">' + escapeHtml(fileName) + '</span>';
                    html += '</div>';
                });
                html += '</div>';
                html += '</div>';
            });
            html += '</div>';
            container.innerHTML = html;

            setupTagsDragDrop(container);
            setupTagsContextMenu(container);
            updateSidebarStats();
        }
    } catch (e) {
        container.innerHTML = '<div class="sidebar-view-empty">加载标签失败</div>';
    }
}

function setupTagsDragDrop(container) {
    if (container._tagsDragDropReady) return;
    container._tagsDragDropReady = true;

    container.addEventListener('dragstart', function(e) {
        var fileEl = e.target.closest('.sidebar-tag-file');
        if (!fileEl) return;

        var filePath = fileEl.getAttribute('data-file-path');
        if (!filePath) return;

        _tagsDragData.filePath = filePath;
        _tagsDragData.fileName = fileEl.getAttribute('data-file-name') || '文件';
        fileEl.classList.add('dragging');

        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', filePath);
        e.dataTransfer.setData('text/html', '<span>' + escapeHtml(_tagsDragData.fileName) + '</span>');
    });

    container.addEventListener('dragend', function(e) {
        var fileEl = e.target.closest('.sidebar-tag-file');
        if (fileEl) fileEl.classList.remove('dragging');

        container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });

        _tagsDragData.filePath = null;
        _tagsDragData.fileName = null;
    });

    container.addEventListener('dragover', function(e) {
        if (!_tagsDragData.filePath) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';

        var rowEl = e.target.closest('.sidebar-tag-row');
        var groupEl = e.target.closest('.sidebar-tag-group');

        container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });

        if (rowEl) {
            var targetTag = rowEl.closest('.sidebar-tag-group')?.getAttribute('data-tag-name');
            if (targetTag) {
                rowEl.classList.add('drag-over');
            }
        } else if (groupEl) {
            var row = groupEl.querySelector('.sidebar-tag-row');
            if (row) row.classList.add('drag-over');
        }
    });

    container.addEventListener('dragleave', function(e) {
        var rowEl = e.target.closest('.sidebar-tag-row');
        if (rowEl) rowEl.classList.remove('drag-over', 'drag-over-top');
    });

    container.addEventListener('drop', async function(e) {
        e.preventDefault();

        if (!_tagsDragData.filePath) return;

        var rowEl = e.target.closest('.sidebar-tag-row');
        var groupEl = e.target.closest('.sidebar-tag-group');

        var targetTag = null;
        if (rowEl) {
            targetTag = rowEl.closest('.sidebar-tag-group')?.getAttribute('data-tag-name');
        } else if (groupEl) {
            targetTag = groupEl.getAttribute('data-tag-name');
        }

        if (!targetTag) {
            container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
                row.classList.remove('drag-over', 'drag-over-top');
            });
            return;
        }

        try {
            var result = await window.api.addTagToFile(_tagsDragData.filePath, targetTag);
            if (result && result.success) {
                await loadTagsView();
            } else {
                alert('添加标签失败：' + (result ? result.message : '未知错误'));
            }
        } catch (err) {
            console.error('[Tags] add tag error:', err);
            alert('添加标签失败：' + (err.message || '发生错误'));
        }

        container.querySelectorAll('.sidebar-tag-row').forEach(function(row) {
            row.classList.remove('drag-over', 'drag-over-top');
        });
    });
}

function setupTagsContextMenu(container) {
    container.addEventListener('contextmenu', function(e) {
        var fileEl = e.target.closest('.sidebar-tag-file');
        var rowEl = e.target.closest('.sidebar-tag-row');

        if (fileEl) {
            e.preventDefault();
            e.stopPropagation();
            showTagsContextMenu(e, fileEl);
        } else if (rowEl) {
            e.preventDefault();
            e.stopPropagation();
            showTagRowContextMenu(e, rowEl);
        }
    });
}

function showTagRowContextMenu(e, rowEl) {
    hideTreeContextMenu();

    var tagName = rowEl.getAttribute('data-tag-name');
    var tagNameEl = rowEl.querySelector('.sidebar-tag-name');
    if (!tagName) return;

    var menu = document.createElement('div');
    menu.className = 'tree-context-menu';
    menu.id = 'tree-ctx-menu';

    var items = [];

    items.push({
        label: '更改名称',
        icon: window.Icons.get('fileEdit'),
        action: function() {
            if (tagNameEl) {
                startTagRename(tagNameEl, tagName);
            }
        }
    });

    items.push({
        label: '删除标签',
        icon: window.Icons.get('trash'),
        action: function() {
            onDeleteTag(tagName);
        }
    });

    items.forEach(function(item) {
        var el = document.createElement('div');
        el.className = 'ctx-menu-item';
        el.innerHTML = item.icon + '<span>' + item.label + '</span>';
        el.addEventListener('click', function() {
            hideTreeContextMenu();
            item.action();
        });
        menu.appendChild(el);
    });

    document.body.appendChild(menu);

    var x = e.clientX;
    var y = e.clientY;
    var mw = menu.offsetWidth;
    var mh = menu.offsetHeight;
    if (x + mw > window.innerWidth) x = window.innerWidth - mw - 4;
    if (y + mh > window.innerHeight) y = window.innerHeight - mh - 4;
    if (x < 0) x = 4;
    if (y < 0) y = 4;
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
}

function startTagRename(tagNameEl, oldTagName) {
    var parentRow = tagNameEl.closest('.sidebar-tag-row');
    if (!parentRow) return;

    var originalDisplay = tagNameEl.style.display;

    var input = document.createElement('input');
    input.type = 'text';
    input.className = 'topic-rename-input';
    input.value = oldTagName;
    input.style.minWidth = (tagNameEl.offsetWidth + 20) + 'px';

    tagNameEl.style.display = 'none';
    parentRow.insertBefore(input, tagNameEl.nextSibling);
    input.focus();
    input.select();

    var finished = false;
    function finishRename(cancel) {
        if (finished) return;
        finished = true;

        var newName = input.value.trim();
        input.remove();
        tagNameEl.style.display = originalDisplay || '';

        if (cancel || !newName || newName === oldTagName) {
            return;
        }

        window.api.renameTag(oldTagName, newName).then(function(result) {
            if (result && result.success) {
                loadTagsView(true);
            } else {
                alert('重命名标签失败：' + (result && result.message ? result.message : '未知错误'));
            }
        }).catch(function(e) {
            console.error('[Tag] rename error:', e);
        });
    }

    input.addEventListener('blur', function() {
        finishRename(false);
    });

    input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            finishRename(true);
        }
    });

    input.addEventListener('click', function(e) {
        e.stopPropagation();
    });
}

async function onDeleteTag(tagName) {
    var confirmed = await window._customConfirm('确定要删除标签「' + tagName + '」吗？\n\n该标签将从所有文件的 YAML tags 中移除，同时更新 WIKI.md。');
    if (!confirmed) return;

    window.api.deleteTag(tagName).then(function(result) {
        if (result && result.success) {
            loadTagsView(true);
        } else {
            alert('删除标签失败：' + (result && result.message ? result.message : '未知错误'));
        }
    }).catch(function(e) {
        console.error('[Tag] delete error:', e);
        alert('删除标签出错');
    });
}

function showTagsContextMenu(e, fileEl) {
    hideTreeContextMenu();

    var path = fileEl.getAttribute('data-file-path');
    var name = fileEl.getAttribute('data-file-name');

    var menu = document.createElement('div');
    menu.className = 'tree-context-menu';
    menu.id = 'tree-ctx-menu';

    var items = [];

    items.push({
        label: '在访达中显示',
        icon: window.Icons.get('folder'),
        action: function() { revealInFinder(path); }
    });

    items.push({
        label: '在新窗口打开',
        icon: window.Icons.get('folderOpen'),
        action: function() {
            if (window.api && window.api.openFileInNewWindow) {
                window.api.openFileInNewWindow(path, name);
            }
        }
    });

    items.forEach(function(item) {
        var el = document.createElement('div');
        el.className = 'ctx-menu-item';
        el.innerHTML = item.icon + '<span>' + item.label + '</span>';
        el.addEventListener('click', function() {
            hideTreeContextMenu();
            item.action();
        });
        menu.appendChild(el);
    });

    document.body.appendChild(menu);

    var x = e.clientX;
    var y = e.clientY;
    var mw = menu.offsetWidth;
    var mh = menu.offsetHeight;
    if (x + mw > window.innerWidth) x = window.innerWidth - mw - 4;
    if (y + mh > window.innerHeight) y = window.innerHeight - mh - 4;
    if (x < 0) x = 4;
    if (y < 0) y = 4;
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
}

async function doAutoTag() {
    var btn = document.getElementById('btn-auto-tag');
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
    }
    try {
        var result = await window.api.autoTagFiles();
        if (result && result.success) {
            setTimeout(function() { loadTagsView(); }, 1000);
        }
    } catch (e) {
        console.error('[Tags] auto tag error:', e);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
        }
    }
}

function onShowAddTagInput() {
    var inputArea = document.getElementById('sidebar-tag-input');
    if (!inputArea) return;
    inputArea.style.display = 'flex';
    var field = document.getElementById('tag-input-field');
    if (field) {
        field.value = '';
        field.focus();
    }
}

function onHideTagInput() {
    var inputArea = document.getElementById('sidebar-tag-input');
    if (!inputArea) return;
    inputArea.style.display = 'none';
    var field = document.getElementById('tag-input-field');
    if (field) field.value = '';
}

function onTagInputChange() {
    var field = document.getElementById('tag-input-field');
    var confirmBtn = document.getElementById('tag-input-confirm');
    if (!field || !confirmBtn) return;
    confirmBtn.disabled = !field.value.trim();
}

async function onConfirmTag() {
    var field = document.getElementById('tag-input-field');
    if (!field) return;
    var tagName = field.value.trim();
    if (!tagName) return;

    try {
        var result = await window.api.createTag(tagName);
        if (result && result.success) {
            onHideTagInput();
            loadTagsView();
        } else {
            alert('创建标签失败：' + (result ? result.message || '未知错误' : '未知错误'));
        }
    } catch (e) {
        alert('创建标签出错：' + (e.message || e));
    }
}

function setupTagInputEvents() {
    var cancelBtn = document.getElementById('tag-input-cancel');
    var confirmBtn = document.getElementById('tag-input-confirm');
    var field = document.getElementById('tag-input-field');

    if (cancelBtn) {
        cancelBtn.addEventListener('click', function() {
            onHideTagInput();
        });
    }

    if (confirmBtn) {
        confirmBtn.addEventListener('click', function() {
            onConfirmTag();
        });
    }

    if (field) {
        field.addEventListener('input', function() {
            onTagInputChange();
        });
        field.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                onConfirmTag();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                onHideTagInput();
            }
        });
    }
}

window.doAutoTag = doAutoTag;
window.onShowAddTagInput = onShowAddTagInput;
window.loadTagsView = loadTagsView;

})();

