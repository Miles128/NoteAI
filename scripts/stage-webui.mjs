#!/usr/bin/env node
/**
 * webui 前端发布组装：
 *  把运行时必需文件按原相对路径复制到 webui/app/（构建产物，gitignore，不入库），
 *  Tauri `frontendDist` 只 serve 该目录，避免源码（*.ts/main.mjs/package.json
 *  等）被打进生产包。
 *
 * 用法：
 *   node scripts/stage-webui.mjs          # 一次性组装（缺文件则报错退出）
 *   node scripts/stage-webui.mjs --watch  # 组装一次后监听输入变化自动重组
 */
import { cpSync, existsSync, mkdirSync, rmSync, watch } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(ROOT, 'webui');
export const STAGE_DIR = join(SRC, 'app');

// 运行时必需条目（相对 webui/）：文件或目录，原样镜像到 webui/app/。
// 来源：index.html 的全部本地 src/href + 各模块 loadLazyScript/loadLazyCss
// 动态加载路径（d3/marked/purify/highlight/tiptap/pdfjs/locales）。
const STATIC_ENTRIES = [
    'index.html',
    'css',
    'locales',
    'dist', // esbuild 输出 main.js + chunks/
    'js/storage.bundle.js',
    'js/error-handler.bundle.js',
    'lib/tiptap-bundle.js',
    'd3.min.js',
    'marked.min.js',
    'purify.min.js',
    'highlight.min.js',
    'hljs-github.css',
    'hljs-github-dark.css',
    'pdfjs-legacy.min.js',
    'pdfjs-legacy.worker.min.js',
];

export async function stageWebui({ strict = true } = {}) {
    const missing = STATIC_ENTRIES.filter((e) => !existsSync(join(SRC, e)));
    if (missing.length > 0) {
        const msg = `[stage-webui] missing runtime assets (run the webui/tiptap/highlight builds first): ${missing.join(', ')}`;
        if (strict) throw new Error(msg);
        console.warn(msg);
    }
    rmSync(STAGE_DIR, { recursive: true, force: true });
    mkdirSync(STAGE_DIR, { recursive: true });
    for (const entry of STATIC_ENTRIES) {
        const from = join(SRC, entry);
        if (!existsSync(from)) continue;
        cpSync(from, join(STAGE_DIR, entry), { recursive: true });
    }
    console.log(`[stage-webui] staged ${STATIC_ENTRIES.length} entries -> webui/app/`);
}

// 监听输入变化（不含输出目录自身，避免自触发），防抖后重组。
const WATCH_ROOTS = ['index.html', 'css', 'js', 'locales', 'lib', 'dist',
    'd3.min.js', 'marked.min.js', 'purify.min.js', 'highlight.min.js',
    'hljs-github.css', 'hljs-github-dark.css',
    'pdfjs-legacy.min.js', 'pdfjs-legacy.worker.min.js'];

export function watchStage({ debounceMs = 500 } = {}) {
    let timer = null;
    const restage = () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
            stageWebui({ strict: false }).catch((err) => console.error('[stage-webui]', err.message));
        }, debounceMs);
    };
    for (const rel of WATCH_ROOTS) {
        const target = join(SRC, rel);
        if (!existsSync(target)) continue;
        try {
            watch(target, { recursive: true }, restage);
        } catch (err) {
            console.warn(`[stage-webui] cannot watch ${rel}: ${err.message}`);
        }
    }
    console.log('[stage-webui] watching for changes…');
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
    if (process.argv.includes('--watch')) {
        await stageWebui({ strict: false });
        watchStage();
    } else {
        await stageWebui();
    }
}
