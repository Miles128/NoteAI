// ============================================================================
// semantic-graph.js —— 语义关系星云图（实体/概念/文档共现网络）
// 职责：语义图谱模式下的 D3 力导向渲染、scope 控件、缩放交互与点击导航。
// 对外：window.SemanticGraphModule
//   数据:  load / getState
//   交互:  zoomIn / zoomOut / zoomReset / refresh / setModeActive
// 依赖（调用时动态读取，无加载期耦合）：
//   window.api.getSemanticGraphData、window.AppState、window.t
//   window.SemanticWorkbenchModule.openObject、window.TreeModule.selectFile
// ============================================================================
(function() { 'use strict';

var _state = {
    scope: 'auto',          // auto | all | doc
    limit: 80,
    includeDocs: false,
    minShare: 2,
    loading: false,
    error: null,
    data: null
};

var _svg = null;
var _simulation = null;
var _zoom = null;
var _rootG = null;
var _nodesG = null;
var _edgesG = null;

var _ENTITY_COLORS = {
    product: '#5B7DB1',
    artifact: '#8fa9d0',
    model: '#4a90d9',
    organization: '#2f6fb3',
    person: '#1f4e79',
    protocol: '#9bb8e0',
    other: '#86a9d6'
};
var _CONCEPT_COLOR = '#7c4dff';
var _DOC_COLOR = '#9aa0a6';
var _EDGE_COLOR = 'rgba(120,140,170,0.35)';
var _HIGHLIGHT_EDGE_COLOR = 'rgba(90,120,200,0.7)';

function t(key) {
    return (window.t && window.t(key)) || key;
}

function _container() {
    return document.getElementById('semantic-graph-container');
}

function _graphBody() {
    return document.getElementById('graph-panel-body');
}

function _resolveScope() {
    if (_state.scope === 'doc') return 'doc';
    if (_state.scope === 'all') return 'all';
    // auto：当前有打开文档则按文档，否则全库
    var current = window.AppState && window.AppState.selectedFilePath;
    return current ? 'doc' : 'all';
}

function _currentFilePath() {
    return window.AppState && window.AppState.selectedFilePath;
}

function _buildRequest() {
    var scope = _resolveScope();
    var req = {
        scope: scope,
        limit: _state.limit,
        min_share: _state.minShare,
        include_docs: _state.includeDocs
    };
    if (scope !== 'all' && _currentFilePath()) {
        req.filter = _currentFilePath();
    }
    return req;
}

function _nodeColor(d) {
    if (d.kind === 'concept') return _CONCEPT_COLOR;
    if (d.kind === 'doc') return _DOC_COLOR;
    return _ENTITY_COLORS[d.entity_type] || _ENTITY_COLORS.other;
}

function _nodeRadius(d) {
    if (d.kind === 'doc') return Math.max(3, Math.min(8, 2 + Math.sqrt(d.count || 1) * 0.6));
    return Math.max(5, Math.min(22, 3 + Math.sqrt(d.count || 1) * 1.8));
}

function _nodeFontSize(d) {
    var r = _nodeRadius(d);
    return (d.kind === 'doc') ? '7px' : (r > 14 ? '9px' : '8px');
}

function _displayName(d) {
    var name = d.name || d.id;
    return name.length > 14 ? name.slice(0, 13) + '…' : name;
}

function _nodeTooltip(d) {
    var lines = [];
    if (d.kind === 'entity') {
        lines.push(t('graph.semantic.entity') + ': ' + d.name);
        lines.push(t('graph.stats.topics') + ': ' + (d.entity_type || 'other'));
    } else if (d.kind === 'concept') {
        lines.push(t('graph.semantic.concept') + ': ' + d.name);
    } else {
        lines.push(t('graph.semantic.doc') + ': ' + d.name);
    }
    lines.push(t('graph.semantic.objectSuffix') ? ('×' + d.count) : ('×' + d.count));
    if (d.description) lines.push(d.description.length > 120 ? d.description.slice(0, 119) + '…' : d.description);
    return lines.join('\n');
}

function _clearSvg() {
    if (_simulation) {
        _simulation.stop();
        _simulation = null;
    }
    if (_svg) {
        _svg.selectAll('*').remove();
        _svg.remove();
        _svg = null;
    }
    _rootG = _nodesG = _edgesG = null;
    _zoom = null;
}

function _render(data) {
    var body = _graphBody();
    var container = _container();
    if (!container || !body) return;
    container.style.display = 'block';
    // 清理 G3 渲染的 svg（本面板 body 内可能已有其他 svg）
    body.querySelectorAll('svg').forEach(function(s) { s.remove(); });

    var width = container.clientWidth || body.clientWidth || 800;
    var height = container.clientHeight || body.clientHeight || 560;

    _svg = d3.select(container)
        .append('svg')
        .attr('width', width)
        .attr('height', height)
        .style('display', 'block')
        .style('width', '100%')
        .style('height', '100%');

    _zoom = d3.zoom()
        .scaleExtent([0.25, 6])
        .on('zoom', function(evt) {
            if (_rootG) _rootG.attr('transform', evt.transform);
            var pct = document.getElementById('semantic-graph-zoom-percent');
            if (pct) pct.textContent = Math.round(evt.transform.k * 100) + '%';
        });
    _svg.call(_zoom);

    _rootG = _svg.append('g');
    _edgesG = _rootG.append('g');
    _nodesG = _rootG.append('g');

    var links = (data.edges || []).map(function(e) {
        return { source: e.source, target: e.target, weight: e.weight || 1, relation_type: e.relation_type };
    });
    var nodes = (data.nodes || []).map(function(n) {
        return Object.assign({}, n, { weight: n.count || 1 });
    });
    var idIndex = {};
    nodes.forEach(function(n) { idIndex[n.id] = n; });
    links = links.filter(function(l) { return idIndex[l.source] && idIndex[l.target]; });

    var linkEls = _edgesG.selectAll('line').data(links).enter().append('line')
        .attr('stroke', _EDGE_COLOR)
        .attr('stroke-width', function(d) { return Math.max(0.5, Math.min(3.5, Math.sqrt(d.weight) * 0.8)); })
        .style('opacity', 0.55);

    var nodeEls = _nodesG.selectAll('g').data(nodes).enter().append('g')
        .attr('class', function(d) { return 'semantic-graph-node semantic-graph-node-' + (d.kind || 'object'); })
        .style('cursor', 'pointer');

    nodeEls.append('circle')
        .attr('r', function(d) { return _nodeRadius(d); })
        .attr('fill', function(d) { return _nodeColor(d); })
        .attr('stroke', 'rgba(255,255,255,0.85)')
        .attr('stroke-width', 1);

    nodeEls.append('text')
        .attr('dy', function(d) { return _nodeRadius(d) + 11; })
        .attr('text-anchor', 'middle')
        .attr('font-size', function(d) { return _nodeFontSize(d); })
        .attr('fill', function(d) {
            return d.kind === 'concept' ? 'var(--color-tag, #6a3de8)' : 'var(--text-muted, #777)';
        })
        .style('pointer-events', 'none')
        .text(function(d) { return _displayName(d); });

    nodeEls.append('title').text(function(d) { return _nodeTooltip(d); });

    nodeEls.on('click', function(evt, d) {
        evt.stopPropagation();
        _onNodeClick(d);
    });

    _simulation = d3.forceSimulation(nodes)
        .force('link', d3.forceLink(links).id(function(d) { return d.id; })
            .distance(function(l) { return Math.max(40, 110 - (l.weight || 1) * 4); })
            .strength(0.35))
        .force('charge', d3.forceManyBody().strength(-160))
        .force('collide', d3.forceCollide().radius(function(d) { return _nodeRadius(d) + 14; }))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .on('tick', function() {
            linkEls
                .attr('x1', function(d) { return d.source.x; })
                .attr('y1', function(d) { return d.source.y; })
                .attr('x2', function(d) { return d.target.x; })
                .attr('y2', function(d) { return d.target.y; });
            nodeEls.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; });
        });

    // 点击空白取消高亮
    _svg.on('click', function() {
        _highlight(null);
    });
}

function _highlight(activeNode) {
    if (!_svg || !_data) return;
    _nodesG.selectAll('g').each(function(d) {
        d3.select(this).select('circle').attr('stroke',
            activeNode && d.id === activeNode.id ? '#e85d3a' : 'rgba(255,255,255,0.85)');
    });
    _edgesG.selectAll('line')
        .attr('stroke', function(l) {
            if (!activeNode) return _EDGE_COLOR;
            return (l.source.id === activeNode.id || l.target.id === activeNode.id) ? _HIGHLIGHT_EDGE_COLOR : _EDGE_COLOR;
        })
        .style('opacity', function(l) {
            if (!activeNode) return 0.55;
            return (l.source.id === activeNode.id || l.target.id === activeNode.id) ? 0.95 : 0.15;
        });
}

function _onNodeClick(d) {
    if (d.kind === 'entity' || d.kind === 'concept') {
        if (window.SemanticWorkbenchModule && window.SemanticWorkbenchModule.openObject) {
            window.SemanticWorkbenchModule.openObject(d.kind, d.object_id);
        }
        return;
    }
    if (d.kind === 'doc' && d.path) {
        var fileName = (d.path.split('/').pop() || '').replace(/\.md$/i, '');
        if (window.TreeModule && window.TreeModule.selectFile) {
            window.TreeModule.selectFile(d.path, fileName);
        }
    }
}

function _updateStats(data) {
    var notesEl = document.getElementById('graph-stat-notes');
    var topicsEl = document.getElementById('graph-stat-topics');
    if (!notesEl || !topicsEl) return;
    notesEl.textContent = (data.nodes || []).length;
    topicsEl.textContent = (data.edges || []).length;
    document.querySelectorAll('.graph-stats-bar [data-i18n]').forEach(function(el) { el.style.display = 'none'; });
    notesEl.title = t('graph.semantic.objectSuffix');
    topicsEl.title = t('graph.semantic.edgeSuffix');
}

function _renderLegend(data) {
    var legend = document.getElementById('graph-legend');
    if (!legend) return;
    var hasEntities = (data.nodes || []).some(function(n) { return n.kind === 'entity'; });
    var hasConcepts = (data.nodes || []).some(function(n) { return n.kind === 'concept'; });
    var hasDocs = (data.nodes || []).some(function(n) { return n.kind === 'doc'; });
    var html = '';
    if (hasEntities) html += '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#5B7DB1"></span>' + t('graph.semantic.entity') + '</span>';
    if (hasConcepts) html += '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:' + _CONCEPT_COLOR + '"></span>' + t('graph.semantic.concept') + '</span>';
    if (hasDocs) html += '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:' + _DOC_COLOR + '"></span>' + t('graph.semantic.doc') + '</span>';
    if ((data.edges || []).length) html += '<span class="graph-legend-item"><span class="graph-legend-line"></span>' + t('graph.semantic.edge') + '</span>';
    legend.innerHTML = html;
    legend.style.display = html ? '' : 'none';
}

function _showEmpty(message) {
    _clearSvg();
    var container = _container();
    if (!container) return;
    container.style.display = 'block';
    container.innerHTML = '<div class="graph-empty" style="display:block;">' + (message || t('graph.semantic.empty')) + '</div>';
}

function load() {
    var container = _container();
    if (!container) return;
    _state.error = null;
    _state.loading = true;
    var loading = document.getElementById('graph-loading');
    if (loading) loading.style.display = 'block';

    var req = _buildRequest();
    if (!window.api || !window.api.getSemanticGraphData) {
        _showEmpty('API 未就绪');
        if (loading) loading.style.display = 'none';
        return;
    }
    window.api.getSemanticGraphData(req).then(function(result) {
        _state.loading = false;
        if (loading) loading.style.display = 'none';
        if (!result || !result.success) {
            _showEmpty((result && result.message) || t('graph.semantic.empty'));
            return;
        }
        _data = result;
        container.innerHTML = '';
        if (!result.nodes || !result.nodes.length) {
            _showEmpty();
            return;
        }
        _render(result);
        _updateStats(result);
        _renderLegend(result);
        var pct = document.getElementById('semantic-graph-zoom-percent');
        if (pct) pct.textContent = '100%';
    }).catch(function(err) {
        _state.loading = false;
        if (loading) loading.style.display = 'none';
        _showEmpty('加载失败: ' + (err && err.message ? err.message : String(err)));
    });
}

function zoomBy(factor) {
    if (!_svg || !_zoom) return;
    _svg.transition().duration(150).call(_zoom.scaleBy, factor);
}

function zoomReset() {
    if (!_svg || !_zoom) return;
    _svg.transition().duration(150).call(_zoom.transform, d3.zoomIdentity);
}

function refresh() {
    var limitEl = document.getElementById('semantic-graph-limit');
    var scopeEl = document.getElementById('semantic-graph-scope');
    var docsEl = document.getElementById('semantic-graph-docs');
    var shareEl = document.getElementById('semantic-graph-min-share');
    if (limitEl) _state.limit = parseInt(limitEl.value, 10) || 80;
    if (scopeEl) _state.scope = scopeEl.value || 'auto';
    if (docsEl) _state.includeDocs = !!docsEl.checked;
    if (shareEl) _state.minShare = parseInt(shareEl.value, 10) || 2;
    load();
}

function setModeActive(active) {
    var container = _container();
    var controls = document.getElementById('graph-semantic-controls');
    if (container) container.style.display = active ? 'block' : 'none';
    if (controls) controls.style.display = active ? 'flex' : 'none';
    if (active) {
        refresh();
    } else {
        _clearSvg();
        var body = _graphBody();
        if (body) body.querySelectorAll('#semantic-graph-container').forEach(function(el) { el.style.display = 'none'; });
    }
}

window.SemanticGraphModule = {
    load: load,
    refresh: refresh,
    zoomIn: function() { zoomBy(1.3); },
    zoomOut: function() { zoomBy(1 / 1.3); },
    zoomReset: zoomReset,
    setModeActive: setModeActive,
    isActive: function() { return (window.AppState && window.AppState.graphMode === 'semantic') || false; }
};

})();
