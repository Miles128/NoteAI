// 知识图谱布局 / 渲染辅助（由 G3.ts 导入）
// ================================================================
// 知识图谱 (D3 力导向布局 - Obsidian 风格)
// ================================================================

/** 图谱拖动：收集某主题节点下所有子节点 id */
export function _collectDescendantIds(rootId: any, childMap: any) {
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

export const _GRAPH_TAU = Math.PI * 2;
export const _GRAPH_GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
// 布局参数默认值 / Schema / Storage 读写与面板 UI 已拆至 graph-layout-params.js
// （window.GraphLayoutParams，见 main.mjs 加载顺序：本文件之前加载）。
export const GRAPH_LAYOUT_DEFAULTS: any = window.GraphLayoutParams!.defaults;
export const loadGraphLayoutConfig: any = window.GraphLayoutParams!.load;
export const saveGraphLayoutConfig: any = window.GraphLayoutParams!.save;
export const resetGraphLayoutConfigStorage: any = window.GraphLayoutParams!.resetStorage;
export const loadGraphLayoutMode: any = window.GraphLayoutParams!.loadMode;
export const saveGraphLayoutMode: any = window.GraphLayoutParams!.saveMode;
/** 节点圆半径显示缩放（相对布局配置值） */
export const _GRAPH_RADIUS_DISPLAY_SCALE = 0.75;

/** 图谱节点实际渲染半径（配置值 × 显示缩放） */
export function _graphNodeRadius(d: any, lc: any) {
    const base = (d.type === 'topic' && d.level === 1) ? lc.radiusL1 : lc.radiusOther;
    return base * _GRAPH_RADIUS_DISPLAY_SCALE;
}

export function _graphNodeColor(d: any) {
    if (d.type === 'topic') {
        if (d.level === 1) return '#e85d3a';
        if (d.level === 2) return '#ea8600';
        return '#f4a930';
    }
    if (d.type === 'tag') return '#7c4dff';
    return '#81c784';
}

export function _graphNodeStroke(d: any) {
    if (d.has_abstract) return '#e6c200';
    if (d.type === 'tag') return 'rgba(124,77,255,0.4)';
    return d.type === 'topic' ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.25)';
}

export function _graphNodeStrokeWidth(d: any) {
    return d.has_abstract ? 3 : 0.8;
}

export function _graphNodeFontSize(d: any) {
    if (d.type === 'topic' && d.level === 1) return '10px';
    if (d.type === 'topic' && d.level === 2) return '9px';
    if (d.type === 'tag') return '9px';
    return '8px';
}

export function _graphNodeTextFill(d: any) {
    if (d.type === 'topic') return 'var(--text-muted, #555)';
    if (d.type === 'tag') return 'var(--color-tag, #6a3de8)';
    return 'var(--text-muted, #777)';
}

export function _graphNodeTextDisplay(d: any, showFilenames: any) {
    if (d.type === 'topic') return '';
    if (d.type === 'tag') return '';
    return showFilenames ? '' : 'none';
}

export function _graphNodeClass(d: any) {
    var parts = ['graph-node', 'graph-node-' + (d.type || 'unknown')];
    if (d.type === 'topic') parts.push('graph-node-level-' + (d.level || 0));
    if (d.has_abstract) parts.push('has-survey');
    return parts.join(' ');
}

export function _graphNodeSubtitle(d: any) {
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

export function _treeDepthLabel(depth: any, rows: any) {
    const types = new Set((rows || []).map(function(d: any) { return d.data && d.data.type; }));
    if (types.size === 1 && types.has('tag')) return (window.t && window.t('graph.tree.depthTags')) || 'Tags';
    if (types.size === 1 && types.has('file')) return (window.t && window.t('graph.tree.depthNotes')) || 'Notes';
    if (depth === 1) return (window.t && window.t('graph.tree.depthL1')) || 'L1';
    if (depth === 2) return (window.t && window.t('graph.tree.depthL2')) || 'L2';
    if (depth === 3) return (window.t && window.t('graph.tree.depthL3')) || 'L3';
    return (window.t && window.t('graph.tree.depthNotes')) || 'Notes';
}

export function _mindMapTextWidth(text: any) {
    return Array.from(String(text || '')).reduce(function(width, char) {
        return width + (/[^\u0000-\u00ff]/.test(char) ? 13 : 7.2);
    }, 0);
}

export function _mindMapNodeWidth(d: any) {
    const padding = d.type === 'file' ? 18 : 28;
    const minWidth = d.type === 'file' ? 58 : 82;
    const maxWidth = d.type === 'file' ? 172 : 196;
    return Math.max(minWidth, Math.min(maxWidth, _mindMapTextWidth(d.name) + padding));
}

export function _mindMapNodeHeight(d: any) {
    if (d.type === 'file') return 25;
    if (d.type === 'topic' && Number(d.level || 0) === 1) return 42;
    return 36;
}

export function _mindMapLabel(text: any, maxLength: any) {
    const chars = Array.from(String(text || ''));
    return chars.length > maxLength ? chars.slice(0, maxLength - 1).join('') + '…' : chars.join('');
}

export function _createGraphNode(nodeSelection: any, getRadius: any, showFilenames: any) {
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

export function _graphCfg() {
    return ((window.Graph3Tier as any)?.layoutConfig) || GRAPH_LAYOUT_DEFAULTS;
}

export function _noteDiskRadius(noteCount: any) {
    const c = _graphCfg();
    const n = Math.max(1, noteCount);
    return Math.min(c.noteDiskMax, Math.max(c.noteDiskMin, c.noteDiskBase + c.noteDiskSqrtCoef * Math.sqrt(n)));
}

export function _l2RingRadius(l2Count: any, maxNotesPerL2: any) {
    const c = _graphCfg();
    const n2 = Math.max(1, l2Count);
    const nf = Math.max(1, maxNotesPerL2);
    return Math.min(c.l2RingMax, Math.max(c.l2RingMin,
        c.l2RingBase + c.l2RingSqrtL2 * Math.sqrt(n2) + c.l2RingSqrtNotes * Math.sqrt(nf)));
}

export function _l3TopicDiskRadius(l3Count: any) {
    const c = _graphCfg();
    const n = Math.max(1, l3Count);
    return Math.min(c.l3RingMax, Math.max(c.l3RingMin, c.l3RingBase + c.l3RingSqrtL3 * Math.sqrt(n)));
}

/** 在圆盘内均匀散布（非圆周）；itemIds 为节点 id 列表 */
export function _scatterInDisk(ox: any, oy: any, itemIds: any, nodeMap: any, maxRadius: any, coordKey: any, clusterId: any, depthVal: any) {
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
export function _scatterTopicsInAnnulus(ox: any, oy: any, topicIds: any, nodeMap: any, rInner: any, rOuter: any, coordKey: any, depthBase: any, onPlaced: any) {
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

export function _seedGraphPositions(nodes: any) {
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

export function _pinGraphNodes(nodes: any) {
    nodes.forEach(function(n: any) {
        if (n.tx == null || n.ty == null) return;
        n.tx = n.x;
        n.ty = n.y;
        n.fx = n.x;
        n.fy = n.y;
    });
}

export function _graphCollideRadius(d: any, getRadius: any) {
    const c = _graphCfg();
    if (d.type === 'file') return getRadius(d) + c.fileCollidePad;
    return getRadius(d) + c.topicCollidePad;
}

export function _graphTargetStrength(d: any) {
    const c = _graphCfg();
    if (d._dragging) return 0;
    if (d.type === 'topic') return c.targetStrengthTopic;
    return c.targetStrengthFile;
}

export function _graphChargeStrength(d: any) {
    const c = _graphCfg();
    if (d.type === 'topic' && d.level === 1) return c.chargeL1;
    if (d.type === 'topic') return c.chargeTopic;
    return c.chargeFile;
}

/** 图谱数据内容指纹：节点/边数量相同但内容变化（重命名、标签、层级等）
 *  时也能识别，避免 _doLoad 错误跳过刷新。O(n log n)，仅几百节点。 */
export function _graphDataFingerprint(data: any) {
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
export function _graphClusterRepelForce(nodes: any) {
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

export function _startGraphRelaxation(nodes: any, edges: any, getRadius: any, onTick: any, onEnd: any) {
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

export function _layoutTopicFilesAndChildren(topicId: any, ox: any, oy: any, childMap: any, nodeMap: any, parentMap: any, coordKey: any, depthBase: any) {
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

export function _layoutL1TopicCluster(l1Id: any, originX: any, originY: any, childMap: any, nodeMap: any, parentMap: any, coordKey: any, depthBase: any) {
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

export function _applyTopicHierarchyLayout(nodes: any, childMap: any, nodeMap: any, parentMap: any, cx: any, cy: any, svgW: any, svgH: any, coordKey: any) {
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

export function _resolveL1ClusterId(d: any, nodeMap: any, parentMap: any) {
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

export function _dragGroupForNode(d: any, childMap: any, nodeMap: any, parentMap: any, nodes: any) {
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

export function _makeGraphDragHandlers(childMap: any, nodeMap: any, parentMap: any, nodes: any, edges: any, simulation: any, self: any) {
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

