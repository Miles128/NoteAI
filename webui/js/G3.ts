import {
    _collectDescendantIds,
    _GRAPH_TAU,
    _GRAPH_GOLDEN_ANGLE,
    GRAPH_LAYOUT_DEFAULTS,
    loadGraphLayoutConfig,
    saveGraphLayoutConfig,
    resetGraphLayoutConfigStorage,
    loadGraphLayoutMode,
    saveGraphLayoutMode,
    _GRAPH_RADIUS_DISPLAY_SCALE,
    _graphNodeRadius,
    _graphNodeColor,
    _graphNodeStroke,
    _graphNodeStrokeWidth,
    _graphNodeFontSize,
    _graphNodeTextFill,
    _graphNodeTextDisplay,
    _graphNodeClass,
    _graphNodeSubtitle,
    _treeDepthLabel,
    _mindMapTextWidth,
    _mindMapNodeWidth,
    _mindMapNodeHeight,
    _mindMapLabel,
    _createGraphNode,
    _graphCfg,
    _noteDiskRadius,
    _l2RingRadius,
    _l3TopicDiskRadius,
    _scatterInDisk,
    _scatterTopicsInAnnulus,
    _seedGraphPositions,
    _pinGraphNodes,
    _graphCollideRadius,
    _graphTargetStrength,
    _graphChargeStrength,
    _graphDataFingerprint,
    _graphClusterRepelForce,
    _startGraphRelaxation,
    _layoutTopicFilesAndChildren,
    _layoutL1TopicCluster,
    _applyTopicHierarchyLayout,
    _resolveL1ClusterId,
    _dragGroupForNode,
    _makeGraphDragHandlers
} from './G3-layout';

const Graph3Tier = {
    data: null as any,
    svg: null as any,
    g: null as any,
    zoom: null as any,
    showFilenames: false,
    simulation: null as any,
    filter: 'topic',
    // The balanced mind map is easier to scan, so it is the first-run default.
    // Keep constellation available for relationship exploration and remember
    // an explicit user choice across sessions.
    layoutMode: loadGraphLayoutMode(),
    treeCollapsedIds: new Set(),
    treeInitialCollapseApplied: false,
    layoutConfig: loadGraphLayoutConfig(),
    _graphBodyResizeObserver: null as any,
    _resizePaused: false,
    _resizePending: false,

    initLayoutConfig() {
        this.layoutConfig = loadGraphLayoutConfig();
    },

    reloadLayoutConfig() {
        this.initLayoutConfig();
    },

    // 布局参数面板 UI 已拆至 graph-layout-params.js，此处保留同名方法作为委托，
    // 以维持 window.Graph3Tier 的公开接口不变。
    _buildLayoutSettingsForm() {
        window.GraphLayoutParams!.buildForm!(this.layoutConfig);
    },

    openLayoutSettings() {
        window.GraphLayoutParams!.open!();
    },

    closeLayoutSettings() {
        window.GraphLayoutParams!.close!();
    },

    readLayoutSettingsFromForm() {
        return window.GraphLayoutParams!.readForm!();
    },

    _scheduleLayoutApply() {
        window.GraphLayoutParams!.scheduleApply!();
    },

    reloadGraphLayout() {
        const panel = document.getElementById('graph-panel');
        if (panel && panel.style.display === 'none') return;

        if (!this.data || !this.data.nodes || !this.data.nodes.length) {
            this.load(this.filter || 'topic');
            return;
        }

        if (this.simulation) this.simulation.stop();
        this.simulation = null;

        const self = this;
        const run = function() {
            self.initD3();
            if (!self.svg) return;
            self.render();
            requestAnimationFrame(function() { self.resize(); });
        };
        requestAnimationFrame(function() { requestAnimationFrame(run); });
    },

    applyLayoutSettings(cfg: any, options: any) {
        const opts = options || {};
        this.layoutConfig = Object.assign({}, GRAPH_LAYOUT_DEFAULTS, cfg);
        saveGraphLayoutConfig(this.layoutConfig);
        if (opts.reload === false) return;
        this.reloadGraphLayout();
    },

    resetLayoutSettings() {
        window.GraphLayoutParams!.reset!();
    },

    pauseResize() {
        this._resizePaused = true;
    },

    resumeResize() {
        this._resizePaused = false;
        if (this._resizePending) {
            this._resizePending = false;
            this.resize();
        }
    },

    stopSimulation() {
        if (this.simulation) {
            this.simulation.stop();
            this.simulation = null;
        }
    },

    _disconnectGraphPanelBodyResize() {
        if (this._graphBodyResizeObserver) {
            this._graphBodyResizeObserver.disconnect();
            this._graphBodyResizeObserver = null;
        }
    },

    _observeGraphPanelBodyResize(container: any) {
        this._disconnectGraphPanelBodyResize();
        if (!container || typeof ResizeObserver === 'undefined') return;
        const self = this;
        this._graphBodyResizeObserver = new ResizeObserver(() => {
            if (self._resizePaused) {
                self._resizePending = true;
                return;
            }
            requestAnimationFrame(function() {
                self.resize();
            });
        });
        this._graphBodyResizeObserver.observe(container);
    },

    _clampNodesToView(nodes: any, w: any, h: any, getRadius: any) {
        if (!w || !h || !nodes || !nodes.length) return;
        const sidePad = Math.min(108, Math.max(36, w * this.layoutConfig.clampSideRatio));
        nodes.forEach((d: any) => {
            const r = getRadius(d) + 6;
            const topPad = r + 20;
            const botPad = r + 14;
            d.x = Math.max(sidePad, Math.min(w - sidePad, d.x));
            d.y = Math.max(topPad, Math.min(h - botPad, d.y));
        });
    },

    /** Bounds for zoom-to-fit: account for circles + labels (above nodes). */
    _boundsFromNodes(nodes: any, w: any, h: any, getRadius: any) {
        let x1 = Infinity;
        let y1 = Infinity;
        let x2 = -Infinity;
        let y2 = -Infinity;
        const mx = this.layoutConfig.boundsMargin;
        nodes.forEach((d: any) => {
            const r = getRadius(d) + 8;
            const padTop = r + 22;
            const padBot = r + 14;
            x1 = Math.min(x1, d.x - mx);
            x2 = Math.max(x2, d.x + mx);
            y1 = Math.min(y1, d.y - padTop);
            y2 = Math.max(y2, d.y + padBot);
        });
        if (!Number.isFinite(x1)) return { x1: 0, y1: 0, x2: w || 800, y2: h || 600 };
        return { x1, y1, x2, y2 };
    },

    _fitGraphToBounds(nodes: any, svgW: any, svgH: any, getRadius: any, duration: any) {
        if (!this.svg || !this.zoom || !nodes.length) return;
        const bounds = this._boundsFromNodes(nodes, svgW, svgH, getRadius);
        const bw = bounds.x2 - bounds.x1 || 100;
        const bh = bounds.y2 - bounds.y1 || 100;
        const pad = this.layoutConfig.fitPad;
        const scale = Math.min((svgW - pad * 2) / bw, (svgH - pad * 2) / bh, this.layoutConfig.fitMaxScale);
        const midX = (bounds.x1 + bounds.x2) / 2;
        const midY = (bounds.y1 + bounds.y2) / 2;
        const dur = duration == null ? 800 : duration;
        const tr = window.d3.zoomIdentity.translate(svgW / 2, svgH / 2).scale(Math.max(0.15, scale)).translate(-midX, -midY);
        if (dur > 0) {
            this.svg.transition().duration(dur).call(this.zoom.transform, tr);
        } else {
            this.svg.call(this.zoom.transform, tr);
        }
    },

    _loadDebounceTimer: null as any,
    _lastLoadFilter: null as any,
    _lastLoadTime: 0,
    _lastDataHash: null as any,

    async load(filter?: any, force?: any) {
        if (filter && filter !== this.filter) {
            this.filter = filter;
            this.treeCollapsedIds.clear();
            this.treeInitialCollapseApplied = false;
        } else if (filter) {
            this.filter = filter;
        }
        var panel = document.getElementById('graph-panel');
        if (panel && panel.style.display === 'none') return;
        if (force) {
            this._lastLoadTime = 0;
            this._lastDataHash = null;
        }
        var now = Date.now();
        var sameFilter = (filter === this._lastLoadFilter);
        if (sameFilter && now - this._lastLoadTime < 10000) {
            if (this._loadDebounceTimer) clearTimeout(this._loadDebounceTimer);
            var self = this;
            this._loadDebounceTimer = setTimeout(function() {
                self._loadDebounceTimer = null;
                self._doLoad();
            }, 10000 - (now - this._lastLoadTime));
            return;
        }
        this._doLoad();
    },

    async _doLoad() {
        await window.loadLazyScript('d3.min.js').catch(function() { return false; });
        this._lastLoadFilter = this.filter;
        this._lastLoadTime = Date.now();
        this.initLayoutConfig();
        try {
            this.data = await window.api.getGraphData(this.filter);
            if (!this.data || !Array.isArray(this.data.nodes) || !Array.isArray(this.data.edges)) {
                console.error('图谱数据格式异常:', this.data);
                this.data = { nodes: [], edges: [] };
            }
            var hash = _graphDataFingerprint(this.data);
            if (hash === this._lastDataHash && this.svg) return;
            this._lastDataHash = hash;
            this._updateFilterBtns();
            this._updateLayoutModeBtns();
            this._updateLegend();
            this._updateStats();
            this.initD3();
            this.render();
        } catch (e) {
            console.error('图谱加载失败:', e);
            if (e && (e as any).stack) console.error((e as any).stack);
        }
    },

    _updateFilterBtns() {
        document.querySelectorAll('#graph-filter-bar .graph-filter-btn').forEach(btn => {
            btn.classList.toggle('active', (btn as HTMLElement).dataset.filter === this.filter);
        });
    },

    _updateLayoutModeBtns() {
        document.querySelectorAll('#graph-layout-mode .graph-layout-mode-btn').forEach(btn => {
            btn.classList.toggle('active', (btn as HTMLElement).dataset.layoutMode === this.layoutMode);
        });
    },

    setLayoutMode(mode: any) {
        const nextMode = mode === 'tree' ? 'tree' : 'constellation';
        if (nextMode === this.layoutMode) return;
        this.layoutMode = nextMode;
        saveGraphLayoutMode(nextMode);
        this._updateLayoutModeBtns();
        this._updateLegend();
        if (this.data && this.svg) {
            this.initD3();
            this.render();
        }
    },

    toggleTreeNodeCollapsed(nodeId: any) {
        if (!nodeId) return;
        if (this.treeCollapsedIds.has(nodeId)) {
            this.treeCollapsedIds.delete(nodeId);
        } else {
            this.treeCollapsedIds.add(nodeId);
        }
        if (this.layoutMode === 'tree' && this.data && this.svg) {
            this.renderTreeLayout();
        }
    },

    _legendItem(color: any, size: any, labelKey: any) {
        var label = window.t(labelKey);
        var item = document.createElement('span');
        item.className = 'graph-legend-item';
        item.title = label;
        var dot = document.createElement('span');
        dot.className = 'graph-legend-dot';
        dot.style.background = color;
        dot.style.width = size + 'px';
        dot.style.height = size + 'px';
        dot.style.borderRadius = '50%';
        dot.style.display = 'inline-block';
        var text = document.createElement('span');
        text.className = 'graph-legend-label';
        text.textContent = label;
        item.appendChild(dot);
        item.appendChild(text);
        return item;
    },

    _updateLegend() {
        const el = document.getElementById('graph-legend');
        if (!el) return;
        el.style.display = this.layoutMode === 'tree' ? 'none' : 'flex';
        el.innerHTML = '';
        var items = [];
        if (this.filter === 'tag' || this.filter === 'all') {
            items = [
                this._legendItem('#7c4dff', 8, 'graph.legend.tags'),
                this._legendItem('#81c784', 6, 'graph.legend.notes')
            ];
        } else {
            items = [
                this._legendItem('#ea8600', 6, 'graph.legend.l2'),
                this._legendItem('#f4a930', 5, 'graph.legend.l3'),
                this._legendItem('#81c784', 4, 'graph.legend.notes')
            ];
        }
        items.forEach(function(item) { el.appendChild(item); });
    },

    _updateStats() {
        const topicNodes = (this.data.nodes || []).filter((n: any) => n.type === 'topic').length;
        const tagNodes = (this.data.nodes || []).filter((n: any) => n.type === 'tag').length;
        const fileNodes = (this.data.nodes || []).filter((n: any) => n.type === 'file').length;
        const gs1 = document.getElementById('graph-stat-notes');
        const gs2 = document.getElementById('graph-stat-topics');
        if (gs1) gs1.textContent = fileNodes;
        if (gs2) gs2.textContent = topicNodes + tagNodes;
    },

    initD3() {
        const container = document.getElementById('graph-panel-body');
        if (!container) return;

        this._disconnectGraphPanelBodyResize();

        const oldSvg = document.getElementById('graph-svg-3tier');
        if (oldSvg) oldSvg.remove();
        if (this.simulation) this.simulation.stop();

        const w = container.clientWidth || 800;
        const h = container.clientHeight || 600;

        this.svg = window.d3.select(container)
            .append('svg')
            .attr('id', 'graph-svg-3tier')
            .attr('width', w)
            .attr('height', h)
            .style('position', 'absolute').style('top', 0).style('left', 0)
            .style('z-index', 0)
            .style('background', 'var(--bg, #fafafa)');

        this.g = this.svg.append('g');

        this.zoom = window.d3.zoom()
            .scaleExtent([0.06, 5])
            .on('zoom', (e: any) => {
                this.g.attr('transform', e.transform);
                this._updateZoomPercent(e.transform.k);
            });
        this.svg.call(this.zoom);
        this._updateZoomPercent(1);

        this._observeGraphPanelBodyResize(container);

        // Prevent zoom on node drag
        this.svg.on('dblclick.zoom', null);

        const emptyEl = document.getElementById('graph-empty');
        const loadingEl = document.getElementById('graph-loading');
        if (loadingEl) loadingEl.style.display = 'none';
        if (!this.data || !this.data.nodes || this.data.nodes.length === 0) {
            if (emptyEl) { emptyEl.textContent = window.t('graph.empty'); emptyEl.style.display = ''; }
            return;
        }
        if (emptyEl) emptyEl.style.display = 'none';
    },

    render() {
        if (!this.svg || !this.data) return;
        this.g.selectAll('*').remove();
        this.svg.classed('is-mindmap', this.layoutMode === 'tree');

        if (this.layoutMode === 'tree') {
            this.renderTreeLayout();
            return;
        }

        const svgW = +this.svg.attr('width');
        const svgH = +this.svg.attr('height');
        const cx = svgW / 2;
        const cy = svgH / 2;
        const self = this;

        const nodes = this.data.nodes.map((n: any) => Object.assign({}, n));
        const edges = this.data.edges.map((e: any) => ({
            source: e.source,
            target: e.target,
        }));

        const lc = this.layoutConfig;
        const getRadius = (d: any) => _graphNodeRadius(d, lc);

        // ===== Constellation layout: L1 spread out, children cluster around L1 =====
        const childMap: any = {};
        const parentMap: any = {};
        edges.forEach((e: any) => {
            const src = typeof e.source === 'string' ? e.source : e.source.id || e.source;
            const tgt = typeof e.target === 'string' ? e.target : e.target.id || e.target;
            if (!childMap[src]) childMap[src] = [];
            childMap[src].push(tgt);
            parentMap[tgt] = src;
        });

        const nodeMap: any = {};
        nodes.forEach((n: any) => { nodeMap[n.id] = n; });

        _applyTopicHierarchyLayout(nodes, childMap, nodeMap, parentMap, cx, cy, svgW, svgH, 'tx');
        nodes.forEach(function(n: any) {
            if (n.tx == null || n.ty == null) {
                n.tx = cx;
                n.ty = cy;
            }
        });
        _seedGraphPositions(nodes);

        const nodeGroup = this.g.append('g').attr('class', 'graph-nodes');
        const node = nodeGroup.selectAll('g')
            .data(nodes)
            .join('g')
            .attr('cursor', 'pointer');

        _createGraphNode(node, getRadius, self.showFilenames);

        const updateNodePos = function() {
            node.attr('transform', function(d: any) { return 'translate(' + d.x + ',' + d.y + ')'; });
        };

        // Hover effects
        node.on('mouseenter', function(this: any, e: any, d: any) {
            window.d3.select(this).select('circle')
                .transition().duration(150)
                .attr('r', getRadius(d) * 1.3);
        }).on('mouseleave', function(this: any, e: any, d: any) {
            window.d3.select(this).select('circle')
                .transition().duration(150)
                .attr('r', getRadius(d));
        });

        // Double-click: open abstract for topics that have one
        node.on('dblclick', (e: any, d: any) => {
            e.stopPropagation();
            if (d.type === 'topic' && d.has_abstract && d.abstract_file && typeof window.showPreview === 'function') {
                window.showPreview({ path: d.abstract_file, name: (d.name || d.id) + ' ' + window.t('graph.stats.survey') });
            }
        });

        // Click
        node.on('click', (e: any, d: any) => {
            e.stopPropagation();
            if (d.type === 'file' && d.full_path && typeof window.showPreview === 'function') {
                window.showPreview({ path: d.full_path, name: d.name });
            } else if (d.type === 'topic') {
                if (d.has_abstract && d.abstract_file && typeof window.showPreview === 'function') {
                    window.showPreview({ path: d.abstract_file, name: (d.name || d.id) + ' ' + window.t('graph.stats.survey') });
                } else {
                    // Center and zoom on this node
                    const node = self.svg.node();
                    const svgW = node ? node.clientWidth : 800;
                    const svgH = node ? node.clientHeight : 600;
                    const currentTransform = window.d3.zoomTransform(node);
                    const scale = Math.min(2, currentTransform.k * 1.5);
                    self.svg.transition().duration(500).call(
                        self.zoom.transform,
                        window.d3.zoomIdentity.translate(svgW / 2, svgH / 2).scale(scale).translate(-d.x, -d.y)
                    );
                }
            }
        });

        updateNodePos();
        const selfRef = this;
        this.simulation = _startGraphRelaxation(nodes, edges, getRadius, updateNodePos, function() {
            selfRef._fitGraphToBounds(nodes, svgW, svgH, getRadius, 800);
        });
        node.call(_makeGraphDragHandlers(childMap, nodeMap, parentMap, nodes, edges, this.simulation, self));

        // Click background to deselect
        this.svg.on('click', () => {});
    },

    _graphNodeClick(e: any, d: any) {
        e.stopPropagation();
        if (d.type === 'file' && d.full_path && typeof window.showPreview === 'function') {
            window.showPreview({ path: d.full_path, name: d.name });
        } else if (d.type === 'topic' && d.has_abstract && d.abstract_file && typeof window.showPreview === 'function') {
            window.showPreview({ path: d.abstract_file, name: (d.name || d.id) + ' ' + window.t('graph.stats.survey') });
        }
    },

    renderTreeLayout() {
        if (!this.svg || !this.data) return;
        if (this.simulation) this.simulation.stop();
        this.simulation = null;

        const svgW = +this.svg.attr('width');
        const svgH = +this.svg.attr('height');
        const nodes = (this.data.nodes || []).map((n: any) => Object.assign({}, n));
        const edges = (this.data.edges || []).map((e: any) => ({
            source: typeof e.source === 'string' ? e.source : e.source.id || e.source,
            target: typeof e.target === 'string' ? e.target : e.target.id || e.target,
        }));
        if (!nodes.length) return;

        const nodeMap: any = {};
        nodes.forEach((n: any) => { nodeMap[n.id] = n; });
        const isVisibleType = (n: any) => this.showFilenames || n.type !== 'file';
        const childrenByParent: any = {};
        const hasParent = new Set();
        edges.forEach((e: any) => {
            if (!nodeMap[e.source] || !nodeMap[e.target] || e.source === e.target) return;
            if (!childrenByParent[e.source]) childrenByParent[e.source] = [];
            childrenByParent[e.source].push(e.target);
            if (isVisibleType(nodeMap[e.target])) hasParent.add(e.target);
        });

        const orderedNodes = nodes.filter(isVisibleType).sort((a: any, b: any) => {
            const la = a.type === 'topic' ? (a.level || 0) : 9;
            const lb = b.type === 'topic' ? (b.level || 0) : 9;
            return la - lb || String(a.name || a.id).localeCompare(String(b.name || b.id), 'zh-Hans-CN');
        });
        const visibleChildIds = (nodeId: any) => (childrenByParent[nodeId] || [])
            .filter((id: any) => nodeMap[id] && isVisibleType(nodeMap[id]));

        if (!this.treeInitialCollapseApplied) {
            orderedNodes.forEach((n: any) => {
                if (!visibleChildIds(n.id).length) return;
                if ((n.type === 'topic' && Number(n.level || 0) >= 2) || n.type === 'tag') {
                    this.treeCollapsedIds.add(n.id);
                }
            });
            this.treeInitialCollapseApplied = true;
        }

        const rootNodes = orderedNodes.filter((n: any) => !hasParent.has(n.id));
        const visited = new Set();
        const collapsed = this.treeCollapsedIds;
        const markDescendantsVisited = (nodeId: any) => {
            visibleChildIds(nodeId).forEach((childId: any) => {
                if (visited.has(childId)) return;
                visited.add(childId);
                markDescendantsVisited(childId);
            });
        };
        const toTreeNode = (n: any) => {
            visited.add(n.id);
            const rawChildIds = visibleChildIds(n.id);
            const isCollapsed = collapsed.has(n.id) && rawChildIds.length > 0;
            if (isCollapsed) {
                markDescendantsVisited(n.id);
                return Object.assign({}, n, {
                    children: [],
                    _hasChildren: true,
                    _childCount: rawChildIds.length,
                    _collapsed: true,
                });
            }
            const children = rawChildIds
                .filter((id: any) => !visited.has(id))
                .map((id: any) => nodeMap[id])
                .sort((a: any, b: any) => String(a.name || a.id).localeCompare(String(b.name || b.id), 'zh-Hans-CN'))
                .map(toTreeNode);
            return Object.assign({}, n, {
                children,
                _hasChildren: rawChildIds.length > 0,
                _childCount: rawChildIds.length,
                _collapsed: false,
            });
        };

        const roots: any[] = [];
        const rootCandidates = rootNodes.length ? rootNodes : orderedNodes;
        rootCandidates.forEach((n: any) => { if (!visited.has(n.id)) roots.push(toTreeNode(n)); });
        orderedNodes.forEach((n: any) => { if (!visited.has(n.id)) roots.push(toTreeNode(n)); });
        if (!roots.length) return;

        const subtreeWeight = (branch: any) => 1 + (branch.children || []).reduce((sum: any, child: any) => sum + subtreeWeight(child), 0);
        const sides: any[][] = [[], []];
        const sideWeights = [0, 0];
        roots.forEach((branch: any, index: any) => {
            const sideIndex = sideWeights[0] === sideWeights[1] ? index % 2 : (sideWeights[0] < sideWeights[1] ? 0 : 1);
            sides[sideIndex].push(branch);
            sideWeights[sideIndex] += subtreeWeight(branch);
        });

        const center = {
            id: '__mindmap_root__',
            name: (window.t && window.t('graph.tree.rootLabel')) || 'Knowledge base',
            x: svgW / 2,
            y: svgH / 2,
            _mindWidth: 132,
            _mindHeight: 50,
        };
        const rowGap = this.showFilenames ? 42 : 52;
        const colGap = (this.showFilenames ? 178 : 204) * 1.75;
        const visibleNodes: any[] = [];
        const links: any[] = [];

        const layoutSide = (branches: any, direction: any) => {
            if (!branches.length) return;
            const sideRoot = window.d3.hierarchy({ id: '__side__', children: branches });
            window.d3.tree().nodeSize([rowGap, colGap])(sideRoot);
            const descendants = sideRoot.descendants().filter((d: any) => d.data.id !== '__side__');
            const minY = window.d3.min(descendants, (d: any) => d.x) || 0;
            const maxY = window.d3.max(descendants, (d: any) => d.x) || 0;
            const offsetY = center.y - (minY + maxY) / 2;
            descendants.forEach((d: any) => {
                d.data.x = center.x + direction * d.depth * colGap;
                d.data.y = d.x + offsetY;
                d.data.treeDepth = d.depth;
                d.data._mindSide = direction;
                d.data._mindWidth = _mindMapNodeWidth(d.data);
                d.data._mindHeight = _mindMapNodeHeight(d.data);
                visibleNodes.push(d);
                links.push({
                    source: d.parent && d.parent.data.id !== '__side__' ? d.parent.data : center,
                    target: d.data,
                });
            });
        };
        layoutSide(sides[0], -1);
        layoutSide(sides[1], 1);

        this.g.selectAll('*').remove();
        const rootGroup = this.g.append('g')
            .attr('class', 'graph-mindmap-root')
            .attr('transform', 'translate(' + center.x + ',' + center.y + ')');
        rootGroup.append('rect')
            .attr('x', -center._mindWidth / 2)
            .attr('y', -center._mindHeight / 2)
            .attr('width', center._mindWidth)
            .attr('height', center._mindHeight)
            .attr('rx', 15);
        rootGroup.append('text')
            .attr('text-anchor', 'middle')
            .attr('dy', '0.36em')
            .text(center.name);

        this.g.append('g')
            .attr('class', 'graph-tree-links graph-mindmap-links')
            .selectAll('path')
            .data(links)
            .join('path')
            .attr('class', (link: any) => 'graph-tree-link graph-mindmap-link graph-mindmap-link-depth-' + link.target.treeDepth)
            .attr('fill', 'none')
            .attr('d', (link: any) => {
                const side = link.target._mindSide;
                const sx = link.source.x + side * link.source._mindWidth / 2;
                const sy = link.source.y;
                const tx = link.target.x - side * link.target._mindWidth / 2;
                const ty = link.target.y;
                const curve = Math.max(38, Math.abs(tx - sx) * 0.52);
                return 'M' + sx + ',' + sy + 'C' + (sx + side * curve) + ',' + sy + ' ' + (tx - side * curve) + ',' + ty + ' ' + tx + ',' + ty;
            });

        const self = this;
        const node = this.g.append('g')
            .attr('class', 'graph-nodes graph-tree-nodes graph-mindmap-nodes')
            .selectAll('g')
            .data(visibleNodes.map((d: any) => d.data))
            .join('g')
            .attr('class', (d: any) => _graphNodeClass(d) + ' graph-mindmap-node mindmap-side-' + (d._mindSide < 0 ? 'left' : 'right'))
            .attr('cursor', 'pointer')
            .attr('transform', (d: any) => 'translate(' + d.x + ',' + d.y + ')');

        node.append('rect')
            .attr('class', 'graph-mindmap-node-surface')
            .attr('x', (d: any) => -d._mindWidth / 2)
            .attr('y', (d: any) => -d._mindHeight / 2)
            .attr('width', (d: any) => d._mindWidth)
            .attr('height', (d: any) => d._mindHeight)
            .attr('rx', (d: any) => d.type === 'file' ? 7 : 11);
        node.append('text')
            .attr('class', 'graph-mindmap-label')
            .attr('text-anchor', 'middle')
            .attr('y', (d: any) => d.type === 'file' ? 4 : -4)
            .text((d: any) => _mindMapLabel(d.name, d.type === 'file' ? 22 : 18));
        node.filter((d: any) => d.type !== 'file').append('text')
            .attr('class', 'graph-tree-subtitle graph-mindmap-meta')
            .attr('text-anchor', 'middle')
            .attr('y', 11)
            .text(_graphNodeSubtitle);
        node.append('title').text((d: any) => (d.name || '') + '\n' + _graphNodeSubtitle(d));

        const toggles = node.filter((d: any) => d._hasChildren)
            .append('g')
            .attr('class', 'graph-tree-toggle-node graph-mindmap-toggle')
            .attr('transform', (d: any) => 'translate(' + (d._mindSide * (d._mindWidth / 2 + 11)) + ',0)')
            .attr('cursor', 'pointer');
        toggles.append('circle').attr('r', 7);
        toggles.append('path').attr('class', 'graph-tree-toggle-minus').attr('d', 'M-3,0H3');
        toggles.append('path')
            .attr('class', 'graph-tree-toggle-plus')
            .attr('d', 'M0,-3V3')
            .style('display', (d: any) => d._collapsed ? '' : 'none');
        toggles.on('click', function(e: any, d: any) {
            e.stopPropagation();
            self.toggleTreeNodeCollapsed(d.id);
        });

        const pathByNode: any = {};
        visibleNodes.forEach((d: any) => {
            const ids = new Set();
            let current = d;
            while (current && current.data && current.data.id !== '__side__') {
                ids.add(current.data.id);
                current = current.parent;
            }
            d.descendants().forEach((child: any) => {
                if (child.data && child.data.id !== '__side__') ids.add(child.data.id);
            });
            pathByNode[d.data.id] = ids;
        });
        const setTreeFocus = (targetId: any) => {
            const pathSet = pathByNode[targetId] || new Set();
            node.classed('is-dimmed', (d: any) => !pathSet.has(d.id));
            node.classed('is-path', (d: any) => pathSet.has(d.id));
            node.classed('is-focus', (d: any) => d.id === targetId);
            self.g.selectAll('.graph-tree-link')
                .classed('is-dimmed', (link: any) => !pathSet.has(link.target.id))
                .classed('is-path', (link: any) => pathSet.has(link.target.id));
        };
        const clearTreeFocus = () => {
            node.classed('is-dimmed', false).classed('is-path', false).classed('is-focus', false);
            self.g.selectAll('.graph-tree-link').classed('is-dimmed', false).classed('is-path', false);
        };

        node.on('mouseenter', function(e: any, d: any) {
            setTreeFocus(d.id);
        }).on('mouseleave', clearTreeFocus);
        node.on('click', (e: any, d: any) => self._graphNodeClick(e, d));
        node.on('dblclick', function(e: any, d: any) {
            e.stopPropagation();
            if (d._hasChildren) self.toggleTreeNodeCollapsed(d.id);
            else self._graphNodeClick(e, d);
        });

        const layoutNodes = visibleNodes.map((d: any) => d.data).concat([center]);
        const bounds = {
            x1: window.d3.min(layoutNodes, (d: any) => d.x - d._mindWidth / 2 - 18) || 0,
            y1: window.d3.min(layoutNodes, (d: any) => d.y - d._mindHeight / 2 - 12) || 0,
            x2: window.d3.max(layoutNodes, (d: any) => d.x + d._mindWidth / 2 + 18) || svgW,
            y2: window.d3.max(layoutNodes, (d: any) => d.y + d._mindHeight / 2 + 12) || svgH,
        };
        const bw = Math.max(180, bounds.x2 - bounds.x1);
        const bh = Math.max(160, bounds.y2 - bounds.y1);
        // Keep the mind map spacious. Fit vertically, and let wide branches pan
        // beyond the viewport instead of shrinking the entire map horizontally.
        const scale = Math.max(0.42, Math.min((svgH - 92) / bh, 1));
        const midX = (bounds.x1 + bounds.x2) / 2;
        const midY = (bounds.y1 + bounds.y2) / 2;
        this.svg.transition().duration(420).call(
            this.zoom.transform,
            window.d3.zoomIdentity.translate(svgW / 2, svgH / 2).scale(Math.max(0.28, scale)).translate(-midX, -midY)
        );
    },

    resize() {
        if (!this.svg || !this.data) return;
        const container = document.getElementById('graph-panel-body');
        if (!container) return;
        const rawW = container.clientWidth;
        const rawH = container.clientHeight;
        if (!rawW || !rawH || rawW < 48 || rawH < 48) return;

        const newW = rawW;
        const newH = rawH;
        const oldW = +this.svg.attr('width');
        const oldH = +this.svg.attr('height');

        if (newW === oldW && newH === oldH) return;

        this.svg.attr('width', newW).attr('height', newH);

        if (this.layoutMode === 'tree') {
            this.renderTreeLayout();
            return;
        }

        if (!this.simulation) return;

        // Re-center and re-fit without rebuilding
        var self = this;
        var nodes = this.simulation.nodes();
        if (!nodes || !nodes.length) return;

        function getRZ(d: any) {
            if (d.type === 'topic') {
                if (d.level === 1) return 7;
                if (d.level === 2) return 5;
                return 4;
            }
            if (d.type === 'tag') return 4 + Math.min(d.file_count || 0, 30) * 0.25;
            return 2.5;
        }

        this._clampNodesToView(nodes, newW, newH, getRZ);

        var bounds = self._boundsFromNodes(nodes, newW, newH, getRZ);
        var bw = bounds.x2 - bounds.x1 || 100;
        var bh = bounds.y2 - bounds.y1 || 100;
        var scale = Math.min((newW - 120) / bw, (newH - 120) / bh, 1.5);
        var midX = (bounds.x1 + bounds.x2) / 2;
        var midY = (bounds.y1 + bounds.y2) / 2;

        self.svg.transition().duration(300).call(
            self.zoom.transform,
            window.d3.zoomIdentity.translate(newW / 2, newH / 2).scale(Math.max(0.15, scale)).translate(-midX, -midY)
        );
    },

    zoomIn() {
        if (this.svg && this.zoom) this.svg.transition().duration(300).call(this.zoom.scaleBy, 1.3);
    },
    zoomOut() {
        if (this.svg && this.zoom) this.svg.transition().duration(300).call(this.zoom.scaleBy, 0.7);
    },

    zoomReset() {
        if (this.svg && this.zoom) this.svg.transition().duration(300).call(this.zoom.scaleTo, 1);
    },

    _updateZoomPercent(scale: any) {
        const percent = document.getElementById('graph-zoom-percent');
        if (percent) percent.textContent = Math.round((Number(scale) || 1) * 100) + '%';
    },

    replay() {
        if (!this.svg || !this.data) return;
        if (this.layoutMode === 'tree') {
            this.renderTreeLayout();
            return;
        }
        if (this.simulation) this.simulation.stop();
        this.simulation = null;

        var self = this;
        var nodes = this.data.nodes.map(function(n: any) { return Object.assign({}, n); });
        var edges = this.data.edges.map(function(e: any) {
            return { source: typeof e.source === 'string' ? e.source : e.source.id || e.source,
                     target: typeof e.target === 'string' ? e.target : e.target.id || e.target };
        });

        var svgW = +this.svg.attr('width');
        var svgH = +this.svg.attr('height');
        var cx = svgW / 2;
        var cy = svgH / 2;

        var nodeMap: any = {};
        nodes.forEach(function(n: any) { nodeMap[n.id] = n; });

        // ---- compute target positions (constellation layout) ----
        var childMap: any = {};
        var parentMap: any = {};
        edges.forEach(function(e: any) {
            if (!childMap[e.source]) childMap[e.source] = [];
            childMap[e.source].push(e.target);
            parentMap[e.target] = e.source;
        });

        _applyTopicHierarchyLayout(nodes, childMap, nodeMap, parentMap, cx, cy, svgW, svgH, '_tx');
        nodes.forEach(function(n: any) {
            if (n._tx == null || n._ty == null) {
                n._tx = cx;
                n._ty = cy;
            }
        });
        _seedGraphPositions(nodes);

        var maxD = 0;
        nodes.forEach(function(n: any) { if ((n._depth || 0) > maxD) maxD = n._depth || 0; });
        nodes.forEach(function(n: any) {
            if (n._depth == null) n._depth = maxD + 1;
        });
        nodes.forEach(function(n: any) { if (n._depth > maxD) maxD = n._depth; });

        // ---- build SVG elements ----
        this.g.selectAll('*').remove();

        var lc = self.layoutConfig;
        var getRadius = function(d: any) { return _graphNodeRadius(d, lc); };

        // Create all elements hidden initially
        var nodeGroup = self.g.append('g').attr('class', 'graph-nodes');

        var nodeSel = nodeGroup.selectAll('g').data(nodes).join('g')
            .attr('cursor', 'pointer')
            .attr('opacity', 0)
            .attr('transform', function(d: any) { return 'translate(' + d.x + ',' + d.y + ')'; });

        _createGraphNode(nodeSel, getRadius, self.showFilenames);

        var rc = self.layoutConfig;
        var depthRevealInterval = Math.max(rc.replayRevealMinMs,
            Math.min(rc.replayRevealMaxMs, rc.replayRevealBudgetMs / (maxD + 1)));
        var l1s = nodes.filter(function(n: any) { return n.type === 'topic' && n.level === 1; });
        var l1Ids = new Set(l1s.map(function(n: any) { return n.id; }));
        var revealed = new Set(l1Ids);
        var currentDepth = 1;
        var revealTimer = null;

        function syncReveal() {
            nodeSel.attr('opacity', function(d: any) { return revealed.has(d.id) ? 1 : 0; });
        }

        syncReveal();

        function updateReplayPos() {
            nodeSel.attr('transform', function(d: any) { return 'translate(' + d.x + ',' + d.y + ')'; });
        }

        self.simulation = _startGraphRelaxation(nodes, edges, getRadius, updateReplayPos, function() {
            nodeSel.call(_makeGraphDragHandlers(childMap, nodeMap, parentMap, nodes, edges, self.simulation, self));
        });

        function revealNextDepth() {
            if (currentDepth > maxD) {
                self._fitGraphToBounds(nodes, svgW, svgH, getRadius, 600);
                return;
            }
            nodes.filter(function(n: any) { return (n._depth || 0) === currentDepth; })
                .forEach(function(n: any) { revealed.add(n.id); });
            syncReveal();
            currentDepth++;
            if (currentDepth <= maxD) {
                revealTimer = setTimeout(revealNextDepth, depthRevealInterval);
            } else {
                self._fitGraphToBounds(nodes, svgW, svgH, getRadius, 600);
            }
        }

        if (maxD === 0) {
            nodes.forEach(function(n: any) { revealed.add(n.id); });
            syncReveal();
            self._fitGraphToBounds(nodes, svgW, svgH, getRadius, 600);
        } else if (maxD >= 1) {
            revealTimer = setTimeout(revealNextDepth, depthRevealInterval);
        }
    },
};

window.Graph3Tier = Graph3Tier;

function graphZoomIn() { Graph3Tier.zoomIn(); }
function graphZoomOut() { Graph3Tier.zoomOut(); }
function graphZoomReset() { Graph3Tier.zoomReset(); }
function graphReplay() { Graph3Tier.replay(); }
function loadRelationGraphData() { Graph3Tier.load(); }
function graphSetLayoutMode(mode: any) { Graph3Tier.setLayoutMode(mode); }
function graphToggleFilenames() {
    Graph3Tier.showFilenames = !Graph3Tier.showFilenames;
    Graph3Tier.treeInitialCollapseApplied = false;
    var btn = document.getElementById('graph-toggle-filenames');
    if (btn) btn.classList.toggle('active', Graph3Tier.showFilenames);
    if (Graph3Tier.layoutMode === 'tree') {
        Graph3Tier.renderTreeLayout();
        return;
    }
    if (Graph3Tier.g) {
        Graph3Tier.g.selectAll('.graph-nodes text').style('display', function(d: any) {
            if (d.type === 'topic') return '';
            if (d.type === 'tag') return '';
            return Graph3Tier.showFilenames ? '' : 'none';
        });
    }
}
window.graphZoomIn = graphZoomIn;
window.graphZoomOut = graphZoomOut;
window.graphZoomReset = graphZoomReset;
window.graphReplay = graphReplay;
window.loadRelationGraphData = loadRelationGraphData;
window.graphSetLayoutMode = graphSetLayoutMode;
window.graphToggleFilenames = graphToggleFilenames;

// graphOpenLayoutSettings / graphCloseLayoutSettings / graphApplyLayoutSettings /
// graphResetLayoutSettings 与 window.GraphLayoutParams 已迁至 graph-layout-params.js。

// 本模块由 main.mjs 动态 import（在 storage.js 经典脚本之后），执行时 DOM 已解析完成，
// 直接绑定（不再依赖 DOMContentLoaded 重放）
(() => {
    var fnBtn = document.getElementById('graph-toggle-filenames');
    if (fnBtn) fnBtn.classList.toggle('active', Graph3Tier.showFilenames);
    document.querySelectorAll('#graph-filter-bar .graph-filter-btn').forEach(btn => {
        btn.addEventListener('click', function (this: any) {
            const f = this.dataset.filter;
            Graph3Tier.load(f);
        });
    });
    document.querySelectorAll('#graph-layout-mode .graph-layout-mode-btn').forEach(btn => {
        btn.addEventListener('click', function (this: any) {
            Graph3Tier.setLayoutMode(this.dataset.layoutMode);
        });
    });
})();

window.addEventListener('resize', () => Graph3Tier.resize());
