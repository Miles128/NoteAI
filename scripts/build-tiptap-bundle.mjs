import * as esbuild from 'esbuild';
import * as fs from 'fs';

const entryPoint = 'webui/js/tiptap-bundle-entry.mjs';
const outFile = 'webui/lib/tiptap-bundle.js';
const dependencyLock = 'package-lock.json';

/**
 * 判断 outfile 是否已是最新。
 * 入口文件或依赖锁文件更新后都必须重新打包，避免依赖升级后继续发布旧 bundle。
 */
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
  console.log(`[build:tiptap] ${outFile} is up to date, skipping.`);
  process.exit(0);
}

await esbuild.build({
  entryPoints: [entryPoint],
  bundle: true,
  format: 'iife',
  globalName: 'TiptapBundle',
  outfile: outFile,
  minify: true,
  sourcemap: false,
  target: ['es2020'],
});

console.log(`[build:tiptap] bundled to ${outFile}`);
