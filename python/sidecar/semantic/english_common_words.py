"""English common-word blacklist for the semantic noise gate.

词表数据在同目录 ``english_common_words.txt``（Google Trillion Word Corpus
词频表前 3000 词（3-12 位纯小写）合并历史词表，一词一行）。普通英文词在
语义库里几乎不可能是具名对象；专名（China/Pandas 等）首字母大写不匹配
门禁的小写规则，由 _ALLOWED_ENGLISH_OBJECT_NAMES 白名单放行。
"""

from __future__ import annotations

from pathlib import Path

_COMMON_ENGLISH_WORDS = frozenset((Path(__file__).with_suffix(".txt")).read_text(encoding="utf-8").split())
