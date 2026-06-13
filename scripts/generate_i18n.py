#!/usr/bin/env python3
"""Generate locale JSON and patch webui JS/HTML to use t() keys."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBUI = ROOT / "webui"
LOCALES = WEBUI / "locales"
JS_DIR = WEBUI / "js"

SKIP_JS = {"i18n.js", "marked.min.js", "highlight.min.js"}

# Manual English translations for common keys (fallback: copy zh)
EN_OVERRIDES: dict[str, str] = {
    "common.cancel": "Cancel",
    "common.close": "Close",
    "common.confirm": "Confirm",
    "common.collapse": "Collapse",
    "common.loading": "Loading…",
    "common.save": "Save",
    "common.saved": "Saved",
    "common.error": "Error",
    "common.retry": "Retry",
    "common.skip": "Skip",
}


def _slug(text: str, max_len: int = 48) -> str:
    t = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text.strip())
    t = t.strip("_")[:max_len]
    return t or "text"


def _module_prefix(filename: str) -> str:
    name = filename.replace(".js", "")
    mapping = {
        "app": "app",
        "assistant": "assistant",
        "pending": "pending",
        "settings": "settings",
        "sidebar": "sidebar",
        "search": "search",
        "ingest": "ingest",
        "editor": "editor",
        "preview": "preview",
        "workspace": "workspace",
        "tree": "tree",
        "topic": "topic",
        "tags": "tags",
        "links": "links",
        "downloader": "download",
        "integrator": "integrator",
        "converter": "converter",
        "quick-create": "quickCreate",
        "schema-wizard": "schemaWizard",
        "cloud-sync": "cloudSync",
        "toast": "toast",
        "error-handler": "error",
        "G3": "graph",
        "topic-tree-3tier": "topicTree",
    }
    return mapping.get(name, name.replace("-", ""))


def _set_nested(d: dict, key: str, value: str) -> None:
    parts = key.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _translate_en(zh: str, key: str) -> str:
    if key in EN_OVERRIDES:
        return EN_OVERRIDES[key]
    # Keep keys that are mostly English/technical
    if not re.search(r"[\u4e00-\u9fff]", zh):
        return zh
    return f"[EN] {zh}"  # placeholder for manual review


def extract_js_strings(content: str) -> list[str]:
    results: list[str] = []
    for m in re.finditer(r"(['\"`])([^\1\\]|\\.)*?\1", content):
        s = m.group(0)[1:-1]
        if not re.search(r"[\u4e00-\u9fff]", s):
            continue
        if len(s) > 300:
            continue
        if "function" in s or "=>" in s:
            continue
        # unescape
        try:
            s = bytes(s, "utf-8").decode("unicode_escape") if "\\n" in s else s
        except Exception:
            pass
        results.append(s)
    return results


def main() -> None:
    zh: dict = {}
    key_for_text: dict[str, str] = {}
    counters: dict[str, int] = {}

    for js_path in sorted(JS_DIR.glob("*.js")):
        if js_path.name in SKIP_JS:
            continue
        prefix = _module_prefix(js_path.name)
        content = js_path.read_text(encoding="utf-8")
        for s in extract_js_strings(content):
            if s in key_for_text:
                continue
            base = _slug(s)
            counters[prefix] = counters.get(prefix, 0) + 1
            key = f"{prefix}.{base}"
            # dedupe key names
            n = 1
            orig = key
            while key in {v for v in key_for_text.values()}:
                n += 1
                key = f"{orig}_{n}"
            key_for_text[s] = key
            _set_nested(zh, key, s)

    LOCALES.mkdir(parents=True, exist_ok=True)
    (LOCALES / "zh-CN.json").write_text(json.dumps(zh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    en: dict = {}

    def walk(d: dict, prefix: str = "") -> None:
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                walk(v, full)
            else:
                _set_nested(en, full, _translate_en(v, full))

    walk(zh)
    (LOCALES / "en.json").write_text(json.dumps(en, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Generated {len(key_for_text)} keys")
    print(f"Written {LOCALES / 'zh-CN.json'} and {LOCALES / 'en.json'}")


if __name__ == "__main__":
    main()
