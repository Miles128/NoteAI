// ================================================================
// 知识图谱 (D3 力导向布局 - Obsidian 风格)
// ================================================================

/** 图谱拖动：收集某主题节点下所有子节点 id */
function _collectDescendantIds(rootId, childMap) {
    const seen = new Set();
    const stack = (childMap[rootId] || []).slice();
    while (stack.length) {
        const id = stack.pop();
        if (seen.has(id)) continue;
        seen.add(id);
        (childMap[id] || []).forEach(function(cid) { stack.push(cid); });
    }
    return seen;
}

const _GRAPH_TAU = Math.PI * 2;
const _GRAPH_GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const GRAPH_LAYOUT_STORAGE_KEY = window.Storage.KEYS.GRAPH_LAYOUT;

/** @type {Record<string, number>} */
const GRAPH_LAYOUT_DEFAULTS = {
    l1PackRatio: 0.3,
    orphanRadiusRatio: 0.12,
    l1NoteMaxRingRatio: 0.28,
    l2AnnulusGap: 9,
    l2InnerFallbackRatio: 0.3,
    l2OuterRingRatio: 0.92,
    annulusMinSpan: 12,
    annulusSingleTopicRatio: 0.55,
    annulusAngleOffset: 0.9,
    l3InnerRatio: 0.4,
    l3InnerMinGap: 6,
    noteDiskMin: 6,
    noteDiskMax: 30,
    noteDiskBase: 3.5,
    noteDiskSqrtCoef: 2.2,
    noteSingleRadiusRatio: 0.16,
    l2RingMin: 32,
    l2RingMax: 88,
    l2RingBase: 16,
    l2RingSqrtL2: 7.5,
    l2RingSqrtNotes: 1.5,
    l3RingMin: 10,
    l3RingMax: 32,
    l3RingBase: 7,
    l3RingSqrtL3: 4.5,
    topicCollidePad: 13,
    fileCollidePad: 4,
    chargeL1: -18,
    chargeTopic: -14,
    chargeFile: -5,
    targetStrengthTopic: 0.88,
    targetStrengthFile: 0.8,
    clusterRepelDist: 150,
    clusterRepelForce: 520,
    collideIterations: 5,
    simAlpha: 0.55,
    simAlphaDecay: 0.12,
    simVelocityDecay: 0.72,
    radiusL1: 5,
    radiusOther: 4,
    fitPad: 60,
    fitMaxScale: 1.5,
    clampSideRatio: 0.12,
    boundsMargin: 52,
    replayRevealMinMs: 800,
    replayRevealMaxMs: 3000,
    replayRevealBudgetMs: 24000,
};

/** @type {{ key: string, groupKey: string, min: number, max: number, step: number }[]} */
const GRAPH_LAYOUT_SCHEMA = [
    { key: 'l1PackRatio', groupKey: 'l1Global', min: 0.08, max: 0.5, step: 0.01 },
    { key: 'orphanRadiusRatio', groupKey: 'l1Global', min: 0.04, max: 0.25, step: 0.01 },
    { key: 'l1NoteMaxRingRatio', groupKey: 'l2Layout', min: 0.1, max: 0.5, step: 0.01 },
    { key: 'l2AnnulusGap', groupKey: 'l2Layout', min: 0, max: 40, step: 1 },
    { key: 'l2InnerFallbackRatio', groupKey: 'l2Layout', min: 0.1, max: 0.6, step: 0.01 },
    { key: 'l2OuterRingRatio', groupKey: 'l2Layout', min: 0.7, max: 1, step: 0.01 },
    { key: 'annulusMinSpan', groupKey: 'l2Layout', min: 4, max: 40, step: 1 },
    { key: 'annulusSingleTopicRatio', groupKey: 'l2Layout', min: 0.3, max: 0.8, step: 0.01 },
    { key: 'annulusAngleOffset', groupKey: 'l2Layout', min: 0, max: 3.14, step: 0.05 },
    { key: 'l3InnerRatio', groupKey: 'l3Layout', min: 0.2, max: 0.7, step: 0.01 },
    { key: 'l3InnerMinGap', groupKey: 'l3Layout', min: 0, max: 20, step: 1 },
    { key: 'noteDiskMin', groupKey: 'noteScatter', min: 3, max: 30, step: 1 },
    { key: 'noteDiskMax', groupKey: 'noteScatter', min: 15, max: 80, step: 1 },
    { key: 'noteDiskBase', groupKey: 'noteScatter', min: 0, max: 20, step: 0.5 },
    { key: 'noteDiskSqrtCoef', groupKey: 'noteScatter', min: 0.5, max: 8, step: 0.1 },
    { key: 'noteSingleRadiusRatio', groupKey: 'noteScatter', min: 0.05, max: 0.4, step: 0.01 },
    { key: 'l2RingMin', groupKey: 'l2RingFormula', min: 16, max: 80, step: 1 },
    { key: 'l2RingMax', groupKey: 'l2RingFormula', min: 40, max: 160, step: 1 },
    { key: 'l2RingBase', groupKey: 'l2RingFormula', min: 0, max: 40, step: 1 },
    { key: 'l2RingSqrtL2', groupKey: 'l2RingFormula', min: 0, max: 20, step: 0.5 },
    { key: 'l2RingSqrtNotes', groupKey: 'l2RingFormula', min: 0, max: 5, step: 0.1 },
    { key: 'l3RingMin', groupKey: 'l3RingFormula', min: 6, max: 40, step: 1 },
    { key: 'l3RingMax', groupKey: 'l3RingFormula', min: 16, max: 80, step: 1 },
    { key: 'l3RingBase', groupKey: 'l3RingFormula', min: 0, max: 30, step: 1 },
    { key: 'l3RingSqrtL3', groupKey: 'l3RingFormula', min: 0, max: 12, step: 0.5 },
    { key: 'topicCollidePad', groupKey: 'simulation', min: 0, max: 30, step: 1 },
    { key: 'fileCollidePad', groupKey: 'simulation', min: 0, max: 20, step: 1 },
    { key: 'chargeL1', groupKey: 'simulation', min: -80, max: -1, step: 1 },
    { key: 'chargeTopic', groupKey: 'simulation', min: -60, max: -1, step: 1 },
    { key: 'chargeFile', groupKey: 'simulation', min: -40, max: 0, step: 1 },
    { key: 'targetStrengthTopic', groupKey: 'simulation', min: 0.3, max: 1, step: 0.01 },
    { key: 'targetStrengthFile', groupKey: 'simulation', min: 0.3, max: 1, step: 0.01 },
    { key: 'clusterRepelDist', groupKey: 'simulation', min: 40, max: 300, step: 5 },
    { key: 'clusterRepelForce', groupKey: 'simulation', min: 50, max: 1200, step: 10 },
    { key: 'collideIterations', groupKey: 'simulation', min: 1, max: 12, step: 1 },
    { key: 'simAlpha', groupKey: 'simulation', min: 0.1, max: 1, step: 0.05 },
    { key: 'simAlphaDecay', groupKey: 'simulation', min: 0.02, max: 0.3, step: 0.01 },
    { key: 'simVelocityDecay', groupKey: 'simulation', min: 0.3, max: 0.95, step: 0.01 },
    { key: 'radiusL1', groupKey: 'nodeDisplay', min: 3, max: 16, step: 1 },
    { key: 'radiusOther', groupKey: 'nodeDisplay', min: 2, max: 14, step: 1 },
    { key: 'fitPad', groupKey: 'view', min: 20, max: 120, step: 5 },
    { key: 'fitMaxScale', groupKey: 'view', min: 0.5, max: 3, step: 0.1 },
    { key: 'clampSideRatio', groupKey: 'view', min: 0.05, max: 0.25, step: 0.01 },
    { key: 'boundsMargin', groupKey: 'view', min: 20, max: 120, step: 4 },
    { key: 'replayRevealMinMs', groupKey: 'replay', min: 200, max: 3000, step: 50 },
    { key: 'replayRevealMaxMs', groupKey: 'replay', min: 500, max: 8000, step: 100 },
    { key: 'replayRevealBudgetMs', groupKey: 'replay', min: 5000, max: 60000, step: 500 },
];

function _graphLayoutSchemaByKey() {
    const map = {};
    GRAPH_LAYOUT_SCHEMA.forEach(function(p) { map[p.key] = p; });
    return map;
}

function _formatGraphLayoutValue(v, step) {
    const n = Number(v);
    if (!Number.isFinite(n)) return '';
    if (step >= 1) return String(Math.round(n));
    if (step >= 0.1) return n.toFixed(1);
    return n.toFixed(2);
}

function _snapGraphLayoutValue(v, param) {
    const n = Number(v);
    if (!Number.isFinite(n)) return param.min;
    const steps = Math.round((n - param.min) / param.step);
    const snapped = param.min + steps * param.step;
    return Math.min(param.max, Math.max(param.min, snapped));
}

function loadGraphLayoutConfig() {
    const cfg = Object.assign({}, GRAPH_LAYOUT_DEFAULTS);
    const saved = window.Storage.getItem(GRAPH_LAYOUT_STORAGE_KEY, null, { silent: true });
    if (saved) {
        const schema = _graphLayoutSchemaByKey();
        Object.keys(saved).forEach(function(key) {
            if (!schema[key]) return;
            const v = Number(saved[key]);
            if (!Number.isFinite(v)) return;
            const p = schema[key];
            cfg[key] = Math.min(p.max, Math.max(p.min, v));
        });
    }
    return cfg;
}

function saveGraphLayoutConfig(cfg) {
    window.Storage.setItem(GRAPH_LAYOUT_STORAGE_KEY, cfg);
}

function resetGraphLayoutConfigStorage() {
    window.Storage.removeItem(GRAPH_LAYOUT_STORAGE_KEY);
}

function _graphCfg() {
    return (Graph3Tier && Graph3Tier.layoutConfig) ? Graph3Tier.layoutConfig : GRAPH_LAYOUT_DEFAULTS;
}

function _noteDiskRadius(noteCount) {
    const c = _graphCfg();
    const n = Math.max(1, noteCount);
    return Math.min(c.noteDiskMax, Math.max(c.noteDiskMin, c.noteDiskBase + c.noteDiskSqrtCoef * Math.sqrt(n)));
}

function _l2RingRadius(l2Count, maxNotesPerL2) {
    const c = _graphCfg();
    const n2 = Math.max(1, l2Count);
    const nf = Math.max(1, maxNotesPerL2);
    return Math.min(c.l2RingMax, Math.max(c.l2RingMin,
        c.l2RingBase + c.l2RingSqrtL2 * Math.sqrt(n2) + c.l2RingSqrtNotes * Math.sqrt(nf)));
}

function _l3TopicDiskRadius(l3Count) {
    const c = _graphCfg();
    const n = Math.max(1, l3Count);
    return Math.min(c.l3RingMax, Math.max(c.l3RingMin, c.l3RingBase + c.l3RingSqrtL3 * Math.sqrt(n)));
}

/** 在圆盘内均匀散布（非圆周）；itemIds 为节点 id 列表 */
function _scatterInDisk(ox, oy, itemIds, nodeMap, maxRadius, coordKey, clusterId, depthVal) {
    const xk = coordKey;
    const yk = coordKey === '_tx' ? '_ty' : 'ty';
    const n = itemIds.length;
    if (!n) return;
    const c = _graphCfg();
    const R = Math.max(c.noteDiskMin, maxRadius);
    itemIds.forEach(function(id, i) {
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
function _scatterTopicsInAnnulus(ox, oy, topicIds, nodeMap, rInner, rOuter, coordKey, depthBase, onPlaced) {
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
    topicIds.forEach(function(tid, i) {
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

function _seedGraphPositions(nodes) {
    nodes.forEach(function(n) {
        if (n.tx == null || n.ty == null) return;
        n.x = n.tx;
        n.y = n.ty;
        n.fx = null;
        n.fy = null;
        n.vx = 0;
        n.vy = 0;
    });
}

function _pinGraphNodes(nodes) {
    nodes.forEach(function(n) {
        if (n.tx == null || n.ty == null) return;
        n.tx = n.x;
        n.ty = n.y;
        n.fx = n.x;
        n.fy = n.y;
    });
}

function _graphCollideRadius(d, getRadius) {
    const c = _graphCfg();
    if (d.type === 'file') return getRadius(d) + c.fileCollidePad;
    return getRadius(d) + c.topicCollidePad;
}

function _graphTargetStrength(d) {
    const c = _graphCfg();
    if (d._dragging) return 0;
    if (d.type === 'topic') return c.targetStrengthTopic;
    return c.targetStrengthFile;
}

function _graphChargeStrength(d) {
    const c = _graphCfg();
    if (d.type === 'topic' && d.level === 1) return c.chargeL1;
    if (d.type === 'topic') return c.chargeTopic;
    return c.chargeFile;
}

/** 不同一级主题簇之间：仅近距离互斥，避免整图被撑开 */
function _graphClusterRepelForce(nodes) {
    const c = _graphCfg();
    return function(alpha) {
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const a = nodes[i];
                const b = nodes[j];
                if (a._l1Group === b._l1Group) continue;
                let dx = a.x - b.x;
                let dy = a.y - b.y;
                const dist = Math.hypot(dx, dy) || 1;
                if (dist > c.clusterRepelDist) continue;
                const force = c.clusterRepelForce * alpha / (dist * dist);
                a.vx += (dx / dist) * force;
                a.vy += (dy / dist) * force;
                b.vx -= (dx / dist) * force;
                b.vy -= (dy / dist) * force;
            }
        }
    };
}

function _startGraphRelaxation(nodes, edges, getRadius, onTick, onEnd) {
    const c = _graphCfg();
    const sim = d3.forceSimulation(nodes)
        .force('x', d3.forceX(function(d) { return d.tx; }).strength(_graphTargetStrength))
        .force('y', d3.forceY(function(d) { return d.ty; }).strength(_graphTargetStrength))
        .force('charge', d3.forceManyBody().strength(_graphChargeStrength))
        .force('collide', d3.forceCollide(function(d) { return _graphCollideRadius(d, getRadius); })
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

function _layoutTopicFilesAndChildren(topicId, ox, oy, childMap, nodeMap, parentMap, coordKey, depthBase) {
    const subTopics = (childMap[topicId] || []).filter(function(cid) {
        return nodeMap[cid] && nodeMap[cid].type === 'topic' && parentMap[cid] === topicId;
    });
    const fileIds = (childMap[topicId] || []).filter(function(cid) {
        return nodeMap[cid] && nodeMap[cid].type === 'file';
    });

    if (subTopics.length) {
        const r3 = _l3TopicDiskRadius(subTopics.length);
        const c = _graphCfg();
        const r3Inner = Math.min(r3 * c.l3InnerRatio, r3 - c.l3InnerMinGap);
        _scatterTopicsInAnnulus(ox, oy, subTopics, nodeMap, r3Inner, r3, coordKey, depthBase, function(subId, sx, sy) {
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

function _layoutL1TopicCluster(l1Id, originX, originY, childMap, nodeMap, parentMap, coordKey, depthBase) {
    const xk = coordKey;
    const yk = coordKey === '_tx' ? '_ty' : 'ty';
    const l1 = nodeMap[l1Id];
    if (!l1) return;

    l1[xk] = originX;
    l1[yk] = originY;
    l1._l1Group = l1Id;
    if (depthBase != null) l1._depth = depthBase;

    const l2Ids = (childMap[l1Id] || []).filter(function(cid) {
        return parentMap[cid] === l1Id && nodeMap[cid] && nodeMap[cid].type === 'topic';
    });
    const directFiles = (childMap[l1Id] || []).filter(function(cid) {
        return nodeMap[cid] && nodeMap[cid].type === 'file';
    });

    let maxFiles = 0;
    l2Ids.forEach(function(l2id) {
        const fc = (childMap[l2id] || []).filter(function(c) {
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
    _scatterTopicsInAnnulus(originX, originY, l2Ids, nodeMap, l2Inner, ringR * cL2.l2OuterRingRatio, coordKey, depthBase, function(l2id, lx, ly) {
        const l2 = nodeMap[l2id];
        if (!l2) return;
        l2._l1Group = l1Id;
        _layoutTopicFilesAndChildren(l2id, lx, ly, childMap, nodeMap, parentMap, coordKey, depthBase + 1);
    });
}

function _applyTopicHierarchyLayout(nodes, childMap, nodeMap, parentMap, cx, cy, svgW, svgH, coordKey) {
    const xk = coordKey || 'tx';
    const yk = coordKey === '_tx' ? '_ty' : 'ty';

    nodes.forEach(function(n) {
        n[xk] = undefined;
        n[yk] = undefined;
        n._l2Cluster = null;
        n._l1Group = null;
    });

    const l1Nodes = nodes.filter(function(n) { return n.type === 'topic' && n.level === 1; });
    const l1Count = l1Nodes.length;
    const packR = Math.min(svgW, svgH) * _graphCfg().l1PackRatio;

    l1Nodes.forEach(function(l1, i) {
        let ox = cx;
        let oy = cy;
        if (l1Count > 1) {
            const angle = _GRAPH_TAU * (i + 0.5) / l1Count - Math.PI / 2;
            ox = cx + Math.cos(angle) * packR;
            oy = cy + Math.sin(angle) * packR;
        }
        _layoutL1TopicCluster(l1.id, ox, oy, childMap, nodeMap, parentMap, coordKey, coordKey === '_tx' ? 0 : null);
    });

    const orphans = nodes.filter(function(n) { return n[xk] === undefined; });
    const orphanCount = orphans.length;
    const orphanR = Math.min(svgW, svgH) * _graphCfg().orphanRadiusRatio;
    orphans.forEach(function(n, i) {
        const angle = orphanCount > 1 ? _GRAPH_TAU * (i + 0.5) / orphanCount : 0;
        n[xk] = cx + Math.cos(angle) * orphanR;
        n[yk] = cy + Math.sin(angle) * orphanR;
        n._l1Group = '__orphan__';
    });

    nodes.forEach(function(n) {
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

function _resolveL1ClusterId(d, nodeMap, parentMap) {
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

function _dragGroupForNode(d, childMap, nodeMap, parentMap, nodes) {
    const l1Id = _resolveL1ClusterId(d, nodeMap, parentMap);
    if (l1Id) {
        const desc = _collectDescendantIds(l1Id, childMap);
        return nodes.filter(function(n) { return n.id === l1Id || desc.has(n.id); });
    }
    if (d.type === 'topic') {
        const desc = _collectDescendantIds(d.id, childMap);
        return nodes.filter(function(n) { return n.id === d.id || desc.has(n.id); });
    }
    return [d];
}

function _makeGraphDragHandlers(childMap, nodeMap, parentMap, nodes, edges, simulation, self) {
    return d3.drag()
        .on('start', function(e, d) {
            if (simulation && !e.active) simulation.alphaTarget(0.3).restart();
            const group = _dragGroupForNode(d, childMap, nodeMap, parentMap, nodes);
            d._dragGroup = group;
            d._dragAnchorX = d.x;
            d._dragAnchorY = d.y;
            group.forEach(function(n) {
                n._dragging = true;
                n._dragStartX = n.x;
                n._dragStartY = n.y;
                n._dragStartTx = n.tx;
                n._dragStartTy = n.ty;
            });
            nodes.forEach(function(n) {
                if (!n._dragging) {
                    n._dragStartTx = n.tx;
                    n._dragStartTy = n.ty;
                }
            });
            d.fx = d.x;
            d.fy = d.y;
        })
        .on('drag', function(e, d) {
            const dx = e.x - d._dragAnchorX;
            const dy = e.y - d._dragAnchorY;
            d.fx = d._dragStartX + dx;
            d.fy = d._dragStartY + dy;
            d.x = d.fx;
            d.y = d.fy;
            d.tx = d.x;
            d.ty = d.y;
            (d._dragGroup || [d]).forEach(function(n) {
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
            var draggedIds = new Set((d._dragGroup || [d]).map(function(n) { return n.id; }));
            nodes.forEach(function(n) {
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
                self.g.selectAll('.graph-nodes g').attr('transform', function(nd) {
                    return 'translate(' + nd.x + ',' + nd.y + ')';
                });
            }
        })
        .on('end', function(e, d) {
            if (simulation && !e.active) simulation.alphaTarget(0);
            (d._dragGroup || [d]).forEach(function(n) {
                n._dragging = false;
                n.tx = n.x;
                n.ty = n.y;
                n.fx = n.x;
                n.fy = n.y;
            });
            nodes.forEach(function(n) {
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
    data: null,
    svg: null,
    g: null,
    zoom: null,
    showFilenames: false,
    simulation: null,
    filter: 'topic',
    layoutConfig: loadGraphLayoutConfig(),
    _graphBodyResizeObserver: null,
    _resizePaused: false,
    _resizePending: false,

    initLayoutConfig() {
        this.layoutConfig = loadGraphLayoutConfig();
    },

    reloadLayoutConfig() {
        this.initLayoutConfig();
    },

    _buildLayoutSettingsForm() {
        const form = document.getElementById('graph-settings-form');
        if (!form) return;
        form.innerHTML = '';
        let lastGroup = '';
        const cfg = this.layoutConfig;
        const self = this;
        GRAPH_LAYOUT_SCHEMA.forEach(function(param) {
            if (param.groupKey !== lastGroup) {
                lastGroup = param.groupKey;
                const title = document.createElement('div');
                title.className = 'graph-settings-group-title';
                title.textContent = window.t('graph.paramGroup.' + param.groupKey);
                form.appendChild(title);
            }
            const value = _snapGraphLayoutValue(cfg[param.key], param);
            const row = document.createElement('div');
            row.className = 'graph-settings-row';
            const head = document.createElement('div');
            head.className = 'graph-settings-row-head';
            const label = document.createElement('span');
            label.className = 'graph-settings-label';
            label.textContent = window.t('graph.param.' + param.key);
            const valueEl = document.createElement('span');
            valueEl.className = 'graph-settings-value';
            valueEl.textContent = _formatGraphLayoutValue(value, param.step);
            const input = document.createElement('input');
            input.type = 'range';
            input.className = 'graph-settings-range';
            input.dataset.key = param.key;
            input.min = String(param.min);
            input.max = String(param.max);
            input.step = String(param.step);
            input.value = String(value);
            input.addEventListener('input', function() {
                valueEl.textContent = _formatGraphLayoutValue(input.value, param.step);
                self._scheduleLayoutApply();
            });
            input.addEventListener('change', function() {
                valueEl.textContent = _formatGraphLayoutValue(input.value, param.step);
                if (self._layoutApplyTimer) {
                    clearTimeout(self._layoutApplyTimer);
                    self._layoutApplyTimer = null;
                }
                self.applyLayoutSettings(self.readLayoutSettingsFromForm());
            });
            head.appendChild(label);
            head.appendChild(valueEl);
            row.appendChild(head);
            row.appendChild(input);
            form.appendChild(row);
        });
    },

    openLayoutSettings() {
        const panel = document.getElementById('graph-panel');
        const sidebar = document.getElementById('graph-settings-sidebar');
        const btn = document.getElementById('graph-layout-settings-btn');
        if (!panel || !sidebar) return;
        if (!sidebar.hidden && panel.classList.contains('graph-settings-open')) {
            this.closeLayoutSettings();
            return;
        }
        this._buildLayoutSettingsForm();
        sidebar.hidden = false;
        panel.classList.add('graph-settings-open');
        if (btn) btn.classList.add('active');
        const self = this;
        requestAnimationFrame(function() { self.resize(); });
    },

    closeLayoutSettings() {
        const panel = document.getElementById('graph-panel');
        const sidebar = document.getElementById('graph-settings-sidebar');
        const btn = document.getElementById('graph-layout-settings-btn');
        if (this._layoutApplyTimer) {
            clearTimeout(this._layoutApplyTimer);
            this._layoutApplyTimer = null;
        }
        if (sidebar) sidebar.hidden = true;
        if (panel) panel.classList.remove('graph-settings-open');
        if (btn) btn.classList.remove('active');
        const self = this;
        requestAnimationFrame(function() {
            requestAnimationFrame(function() {
                if (self.data && self.data.nodes && self.data.nodes.length) {
                    self.reloadGraphLayout();
                } else {
                    self.resize();
                }
            });
        });
    },

    readLayoutSettingsFromForm() {
        const cfg = Object.assign({}, this.layoutConfig);
        const schema = _graphLayoutSchemaByKey();
        document.querySelectorAll('#graph-settings-form .graph-settings-range').forEach(function(input) {
            const key = input.dataset.key;
            if (!key || !schema[key]) return;
            const p = schema[key];
            cfg[key] = _snapGraphLayoutValue(input.value, p);
        });
        return cfg;
    },

    _scheduleLayoutApply() {
        if (this._layoutApplyTimer) clearTimeout(this._layoutApplyTimer);
        const self = this;
        this._layoutApplyTimer = setTimeout(function() {
            self._layoutApplyTimer = null;
            self.applyLayoutSettings(self.readLayoutSettingsFromForm());
        }, 100);
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

    applyLayoutSettings(cfg, options) {
        const opts = options || {};
        this.layoutConfig = Object.assign({}, GRAPH_LAYOUT_DEFAULTS, cfg);
        saveGraphLayoutConfig(this.layoutConfig);
        if (opts.reload === false) return;
        this.reloadGraphLayout();
    },

    resetLayoutSettings() {
        resetGraphLayoutConfigStorage();
        this.layoutConfig = loadGraphLayoutConfig();
        this._buildLayoutSettingsForm();
        this.applyLayoutSettings(this.layoutConfig);
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

    _disconnectGraphPanelBodyResize() {
        if (this._graphBodyResizeObserver) {
            this._graphBodyResizeObserver.disconnect();
            this._graphBodyResizeObserver = null;
        }
    },

    _observeGraphPanelBodyResize(container) {
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

    _clampNodesToView(nodes, w, h, getRadius) {
        if (!w || !h || !nodes || !nodes.length) return;
        const sidePad = Math.min(108, Math.max(36, w * this.layoutConfig.clampSideRatio));
        nodes.forEach(d => {
            const r = getRadius(d) + 6;
            const topPad = r + 20;
            const botPad = r + 14;
            d.x = Math.max(sidePad, Math.min(w - sidePad, d.x));
            d.y = Math.max(topPad, Math.min(h - botPad, d.y));
        });
    },

    /** Bounds for zoom-to-fit: account for circles + labels (above nodes). */
    _boundsFromNodes(nodes, w, h, getRadius) {
        let x1 = Infinity;
        let y1 = Infinity;
        let x2 = -Infinity;
        let y2 = -Infinity;
        const mx = this.layoutConfig.boundsMargin;
        nodes.forEach(d => {
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

    _fitGraphToBounds(nodes, svgW, svgH, getRadius, duration) {
        if (!this.svg || !this.zoom || !nodes.length) return;
        const bounds = this._boundsFromNodes(nodes, svgW, svgH, getRadius);
        const bw = bounds.x2 - bounds.x1 || 100;
        const bh = bounds.y2 - bounds.y1 || 100;
        const pad = this.layoutConfig.fitPad;
        const scale = Math.min((svgW - pad * 2) / bw, (svgH - pad * 2) / bh, this.layoutConfig.fitMaxScale);
        const midX = (bounds.x1 + bounds.x2) / 2;
        const midY = (bounds.y1 + bounds.y2) / 2;
        const dur = duration == null ? 800 : duration;
        const tr = d3.zoomIdentity.translate(svgW / 2, svgH / 2).scale(Math.max(0.15, scale)).translate(-midX, -midY);
        if (dur > 0) {
            this.svg.transition().duration(dur).call(this.zoom.transform, tr);
        } else {
            this.svg.call(this.zoom.transform, tr);
        }
    },

    _loadDebounceTimer: null,
    _lastLoadFilter: null,
    _lastLoadTime: 0,
    _lastDataHash: null,

    async load(filter, force) {
        if (filter) this.filter = filter;
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
            this.data = await api.getGraphData(this.filter);
            if (!this.data || !Array.isArray(this.data.nodes) || !Array.isArray(this.data.edges)) {
                console.error('图谱数据格式异常:', this.data);
                this.data = { nodes: [], edges: [] };
            }
            var hash = this.data.nodes.length + ':' + this.data.edges.length;
            if (hash === this._lastDataHash && this.svg) return;
            this._lastDataHash = hash;
            this._updateFilterBtns();
            this._updateLegend();
            this._updateStats();
            this.initD3();
            this.render();
        } catch (e) {
            console.error('图谱加载失败:', e);
            if (e && e.stack) console.error(e.stack);
        }
    },

    _updateFilterBtns() {
        document.querySelectorAll('#graph-filter-bar .graph-filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.filter === this.filter);
        });
    },

    _legendItem(color, size, labelKey) {
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
        const topicNodes = (this.data.nodes || []).filter(n => n.type === 'topic').length;
        const tagNodes = (this.data.nodes || []).filter(n => n.type === 'tag').length;
        const fileNodes = (this.data.nodes || []).filter(n => n.type === 'file').length;
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

        this.svg = d3.select(container)
            .append('svg')
            .attr('id', 'graph-svg-3tier')
            .attr('width', w)
            .attr('height', h)
            .style('position', 'absolute').style('top', 0).style('left', 0)
            .style('z-index', 0)
            .style('background', 'var(--bg, #fafafa)');

        this.g = this.svg.append('g');

        this.zoom = d3.zoom()
            .scaleExtent([0.06, 5])
            .on('zoom', (e) => { this.g.attr('transform', e.transform); });
        this.svg.call(this.zoom);

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

        const svgW = +this.svg.attr('width');
        const svgH = +this.svg.attr('height');
        const cx = svgW / 2;
        const cy = svgH / 2;
        const self = this;

        const nodes = this.data.nodes.map(n => Object.assign({}, n));
        const edges = this.data.edges.map(e => ({
            source: e.source,
            target: e.target,
        }));

        const lc = this.layoutConfig;
        const getRadius = d => {
            if (d.type === 'topic' && d.level === 1) return lc.radiusL1;
            return lc.radiusOther;
        };

        const getColor = d => {
            if (d.type === 'topic') {
                if (d.level === 1) return '#e85d3a';
                if (d.level === 2) return '#ea8600';
                return '#f4a930';
            }
            if (d.type === 'tag') return '#7c4dff';
            return '#81c784';
        };

        // ===== Constellation layout: L1 spread out, children cluster around L1 =====
        const childMap = {};
        const parentMap = {};
        edges.forEach(e => {
            const src = typeof e.source === 'string' ? e.source : e.source.id || e.source;
            const tgt = typeof e.target === 'string' ? e.target : e.target.id || e.target;
            if (!childMap[src]) childMap[src] = [];
            childMap[src].push(tgt);
            parentMap[tgt] = src;
        });

        const nodeMap = {};
        nodes.forEach(n => { nodeMap[n.id] = n; });

        _applyTopicHierarchyLayout(nodes, childMap, nodeMap, parentMap, cx, cy, svgW, svgH, 'tx');
        nodes.forEach(function(n) {
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

        // Single circle per node - solid yellow stroke for abstract, no dashed
        node.append('circle')
            .attr('r', d => getRadius(d))
            .attr('fill', d => getColor(d))
            .attr('stroke', d => {
                if (d.has_abstract) return '#e6c200';
                if (d.type === 'tag') return 'rgba(124,77,255,0.4)';
                return d.type === 'topic' ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.25)';
            })
            .attr('stroke-width', d => d.has_abstract ? 3 : 0.8);

        // Labels - show full names
        const label = node.append('text')
            .text(d => d.name || '')
            .attr('text-anchor', 'middle')
            .attr('dy', d => -(getRadius(d) + 4))
            .style('font-size', d => {
                if (d.type === 'topic' && d.level === 1) return '10px';
                if (d.type === 'topic' && d.level === 2) return '9px';
                if (d.type === 'tag') return '9px';
                return '8px';
            })
            .style('font-weight', d => d.type === 'topic' && d.level <= 2 ? 'bold' : 'normal')
            .style('fill', d => {
                if (d.type === 'topic') return 'var(--text-muted, #555)';
                if (d.type === 'tag') return 'var(--color-tag, #6a3de8)';
                return 'var(--text-muted, #777)';
            })
            .style('pointer-events', 'none')
            .style('display', d => {
                if (d.type === 'topic') return '';
                if (d.type === 'tag') return '';
                return self.showFilenames ? '' : 'none';
            });

        const updateNodePos = function() {
            node.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; });
        };

        // Hover effects
        node.on('mouseenter', function(e, d) {
            d3.select(this).select('circle')
                .transition().duration(150)
                .attr('r', getRadius(d) * 1.3);
        }).on('mouseleave', function(e, d) {
            d3.select(this).select('circle')
                .transition().duration(150)
                .attr('r', getRadius(d));
        });

        // Double-click: open abstract for topics that have one
        node.on('dblclick', (e, d) => {
            e.stopPropagation();
            if (d.type === 'topic' && d.has_abstract && d.abstract_file && typeof showPreview === 'function') {
                showPreview({ path: d.abstract_file, name: (d.name || d.id) + ' ' + window.t('graph.stats.survey') });
            }
        });

        // Click
        node.on('click', (e, d) => {
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
                    const currentTransform = d3.zoomTransform(node);
                    const scale = Math.min(2, currentTransform.k * 1.5);
                    self.svg.transition().duration(500).call(
                        self.zoom.transform,
                        d3.zoomIdentity.translate(svgW / 2, svgH / 2).scale(scale).translate(-d.x, -d.y)
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

        if (!this.simulation) return;

        // Re-center and re-fit without rebuilding
        var self = this;
        var nodes = this.simulation.nodes();
        if (!nodes || !nodes.length) return;

        function getRZ(d) {
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
            d3.zoomIdentity.translate(newW / 2, newH / 2).scale(Math.max(0.15, scale)).translate(-midX, -midY)
        );
    },

    zoomIn() {
        if (this.svg && this.zoom) this.svg.transition().duration(300).call(this.zoom.scaleBy, 1.3);
    },
    zoomOut() {
        if (this.svg && this.zoom) this.svg.transition().duration(300).call(this.zoom.scaleBy, 0.7);
    },

    replay() {
        if (!this.svg || !this.data) return;
        if (this.simulation) this.simulation.stop();
        this.simulation = null;

        var self = this;
        var nodes = this.data.nodes.map(function(n) { return Object.assign({}, n); });
        var edges = this.data.edges.map(function(e) {
            return { source: typeof e.source === 'string' ? e.source : e.source.id || e.source,
                     target: typeof e.target === 'string' ? e.target : e.target.id || e.target };
        });

        var svgW = +this.svg.attr('width');
        var svgH = +this.svg.attr('height');
        var cx = svgW / 2;
        var cy = svgH / 2;

        var nodeMap = {};
        nodes.forEach(function(n) { nodeMap[n.id] = n; });

        // ---- compute target positions (constellation layout) ----
        var childMap = {};
        var parentMap = {};
        edges.forEach(function(e) {
            if (!childMap[e.source]) childMap[e.source] = [];
            childMap[e.source].push(e.target);
            parentMap[e.target] = e.source;
        });

        _applyTopicHierarchyLayout(nodes, childMap, nodeMap, parentMap, cx, cy, svgW, svgH, '_tx');
        nodes.forEach(function(n) {
            if (n._tx == null || n._ty == null) {
                n._tx = cx;
                n._ty = cy;
            }
        });
        _seedGraphPositions(nodes);

        var maxD = 0;
        nodes.forEach(function(n) { if ((n._depth || 0) > maxD) maxD = n._depth || 0; });
        nodes.forEach(function(n) {
            if (n._depth == null) n._depth = maxD + 1;
        });
        nodes.forEach(function(n) { if (n._depth > maxD) maxD = n._depth; });

        // ---- build SVG elements ----
        this.g.selectAll('*').remove();

        var lc = self.layoutConfig;
        var getRadius = function(d) {
            if (d.type === 'topic' && d.level === 1) return lc.radiusL1;
            return lc.radiusOther;
        };
        var getColor = function(d) {
            if (d.type === 'topic') return d.level === 1 ? '#e85d3a' : d.level === 2 ? '#ea8600' : '#f4a930';
            if (d.type === 'tag') return '#7c4dff';
            return '#81c784';
        };

        // Create all elements hidden initially
        var nodeGroup = self.g.append('g').attr('class', 'graph-nodes');

        var nodeSel = nodeGroup.selectAll('g').data(nodes).join('g')
            .attr('cursor', 'pointer')
            .attr('opacity', 0)
            .attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; });

        nodeSel.append('circle')
            .attr('r', function(d) { return getRadius(d); })
            .attr('fill', function(d) { return getColor(d); })
            .attr('stroke', function(d) { return d.has_abstract ? '#e6c200' : 'rgba(255,255,255,0.3)'; })
            .attr('stroke-width', function(d) { return d.has_abstract ? 3 : 0.8; });

        nodeSel.append('text')
            .text(function(d) { return d.name || ''; })
            .attr('text-anchor', 'middle')
            .attr('dy', function(d) { return -(getRadius(d) + 4); })
            .style('font-size', function(d) {
                if (d.type === 'topic' && d.level === 1) return '10px';
                if (d.type === 'topic' && d.level === 2) return '9px';
                if (d.type === 'tag') return '9px';
                return '8px';
            })
            .style('font-weight', function(d) { return d.type === 'topic' && d.level <= 2 ? 'bold' : 'normal'; })
            .style('fill', function(d) {
                if (d.type === 'topic') return 'var(--text-muted, #555)';
                if (d.type === 'tag') return 'var(--color-tag, #6a3de8)';
                return 'var(--text-muted, #777)';
            })
            .style('pointer-events', 'none')
            .style('display', function(d) {
                if (d.type === 'topic') return '';
                if (d.type === 'tag') return '';
                return self.showFilenames ? '' : 'none';
            });

        var rc = self.layoutConfig;
        var depthRevealInterval = Math.max(rc.replayRevealMinMs,
            Math.min(rc.replayRevealMaxMs, rc.replayRevealBudgetMs / (maxD + 1)));
        var l1s = nodes.filter(function(n) { return n.type === 'topic' && n.level === 1; });
        var l1Ids = new Set(l1s.map(function(n) { return n.id; }));
        var revealed = new Set(l1Ids);
        var currentDepth = 1;
        var revealTimer = null;

        function syncReveal() {
            nodeSel.attr('opacity', function(d) { return revealed.has(d.id) ? 1 : 0; });
        }

        syncReveal();

        function updateReplayPos() {
            nodeSel.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; });
        }

        self.simulation = _startGraphRelaxation(nodes, edges, getRadius, updateReplayPos, function() {
            nodeSel.call(_makeGraphDragHandlers(childMap, nodeMap, parentMap, nodes, edges, self.simulation, self));
        });

        function revealNextDepth() {
            if (currentDepth > maxD) {
                self._fitGraphToBounds(nodes, svgW, svgH, getRadius, 600);
                return;
            }
            nodes.filter(function(n) { return (n._depth || 0) === currentDepth; })
                .forEach(function(n) { revealed.add(n.id); });
            syncReveal();
            currentDepth++;
            if (currentDepth <= maxD) {
                revealTimer = setTimeout(revealNextDepth, depthRevealInterval);
            } else {
                self._fitGraphToBounds(nodes, svgW, svgH, getRadius, 600);
            }
        }

        if (maxD === 0) {
            nodes.forEach(function(n) { revealed.add(n.id); });
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
function graphReplay() { Graph3Tier.replay(); }
function loadRelationGraphData() { Graph3Tier.load(); }
function graphToggleFilenames() {
    Graph3Tier.showFilenames = !Graph3Tier.showFilenames;
    var btn = document.getElementById('graph-toggle-filenames');
    if (btn) btn.classList.toggle('active', Graph3Tier.showFilenames);
    if (Graph3Tier.g) {
        Graph3Tier.g.selectAll('.graph-nodes text').style('display', function(d) {
            if (d.type === 'topic') return '';
            if (d.type === 'tag') return '';
            return Graph3Tier.showFilenames ? '' : 'none';
        });
    }
}
window.graphZoomIn = graphZoomIn;
window.graphZoomOut = graphZoomOut;
window.graphReplay = graphReplay;
window.loadRelationGraphData = loadRelationGraphData;
window.graphToggleFilenames = graphToggleFilenames;

function graphOpenLayoutSettings() { Graph3Tier.openLayoutSettings(); }
function graphCloseLayoutSettings() { Graph3Tier.closeLayoutSettings(); }
function graphApplyLayoutSettings() {
    Graph3Tier.applyLayoutSettings(Graph3Tier.readLayoutSettingsFromForm());
}
function graphResetLayoutSettings() { Graph3Tier.resetLayoutSettings(); }
window.graphOpenLayoutSettings = graphOpenLayoutSettings;
window.graphCloseLayoutSettings = graphCloseLayoutSettings;
window.graphApplyLayoutSettings = graphApplyLayoutSettings;
window.graphResetLayoutSettings = graphResetLayoutSettings;
window.GraphLayoutParams = {
    defaults: GRAPH_LAYOUT_DEFAULTS,
    schema: GRAPH_LAYOUT_SCHEMA,
    load: loadGraphLayoutConfig,
};

document.addEventListener('DOMContentLoaded', () => {
    var fnBtn = document.getElementById('graph-toggle-filenames');
    if (fnBtn) fnBtn.classList.toggle('active', Graph3Tier.showFilenames);
    document.querySelectorAll('#graph-filter-bar .graph-filter-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const f = this.dataset.filter;
            Graph3Tier.load(f);
        });
    });
});

window.addEventListener('resize', () => Graph3Tier.resize());
