#!/usr/bin/env node
/**
 * webui 前端打包：
 *  1) main.mjs + 48 个模块 → 单个 ESM bundle（webui/dist/main.js）
 *  2) storage.ts → 经典 IIFE bundle（webui/js/storage.bundle.js），
 *     供 index.html 在模块执行前同步加载（window.Storage 前置契约）
 * dev 模式默认非压缩（含 inline sourcemap），release 用 --minify。
 */
import { build } from 'esbuild';

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

if (watch) {
    const ctx = await build({ ...mainOptions, sourcemap: 'inline' });
    await ctx.watch();
    const storageCtx = await build({ ...storageOptions, sourcemap: 'inline' });
    await storageCtx.watch();
    console.log('[build-webui] watching for changes…');
} else {
    await Promise.all([build(mainOptions), build(storageOptions)]);
}