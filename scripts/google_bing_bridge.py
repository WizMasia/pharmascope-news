#!/usr/bin/env python3
"""Google News discovery -> Bing direct article URL matching.

The scheduled collector imports :func:`resolve_via_bing` for Google RSS URLs.
Only candidates scoring at or above the configured threshold are accepted.
"""
from __future__ import annotations

import html
import re
import subprocess
import urllib.parse
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse


_SOURCE_SUFFIX_RE = re.compile(r"\s+(?:-|\||–|—)\s+[^|]+$")
_NON_WORD_RE = re.compile(r"[^0-9A-Za-z가-힣]+")


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def normalize_title(title: str, source: str = "") -> str:
    """Normalize a title for cross-search comparison."""
    value = _text(title).lower()
    source_text = _text(source).lower()
    if source_text:
        value = re.sub(rf"\s*[-|–—]\s*{re.escape(source_text)}\s*$", "", value)
    value = _SOURCE_SUFFIX_RE.sub("", value)
    return _NON_WORD_RE.sub(" ", value).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in normalize_title(value).split() if len(token) > 1}


def _source_matches(article: dict, candidate: dict) -> bool:
    expected = _text(article.get("source", "")).lower()
    if not expected:
        return False
    observed = " ".join(
        [
            _text(candidate.get("source", "")),
            _text(candidate.get("title", "")),
            urlparse(_text(candidate.get("url", ""))).hostname or "",
        ]
    ).lower()
    expected_key = re.sub(r"[^0-9a-z가-힣]", "", expected)
    observed_key = re.sub(r"[^0-9a-z가-힣]", "", observed)
    return bool(expected_key and expected_key in observed_key)


def score_candidate(article: dict, candidate: dict) -> dict:
    """Score one Bing candidate against one Google-discovered article.

    Score is 0..100: title similarity (0..60), source match (30), and a
    verified-looking direct URL (10). This deliberately does not use an LLM.
    """
    expected = normalize_title(article.get("title", ""), article.get("source", ""))
    observed = normalize_title(candidate.get("title", ""), candidate.get("source", ""))
    title_ratio = SequenceMatcher(None, expected, observed).ratio() if expected and observed else 0.0
    expected_tokens = _tokens(expected)
    observed_tokens = _tokens(observed)
    token_ratio = (
        len(expected_tokens & observed_tokens) / len(expected_tokens | observed_tokens)
        if expected_tokens and observed_tokens
        else 0.0
    )
    title_similarity = max(title_ratio, token_ratio)
    domain_match = _source_matches(article, candidate)
    url = _text(candidate.get("url", ""))
    direct_url = bool(url.startswith(("http://", "https://")) and "news.google.com" not in url)
    score = round(title_similarity * 60) + (30 if domain_match else 0) + (10 if direct_url else 0)
    return {
        "score": min(score, 100),
        "title_similarity": round(title_similarity, 4),
        "domain_match": domain_match,
        "direct_url": direct_url,
    }


def find_best_match(article: dict, candidates: list[dict], threshold: int = 70) -> dict | None:
    """Return the highest-scoring direct-URL candidate above threshold."""
    ranked: list[dict] = []
    for candidate in candidates:
        result = score_candidate(article, candidate)
        if not result["direct_url"]:
            continue
        ranked.append({**candidate, **result})
    if not ranked:
        return None
    best = max(ranked, key=lambda item: item["score"])
    if best["score"] < threshold:
        return None
    best["url_source"] = "bing_match"
    best["match_title"] = best.get("title", "")
    return best


def _parse_bing_cards(page: str, limit: int = 10) -> list[dict]:
    """Parse the stable fields from Bing News cards without a browser."""
    cards = re.findall(r'<div class="news-card newsitem[^>]*>.*?</div>\s*</div>\s*</div>', page, re.S)
    results = []
    for card in cards:
        url_match = re.search(r'\surl="([^"]+)"', card)
        title_match = re.search(r'<h2[^>]*>(.*?)</h2>', card, re.S)
        source_match = re.search(r'data-author="([^"]*)"', card)
        time_match = re.search(r'<div class="ns_sc_tm"[^>]*>(.*?)</div>', card, re.S)
        if not url_match or not title_match:
            continue
        results.append(
            {
                "title": _text(re.sub(r"<[^>]+>", " ", title_match.group(1))),
                "source": _text(source_match.group(1) if source_match else ""),
                "url": html.unescape(url_match.group(1)),
                "time": _text(time_match.group(1) if time_match else ""),
            }
        )
        if len(results) >= limit:
            break
    return results


def search_bing_candidates(title: str, limit: int = 10, timeout: int = 15) -> list[dict]:
    """Search Bing News for one title and return candidate direct URLs."""
    query = urllib.parse.quote(f'"{_text(title)}"')
    url = f"https://www.bing.com/news/search?q={query}&setlang=en-us&cc=US"
    proc = subprocess.run(
        [
            "curl", "-sL", "--compressed", "--max-time", str(timeout),
            "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36", url,
        ],
        capture_output=True,
        text=True,
        timeout=timeout + 5,
    )
    if proc.returncode != 0:
        return []
    return _parse_bing_cards(proc.stdout, limit=limit)


def resolve_via_bing(article: dict, threshold: int = 70, limit: int = 10) -> dict | None:
    """Search Bing for a Google article and return a verified candidate."""
    candidates = search_bing_candidates(article.get("title", ""), limit=limit)
    return find_best_match(article, candidates, threshold=threshold)


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title")
    parser.add_argument("--source", default="")
    parser.add_argument("--threshold", type=int, default=70)
    args = parser.parse_args()
    article = {"title": args.title, "source": args.source}
    print(json.dumps(resolve_via_bing(article, threshold=args.threshold), ensure_ascii=False, indent=2))
