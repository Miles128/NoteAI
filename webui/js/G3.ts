// ================================================================
// 知识图谱 (D3 力导向布局 - Obsidian 风格)
// ================================================================

/** 图谱拖动：收集某主题节点下所有子节点 id */
function _collectDescendantIds(rootId: any, childMap: any) {
    const seen = new Set();
    const stack = (childMap[rootId] || []).slice();
    while (stack.length) {
        const id = stack.pop();
        if (seen.has(id)) continue;
        seen.add(id);
        (childMap[id] || []).forEach(function(cid: any) { stack.push(cid); });
    }
    return seen;
}

const _GRAPH_TAU = Math.PI * 2;
const _GRAPH_GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
// 布局参数默认值 / Schema / Storage 读写与面板 UI 已拆至 graph-layout-params.js
// （window.GraphLayoutParams，见 main.mjs 加载顺序：本文件之前加载）。
const GRAPH_LAYOUT_DEFAULTS: any = window.GraphLayoutParams!.defaults;
const loadGraphLayoutConfig: any = window.GraphLayoutParams!.load;
const saveGraphLayoutConfig: any = window.GraphLayoutParams!.save;
const resetGraphLayoutConfigStorage: any = window.GraphLayoutParams!.resetStorage;
const loadGraphLayoutMode: any = window.GraphLayoutParams!.loadMode;
const saveGraphLayoutMode: any = window.GraphLayoutParams!.saveMode;
var showPreview: any;
/** 节点圆半径显示缩放（相对布局配置值） */
const _GRAPH_RADIUS_DISPLAY_SCALE = 0.75;

/** 图谱节点实际渲染半径（配置值 × 显示缩放） */
function _graphNodeRadius(d: any, lc: any) {
    const base = (d.type === 'topic' && d.level === 1) ? lc.radiusL1 : lc.radiusOther;
    return base * _GRAPH_RADIUS_DISPLAY_SCALE;
}

function _graphNodeColor(d: any) {
    if (d.type === 'topic') {
        if (d.level === 1) return '#e85d3a';
        if (d.level === 2) return '#ea8600';
        return '#f4a930';
    }
    if (d.type === 'tag') return '#7c4dff';
    return '#81c784';
}

function _graphNodeStroke(d: any) {
    if (d.has_abstract) return '#e6c200';
    if (d.type === 'tag') return 'rgba(124,77,255,0.4)';
    return d.type === 'topic' ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.25)';
}

function _graphNodeStrokeWidth(d: any) {
    return d.has_abstract ? 3 : 0.8;
}

function _graphNodeFontSize(d: any) {
    if (d.type === 'topic' && d.level === 1) return '10px';
    if (d.type === 'topic' && d.level === 2) return '9px';
    if (d.type === 'tag') return '9px';
    return '8px';
}

function _graphNodeTextFill(d: any) {
    if (d.type === 'topic') return 'var(--text-muted, #555)';
    if (d.type === 'tag') return 'var(--color-tag, #6a3de8)';
    return 'var(--text-muted, #777)';
}

function _graphNodeTextDisplay(d: any, showFilenames: any) {
    if (d.type === 'topic') return '';
    if (d.type === 'tag') return '';
    return showFilenames ? '' : 'none';
}

function _graphNodeClass(d: any) {
    var parts = ['graph-node', 'graph-node-' + (d.type || 'unknown')];
    if (d.type === 'topic') parts.push('graph-node-level-' + (d.level || 0));
    if (d.has_abstract) parts.push('has-survey');
    return parts.join(' ');
}

function _graphNodeSubtitle(d: any) {
    if (d.type === 'topic') {
        var count = Number(d.file_count || 0);
        var text = count + ((window.t && window.t('graph.tree.noteCountSuffix')) || ' notes');
        if (d.has_abstract) text += ' · ' + ((window.t && window.t('graph.stats.survey')) || 'Survey');
        if (d._collapsed) text += ' · ' + ((window.t && window.t('graph.tree.collapsed')) || 'Collapsed');
        return text;
    }
    if (d.type === 'tag') {
        var tagText = Number(d.file_count || 0) + ((window.t && window.t('graph.tree.noteCountSuffix')) || ' notes');
        if (d._collapsed) tagText += ' · ' + ((window.t && window.t('graph.tree.collapsed')) || 'Collapsed');
        return tagText;
    }
    return (window.t && window.t('graph.tree.noteType')) || 'Note';
}

function _treeDepthLabel(depth: any, rows: any) {
    const types = new Set((rows || []).map(function(d: any) { return d.data && d.data.type; }));
    if (types.size === 1 && types.has('tag')) return (window.t && window.t('graph.tree.depthTags')) || 'Tags';
    if (types.size === 1 && types.has('file')) return (window.t && window.t('graph.tree.depthNotes')) || 'Notes';
    if (depth === 1) return (window.t && window.t('graph.tree.depthL1')) || 'L1';
    if (depth === 2) return (window.t && window.t('graph.tree.depthL2')) || 'L2';
    if (depth === 3) return (window.t && window.t('graph.tree.depthL3')) || 'L3';
    return (window.t && window.t('graph.tree.depthNotes')) || 'Notes';
}

function _mindMapTextWidth(text: any) {
    return Array.from(String(text || '')).reduce(function(width, char) {
        return width + (/[^\u0000-\u00ff]/.test(char) ? 13 : 7.2);
    }, 0);
}

function _mindMapNodeWidth(d: any) {
    const padding = d.type === 'file' ? 18 : 28;
    const minWidth = d.type === 'file' ? 58 : 82;
    const maxWidth = d.type === 'file' ? 172 : 196;
    return Math.max(minWidth, Math.min(maxWidth, _mindMapTextWidth(d.name) + padding));
}

function _mindMapNodeHeight(d: any) {
    if (d.type === 'file') return 25;
    if (d.type === 'topic' && Number(d.level || 0) === 1) return 42;
    return 36;
}

function _mindMapLabel(text: any, maxLength: any) {
    const chars = Array.from(String(text || ''));
    return chars.length > maxLength ? chars.slice(0, maxLength - 1).join('') + '…' : chars.join('');
}

function _createGraphNode(nodeSelection: any, getRadius: any, showFilenames: any) {
    nodeSelection.attr('class', _graphNodeClass);

    nodeSelection.append('circle')
        .attr('r', (d: any) => getRadius(d))
        .attr('fill', _graphNodeColor)
        .attr('stroke', _graphNodeStroke)
        .attr('stroke-width', _graphNodeStrokeWidth);

    nodeSelection.append('text')
        .text((d: any) => d.name || '')
        .attr('text-anchor', 'middle')
        .attr('dy', (d: any) => -(getRadius(d) + 4))
        .style('font-size', _graphNodeFontSize)
        .style('font-weight', (d: any) => d.type === 'topic' && d.level <= 2 ? 'bold' : 'normal')
        .style('fill', _graphNodeTextFill)
        .style('pointer-events', 'none')
        .style('display', (d: any) => _graphNodeTextDisplay(d, showFilenames));

    nodeSelection.append('title')
        .text(function(d: any) {
            return (d.name || '') + '\n' + _graphNodeSubtitle(d);
        });
}

function _graphCfg() {
    return (Graph3Tier && Graph3Tier.layoutConfig) ? Graph3Tier.layoutConfig : GRAPH_LAYOUT_DEFAULTS;
}

function _noteDiskRadius(noteCount: any) {
    const c = _graphCfg();
    const n = Math.max(1, noteCount);
    return Math.min(c.noteDiskMax, Math.max(c.noteDiskMin, c.noteDiskBase + c.noteDiskSqrtCoef * Math.sqrt(n)));
}

function _l2RingRadius(l2Count: any, maxNotesPerL2: any) {
    const c = _graphCfg();
    const n2 = Math.max(1, l2Count);
    const nf = Math.max(1, maxNotesPerL2);
    return Math.min(c.l2RingMax, Math.max(c.l2RingMin,
        c.l2RingBase + c.l2RingSqrtL2 * Math.sqrt(n2) + c.l2RingSqrtNotes * Math.sqrt(nf)));
}

function _l3TopicDiskRadius(l3Count: any) {
    const c = _graphCfg();
    const n = Math.max(1, l3Count);
    return Math.min(c.l3RingMax, Math.max(c.l3RingMin, c.l3RingBase + c.l3RingSqrtL3 * Math.sqrt(n)));
}

/** 在圆盘内均匀散布（非圆周）；itemIds 为节点 id 列表 */
function _scatterInDisk(ox: any, oy: any, itemIds: any, nodeMap: any, maxRadius: any, coordKey: any, clusterId: any, depthVal: any) {
    const xk = coordKey;
    const yk = coordKey === '_tx' ? '_ty' : 'ty';
    const n = itemIds.length;
    if (!n) return;
    const c = _graphCfg();
    const R = Math.max(c.noteDiskMin, maxRadius);
    itemIds.forEach(function(id: any, i: any) {
        const node = nodeMap[id];
        if (!node) return;
        const t = (i + 0.5) / n;
        const r = n === 1 ? R * c.noteSingleRadiusRatio : R * Math.sqrt(t);
        const angle = i * _GRAPH_GOLDEN_ANGLE;
        node[xk] = ox + Math.cos(angle) * r;
        node[yk] = oy + Math.sin(angle) * r;
        if (clusterId != null) node._l2Cluster = clusterId;
        if (depthVal != null) node._depth = depthVal;
    });
}

/** 主题节点在环形区域内散布（内圈留给一级直属笔记） */
function _scatterTopicsInAnnulus(ox: any, oy: any, topicIds: any, nodeMap: any, rInner: any, rOuter: any, coordKey: any, depthBase: any, onPlaced: any) {
    const xk = coordKey;
    const yk = coordKey === '_tx' ? '_ty' : 'ty';
    const n = topicIds.length;
    if (!n) return;
    const c = _graphCfg();
    const ri = Math.max(0, rInner);
    const ro = Math.max(ri + c.annulusMinSpan, rOuter);
    const ri2 = ri * ri;
    const ro2 = ro * ro;
    const angle0 = c.annulusAngleOffset;
    topicIds.forEach(function(tid: any, i: any) {
        const node = nodeMap[tid];
        if (!node) return;
        const t = (i + 0.5) / n;
        const r = n === 1 ? (ri + ro) * c.annulusSingleTopicRatio : Math.sqrt(ri2 + t * (ro2 - ri2));
        const angle = angle0 + i * _GRAPH_GOLDEN_ANGLE;
        node[xk] = ox + Math.cos(angle) * r;
        node[yk] = oy + Math.sin(angle) * r;
        if (depthBase != null) node._depth = depthBase + 1;
        if (onPlaced) onPlaced(tid, node[xk], node[yk]);
    });
}

function _seedGraphPositions(nodes: any) {
    nodes.forEach(function(n: any) {
        if (n.tx == null || n.ty == null) return;
        n.x = n.tx;
        n.y = n.ty;
        n.fx = null;
        n.fy = null;
        n.vx = 0;
        n.vy = 0;
    });
}

function _pinGraphNodes(nodes: any) {
    nodes.forEach(function(n: any) {
        if (n.tx == null || n.ty == null) return;
        n.tx = n.x;
        n.ty = n.y;
        n.fx = n.x;
        n.fy = n.y;
    });
}

function _graphCollideRadius(d: any, getRadius: any) {
    const c = _graphCfg();
    if (d.type === 'file') return getRadius(d) + c.fileCollidePad;
    return getRadius(d) + c.topicCollidePad;
}

function _graphTargetStrength(d: any) {
    const c = _graphCfg();
    if (d._dragging) return 0;
    if (d.type === 'topic') return c.targetStrengthTopic;
    return c.targetStrengthFile;
}

function _graphChargeStrength(d: any) {
    const c = _graphCfg();
    if (d.type === 'topic' && d.level === 1) return c.chargeL1;
    if (d.type === 'topic') return c.chargeTopic;
    return c.chargeFile;
}

/** 图谱数据内容指纹：节点/边数量相同但内容变化（重命名、标签、层级等）
 *  时也能识别，避免 _doLoad 错误跳过刷新。O(n log n)，仅几百节点。 */
function _graphDataFingerprint(data: any) {
    if (!data || !Array.isArray(data.nodes)) return '';
    var nodes = data.nodes.map(function(n: any) {
        return (n.id || '') + '|' + (n.type || '') + '|' + (n.name || n.label || '') + '|' + (n.level || 0);
    }).sort().join('~');
    var edges = (data.edges || []).map(function(e: any) {
        var s = typeof e.source === 'string' ? e.source : (e.source && e.source.id) || e.source;
        var t = typeof e.target === 'string' ? e.target : (e.target && e.target.id) || e.target;
        return s + '>' + t;
    }).sort().join('~');
    return data.nodes.length + ':' + data.edges.length + ':' + nodes + '|' + edges;
}

/** 不同一级主题簇之间：仅近距离互斥，避免整图被撑开。
 *  空间哈希分桶（按 clusterRepelDist 网格）：只比较同桶/邻桶节点对，
 *  每 tick 从 O(n²) 全对计算降为 O(n·k)（k 为桶内平均节点数）。
 *  原实现 500 节点 = 12.5 万对/tick × ~300 tick 的纯距离计算。 */
function _graphClusterRepelForce(nodes: any) {
    const c = _graphCfg();
    return function(alpha: any) {
        const cell = Math.max(1, c.clusterRepelDist || 60);
        const buckets = new Map();
        for (const node of nodes) {
            const key = Math.floor(node.x / cell) + ',' + Math.floor(node.y / cell);
            let list = buckets.get(key);
            if (!list) { list = []; buckets.set(key, list); }
            list.push(node);
        }
        const force = c.clusterRepelForce * alpha;
        const visited = new Set();
        for (const node of nodes) {
            const bx = Math.floor(node.x / cell);
            const by = Math.floor(node.y / cell);
            for (let ox = -1; ox <= 1; ox++) {
                for (let oy = -1; oy <= 1; oy++) {
                    const list = buckets.get((bx + ox) + ',' + (by + oy));
                    if (!list) continue;
                    for (const other of list) {
                        if (other === node) continue;
                        const idA = node.index < other.index ? node.index : other.index;
                        const idB = node.index < other.index ? other.index : node.index;
                        const pairKey = idA + ':' + idB;
                        if (visited.has(pairKey)) continue;
                        visited.add(pairKey);
                        if (node._l1Group === other._l1Group) continue;
                        let dx = node.x - other.x;
                        let dy = node.y - other.y;
                        const dist = Math.hypot(dx, dy) || 1;
                        if (dist > c.clusterRepelDist) continue;
                        const f = force / (dist * dist);
                        node.vx += (dx / dist) * f;
                        node.vy += (dy / dist) * f;
                        other.vx -= (dx / dist) * f;
                        other.vy -= (dy / dist) * f;
                    }
                }
            }
        }
    };
}

function _startGraphRelaxation(nodes: any, edges: any, getRadius: any, onTick: any, onEnd: any) {
    const c = _graphCfg();
    const sim = window.d3.forceSimulation(nodes)
        .force('x', window.d3.forceX(function(d: any) { return d.tx; }).strength(_graphTargetStrength))
        .force('y', window.d3.forceY(function(d: any) { return d.ty; }).strength(_graphTargetStrength))
        .force('charge', window.d3.forceManyBody().strength(_graphChargeStrength))
        .force('collide', window.d3.forceCollide(function(d: any) { return _graphCollideRadius(d, getRadius); })
            .iterations(Math.round(c.collideIterations)))
        .force('clusterRepel', _graphClusterRepelForce(nodes))
        .alpha(c.simAlpha)
        .alphaDecay(c.simAlphaDecay)
        .velocityDecay(c.simVelocityDecay);

    if (onTick) sim.on('tick', onTick);
    sim.on('end', function() {
        _pinGraphNodes(nodes);
        if (onEnd) onEnd();
    });
    return sim;
}

function _layoutTopicFilesAndChildren(topicId: any, ox: any, oy: any, childMap: any, nodeMap: any, parentMap: any, coordKey: any, depthBase: any) {
    const subTopics = (childMap[topicId] || []).filter(function(cid: any) {
        return nodeMap[cid] && nodeMap[cid].type === 'topic' && parentMap[cid] === topicId;
    });
    const fileIds = (childMap[topicId] || []).filter(function(cid: any) {
        return nodeMap[cid] && nodeMap[cid].type === 'file';
    });

    if (subTopics.length) {
        const r3 = _l3TopicDiskRadius(subTopics.length);
        const c = _graphCfg();
        const r3Inner = Math.min(r3 * c.l3InnerRatio, r3 - c.l3InnerMinGap);
        _scatterTopicsInAnnulus(ox, oy, subTopics, nodeMap, r3Inner, r3, coordKey, depthBase, function(subId: any, sx: any, sy: any) {
            const sub = nodeMap[subId];
            if (sub) sub._l2Cluster = topicId;
            _layoutTopicFilesAndChildren(subId, sx, sy, childMap, nodeMap, parentMap, coordKey, depthBase + 1);
        });
    }
    if (fileIds.length) {
        const noteDepth = depthBase != null ? depthBase + (subTopics.length ? 2 : 1) : null;
        _scatterInDisk(ox, oy, fileIds, nodeMap, _noteDiskRadius(fileIds.length), coordKey, topicId, noteDepth);
    }
}

function _layoutL1TopicCluster(l1Id: any, originX: any, originY: any, childMap: any, nodeMap: any, parentMap: any, coordKey: any, depthBase: any) {
    const xk = coordKey;
    const yk = coordKey === '_tx' ? '_ty' : 'ty';
    const l1 = nodeMap[l1Id];
    if (!l1) return;

    l1[xk] = originX;
    l1[yk] = originY;
    l1._l1Group = l1Id;
    if (depthBase != null) l1._depth = depthBase;

    const l2Ids = (childMap[l1Id] || []).filter(function(cid: any) {
        return parentMap[cid] === l1Id && nodeMap[cid] && nodeMap[cid].type === 'topic';
    });
    const directFiles = (childMap[l1Id] || []).filter(function(cid: any) {
        return nodeMap[cid] && nodeMap[cid].type === 'file';
    });

    let maxFiles = 0;
    l2Ids.forEach(function(l2id: any) {
        const fc = (childMap[l2id] || []).filter(function(c: any) {
            return nodeMap[c] && nodeMap[c].type === 'file';
        }).length;
        if (fc > maxFiles) maxFiles = fc;
    });

    const ringR = l2Ids.length ? _l2RingRadius(l2Ids.length, maxFiles) : 0;
    let l1NoteDiskR = 0;

    if (directFiles.length) {
        const wantR = _noteDiskRadius(directFiles.length);
        const cLayout = _graphCfg();
        l1NoteDiskR = l2Ids.length
            ? Math.min(wantR, ringR * cLayout.l1NoteMaxRingRatio)
            : wantR;
        const l1NoteDepth = depthBase != null ? depthBase + 1 : null;
        _scatterInDisk(originX, originY, directFiles, nodeMap, l1NoteDiskR, coordKey, l1Id, l1NoteDepth);
    }

    if (!l2Ids.length) return;

    const cL2 = _graphCfg();
    const l2Inner = l1NoteDiskR > 0 ? l1NoteDiskR + cL2.l2AnnulusGap : ringR * cL2.l2InnerFallbackRatio;
    _scatterTopicsInAnnulus(originX, originY, l2Ids, nodeMap, l2Inner, ringR * cL2.l2OuterRingRatio, coordKey, depthBase, function(l2id: any, lx: any, ly: any) {
        const l2 = nodeMap[l2id];
        if (!l2) return;
        l2._l1Group = l1Id;
        _layoutTopicFilesAndChildren(l2id, lx, ly, childMap, nodeMap, parentMap, coordKey, depthBase + 1);
    });
}

function _applyTopicHierarchyLayout(nodes: any, childMap: any, nodeMap: any, parentMap: any, cx: any, cy: any, svgW: any, svgH: any, coordKey: any) {
    const xk = coordKey || 'tx';
    const yk = coordKey === '_tx' ? '_ty' : 'ty';

    nodes.forEach(function(n: any) {
        n[xk] = undefined;
        n[yk] = undefined;
        n._l2Cluster = null;
        n._l1Group = null;
    });

    const l1Nodes = nodes.filter(function(n: any) { return n.type === 'topic' && n.level === 1; });
    const l1Count = l1Nodes.length;
    const packR = Math.min(svgW, svgH) * _graphCfg().l1PackRatio;

    l1Nodes.forEach(function(l1: any, i: any) {
        let ox = cx;
        let oy = cy;
        if (l1Count > 1) {
            const angle = _GRAPH_TAU * (i + 0.5) / l1Count - Math.PI / 2;
            ox = cx + Math.cos(angle) * packR;
            oy = cy + Math.sin(angle) * packR;
        }
        _layoutL1TopicCluster(l1.id, ox, oy, childMap, nodeMap, parentMap, coordKey, coordKey === '_tx' ? 0 : null);
    });

    const orphans = nodes.filter(function(n: any) { return n[xk] === undefined; });
    const orphanCount = orphans.length;
    const orphanR = Math.min(svgW, svgH) * _graphCfg().orphanRadiusRatio;
    orphans.forEach(function(n: any, i: any) {
        const angle = orphanCount > 1 ? _GRAPH_TAU * (i + 0.5) / orphanCount : 0;
        n[xk] = cx + Math.cos(angle) * orphanR;
        n[yk] = cy + Math.sin(angle) * orphanR;
        n._l1Group = '__orphan__';
    });

    nodes.forEach(function(n: any) {
        if (n._l1Group) return;
        let cur = n.id;
        const seen = new Set();
        while (cur && !seen.has(cur)) {
            seen.add(cur);
            const p = parentMap[cur];
            if (!p) break;
            const pNode = nodeMap[p];
            if (pNode && pNode.type === 'topic' && pNode.level === 1) {
                n._l1Group = p;
                break;
            }
            cur = p;
        }
        if (!n._l1Group) n._l1Group = '__orphan__';
    });
}

function _resolveL1ClusterId(d: any, nodeMap: any, parentMap: any) {
    if (d._l1Group && d._l1Group !== '__orphan__') return d._l1Group;
    if (d.type === 'topic' && d.level === 1) return d.id;
    let cur = d.id;
    const seen = new Set();
    while (cur && !seen.has(cur)) {
        seen.add(cur);
        const n = nodeMap[cur];
        if (n && n.type === 'topic' && n.level === 1) return n.id;
        cur = parentMap[cur];
    }
    return null;
}

function _dragGroupForNode(d: any, childMap: any, nodeMap: any, parentMap: any, nodes: any) {
    const l1Id = _resolveL1ClusterId(d, nodeMap, parentMap);
    if (l1Id) {
        const desc = _collectDescendantIds(l1Id, childMap);
        return nodes.filter(function(n: any) { return n.id === l1Id || desc.has(n.id); });
    }
    if (d.type === 'topic') {
        const desc = _collectDescendantIds(d.id, childMap);
        return nodes.filter(function(n: any) { return n.id === d.id || desc.has(n.id); });
    }
    return [d];
}

function _makeGraphDragHandlers(childMap: any, nodeMap: any, parentMap: any, nodes: any, edges: any, simulation: any, self: any) {
    return window.d3.drag()
        .on('start', function(e: any, d: any) {
            if (simulation && !e.active) simulation.alphaTarget(0.3).restart();
            const group = _dragGroupForNode(d, childMap, nodeMap, parentMap, nodes);
            d._dragGroup = group;
            d._dragAnchorX = d.x;
            d._dragAnchorY = d.y;
            group.forEach(function(n: any) {
                n._dragging = true;
                n._dragStartX = n.x;
                n._dragStartY = n.y;
                n._dragStartTx = n.tx;
                n._dragStartTy = n.ty;
            });
            nodes.forEach(function(n: any) {
                if (!n._dragging) {
                    n._dragStartTx = n.tx;
                    n._dragStartTy = n.ty;
                }
            });
            d.fx = d.x;
            d.fy = d.y;
        })
        .on('drag', function(e: any, d: any) {
            const dx = e.x - d._dragAnchorX;
            const dy = e.y - d._dragAnchorY;
            d.fx = d._dragStartX + dx;
            d.fy = d._dragStartY + dy;
            d.x = d.fx;
            d.y = d.fy;
            d.tx = d.x;
            d.ty = d.y;
            (d._dragGroup || [d]).forEach(function(n: any) {
                if (n === d) return;
                n.fx = n._dragStartX + dx;
                n.fy = n._dragStartY + dy;
                n.x = n.fx;
                n.y = n.fy;
                if (n._dragStartTx != null && n._dragStartTy != null) {
                    n.tx = n._dragStartTx + dx;
                    n.ty = n._dragStartTy + dy;
                }
            });
            var draggedIds = new Set((d._dragGroup || [d]).map(function(n: any) { return n.id; }));
            nodes.forEach(function(n: any) {
                if (n._dragging || draggedIds.has(n.id)) return;
                var parentId = parentMap[n.id];
                if (parentId && draggedIds.has(parentId)) {
                    n.tx = (n._dragStartTx != null ? n._dragStartTx : n.tx) + dx;
                    n.ty = (n._dragStartTy != null ? n._dragStartTy : n.ty) + dy;
                    n.fx = null;
                    n.fy = null;
                }
            });
            if (simulation) {
                simulation.alpha(Math.max(simulation.alpha(), 0.15)).restart();
            } else if (self.g) {
                self.g.selectAll('.graph-nodes g').attr('transform', function(nd: any) {
                    return 'translate(' + nd.x + ',' + nd.y + ')';
                });
            }
        })
        .on('end', function(e: any, d: any) {
            if (simulation && !e.active) simulation.alphaTarget(0);
            (d._dragGroup || [d]).forEach(function(n: any) {
                n._dragging = false;
                n.tx = n.x;
                n.ty = n.y;
                n.fx = n.x;
                n.fy = n.y;
            });
            nodes.forEach(function(n: any) {
                if (!d._dragGroup || !d._dragGroup.includes(n)) {
                    if (!n._dragging) {
                        n.tx = n.x;
                        n.ty = n.y;
                    }
                }
            });
            d._dragGroup = null;
        });
}

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
            if (d.type === 'topic' && d.has_abstract && d.abstract_file && typeof showPreview === 'function') {
                showPreview({ path: d.abstract_file, name: (d.name || d.id) + ' ' + window.t('graph.stats.survey') });
            }
        });

        // Click
        node.on('click', (e: any, d: any) => {
            e.stopPropagation();
            if (d.type === 'file' && d.full_path && typeof showPreview === 'function') {
                showPreview({ path: d.full_path, name: d.name });
            } else if (d.type === 'topic') {
                if (d.has_abstract && d.abstract_file && typeof showPreview === 'function') {
                    showPreview({ path: d.abstract_file, name: (d.name || d.id) + ' ' + window.t('graph.stats.survey') });
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
        if (d.type === 'file' && d.full_path && typeof showPreview === 'function') {
            showPreview({ path: d.full_path, name: d.name });
        } else if (d.type === 'topic' && d.has_abstract && d.abstract_file && typeof showPreview === 'function') {
            showPreview({ path: d.abstract_file, name: (d.name || d.id) + ' ' + window.t('graph.stats.survey') });
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
