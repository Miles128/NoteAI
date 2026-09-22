#!/usr/bin/env node
/**
 * webui 前端打包：
 *  1) main.mjs + 48 个模块 → ESM bundle（webui/dist/main.js + chunks/，splitting）
 *  2) storage.ts → 经典 IIFE bundle（webui/js/storage.bundle.js），
 *     供 index.html 在模块执行前同步加载（window.Storage 前置契约）
 *  3) error-handler.ts → 经典 IIFE bundle（webui/js/error-handler.bundle.js）
 * 发布组装不在此做（highlight/tiptap 在本脚本之后构建）：
 *  由 npm run stage:webui 把产物 + 静态资源组装到 webui/app/（gitignore），
 *  Tauri frontendDist 只 serve 该目录，源码不进生产包。
 * dev 模式默认非压缩（含 inline sourcemap），release 用 --minify。
 */
import { build, context } from 'esbuild';
import { stageWebui, watchStage } from './stage-webui.mjs';

const minify = process.argv.includes('--minify');
const watch = process.argv.includes('--watch');

const mainOptions = {
    entryPoints: ['webui/js/main.mjs'],
    bundle: true,
    format: 'esm',
    target: 'es2020',
    outdir: 'webui/dist',
    entryNames: '[name]',
    splitting: true,
    chunkNames: 'chunks/[name]-[hash]',
    minify,
    sourcemap: minify ? false : 'inline',
    logLevel: 'info',
};

const storageOptions = {
    entryPoints: ['webui/js/storage.ts'],
    bundle: true,
    format: 'iife',
    target: 'es2020',
    outfile: 'webui/js/storage.bundle.js',
    minify,
    sourcemap: minify ? false : 'inline',
    logLevel: 'info',
};

const errorOptions = {
    entryPoints: ['webui/js/error-handler.ts'],
    bundle: true,
    format: 'iife',
    target: 'es2020',
    outfile: 'webui/js/error-handler.bundle.js',
    minify,
    sourcemap: minify ? false : 'inline',
    logLevel: 'info',
};

if (watch) {
    // NOTE: esbuild 的 build() 结果没有 .watch()，watch 模式必须用 context API。
    const mainCtx = await context({ ...mainOptions, sourcemap: 'inline' });
    const storageCtx = await context({ ...storageOptions, sourcemap: 'inline' });
    const errorCtx = await context({ ...errorOptions, sourcemap: 'inline' });
    await stageWebui({ strict: false });
    await Promise.all([mainCtx.watch(), storageCtx.watch(), errorCtx.watch()]);
    watchStage();
    console.log('[build-webui] watching for changes…');
} else {
    await Promise.all([build(mainOptions), build(storageOptions), build(errorOptions)]);
    // NOTE: 发布组装不在此做：highlight/tiptap bundle 在本脚本之后才构建，
    // 由 npm run stage:webui（或 tauri beforeDev/BuildCommand 链尾）统一组装。
}