# NoteAI Design System

**版本**: 1.1  
**风格**: Minimal / Flat  
**主题**: Dark · Light · Paper（三选一）

---

## 1. 设计原则

| 原则 | 说明 |
|------|------|
| **克制** | 少即是多，不堆砌装饰 |
| **温暖** | 有人情味的工具 |
| **呼吸感** | 留白充足，层级清晰 |
| **一致性** | 三套主题保持相同的信息架构 |

---

## 2. 三套主题

### 2.1 Dark（深蓝夜色）

| 变量 | 色值 | 说明 |
|------|------|------|
| `--bg` | `#0c1018` | 主背景 |
| `--sidebar-bg` | `#121a26` | 侧栏 |
| `--surface` | `#161f2e` | 卡片/面板 |
| `--text` | `#d1dae8` | 主文本 |
| `--text-muted` | `#8494ad` | 辅助文本 |
| `--primary` | `#6C63FF` | 强调色（靛蓝） |
| `--border` | `rgba(88,130,190,0.12)` | 边框 |

### 2.2 Light（中性白）

| 变量 | 色值 | 说明 |
|------|------|------|
| `--bg` | `#ebebea` | 主背景 |
| `--sidebar-bg` | `rgba(255,255,255,0.55)` | 侧栏（毛玻璃） |
| `--surface` | `rgba(255,255,255,0.74)` | 卡片 |
| `--text` | `#1a1a1a` | 主文本 |
| `--text-muted` | `#6e6e6e` | 辅助文本 |
| `--primary` | `#2563eb` | 强调色（蓝） |
| `--border` | `rgba(0,0,0,0.08)` | 边框 |

### 2.3 Paper（羊皮纸）

| 变量 | 色值 | 说明 |
|------|------|------|
| `--bg` | `#e8e3da` | 主背景（暖米色） |
| `--sidebar-bg` | `#ded8cf` | 侧栏 |
| `--surface` | `#f1ebe3` | 卡片 |
| `--text` | `#141c1e` | 主文本 |
| `--text-muted` | `#59554c` | 辅助文本 |
| `--primary` | `#12827d` | 强调色（青绿） |
| `--border` | `rgba(0,0,0,0.075)` | 边框 |

---

## 3. 微调建议

### 3.1 Dark 主题

```css
/* 保持深蓝基调，微调对比度 */
[data-theme="dark"] {
  --bg: #0c1018;           /* 保持 */
  --sidebar-bg: #121a26;   /* 保持 */
  --surface: #1a2332;      /* 稍亮一点，增加层次 */
  --text: #d8e0ec;         /* 稍亮，提高可读性 */
  --text-muted: #7a8ba8;   /* 稍暗，降低干扰 */
  --primary: #6C63FF;      /* 保持 */
  --border: rgba(88,130,190,0.15);  /* 稍明显，增加分隔感 */
}
```

### 3.2 Light 主题

```css
/* 保持清爽白，微调阴影 */
[data-theme="light"] {
  --bg: #f5f5f3;           /* 更接近纯白，但不刺眼 */
  --sidebar-bg: rgba(255,255,255,0.6);  /* 稍重一点 */
  --surface: rgba(255,255,255,0.8);     /* 卡片更清晰 */
  --text: #1a1a1a;         /* 保持 */
  --text-muted: #6b6b6b;   /* 稍深，提高可读性 */
  --primary: #2563eb;      /* 保持 */
  --border: rgba(0,0,0,0.1);            /* 稍明显 */
  --card-shadow: 0 0 0 1px rgba(255,255,255,0.9) inset, 0 2px 12px rgba(0,0,0,0.08);
}
```

### 3.3 Paper 主题

```css
/* 保持纸张质感，微调暖度 */
[data-theme="paper"] {
  --bg: #eae5dc;           /* 稍暖，更像纸张 */
  --sidebar-bg: #e0dbd2;   /* 保持 */
  --surface: #f3ede5;      /* 卡片更亮 */
  --text: #1a2024;         /* 保持深色 */
  --text-muted: #5a5548;   /* 保持 */
  --primary: #12827d;      /* 保持青绿 */
  --border: rgba(0,0,0,0.08);
  --article-bg: #f0ebe2;   /* 文章背景更柔和 */
}
```

---

## 4. 间距规范

基于 4px 网格，保持现有：

| 名称 | 值 | 用途 |
|------|------|------|
| `--space-1` | 4px | 紧凑间距 |
| `--space-2` | 8px | 元素内间距 |
| `--space-3` | 12px | 小组件间距 |
| `--space-4` | 16px | 标准间距 |
| `--space-5` | 20px | 卡片内间距 |
| `--space-6` | 24px | 区块间距 |

---

## 5. 圆角规范

保持现有：

| 名称 | 值 | 用途 |
|------|------|------|
| `--card-radius` | 12px | 卡片、面板 |
| `--btn-radius` | 8px | 按钮 |
| `--input-radius` | 8px | 输入框 |

---

## 6. 阴影规范

### 6.1 Dark 主题

```css
--card-shadow: 0 0 0 1px rgba(80,120,180,0.08), 0 4px 16px rgba(0,0,0,0.42);
```

### 6.2 Light 主题

```css
--card-shadow: 0 0 0 1px rgba(255,255,255,0.9) inset, 0 2px 12px rgba(0,0,0,0.06);
```

### 6.3 Paper 主题

```css
--card-shadow: 0 0 0 1px rgba(0,0,0,0.06), 0 1px 6px rgba(0,0,0,0.05);
```

---

## 7. 组件规范

### 7.1 卡片

```
┌─────────────────────────────────┐
│  padding: 16-20px               │
│  border-radius: 12px            │
│  background: var(--surface)     │
│  box-shadow: var(--card-shadow) │
│                                 │
│  hover:                         │
│    background: var(--surface-hover) │
│    transition: 150ms ease       │
└─────────────────────────────────┘
```

### 7.2 按钮

```css
/* 主按钮 */
.btn-primary {
  background: var(--primary);
  color: var(--on-primary);
  padding: 8px 16px;
  border-radius: var(--btn-radius);
  font-size: 14px;
  font-weight: 500;
  transition: background 150ms;
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

### 7.3 输入框

```css
.input {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--input-radius);
  padding: 8px 12px;
  font-size: 14px;
  transition: border-color 150ms;
}

.input:focus {
  outline: none;
  border-color: var(--primary);
}
```

### 7.4 侧栏

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

---

## 8. 动效规范

### 8.1 时长

| 名称 | 值 | 用途 |
|------|------|------|
| `--duration-fast` | 100ms | 按钮状态 |
| `--duration-normal` | 150ms | 悬浮、聚焦 |
| `--duration-slow` | 250ms | 展开、收起 |

### 8.2 缓动

```css
--ease-default: cubic-bezier(0.4, 0, 0.2, 1);
```

### 8.3 禁用的动效

- ❌ 发光效果
- ❌ 光晕脉动
- ❌ 复杂入场动画
- ❌ 弹性动画
- ❌ 3D 翻转

### 8.4 允许的动效

- ✅ 透明度淡入淡出
- ✅ 平移（slide）
- ✅ 缩放（scale）
- ✅ 边框颜色过渡

---

## 9. 状态色

| 状态 | Dark | Light | Paper |
|------|------|-------|-------|
| 成功 | `#3fb950` | `#059669` | `#048056` |
| 警告 | `#d29922` | `#d97706` | `#c9710a` |
| 错误 | `#f85149` | `#dc2626` | `#cf2222` |

---

## 10. 图谱节点色

| 节点 | Dark | Light | Paper |
|------|------|-------|-------|
| L1 | `#d29922` | `#d97706` | `#c9710a` |
| L2 | `#d29922` | `#d97706` | `#c9710a` |
| L3 | `#d29922` | `#d97706` | `#c9710a` |
| 笔记 | `#6C63FF` | `#2563eb` | `#12827d` |
| 标签 | `#3fb950` | `#059669` | `#048056` |

---

## 11. 与 Obsidian 的差异化

| 维度 | Obsidian | NoteAI |
|------|----------|--------|
| Dark | 纯黑灰 | 深蓝夜色 |
| Light | 冷白 | 暖白/毛玻璃 |
| Paper | 无 | 羊皮纸质感 |
| 主题色 | 无 | 三套各有强调色 |
| 整体气质 | 极客工具 | 知识伙伴 |

---

## 附录：CSS 变量速查

```css
/* 快速使用 */
color: var(--text);
background: var(--surface);
border: 1px solid var(--border);
border-radius: var(--card-radius);
padding: 16px;
transition: all var(--duration-normal) var(--ease-default);
```

---

*维护说明：设计变更时请同步更新本文件，保持代码与文档一致。*
