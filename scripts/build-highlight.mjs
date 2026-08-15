#!/usr/bin/env node
/**
 * highlight.js 打包：修复 webui/highlight.min.js 是损坏占位文件（67B 错误文本）的问题，
 * 从 npm highlight.js 打常用语言子集，导出经典全局 window.hljs。
 */
import * as esbuild from 'esbuild';
import * as fs from 'fs';

const entryPoint = 'webui/js/highlight-bundle-entry.mjs';
const outFile = 'webui/highlight.min.js';
const dependencyLock = 'package-lock.json';

function isUpToDate() {
    try {
        const outStat = fs.statSync(outFile);
        const entryStat = fs.statSync(entryPoint);
        const lockStat = fs.statSync(dependencyLock);
        return outStat.mtimeMs >= Math.max(entryStat.mtimeMs, lockStat.mtimeMs);
    } catch {
        return false;
    }
}

if (isUpToDate()) {
    console.log(`[build:highlight] ${outFile} is up to date, skipping.`);
    process.exit(0);
}

await esbuild.build({
    entryPoints: [entryPoint],
    bundle: true,
    format: 'iife',
    globalName: 'hljs',
    outfile: outFile,
    minify: true,
    sourcemap: false,
    target: ['es2020'],
});

console.log(`[build:highlight] bundled to ${outFile}`);