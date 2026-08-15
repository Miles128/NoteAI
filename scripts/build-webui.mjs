#!/usr/bin/env node
/**
 * webui 前端打包：把 webui/js 的 48 个模块 + main.mjs 打成单个 ESM bundle。
 * dev 模式默认非压缩（含 inline sourcemap），release 用 --minify。
 */
import { build } from 'esbuild';

const minify = process.argv.includes('--minify');
const watch = process.argv.includes('--watch');

const options = {
    entryPoints: ['webui/js/main.mjs'],
    bundle: true,
    format: 'esm',
    target: 'es2020',
    outfile: 'webui/dist/main.js',
    minify,
    sourcemap: minify ? false : 'inline',
    logLevel: 'info',
};

if (watch) {
    const ctx = await build({ ...options, sourcemap: 'inline' });
    await ctx.watch();
    console.log('[build-webui] watching for changes…');
} else {
    await build(options);
}