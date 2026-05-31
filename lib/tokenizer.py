"""Tokenizer wrapper for the benchmark.

Token counts are a GPT-family *proxy* (tiktoken). Claude/Gemini tokenize
differently, so numbers are comparative across approaches, not absolute. The
encoding is recorded alongside every result so the proxy is explicit.
"""
from __future__ import annotations

import functools

# o200k_base is the encoding for GPT-4o / GPT-4.1 / o-series — the closest
# widely-available public proxy for modern frontier tokenizers.
DEFAULT_ENCODING = "o200k_base"


@functools.lru_cache(maxsize=4)
def _enc(encoding: str):
    import tiktoken

    return tiktoken.get_encoding(encoding)


def count_tokens(text: str, encoding: str = DEFAULT_ENCODING) -> int:
    if not text:
        return 0
    return len(_enc(encoding).encode(text))
