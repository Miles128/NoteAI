import * as esbuild from 'esbuild';
import * as fs from 'fs';

const entryPoint = 'webui/js/tiptap-bundle-entry.mjs';
const outFile = 'webui/lib/tiptap-bundle.js';

/**
 * 判断 outfile 是否已是最新（entryPoint 及所有 import 未变更）。
 * 简单策略：若 outfile 存在且 mtime 不早于 entryPoint，则视为无需重建。
 * node_modules 中的依赖通常不变；若手动升级依赖，可删除 outFile 触发重建。
 */
function isUpToDate() {
  try {
    const outStat = fs.statSync(outFile);
    const entryStat = fs.statSync(entryPoint);
    return outStat.mtimeMs >= entryStat.mtimeMs;
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
