#!/usr/bin/env node
/**
 * 打包前清理 python/ 下的构建残渣：
 *  tauri.conf.json 的 bundle.resources 用 glob 递归收 `../python/` 下所有文件，
 *  而 Tauri 的 glob 不支持取反，__pycache__（约 2.2 MB）与 .DS_Store
 *  只能先删掉才不进包。
 *
 * 用法：node scripts/clean-python-artifacts.mjs
 */
import { readdirSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const TARGET = join(ROOT, 'python');

let caches = 0;
let dotFiles = 0;

function walk(dir) {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
            if (entry.name === '__pycache__') {
                rmSync(full, { recursive: true, force: true });
                caches += 1;
            } else {
                walk(full);
            }
        } else if (entry.isFile() && entry.name === '.DS_Store') {
            rmSync(full, { force: true });
            dotFiles += 1;
        }
    }
}

walk(TARGET);
console.log(`clean:pycache — 删除 ${caches} 个 __pycache__、${dotFiles} 个 .DS_Store`);
