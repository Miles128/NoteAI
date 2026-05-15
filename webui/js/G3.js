// ================================================================
// 知识图谱 (D3 力导向布局 - Obsidian 风格)
// ================================================================

const Graph3Tier = {
    data: null,
    svg: null,
    g: null,
    zoom: null,
    simulation: null,
    filter: 'topic',

    async load(filter) {
        if (filter) this.filter = filter;
        try {
            this.data = await api.getGraphData(this.filter);
            if (!this.data || !Array.isArray(this.data.nodes) || !Array.isArray(this.data.edges)) {
                console.error('图谱数据格式异常:', this.data);
                this.data = { nodes: [], edges: [] };
            }
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

    _updateLegend() {
        const el = document.getElementById('graph-legend');
        if (!el) return;
        if (this.filter === 'tag') {
            el.innerHTML = '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#7c4dff;width:8px;height:8px;border-radius:50%;display:inline-block;"></span>标签</span>'
                + '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#81c784;width:6px;height:6px;border-radius:50%;display:inline-block;"></span>笔记</span>';
        } else if (this.filter === 'all') {
            el.innerHTML = '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#e85d3a;width:8px;height:8px;border-radius:50%;display:inline-block;"></span>主题</span>'
                + '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#7c4dff;width:8px;height:8px;border-radius:50%;display:inline-block;"></span>标签</span>'
                + '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#81c784;width:6px;height:6px;border-radius:50%;display:inline-block;"></span>笔记</span>';
        } else {
            el.innerHTML = '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#e85d3a;width:8px;height:8px;border-radius:50%;display:inline-block;"></span>一级</span>'
                + '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#ea8600;width:6px;height:6px;border-radius:50%;display:inline-block;"></span>二级</span>'
                + '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#f4a930;width:5px;height:5px;border-radius:50%;display:inline-block;"></span>三级</span>'
                + '<span class="graph-legend-item"><span class="graph-legend-dot" style="background:#81c784;width:4px;height:4px;border-radius:50%;display:inline-block;"></span>笔记</span>';
        }
    },

    _updateStats() {
        const topicNodes = (this.data.nodes || []).filter(n => n.type === 'topic').length;
        const tagNodes = (this.data.nodes || []).filter(n => n.type === 'tag').length;
        const fileNodes = (this.data.nodes || []).filter(n => n.type === 'file').length;
        const edgesCount = (this.data.edges || []).length;

        const footerEl = document.getElementById('graph-stats');
        if (footerEl) {
            const parts = [];
            if (topicNodes) parts.push(`${topicNodes}主题`);
            if (tagNodes) parts.push(`${tagNodes}标签`);
            if (fileNodes) parts.push(`${fileNodes}笔记`);
            footerEl.textContent = parts.join(' · ');
        }

        const gs1 = document.getElementById('graph-stat-notes');
        const gs2 = document.getElementById('graph-stat-topics');
        const gs3 = document.getElementById('graph-stat-links');
        if (gs1) gs1.textContent = fileNodes;
        if (gs2) gs2.textContent = topicNodes + tagNodes;
        if (gs3) gs3.textContent = edgesCount;
    },

    initD3() {
        const container = document.getElementById('graph-panel-body');
        if (!container) return;

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
            .style('z-index', 1)
            .style('background', 'var(--bg, #fafafa)');

        this.g = this.svg.append('g');

        this.zoom = d3.zoom()
            .scaleExtent([0.06, 5])
            .on('zoom', (e) => { this.g.attr('transform', e.transform); });
        this.svg.call(this.zoom);

        // Prevent zoom on node drag
        this.svg.on('dblclick.zoom', null);

        const emptyEl = document.getElementById('graph-empty');
        const loadingEl = document.getElementById('graph-loading');
        if (loadingEl) loadingEl.style.display = 'none';
        if (!this.data || !this.data.nodes || this.data.nodes.length === 0) {
            if (emptyEl) { emptyEl.textContent = '暂无数据'; emptyEl.style.display = ''; }
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

        const getRadius = d => {
            if (d.type === 'topic') {
                if (d.level === 1) return 7;
                if (d.level === 2) return 5;
                return 4;
            }
            if (d.type === 'tag') return 4 + Math.min(d.file_count || 0, 30) * 0.25;
            return 2.5;
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

        // ===== Sector-based radial layout: zero crossings, even spread =====
        // Build adjacency: parent ID → child IDs
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

        // Compute subtree file count for each node (used for radius scaling)
        const fileCounts = {};
        function computeFileCount(nodeId) {
            if (fileCounts[nodeId] !== undefined) return fileCounts[nodeId];
            const children = childMap[nodeId] || [];
            let count = 0;
            for (const cid of children) {
                const child = nodeMap[cid];
                if (!child) continue;
                if (child.type === 'file') count += 1;
                else count += computeFileCount(cid);
            }
            fileCounts[nodeId] = count;
            return count;
        }
        nodes.forEach(n => { computeFileCount(n.id); });
        const maxFileCount = Math.max(1, ...Object.values(fileCounts));

        // Count total descendant leaves for sector allocation
        function countLeaves(nodeId, visited) {
            if (visited.has(nodeId)) return 0;
            visited.add(nodeId);
            const children = childMap[nodeId] || [];
            if (children.length === 0) return 1;
            return children.reduce((s, c) => s + countLeaves(c, visited), 0);
        }

        const maxR = Math.min(svgW, svgH) * 0.43;
        const rL1    = 18;
        const rL2Min = maxR * 0.12;
        const rL2Max = maxR * 0.32;
        const rL3Min = maxR * 0.28;
        const rL3Max = maxR * 0.48;
        const rFileMin = maxR * 0.40;
        const rFileMax = maxR * 0.72;
        const rTagMin = maxR * 0.30;
        const rTagMax = maxR * 0.55;

        function scaleRadius(minR, maxR, parentId) {
            const fc = fileCounts[parentId] || 0;
            const t = maxFileCount > 0 ? fc / maxFileCount : 0;
            return minR + (maxR - minR) * t;
        }

        // Reset targets
        nodes.forEach(n => { n.tx = undefined; n.ty = undefined; });

        // ---- crossing reduction: compute subtree barycenter angles ----
        const barycenterMap = {};
        function computeBarycenter(nodeId, visited) {
            if (barycenterMap[nodeId] !== undefined) return barycenterMap[nodeId];
            if (visited.has(nodeId)) { barycenterMap[nodeId] = 0; return 0; }
            visited.add(nodeId);
            const ch = (childMap[nodeId] || []).filter(c => nodeMap[c] && !visited.has(c));
            if (ch.length === 0) { barycenterMap[nodeId] = 0; return 0; }
            let sum = 0;
            ch.forEach(function(c, i) {
                computeBarycenter(c, new Set(visited));
                sum += (i / Math.max(1, ch.length - 1)) * 2 - 1; // spread -1..1
            });
            barycenterMap[nodeId] = sum / ch.length;
            return barycenterMap[nodeId];
        }
        nodes.forEach(function(n) { computeBarycenter(n.id, new Set()); });

        // Assign positions recursively within an angular sector
        function assignRadial(parentId, a0, sector, visited) {
            var children = (childMap[parentId] || []).filter(function(c) { return nodeMap[c] && !visited.has(c); });
            if (children.length === 0) return;

            // Sort children by barycenter to minimize edge crossings
            children.sort(function(a, b) {
                return (barycenterMap[a] || 0) - (barycenterMap[b] || 0);
            });

            const totalL = children.reduce((s, c) => s + countLeaves(c, new Set([...visited])), 0) || children.length;
            let a = a0;

            children.forEach(childId => {
                const child = nodeMap[childId];
                const childL = countLeaves(childId, new Set([...visited]));
                const cs = (childL / totalL) * sector;
                const ca = a + cs / 2;

                let r;
                if (child.type === 'topic') {
                    r = child.level === 2
                        ? scaleRadius(rL2Min, rL2Max, childId)
                        : scaleRadius(rL3Min, rL3Max, childId);
                } else if (child.type === 'tag') {
                    r = scaleRadius(rTagMin, rTagMax, childId);
                } else {
                    r = scaleRadius(rFileMin, rFileMax, childId);
                }

                const tx = cx + Math.cos(ca) * r;
                const ty = cy + Math.sin(ca) * r;
                if (child.tx !== undefined) {
                    child.tx = (child.tx + tx) / 2;
                    child.ty = (child.ty + ty) / 2;
                } else {
                    child.tx = tx;
                    child.ty = ty;
                }

                assignRadial(childId, a, cs, new Set([...visited]));
                a += cs;
            });
        }

        // Position L1 topics evenly around center
        const l1Nodes = nodes.filter(n => n.type === 'topic' && n.level === 1);
        const l1Count = l1Nodes.length || 1;
        l1Nodes.forEach((n, i) => {
            const a = (2 * Math.PI * i) / l1Count - Math.PI / 2;
            n.tx = cx + Math.cos(a) * rL1;
            n.ty = cy + Math.sin(a) * rL1;
        });

        // Spread L1→children sectors
        const visited = new Set();
        l1Nodes.forEach((n, i) => {
            const a0 = (2 * Math.PI * i) / l1Count - Math.PI / 2;
            assignRadial(n.id, a0, (2 * Math.PI) / l1Count, visited);
        });

        // Orphaned / tag-only nodes: spread with file-count-scaled radii
        const orphanNodes = nodes.filter(n => n.tx === undefined);
        const orphanCount = orphanNodes.length;
        orphanNodes.forEach((n, i) => {
            const a = (orphanCount > 1 ? (i / orphanCount) : 0) * 2 * Math.PI;
            let r;
            if (n.type === 'tag') {
                r = scaleRadius(rTagMin, rTagMax, n.id);
            } else {
                r = scaleRadius(rFileMin, rFileMax, n.id);
            }
            n.tx = cx + Math.cos(a) * (r + 50);
            n.ty = cy + Math.sin(a) * (r + 50);
        });

        const linkForce = d3.forceLink(edges).id(d => d.id)
            .distance(d => {
                const st = d.source.type || (typeof d.source === 'string' ? 'file' : '');
                const tt = d.target.type || (typeof d.target === 'string' ? 'file' : '');
                if (st === 'topic' && tt === 'topic') return 30;
                return 50;
            })
            .strength(0.05);

        this.simulation = d3.forceSimulation(nodes)
            .force('link', linkForce)
            .force('charge', d3.forceManyBody().strength(-150))
            .force('x', d3.forceX(d => d.tx).strength(d => {
                if (d.type === 'topic' && d.level === 1) return 0.6;
                if (d.type === 'topic') return 0.3;
                if (d.type === 'tag') return 0.2;
                return 0.15;
            }))
            .force('y', d3.forceY(d => d.ty).strength(d => {
                if (d.type === 'topic' && d.level === 1) return 0.6;
                if (d.type === 'topic') return 0.3;
                if (d.type === 'tag') return 0.2;
                return 0.15;
            }))
            .force('collision', d3.forceCollide().radius(d => getRadius(d) + 4))
            .alphaDecay(0.01)
            .velocityDecay(0.4);

        // Links
        const linkGroup = this.g.append('g').attr('class', 'graph-links');
        const link = linkGroup.selectAll('line')
            .data(edges)
            .join('line')
            .attr('stroke', '#c8c8c8')
            .attr('stroke-width', 0.3)
            .attr('opacity', 0.3);

        // Arrowheads for bidirectional display (small dots at both ends)
        // Nodes
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
            .style('pointer-events', 'none');

        // Drag behavior
        const drag = d3.drag()
            .on('start', (e, d) => {
                if (!e.active) self.simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on('drag', (e, d) => {
                d.fx = e.x;
                d.fy = e.y;
            })
            .on('end', (e, d) => {
                if (!e.active) self.simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            });

        node.call(drag);

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
                showPreview({ path: d.abstract_file, name: (d.name || d.id) + ' 综述' });
            }
        });

        // Click
        node.on('click', (e, d) => {
            e.stopPropagation();
            if (d.type === 'file' && d.full_path && typeof showPreview === 'function') {
                showPreview({ path: d.full_path, name: d.name });
            } else if (d.type === 'topic') {
                if (d.has_abstract && d.abstract_file && typeof showPreview === 'function') {
                    showPreview({ path: d.abstract_file, name: (d.name || d.id) + ' 综述' });
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
            } else if (d.type === 'tag' && self.filter === 'tag') {
                if (typeof switchSidebarView === 'function') {
                    switchSidebarView('tags');
                }
            }
        });

        // Tick
        this.simulation.on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        // Initial zoom to fit
        this.simulation.on('end', () => {
            const bounds = { x1: Infinity, y1: Infinity, x2: -Infinity, y2: -Infinity };
            nodes.forEach(n => {
                if (n.x < bounds.x1) bounds.x1 = n.x;
                if (n.y < bounds.y1) bounds.y1 = n.y;
                if (n.x > bounds.x2) bounds.x2 = n.x;
                if (n.y > bounds.y2) bounds.y2 = n.y;
            });
            const bw = bounds.x2 - bounds.x1 || 100;
            const bh = bounds.y2 - bounds.y1 || 100;
            const pad = 60;
            const scale = Math.min((svgW - pad * 2) / bw, (svgH - pad * 2) / bh, 1.5);
            const midX = (bounds.x1 + bounds.x2) / 2;
            const midY = (bounds.y1 + bounds.y2) / 2;
            self.svg.transition().duration(800).call(
                self.zoom.transform,
                d3.zoomIdentity.translate(svgW / 2, svgH / 2).scale(Math.max(0.15, scale)).translate(-midX, -midY)
            );
        });

        // Run simulation
        this.simulation.alpha(0.6).restart();

        // Click background to deselect
        this.svg.on('click', () => {});
    },

    resize() {
        if (!this.svg || !this.data) return;
        const container = document.getElementById('graph-panel-body');
        if (!container) return;
        const newW = container.clientWidth || 800;
        const newH = container.clientHeight || 600;
        const oldW = +this.svg.attr('width');
        const oldH = +this.svg.attr('height');

        if (newW === oldW && newH === oldH) return;

        this.svg.attr('width', newW).attr('height', newH);

        if (!this.simulation) return;

        // Re-center and re-fit without rebuilding
        var self = this;
        var nodes = this.simulation.nodes();
        if (!nodes || !nodes.length) return;

        var bounds = { x1: Infinity, y1: Infinity, x2: -Infinity, y2: -Infinity };
        nodes.forEach(function(n) {
            if (n.x < bounds.x1) bounds.x1 = n.x;
            if (n.y < bounds.y1) bounds.y1 = n.y;
            if (n.x > bounds.x2) bounds.x2 = n.x;
            if (n.y > bounds.y2) bounds.y2 = n.y;
        });
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

        // ---- compute target positions (radial layout) ----
        var childMap = {};
        var parentMap = {};
        edges.forEach(function(e) {
            if (!childMap[e.source]) childMap[e.source] = [];
            childMap[e.source].push(e.target);
            parentMap[e.target] = e.source;
        });

        var fileCounts = {};
        function countFiles(nid) {
            if (fileCounts[nid] !== undefined) return fileCounts[nid];
            var ch = childMap[nid] || [];
            var c = 0;
            ch.forEach(function(cid) { var nd = nodeMap[cid]; if (!nd) return; c += nd.type === 'file' ? 1 : countFiles(cid); });
            fileCounts[nid] = c;
            return c;
        }
        nodes.forEach(function(n) { countFiles(n.id); });
        var maxFC = Math.max(1, Math.max.apply(null, Object.values(fileCounts)));

        function countLeaves(nid, vis) {
            if (vis.has(nid)) return 0; vis.add(nid);
            var ch = childMap[nid] || [];
            return ch.length === 0 ? 1 : ch.reduce(function(s, c) { return s + countLeaves(c, new Set(vis)); }, 0);
        }

        var maxR = Math.min(svgW, svgH) * 0.43;
        function scaleR(minR, maxR2, pid) {
            return minR + (maxR2 - minR) * ((fileCounts[pid] || 0) / maxFC);
        }

        function assignRadial(pid, a0, sector, vis) {
            var ch = (childMap[pid] || []).filter(function(c) { return nodeMap[c] && !vis.has(c); });
            if (ch.length === 0) return;
            var totalL = ch.reduce(function(s, c) { return s + countLeaves(c, new Set(vis)); }, 0) || ch.length;
            var a = a0;
            ch.forEach(function(cid) {
                var nd = nodeMap[cid];
                var cl = countLeaves(cid, new Set(vis));
                var cs = (cl / totalL) * sector;
                var ca = a + cs / 2;
                var r;
                if (nd.type === 'topic') {
                    r = nd.level === 2 ? scaleR(maxR * 0.12, maxR * 0.32, cid) : scaleR(maxR * 0.28, maxR * 0.48, cid);
                } else if (nd.type === 'tag') {
                    r = scaleR(maxR * 0.30, maxR * 0.55, cid);
                } else {
                    r = scaleR(maxR * 0.40, maxR * 0.72, cid);
                }
                nd._tx = cx + Math.cos(ca) * r;
                nd._ty = cy + Math.sin(ca) * r;
                nd._depth = Math.max(nd._depth || 0, (nodeMap[pid] ? (nodeMap[pid]._depth || 0) + 1 : 1));
                assignRadial(cid, a, cs, new Set(vis));
                a += cs;
            });
        }

        var l1s = nodes.filter(function(n) { return n.type === 'topic' && n.level === 1; });
        l1s.forEach(function(n, i) {
            n._depth = 0;
            var a = (2 * Math.PI * i) / (l1s.length || 1) - Math.PI / 2;
            n._tx = cx + Math.cos(a) * 18;
            n._ty = cy + Math.sin(a) * 18;
        });
        var vis = new Set();
        l1s.forEach(function(n, i) {
            assignRadial(n.id, (2 * Math.PI * i) / (l1s.length || 1) - Math.PI / 2, (2 * Math.PI) / (l1s.length || 1), vis);
        });

        var orphans = nodes.filter(function(n) { return n._tx === undefined; });
        var maxD = 0;
        nodes.forEach(function(n) { if (n._depth > maxD) maxD = n._depth; });
        orphans.forEach(function(n, i) {
            n._depth = maxD + 1;
            var a = ((orphans.length > 1 ? i / orphans.length : 0)) * 2 * Math.PI;
            var r = n.type === 'tag' ? scaleR(maxR * 0.30, maxR * 0.55, n.id) : scaleR(maxR * 0.40, maxR * 0.72, n.id);
            n._tx = cx + Math.cos(a) * (r + 50);
            n._ty = cy + Math.sin(a) * (r + 50);
        });

        nodes.forEach(function(n) { maxD = Math.max(maxD, n._depth || 0); });

        // ---- build SVG elements ----
        this.g.selectAll('*').remove();

        var getRadius = function(d) {
            if (d.type === 'topic') return d.level === 1 ? 7 : d.level === 2 ? 5 : 4;
            if (d.type === 'tag') return 4 + Math.min(d.file_count || 0, 30) * 0.25;
            return 2.5;
        };
        var getColor = function(d) {
            if (d.type === 'topic') return d.level === 1 ? '#e85d3a' : d.level === 2 ? '#ea8600' : '#f4a930';
            if (d.type === 'tag') return '#7c4dff';
            return '#81c784';
        };

        // Create all elements hidden initially
        var linkGroup = self.g.append('g').attr('class', 'graph-links');
        var nodeGroup = self.g.append('g').attr('class', 'graph-nodes');

        // Add nodes at center, invisible
        var nodeSel = nodeGroup.selectAll('g').data(nodes).join('g')
            .attr('cursor', 'pointer')
            .attr('opacity', 0)
            .attr('transform', function(d) { d.x = cx; d.y = cy; return 'translate(' + cx + ',' + cy + ')'; });

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
            .style('pointer-events', 'none');

        // Add edges, invisible
        var linkSel = linkGroup.selectAll('line').data(edges).join('line')
            .attr('stroke', '#c8c8c8').attr('stroke-width', 0.3).attr('opacity', 0)
            .attr('x1', cx).attr('y1', cy).attr('x2', cx).attr('y2', cy);

        // ---- force-directed growth animation ----
        var totalNodes = nodes.length;
        var totalTime = Math.max(15000, Math.min(45000, totalNodes * 350)); // ~30-40s for 100 nodes
        var depthInterval = totalTime / (maxD + 2); // time between depth reveals

        // All nodes start at center
        nodes.forEach(function(n) { n.x = cx; n.y = cy; });
        nodeSel
            .attr('transform', function(d) { return 'translate(' + cx + ',' + cy + ')'; });

        // L1 visible immediately
        var l1Ids = new Set(l1s.map(function(n) { return n.id; }));
        nodeSel.filter(function(d) { return l1Ids.has(d.id); }).attr('opacity', 1);
        linkSel.attr('opacity', function(d) { return (l1Ids.has(d.source) && l1Ids.has(d.target)) ? 0.3 : 0; });

        var revealed = new Set(l1Ids);
        var currentRevealDepth = 1;
        var simStartTime = Date.now();

        var sim = d3.forceSimulation(nodes)
            .force('link', d3.forceLink(edges).id(function(d) { return d.id; }).distance(45).strength(0.04))
            .force('charge', d3.forceManyBody().strength(-120))
            .force('x', d3.forceX(function(d) { return d._tx; }).strength(0.01))
            .force('y', d3.forceY(function(d) { return d._ty; }).strength(0.01))
            .force('collision', d3.forceCollide().radius(function(d) { return getRadius(d) + 6; }))
            .alpha(0.3).alphaDecay(0.01).velocityDecay(0.55);

        sim.on('tick', function() {
            var elapsed = Date.now() - simStartTime;

            // Reveal next depth on schedule
            while (currentRevealDepth <= maxD + 1 && elapsed >= currentRevealDepth * depthInterval) {
                nodes.filter(function(n) { return (n._depth || 0) === currentRevealDepth; }).forEach(function(n) {
                    revealed.add(n.id);
                });
                currentRevealDepth++;
            }

            // Update opacity: visible if revealed, fade in over 300ms from reveal time
            nodeSel.attr('opacity', function(d) { return revealed.has(d.id) ? 1 : 0; });

            linkSel
                .attr('opacity', function(d) { return (revealed.has(d.source) && revealed.has(d.target)) ? 0.3 : 0; })
                .attr('x1', function(d) { return d.source.x; }).attr('y1', function(d) { return d.source.y; })
                .attr('x2', function(d) { return d.target.x; }).attr('y2', function(d) { return d.target.y; });

            nodeSel.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; });
        });

        sim.on('end', function() {
            var bounds = { x1: Infinity, y1: Infinity, x2: -Infinity, y2: -Infinity };
            nodes.forEach(function(n) {
                if (n.x < bounds.x1) bounds.x1 = n.x;
                if (n.y < bounds.y1) bounds.y1 = n.y;
                if (n.x > bounds.x2) bounds.x2 = n.x;
                if (n.y > bounds.y2) bounds.y2 = n.y;
            });
            var bw = bounds.x2 - bounds.x1 || 100;
            var bh = bounds.y2 - bounds.y1 || 100;
            var scale = Math.min((svgW - 120) / bw, (svgH - 120) / bh, 1.2);
            var midX = (bounds.x1 + bounds.x2) / 2;
            var midY = (bounds.y1 + bounds.y2) / 2;
            self.svg.transition().duration(600).call(
                self.zoom.transform,
                d3.zoomIdentity.translate(svgW / 2, svgH / 2).scale(Math.max(0.15, scale)).translate(-midX, -midY)
            );
            self.svg.on('click', null);
            self.simulation = null;
        });
    },
};

window.Graph3Tier = Graph3Tier;

function graphZoomIn() { Graph3Tier.zoomIn(); }
function graphZoomOut() { Graph3Tier.zoomOut(); }
function graphReplay() { Graph3Tier.replay(); }
function loadRelationGraphData() { Graph3Tier.load(); }
window.graphZoomIn = graphZoomIn;
window.graphZoomOut = graphZoomOut;
window.graphReplay = graphReplay;
window.loadRelationGraphData = loadRelationGraphData;

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#graph-filter-bar .graph-filter-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const f = this.dataset.filter;
            Graph3Tier.load(f);
        });
    });
});

window.addEventListener('resize', () => Graph3Tier.resize());