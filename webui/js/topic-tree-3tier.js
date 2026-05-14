// ================================================================
// 三层主题树渲染 (追加到 tree.js 或独立为 topic-tree-3tier.js)
// ================================================================

const TopicTree3Tier = {
    treeData: null,
    currentLevel: null,  // 'all', 1, 2, 3

    /**
     * 加载并渲染三层主题树
     */
    async load() {
        try {
            const data = await api.getTopicTree();
            this.treeData = data.topics;
            this.render(data.topics, data.pending);
        } catch (e) {
            console.error('加载主题树失败:', e);
        }
    },

    /**
     * 渲染主题树面板
     */
    render(topics, pending) {
        const container = document.getElementById('topic-tree-container');
        if (!container) return;

        let html = '<div class="topic-tree-3tier">';

        // 一级标题（居中）
        html += '<div class="tier-level tier-l1">';
        html += '<div class="tier-label">一级标题</div>';
        for (const l1 of topics) {
            const hasAbs = l1.has_abstract ? ' has-abstract' : '';
            html += `
                <div class="topic-node topic-l1${hasAbs}" data-name="${this.esc(l1.name)}" data-level="1"
                     onclick="TopicTree3Tier.onClick(this)" ondblclick="TopicTree3Tier.onDblClick(this)">
                    <span class="topic-icon">■</span>
                    <span class="topic-name">${this.esc(l1.name)}</span>
                    <span class="topic-count">${l1.file_count}</span>
                    ${l1.has_abstract ? '<span class="abstract-badge">综述</span>' : ''}
                    <span class="topic-expand">▶</span>
                </div>
                <div class="topic-children tier-l2-container" style="display:none">
                    ${this.renderL2(l1.children, l1.name)}
                </div>
            `;
        }
        html += '</div>';

        // 待确认列表
        if (pending && pending.length > 0) {
            html += '<div class="pending-topics"><div class="tier-label">待确认</div>';
            for (const p of pending) {
                html += `<div class="pending-item" data-file="${this.esc(p.file)}">${this.esc(p.file)}</div>`;
            }
            html += '</div>';
        }

        html += '</div>';
        container.innerHTML = html;
    },

    /**
     * 渲染二级（向外散出）
     */
    renderL2(children, parentL1) {
        let html = '';
        for (const l2 of children) {
            const hasAbs = l2.has_abstract ? ' has-abstract' : '';
            const hasL3 = l2.children && l2.children.length > 0;
            html += `
                <div class="topic-node topic-l2${hasAbs}" data-name="${this.esc(l2.name)}" data-level="2"
                     data-parent="${this.esc(parentL1)}"
                     onclick="TopicTree3Tier.onClick(this)" ondblclick="TopicTree3Tier.onDblClick(this)">
                    <span class="topic-icon">◆</span>
                    <span class="topic-name">${this.esc(l2.name)}</span>
                    <span class="topic-count">${l2.file_count}</span>
                    ${l2.has_abstract ? '<span class="abstract-badge">综述</span>' : ''}
                    ${hasL3 ? '<span class="topic-expand">▶</span>' : ''}
                </div>
            `;

            // 三级 — 只在存在时才渲染
            if (hasL3) {
                html += '<div class="topic-children tier-l3-container" style="display:none">';
                for (const l3 of l2.children) {
                    html += `
                        <div class="topic-node topic-l3" data-name="${this.esc(l3.name)}" data-level="3"
                             data-parent="${this.esc(l2.name)}"
                             onclick="TopicTree3Tier.onClick(this)" ondblclick="TopicTree3Tier.onDblClick(this)">
                            <span class="topic-icon">○</span>
                            <span class="topic-name">${this.esc(l3.name)}</span>
                            <span class="topic-count">${l3.file_count}</span>
                        </div>
                    `;
                }
                html += '</div>';
            }
        }
        return html;
    },

    /**
     * 单击：选中主题，右侧显示文件列表
     */
    onClick(el) {
        const name = el.dataset.name;
        const level = parseInt(el.dataset.level);

        // 高亮
        document.querySelectorAll('.topic-node.active').forEach(n => n.classList.remove('active'));
        el.classList.add('active');

        // 展开/折叠子级
        const childrenContainer = el.nextElementSibling;
        if (childrenContainer && childrenContainer.classList.contains('topic-children')) {
            const isVisible = childrenContainer.style.display !== 'none';
            childrenContainer.style.display = isVisible ? 'none' : 'block';
            const arrow = el.querySelector('.topic-expand');
            if (arrow) arrow.textContent = isVisible ? '▶' : '▼';
        }

        // 加载文件列表到右侧面板
        this.loadFiles(name, level);
    },

    /**
     * 双击：如果有综述，进入综述页面
     */
    onDblClick(el) {
        const name = el.dataset.name;
        const level = parseInt(el.dataset.level);

        if (el.classList.contains('has-abstract')) {
            // 进入综述
            api.generateAbstract(name, level).then(result => {
                if (result.success) {
                    // 在预览区显示综述内容
                    if (typeof showPreview === 'function') {
                        showPreview({ path: result.abstract_file, name: name + ' 综述' });
                    }
                }
            });
        } else {
            // 没有综述，显示文件列表
            this.loadFiles(name, level);
        }
    },

    /**
     * 加载主题下的文件列表
     */
    async loadFiles(name, level) {
        try {
            const result = await api.getTopicFiles(name, level);
            const panel = document.getElementById('topic-files-panel');
            if (!panel) return;

            let html = `<h4>${name}</h4><ul>`;
            for (const f of result.files) {
                html += `<li class="file-item" data-path="${this.esc(f.path)}"
                         onclick="TopicTree3Tier.openFile('${this.esc(f.path)}')">${this.esc(f.name)}</li>`;
            }
            html += '</ul>';

            // 新建文件夹按钮
            html += `<div class="new-folder-btn" onclick="TopicTree3Tier.showNewFolder('${this.esc(name)}', ${level})">
                     + 新建子文件夹</div>`;

            // 综述开关（仅二级主题）
            if (level === 2) {
                html += `<div class="abstract-toggle">
                    <label><input type="checkbox" onchange="TopicTree3Tier.toggleAbstract('${this.esc(name)}', ${level}, this.checked)"> 生成综述</label>
                </div>`;
            }

            // 删除按钮（一级受保护）
            if (level !== 1) {
                html += `<div class="delete-btn" onclick="TopicTree3Tier.deleteTopic('${this.esc(name)}', ${level})">删除此标题</div>`;
            }

            panel.innerHTML = html;
        } catch (e) {
            console.error('加载文件列表失败:', e);
        }
    },

    /**
     * 打开文件预览
     */
    openFile(path) {
        if (typeof showPreview === 'function') {
            showPreview({ path: path });
        }
    },

    /**
     * 新建文件夹对话框
     */
    showNewFolder(parentName, parentLevel) {
        const name = prompt(`在「${parentName}」下新建文件夹（将自动判定层级）:`);
        if (!name) return;

        api.createTopicFolder(name, parentName, parentLevel).then(r => {
            if (r.success) {
                alert(r.message);
                this.load();  // 刷新
            } else {
                alert('创建失败: ' + r.message);
            }
        });
    },

    /**
     * 综述开关
     */
    toggleAbstract(name, level, enable) {
        api.setAbstractConfig(name, level, enable).then(r => {
            if (!r.success) {
                alert(r.message);
                // 复原 checkbox
                document.querySelector('.abstract-toggle input').checked = !enable;
            } else {
                this.load();  // 刷新
            }
        });
    },

    /**
     * 删除主题
     */
    deleteTopic(name, level) {
        if (!confirm(`确定删除「${name}」吗？此操作不可撤销。`)) return;

        api.deleteTopic(name, level).then(r => {
            if (r.success) {
                alert(r.message);
                this.load();
            } else {
                alert('删除失败: ' + r.message);
            }
        });
    },

    esc(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
};