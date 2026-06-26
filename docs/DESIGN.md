# NoteAI Design System

**版本**: 2.0
**风格**: Tolaria-aligned Minimal Flat
**主题**: Dark · Light · Paper（三选一）

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **中性灰调** | 去蓝偏，单一强调色，不堆砌装饰 |
| **无阴影** | `--card-shadow: none`，靠边框和背景色差区分层级 |
| **无渐变** | 纯色背景，不做毛玻璃 / 模糊效果 |
| **小圆角** | 统一 4px，清晰利落 |
| **一致性** | 三套主题保持相同的信息架构与变量命名 |

---

## 2. 三套主题

### 2.1 Dark（中性深色）

| 变量 | 色值 | 说明 |
|------|------|------|
| `--bg` | `#1e1e1e` | 主背景 |
| `--sidebar-bg` | `#252525` | 侧栏 / 顶栏 / 状态栏 |
| `--surface` | `#2d2d2d` | 卡片 / 面板 / 模态框 |
| `--surface-hover` | `rgba(255,255,255,0.05)` | 悬浮态 |
| `--text` | `#e0e0e0` | 主文本 |
| `--text-muted` | `#8a8a8a` | 辅助文本 |
| `--primary` | `#4a9eff` | 强调色（亮蓝） |
| `--primary-dark` | `#3a8ae0` | 强调色按下态 |
| `--primary-light` | `rgba(74,158,255,0.12)` | 强调色浅底 |
| `--primary-hover` | `rgba(74,158,255,0.18)` | 强调色悬浮底 |
| `--border` | `#3a3a3a` | 边框（实色） |
| `--on-primary` | `#ffffff` | 强调色上的文字 |
| `--article-bg` | `#1e1e1e` | 文章阅读区背景 |
| `--glass-blur` | `none` | 无毛玻璃 |

### 2.2 Light（中性白）

| 变量 | 色值 | 说明 |
|------|------|------|
| `--bg` | `#ffffff` | 主背景 |
| `--sidebar-bg` | `#fafafa` | 侧栏 |
| `--surface` | `#f5f5f5` | 卡片 / 面板 |
| `--surface-hover` | `rgba(0,0,0,0.04)` | 悬浮态 |
| `--text` | `#1a1a1a` | 主文本 |
| `--text-muted` | `#666666` | 辅助文本 |
| `--primary` | `#0066ff` | 强调色（蓝） |
| `--primary-dark` | `#0052cc` | 强调色按下态 |
| `--primary-light` | `rgba(0,102,255,0.08)` | 强调色浅底 |
| `--primary-hover` | `rgba(0,102,255,0.12)` | 强调色悬浮底 |
| `--border` | `#e0e0e0` | 边框 |
| `--on-primary` | `#ffffff` | 强调色上的文字 |
| `--article-bg` | `#ffffff` | 文章阅读区背景 |

### 2.3 Paper（羊皮纸）

| 变量 | 色值 | 说明 |
|------|------|------|
| `--bg` | `#f5f1e8` | 主背景（暖米色） |
| `--sidebar-bg` | `#ede8dc` | 侧栏 |
| `--surface` | `#f9f5ec` | 卡片 / 面板 |
| `--surface-hover` | `rgba(0,0,0,0.04)` | 悬浮态 |
| `--text` | `#2a2620` | 主文本 |
| `--text-muted` | `#6b6358` | 辅助文本 |
| `--primary` | `#0d7c77` | 强调色（青绿） |
| `--primary-dark` | `#0a6360` | 强调色按下态 |
| `--primary-light` | `rgba(13,124,119,0.1)` | 强调色浅底 |
| `--primary-hover` | `rgba(13,124,119,0.16)` | 强调色悬浮底 |
| `--border` | `#d8d2c4` | 边框 |
| `--on-primary` | `#ffffff` | 强调色上的文字 |
| `--article-bg` | `#f9f5ec` | 文章阅读区背景 |

---

## 3. 间距规范

基于 4px 网格：

| 名称 | 值 | 用途 |
|------|------|------|
| `--space-1` | 4px | 紧凑间距 |
| `--space-2` | 8px | 元素内间距 |
| `--space-3` | 12px | 小组件间距 |
| `--space-4` | 16px | 标准间距 |
| `--space-5` | 20px | 卡片内间距 |
| `--space-6` | 24px | 区块间距 |

---

## 4. 圆角规范

统一小圆角，三套主题一致：

| 名称 | 值 | 用途 |
|------|------|------|
| `--card-radius` | 4px | 卡片、面板 |
| `--btn-radius` | 4px | 按钮 |
| `--input-radius` | 4px | 输入框 |

---

## 5. 阴影规范

三套主题统一 **无阴影**：

```css
--card-shadow: none;
```

层级区分依靠：
- 背景色差（`--bg` → `--sidebar-bg` → `--surface`）
- 边框（`--border` 实色）
- 悬浮态（`--surface-hover` 半透明叠加）

---

## 6. 组件规范

### 6.1 卡片

```css
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--card-radius);  /* 4px */
  box-shadow: none;
}
.card:hover {
  background: var(--surface-hover);
  transition: background 150ms ease;
}
```

### 6.2 按钮

```css
/* 主按钮 */
.btn-primary {
  background: var(--primary);
  color: var(--on-primary);
  padding: 8px 16px;
  border-radius: var(--btn-radius);  /* 4px */
  font-size: 14px;
  font-weight: 500;
  transition: background 150ms;
}
.btn-primary:active {
  background: var(--primary-dark);
}

/* 次按钮 */
.btn-secondary {
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border);
  padding: 8px 16px;
  border-radius: var(--btn-radius);
}

/* 幽灵按钮 */
.btn-ghost {
  background: transparent;
  color: var(--text-muted);
  padding: 8px 12px;
}
```

### 6.3 输入框

```css
.input {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--input-radius);  /* 4px */
  padding: 8px 12px;
  font-size: 14px;
  transition: border-color 150ms;
}
.input:focus {
  outline: none;
  border-color: var(--primary);
  background: var(--primary-light);
}
```

### 6.4 侧栏

```
┌────────────┬────────────────────────────────┐
│            │                                │
│  width:    │  主内容区                       │
│  240-280px │                                │
│            │                                │
│  bg:       │                                │
│  var(--    │                                │
│  sidebar-  │                                │
│  bg)       │                                │
│            │                                │
└────────────┴────────────────────────────────┘
```

### 6.5 开关

```css
--switch-bg: var(--surface);
--switch-border: var(--border);
--switch-active: var(--primary);
```

---

## 7. 动效规范

### 7.1 时长

| 名称 | 值 | 用途 |
|------|------|------|
| `--duration-fast` | 100ms | 按钮状态 |
| `--duration-normal` | 150ms | 悬浮、聚焦 |
| `--duration-slow` | 250ms | 展开、收起 |

### 7.2 缓动

```css
--ease-default: cubic-bezier(0.4, 0, 0.2, 1);
```

### 7.3 禁用的动效

- ❌ 发光效果（`--glow-cyan`、`--glow-purple` 均设为 `transparent`）
- ❌ 光晕脉动
- ❌ 复杂入场动画
- ❌ 弹性动画
- ❌ 3D 翻转
- ❌ 毛玻璃模糊（`--glass-blur: none`）

### 7.4 允许的动效

- ✅ 透明度淡入淡出
- ✅ 平移（slide）
- ✅ 缩放（scale）
- ✅ 边框 / 背景色过渡

---

## 8. 状态色

| 状态 | Dark | Light | Paper |
|------|------|-------|-------|
| 成功 `--success` | `#4caf50` | `#059669` | `#048056` |
| 警告 `--warning` | `#f5a623` | `#d97706` | `#c9710a` |
| 错误 `--error` | `#e53935` | `#dc2626` | `#cf2222` |

---

## 9. 功能色

三套主题各自定义的功能色变量：

| 变量 | Dark | Light | Paper | 用途 |
|------|------|-------|-------|------|
| `--color-file` | `#4a9eff` | `#0066ff` | `#0d7c77` | 文件节点 |
| `--color-topic` | `#f5a623` | `#d97706` | `#c9710a` | 主题节点 |
| `--color-tag` | `#4caf50` | `#059669` | `#048056` | 标签节点 |
| `--color-change` | `#ab47bc` | `#7c3aed` | `#6d42d9` | 变更标记 |
| `--color-danger` | `#e53935` | `#dc2626` | `#cf2222` | 危险操作 |
| `--color-pending` | `#f5a623` | `#d97706` | `#c9710a` | 待确认 |
| `--color-confirmed` | `#4caf50` | `#059669` | `#048056` | 已确认 |
| `--color-link-incoming` | `#4a9eff` | `#0066ff` | `#0d7c77` | 入链 |
| `--color-link-outgoing` | `#ab47bc` | `#7c3aed` | `#6d42d9` | 出链 |

---

## 10. 图谱节点色

通过 `--graph-color-*` 变量映射到功能色：

| 节点 | Dark | Light | Paper |
|------|------|-------|-------|
| 文件 `--graph-color-file` | `#4a9eff` | `#0066ff` | `#0d7c77` |
| 主题 `--graph-color-topic` | `#f5a623` | `#d97706` | `#c9710a` |
| 标签 `--graph-color-tag` | `#4caf50` | `#059669` | `#048056` |

---

## 11. 字号缩放

通过 `--font-scale` 和 root `font-size` 实现（非 `transform:scale`，避免 Retina 糊化）：

| 档位 | root font-size | `--font-scale` |
|------|----------------|----------------|
| 小（默认） | 14px | 1 |
| 中 | 16px | 1.143 |
| 大 | 18px | 1.286 |

---

## 12. 与 Obsidian 的差异化

| 维度 | Obsidian | NoteAI |
|------|----------|--------|
| Dark | 纯黑灰 | 中性深灰（去蓝偏） |
| Light | 冷白 | 纯白 / 中性灰 |
| Paper | 无 | 羊皮纸质感（扁平化） |
| 阴影 | 有 | 无（`none`） |
| 圆角 | 6-8px | 4px |
| 毛玻璃 | 有 | 无（`none`） |
| 强调色 | 无 | 三套各有单一强调色 |
| 整体气质 | 极客工具 | 知识伙伴 |

---

## 附录：CSS 变量速查

```css
/* 快速使用 */
color: var(--text);
background: var(--surface);
border: 1px solid var(--border);
border-radius: var(--card-radius);  /* 4px */
padding: 16px;
transition: all var(--duration-normal) var(--ease-default);
box-shadow: none;  /* 不使用阴影 */
```

---

*维护说明：设计变更时请同步更新本文件与 `webui/css/variables.css`，保持代码与文档一致。*
