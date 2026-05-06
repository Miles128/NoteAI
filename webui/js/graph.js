window.GraphModule = (function() {
    var _graphData = null;
    var _graphAnimId = null;
    var _graphScale = 1;
    var _graphOffsetX = 0;
    var _graphOffsetY = 0;
    var _graphNodes = null;
    var _graphEdges = null;
    var _graphCanvasW = 0;
    var _graphCanvasH = 0;
    var _graphEvolving = false;
    var _graphAlpha = 1;
    var _graphDrawFrame = null;
    var _graphLoopFn = null;
    var _graphTickFn = null;
    var _graphFilter = 'all';
    var _graphCanvasAbortController = null;
    var _graphNodePositions = {};
    var _showFileLabels = false;

    function loadRelationGraphView() {
        var container = document.getElementById('sidebar-relation');
        if (!container) return;

        var html = '<div class="graph-view">';
        html += '<div class="graph-filter-bar">';
        html += '<button class="graph-filter-btn active" data-gfilter="all" onclick="window.GraphModule.onFilter(\'all\')">全部</button>';
        html += '<button class="graph-filter-btn" data-gfilter="topic" onclick="window.GraphModule.onFilter(\'topic\')">主题</button>';
        html += '<button class="graph-filter-btn" data-gfilter="tag" onclick="window.GraphModule.onFilter(\'tag\')">标签</button>';
        html += '<button class="graph-filter-btn" data-gfilter="link" onclick="window.GraphModule.onFilter(\'link\')">链接</button>';
        html += '<button class="graph-filter-btn graph-label-toggle" id="graph-label-toggle" onclick="window.GraphModule.toggleFileLabels()" title="显示/隐藏文件名称">Aa</button>';
        html += '</div>';
        html += '<div class="graph-canvas-wrap" id="graph-canvas-wrap">';
        html += '<div class="graph-loading" id="graph-loading">加载中...</div>';
        html += '<div class="graph-empty" id="graph-empty" style="display:none;">暂无数据</div>';
        html += '<canvas id="graph-canvas" style="display:none;"></canvas>';
        html += '</div>';
        html += '<div class="graph-legend">';
        html += '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#4A90D9"></span>文件</span>';
        html += '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#E8913A"></span>主题</span>';
        html += '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#50B87F"></span>标签</span>';
        html += '</div>';
        html += '<div class="graph-tooltip" id="graph-tooltip" style="display:none;"></div>';
        html += '</div>';

        container.innerHTML = html;
        loadData();
    }

    async function loadData() {
        var loadingEl = document.getElementById('graph-loading');
        var emptyEl = document.getElementById('graph-empty');
        var canvas = document.getElementById('graph-canvas');

        if (loadingEl) loadingEl.style.display = '';
        if (emptyEl) emptyEl.style.display = 'none';
        if (canvas) canvas.style.display = 'none';

        try {
            var result = await window.api.get_relation_graph();

            if (loadingEl) loadingEl.style.display = 'none';

            if (!result || !result.success) {
                if (emptyEl) {
                    emptyEl.textContent = result?.message || '加载失败';
                    emptyEl.style.display = '';
                }
                return;
            }

            _graphData = result;

            if (!_graphData.nodes || _graphData.nodes.length === 0) {
                if (emptyEl) {
                    emptyEl.textContent = '暂无关系数据';
                    emptyEl.style.display = '';
                }
                return;
            }

            var retryCount = 0;
            function tryInit() {
                var wrap = document.getElementById('graph-panel-body');
                if (wrap && wrap.clientHeight > 20) {
                    initSimulation();
                } else if (retryCount < 20) {
                    retryCount++;
                    setTimeout(tryInit, 50);
                } else {
                    if (emptyEl) {
                        emptyEl.textContent = '图谱容器尺寸异常，请尝试调整窗口大小';
                        emptyEl.style.display = '';
                    }
                }
            }
            setTimeout(tryInit, 100);
        } catch (e) {
            if (loadingEl) loadingEl.style.display = 'none';
            if (emptyEl) {
                emptyEl.textContent = '加载失败: ' + (e.message || e);
                emptyEl.style.display = '';
            }
        }
    }

    function onFilter(filter) {
        _graphFilter = filter;
        document.querySelectorAll('.graph-filter-btn').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.gfilter === filter);
        });
        if (_graphData && _graphData.nodes && _graphData.nodes.length > 0) {
            initSimulation();
        }
    }

    function zoomIn() {
        _graphScale = Math.min(_graphScale * 1.3, 5);
        if (_graphDrawFrame) _graphDrawFrame();
    }

    function zoomOut() {
        _graphScale = Math.max(_graphScale / 1.3, 0.2);
        if (_graphDrawFrame) _graphDrawFrame();
    }

    function toggleEvolve() {
        var btn = document.getElementById('graph-evolve-btn');
        if (!_graphNodes || _graphNodes.length === 0) return;

        if (_graphEvolving) {
            _graphEvolving = false;
            if (btn) btn.classList.remove('active');
            return;
        }

        _graphEvolving = true;
        if (btn) btn.classList.add('active');

        var nodes = _graphNodes;
        var edges = _graphEdges;

        var degreeMap = {};
        nodes.forEach(function(n) { degreeMap[n.id] = 0; });
        edges.forEach(function(e) {
            if (degreeMap[e.source.id] !== undefined) degreeMap[e.source.id]++;
            if (degreeMap[e.target.id] !== undefined) degreeMap[e.target.id]++;
        });

        var sorted = nodes.slice().sort(function(a, b) {
            return (degreeMap[b.id] || 0) - (degreeMap[a.id] || 0);
        });

        var visited = {};
        var revealOrder = [];
        var queue = [sorted[0].id];
        visited[sorted[0].id] = true;

        while (queue.length > 0) {
            var current = queue.shift();
            var node = null;
            for (var i = 0; i < nodes.length; i++) {
                if (nodes[i].id === current) { node = nodes[i]; break; }
            }
            if (!node) continue;
            revealOrder.push(node);

            var neighbors = [];
            edges.forEach(function(e) {
                if (e.source.id === current && !visited[e.target.id]) {
                    neighbors.push(e.target.id);
                    visited[e.target.id] = true;
                }
                if (e.target.id === current && !visited[e.source.id]) {
                    neighbors.push(e.source.id);
                    visited[e.source.id] = true;
                }
            });
            neighbors.sort(function(a, b) { return (degreeMap[b] || 0) - (degreeMap[a] || 0); });
            queue = queue.concat(neighbors);
        }

        sorted.forEach(function(n) {
            if (!visited[n.id]) {
                revealOrder.push(n);
                visited[n.id] = true;
            }
        });

        nodes.forEach(function(n) { n._visible = false; });
        edges.forEach(function(e) { e._visible = false; });

        var revealIndex = 0;
        var batchSize = Math.max(1, Math.ceil(nodes.length / 60));
        var lastRevealTime = 0;
        var revealInterval = 200;

        function revealBatch() {
            if (!_graphEvolving || revealIndex >= revealOrder.length) {
                nodes.forEach(function(n) { n._visible = true; });
                edges.forEach(function(e) { e._visible = true; });
                _graphEvolving = false;
                if (btn) btn.classList.remove('active');
                _graphAlpha = 0.3;
                if (_graphLoopFn) _graphLoopFn();
                return;
            }

            for (var b = 0; b < batchSize && revealIndex < revealOrder.length; b++, revealIndex++) {
                var rnode = revealOrder[revealIndex];
                rnode._visible = true;
                rnode.vx += (Math.random() - 0.5) * 4;
                rnode.vy += (Math.random() - 0.5) * 4;

                edges.forEach(function(e) {
                    if (e.source._visible && e.target._visible) {
                        e._visible = true;
                    }
                    if (e._visible) {
                        var other = null;
                        if (e.source.id === rnode.id) other = e.target;
                        else if (e.target.id === rnode.id) other = e.source;
                        if (other && other._visible) {
                            var dx = other.x - rnode.x;
                            var dy = other.y - rnode.y;
                            var dist = Math.sqrt(dx * dx + dy * dy) || 1;
                            var pushForce = 3;
                            other.vx += dx / dist * pushForce + (Math.random() - 0.5) * 1.5;
                            other.vy += dy / dist * pushForce + (Math.random() - 0.5) * 1.5;
                        }
                    }
                });
            }

            _graphAlpha = 0.4;
        }

        function evolveLoop(timestamp) {
            if (!_graphEvolving) { _graphAnimId = null; return; }

            if (!lastRevealTime) lastRevealTime = timestamp;
            if (timestamp - lastRevealTime >= revealInterval) {
                revealBatch();
                lastRevealTime = timestamp;
            }

            if (_graphTickFn) { for (var i = 0; i < 3; i++) { _graphTickFn(); } }
            if (_graphDrawFrame) _graphDrawFrame();

            _graphAnimId = requestAnimationFrame(evolveLoop);
        }

        _graphAlpha = 0.5;
        if (_graphAnimId) { cancelAnimationFrame(_graphAnimId); _graphAnimId = null; }
        _graphAnimId = requestAnimationFrame(evolveLoop);
    }

    function initSimulation() {
        if (_graphAnimId) {
            cancelAnimationFrame(_graphAnimId);
            _graphAnimId = null;
        }

        var canvas = document.getElementById('graph-canvas');
        var emptyEl = document.getElementById('graph-empty');
        if (!canvas) return;

        var wrap = document.getElementById('graph-panel-body');
        if (!wrap) return;

        var dpr = window.devicePixelRatio || 1;
        var w = wrap.clientWidth;
        var h = wrap.clientHeight;

        if (w < 20 || h < 20) {
            if (emptyEl) {
                emptyEl.textContent = '图谱容器尺寸异常 (' + w + 'x' + h + ')';
                emptyEl.style.display = '';
            }
            canvas.style.display = 'none';
            return;
        }

        canvas.style.display = 'block';
        if (emptyEl) emptyEl.style.display = 'none';

        canvas.width = w * dpr;
        canvas.height = h * dpr;
        canvas.style.width = w + 'px';
        canvas.style.height = h + 'px';

        var ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);

        _graphCanvasW = w;
        _graphCanvasH = h;
        if (Object.keys(_graphNodePositions).length === 0) {
            _graphScale = 2.6;
            _graphOffsetX = 0;
            _graphOffsetY = 0;
        }
        _graphEvolving = false;
        var evolveBtn = document.getElementById('graph-evolve-btn');
        if (evolveBtn) evolveBtn.classList.remove('active');

        var allNodes = _graphData.nodes || [];
        var allEdges = _graphData.edges || [];

        if (allNodes.length === 0) {
            canvas.style.display = 'none';
            if (emptyEl) { emptyEl.textContent = '暂无关系数据'; emptyEl.style.display = ''; }
            return;
        }

        var nodes = [];
        var edges = [];
        var nodeMap = {};

        if (_graphFilter === 'all') {
            allNodes.forEach(function(n) {
                var pos = _graphNodePositions[n.id];
                var node = {
                    id: n.id, label: n.label, nodeType: n.nodeType,
                    x: pos ? pos.x : w / 2 + (Math.random() - 0.5) * w * 0.5,
                    y: pos ? pos.y : h / 2 + (Math.random() - 0.5) * h * 0.5,
                    vx: 0, vy: 0
                };
                nodes.push(node);
                nodeMap[n.id] = node;
            });
            allEdges.forEach(function(e) {
                if (nodeMap[e.source] && nodeMap[e.target]) {
                    edges.push({ source: nodeMap[e.source], target: nodeMap[e.target], type: e.type });
                }
            });
        } else if (_graphFilter === 'topic') {
            var topicIds = new Set();
            allNodes.forEach(function(n) { if (n.nodeType === 'topic') topicIds.add(n.id); });
            var fileIds = new Set();
            allEdges.forEach(function(e) { if (e.type === 'topic') fileIds.add(e.source); });
            allNodes.forEach(function(n) {
                if (topicIds.has(n.id) || fileIds.has(n.id)) {
                    var pos = _graphNodePositions[n.id];
                    var node = { id: n.id, label: n.label, nodeType: n.nodeType, x: pos ? pos.x : w/2+(Math.random()-0.5)*w*0.5, y: pos ? pos.y : h/2+(Math.random()-0.5)*h*0.5, vx:0, vy:0 };
                    nodes.push(node); nodeMap[n.id] = node;
                }
            });
            allEdges.forEach(function(e) {
                if (e.type === 'topic' && nodeMap[e.source] && nodeMap[e.target]) {
                    edges.push({ source: nodeMap[e.source], target: nodeMap[e.target], type: e.type });
                }
            });
        } else if (_graphFilter === 'tag') {
            var tagIds = new Set();
            allNodes.forEach(function(n) { if (n.nodeType === 'tag') tagIds.add(n.id); });
            var fileIds2 = new Set();
            allEdges.forEach(function(e) { if (e.type === 'tag') fileIds2.add(e.source); });
            allNodes.forEach(function(n) {
                if (tagIds.has(n.id) || fileIds2.has(n.id)) {
                    var pos = _graphNodePositions[n.id];
                    var node = { id: n.id, label: n.label, nodeType: n.nodeType, x: pos ? pos.x : w/2+(Math.random()-0.5)*w*0.5, y: pos ? pos.y : h/2+(Math.random()-0.5)*h*0.5, vx:0, vy:0 };
                    nodes.push(node); nodeMap[n.id] = node;
                }
            });
            allEdges.forEach(function(e) {
                if (e.type === 'tag' && nodeMap[e.source] && nodeMap[e.target]) {
                    edges.push({ source: nodeMap[e.source], target: nodeMap[e.target], type: e.type });
                }
            });
        } else if (_graphFilter === 'link') {
            var fileIds3 = new Set();
            allEdges.forEach(function(e) { if (e.type === 'link') { fileIds3.add(e.source); fileIds3.add(e.target); } });
            allNodes.forEach(function(n) {
                if (n.nodeType === 'file' && fileIds3.has(n.id)) {
                    var pos = _graphNodePositions[n.id];
                    var node = { id: n.id, label: n.label, nodeType: n.nodeType, x: pos ? pos.x : w/2+(Math.random()-0.5)*w*0.5, y: pos ? pos.y : h/2+(Math.random()-0.5)*h*0.5, vx:0, vy:0 };
                    nodes.push(node); nodeMap[n.id] = node;
                }
            });
            allEdges.forEach(function(e) {
                if (e.type === 'link' && nodeMap[e.source] && nodeMap[e.target]) {
                    edges.push({ source: nodeMap[e.source], target: nodeMap[e.target], type: e.type });
                }
            });
        }

        if (nodes.length === 0) {
            canvas.style.display = 'none';
            if (emptyEl) { emptyEl.textContent = '该过滤条件下无数据'; emptyEl.style.display = ''; }
            return;
        }

        canvas.style.display = 'block';
        if (emptyEl) emptyEl.style.display = 'none';

        _graphNodes = nodes;
        _graphEdges = edges;

        nodes.forEach(function(n) { n._visible = true; });
        edges.forEach(function(e) { e._visible = true; });

        var reusedCount = 0;
        for (var ri = 0; ri < nodes.length; ri++) {
            if (_graphNodePositions[nodes[ri].id]) reusedCount++;
        }
        var reuseRatio = nodes.length > 0 ? reusedCount / nodes.length : 0;

        var nodeCount = nodes.length;
        var alphaDecay = nodeCount > 200 ? 0.03 : 0.02;
        var alphaMin = 0.001;
        if (reuseRatio > 0.5) {
            _graphAlpha = 0.05;
        } else {
            _graphAlpha = 1;
        }
        var centerPull = nodeCount > 200 ? 0.025 : 0.018;
        var friction = nodeCount > 200 ? 0.85 : 0.88;
        var linkDistance = nodeCount > 200 ? 35 : nodeCount > 100 ? 45 : 55;
        var linkStrength = nodeCount > 200 ? 0.008 : 0.012;
        var repulseStrength = nodeCount > 200 ? 150 : 250;
        var sphereRadius = Math.min(w, h) * 0.48;

        function tick() {
            if (_graphAlpha < alphaMin) { _graphAlpha = alphaMin; }

            for (var i = 0; i < edges.length; i++) {
                var e = edges[i];
                var dx = e.target.x - e.source.x;
                var dy = e.target.y - e.source.y;
                var dist = Math.sqrt(dx * dx + dy * dy) || 1;
                var diff = dist - linkDistance;
                var force = diff * linkStrength * _graphAlpha;
                var fx = dx / dist * force;
                var fy = dy / dist * force;
                e.source.vx += fx; e.source.vy += fy;
                e.target.vx -= fx; e.target.vy -= fy;
            }

            if (nodeCount > 50) {
                var cellSize = linkDistance * 2;
                var grid = {};
                for (var i = 0; i < nodes.length; i++) {
                    var cx = Math.floor(nodes[i].x / cellSize);
                    var cy = Math.floor(nodes[i].y / cellSize);
                    var key = cx + ',' + cy;
                    if (!grid[key]) grid[key] = [];
                    grid[key].push(i);
                }
                for (var key in grid) {
                    var cell = grid[key];
                    var parts = key.split(',');
                    var cx = parseInt(parts[0]);
                    var cy = parseInt(parts[1]);
                    for (var dx = -1; dx <= 1; dx++) {
                        for (var dy = -1; dy <= 1; dy++) {
                            var nkey = (cx + dx) + ',' + (cy + dy);
                            var ncell = grid[nkey];
                            if (!ncell) continue;
                            for (var a = 0; a < cell.length; a++) {
                                var startB = (nkey === key) ? a + 1 : 0;
                                for (var b = startB; b < ncell.length; b++) {
                                    var ni = cell[a];
                                    var nj = ncell[b];
                                    var ddx = nodes[nj].x - nodes[ni].x;
                                    var ddy = nodes[nj].y - nodes[ni].y;
                                    var dist2 = ddx * ddx + ddy * ddy || 1;
                                    var dist = Math.sqrt(dist2);
                                    var f = repulseStrength * _graphAlpha / dist2;
                                    nodes[ni].vx -= ddx / dist * f; nodes[ni].vy -= ddy / dist * f;
                                    nodes[nj].vx += ddx / dist * f; nodes[nj].vy += ddy / dist * f;
                                }
                            }
                        }
                    }
                }
            } else {
                for (var i = 0; i < nodes.length; i++) {
                    for (var j = i + 1; j < nodes.length; j++) {
                        var dx = nodes[j].x - nodes[i].x;
                        var dy = nodes[j].y - nodes[i].y;
                        var dist2 = dx * dx + dy * dy || 1;
                        var dist = Math.sqrt(dist2);
                        var f = repulseStrength * _graphAlpha / dist2;
                        nodes[i].vx -= dx / dist * f; nodes[i].vy -= dy / dist * f;
                        nodes[j].vx += dx / dist * f; nodes[j].vy += dy / dist * f;
                    }
                }
            }

            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                n.vx += (w / 2 - n.x) * centerPull * _graphAlpha;
                n.vy += (h / 2 - n.y) * centerPull * _graphAlpha;
                n.vx *= friction; n.vy *= friction;
                n.x += n.vx; n.y += n.vy;
                var dx = n.x - w / 2;
                var dy = n.y - h / 2;
                var distFromCenter = Math.sqrt(dx * dx + dy * dy);
                if (distFromCenter > sphereRadius) {
                    var scale = sphereRadius / distFromCenter;
                    n.x = w / 2 + dx * scale;
                    n.y = h / 2 + dy * scale;
                    var nx = dx / distFromCenter;
                    var ny = dy / distFromCenter;
                    var dot = n.vx * nx + n.vy * ny;
                    if (dot > 0) {
                        n.vx -= dot * nx * 1.8;
                        n.vy -= dot * ny * 1.8;
                    }
                }
            }
            _graphAlpha *= (1 - alphaDecay);
        }

        var edgeColors = { topic: 'rgba(232,145,58,0.25)', tag: 'rgba(80,184,127,0.25)', link: 'rgba(74,144,217,0.3)' };
        var nodeColors = { file: '#4A90D9', topic: '#E8913A', tag: '#50B87F' };

        function draw() {
            var dw = _graphCanvasW || w;
            var dh = _graphCanvasH || h;
            ctx.clearRect(0, 0, dw, dh);
            ctx.save();
            ctx.translate(dw / 2, dh / 2);
            ctx.scale(_graphScale, _graphScale);
            ctx.translate(-dw / 2 + _graphOffsetX, -dh / 2 + _graphOffsetY);

            var edgeTypeOrder = ['topic', 'tag', 'link'];
            for (var t = 0; t < edgeTypeOrder.length; t++) {
                var etype = edgeTypeOrder[t];
                ctx.strokeStyle = edgeColors[etype] || 'rgba(150,150,150,0.3)';
                ctx.lineWidth = etype === 'link' ? 0.8 : 0.6;
                ctx.setLineDash([]);
                ctx.beginPath();
                for (var i = 0; i < edges.length; i++) {
                    var e = edges[i];
                    if (!e._visible || e.type !== etype) continue;
                    ctx.moveTo(e.source.x, e.source.y);
                    ctx.lineTo(e.target.x, e.target.y);
                }
                ctx.stroke();
                ctx.setLineDash([]);
            }

            var nodeTypeOrder = ['file', 'topic', 'tag'];
            for (var t = 0; t < nodeTypeOrder.length; t++) {
                var ntype = nodeTypeOrder[t];
                ctx.fillStyle = nodeColors[ntype] || '#999';
                ctx.beginPath();
                for (var i = 0; i < nodes.length; i++) {
                    var n = nodes[i];
                    if (!n._visible || n.nodeType !== ntype) continue;
                    var r = ntype === 'file' ? 2.2 : 3.5;
                    ctx.moveTo(n.x + r, n.y);
                    ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
                }
                ctx.fill();
            }

            ctx.fillStyle = '#555';
            ctx.font = '4px -apple-system, BlinkMacSystemFont, sans-serif';
            ctx.textAlign = 'center';
            for (var i = 0; i < nodes.length; i++) {
                var n = nodes[i];
                if (!n._visible) continue;
                if (n.nodeType === 'file') {
                    if (!_showFileLabels && n !== _hoveredNode) continue;
                }
                var r = n.nodeType === 'file' ? 2.2 : 3.5;
                ctx.fillText(n.label, n.x, n.y + r + 5);
            }
            ctx.restore();
        }

        _graphDrawFrame = draw;
        _graphTickFn = tick;

        if (_graphCanvasAbortController) {
            _graphCanvasAbortController.abort();
        }
        _graphCanvasAbortController = new AbortController();
        var acOpts = { signal: _graphCanvasAbortController.signal };

        var _hoveredNode = null;
        var tooltip = document.getElementById('graph-tooltip');

        function screenToGraph(sx, sy) {
            var dw = _graphCanvasW || w;
            var dh = _graphCanvasH || h;
            var gx = (sx - dw / 2) / _graphScale + dw / 2 - _graphOffsetX;
            var gy = (sy - dh / 2) / _graphScale + dh / 2 - _graphOffsetY;
            return { x: gx, y: gy };
        }

        var _dragNode = null;
        var _dragStartX = 0, _dragStartY = 0;
        var _isPanning = false;

        canvas.addEventListener('mousedown', function(ev) {
            var rect = canvas.getBoundingClientRect();
            var mx = ev.clientX - rect.left;
            var my = ev.clientY - rect.top;
            var gp = screenToGraph(mx, my);
            for (var i = nodes.length - 1; i >= 0; i--) {
                var n = nodes[i];
                var r = n.nodeType === 'file' ? 2.2 : 3.5;
                var dx = gp.x - n.x;
                var dy = gp.y - n.y;
                if (dx * dx + dy * dy < (r + 12) * (r + 12)) {
                    _dragNode = n;
                    _dragStartX = mx; _dragStartY = my;
                    return;
                }
            }
            _isPanning = true;
            _dragStartX = mx; _dragStartY = my;
        }, acOpts);

        canvas.addEventListener('mousemove', function(ev) {
            var rect = canvas.getBoundingClientRect();
            var mx = ev.clientX - rect.left;
            var my = ev.clientY - rect.top;

            if (_dragNode) {
                var gp = screenToGraph(mx, my);
                _dragNode.x = gp.x;
                _dragNode.y = gp.y;
                _dragNode.vx = 0; _dragNode.vy = 0;
                draw();
                return;
            }

            if (_isPanning) {
                var dx = mx - _dragStartX;
                var dy = my - _dragStartY;
                _graphOffsetX += dx / _graphScale;
                _graphOffsetY += dy / _graphScale;
                _dragStartX = mx; _dragStartY = my;
                draw();
                return;
            }

            var gp = screenToGraph(mx, my);
            var prevHovered = _hoveredNode;
            _hoveredNode = null;
            for (var i = nodes.length - 1; i >= 0; i--) {
                var n = nodes[i];
                var r = n.nodeType === 'file' ? 2.2 : 3.5;
                var ddx = gp.x - n.x;
                var ddy = gp.y - n.y;
                if (ddx * ddx + ddy * ddy < (r + 8) * (r + 8)) {
                    _hoveredNode = n; break;
                }
            }
            if (_hoveredNode !== prevHovered) draw();
        }, acOpts);

        canvas.addEventListener('mouseup', function() {
            if (_dragNode) {
                _graphNodePositions[_dragNode.id] = { x: _dragNode.x, y: _dragNode.y };
            }
            _dragNode = null;
            _isPanning = false;
        }, acOpts);

        canvas.addEventListener('click', function() {
            if (_hoveredNode) {
                if (_hoveredNode.nodeType === 'file') {
                    if (window.TreeModule && window.TreeModule.selectFile) {
                        window.TreeModule.selectFile(_hoveredNode.id, _hoveredNode.label + '.md');
                    }
                }
            }
        }, acOpts);

        canvas.addEventListener('mouseleave', function() {
            _hoveredNode = null;
            draw();
        }, acOpts);

        canvas.addEventListener('touchstart', function(ev) {
            ev.preventDefault();
            if (ev.touches.length !== 1) return;
            var touch = ev.touches[0];
            var rect = canvas.getBoundingClientRect();
            var mx = touch.clientX - rect.left;
            var my = touch.clientY - rect.top;
            var gp = screenToGraph(mx, my);
            for (var i = nodes.length - 1; i >= 0; i--) {
                var n = nodes[i];
                var r = n.nodeType === 'file' ? 2.2 : 3.5;
                var dx = gp.x - n.x;
                var dy = gp.y - n.y;
                if (dx * dx + dy * dy < (r + 12) * (r + 12)) {
                    _dragNode = n;
                    _dragStartX = mx; _dragStartY = my;
                    return;
                }
            }
            _isPanning = true;
            _dragStartX = mx; _dragStartY = my;
        }, { passive: false, signal: acOpts.signal });

        canvas.addEventListener('touchmove', function(ev) {
            ev.preventDefault();
            if (ev.touches.length !== 1) return;
            var touch = ev.touches[0];
            var rect = canvas.getBoundingClientRect();
            var mx = touch.clientX - rect.left;
            var my = touch.clientY - rect.top;

            if (_dragNode) {
                var gp = screenToGraph(mx, my);
                _dragNode.x = gp.x;
                _dragNode.y = gp.y;
                _dragNode.vx = 0; _dragNode.vy = 0;
                draw();
                return;
            }

            if (_isPanning) {
                var dx = mx - _dragStartX;
                var dy = my - _dragStartY;
                _graphOffsetX += dx / _graphScale;
                _graphOffsetY += dy / _graphScale;
                _dragStartX = mx; _dragStartY = my;
                draw();
            }
        }, { passive: false, signal: acOpts.signal });

        canvas.addEventListener('touchend', function(ev) {
            if (_dragNode && _dragNode.nodeType === 'file') {
                if (window.TreeModule && window.TreeModule.selectFile) {
                    window.TreeModule.selectFile(_dragNode.id, _dragNode.label + '.md');
                }
            }
            _dragNode = null;
            _isPanning = false;
        }, acOpts);

        canvas.addEventListener('wheel', function(ev) {
            ev.preventDefault();
            if (ev.deltaY < 0) {
                _graphScale = Math.min(_graphScale * 1.1, 5);
            } else {
                _graphScale = Math.max(_graphScale / 1.1, 0.2);
            }
            draw();
        }, acOpts);

        function loop() {
            for (var i = 0; i < 3; i++) { tick(); }
            draw();
            if (_graphAlpha > alphaMin * 2 || _graphEvolving) {
                _graphAnimId = requestAnimationFrame(loop);
            } else {
                _graphAnimId = null;
                for (var i = 0; i < nodes.length; i++) {
                    _graphNodePositions[nodes[i].id] = { x: nodes[i].x, y: nodes[i].y };
                }
            }
        }

        _graphLoopFn = loop;
        loop();

        if (window._graphResizeObserver) {
            window._graphResizeObserver.disconnect();
        }
        window._graphResizeObserver = new ResizeObserver(function() {
            var wrapEl = document.getElementById('graph-panel-body');
            var canvasEl = document.getElementById('graph-canvas');
            if (!wrapEl || !canvasEl) return;
            var dpr = window.devicePixelRatio || 1;
            var nw = wrapEl.clientWidth;
            var nh = wrapEl.clientHeight;
            if (nw < 20 || nh < 20) return;
            var oldW = _graphCanvasW || nw;
            var oldH = _graphCanvasH || nh;
            canvasEl.width = nw * dpr;
            canvasEl.height = nh * dpr;
            canvasEl.style.width = nw + 'px';
            canvasEl.style.height = nh + 'px';
            var nctx = canvasEl.getContext('2d');
            nctx.scale(dpr, dpr);
            var scaleRatio = Math.sqrt((nw * nh) / (oldW * oldH));
            if (scaleRatio > 0.05 && scaleRatio < 20 && oldW > 20 && oldH > 20) {
                _graphScale *= scaleRatio;
                _graphScale = Math.max(0.2, Math.min(5, _graphScale));
            }
            _graphOffsetX = 0;
            _graphOffsetY = 0;
            _graphCanvasW = nw;
            _graphCanvasH = nh;
            if (_graphDrawFrame) _graphDrawFrame();
        });
        window._graphResizeObserver.observe(wrap);
    }

    function toggleFileLabels() {
        _showFileLabels = !_showFileLabels;
        var btn = document.getElementById('graph-label-toggle');
        if (btn) btn.classList.toggle('active', _showFileLabels);
        if (_graphDrawFrame) _graphDrawFrame();
    }

    return {
        loadRelationGraphView: loadRelationGraphView,
        loadData: loadData,
        onFilter: onFilter,
        zoomIn: zoomIn,
        zoomOut: zoomOut,
        toggleEvolve: toggleEvolve,
        toggleFileLabels: toggleFileLabels,
        initSimulation: initSimulation
    };
})();
