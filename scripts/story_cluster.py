#!/usr/bin/env python3
"""Conservative, link-preserving clustering for near-duplicate news stories."""
from __future__ import annotations

import re
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any

_SOURCE_SUFFIX_RE = re.compile(r"\s+(?:-|\||–|—)\s+[^|]+$")
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣][0-9A-Za-z가-힣+./-]*")
# Boilerplate headline words must not make unrelated market reports appear to
# describe one event.  Entity/disease/product terms remain available to match.
_CLUSTER_STOP_TOKENS = {
    'market', 'overview', 'major', 'segments', 'strategic', 'developments',
    'leading', 'companies', 'company', 'industry', 'report', 'reports',
    'analysis', 'forecast', 'growth', 'trends', 'trend', 'global', 'latest',
    'news', 'update', 'updates', 'drug', 'drugs', 'treatment', 'therapeutics',
    'pharmaceutical', 'pharma', 'medical', 'healthcare', '시장', '전망',
    '분석', '보고서', '글로벌', '산업', '기업', '개발', '주요', '동향', '신약',
}


def normalize_title(value: Any, source: str = "") -> str:
    """Normalize a headline while removing a trailing publisher suffix."""
    title = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    source_key = re.escape(re.sub(r"\s+", " ", str(source or "")).strip().lower())
    if source_key:
        title = re.sub(rf"\s*[-|–—]\s*{source_key}\s*$", "", title)
    title = _SOURCE_SUFFIX_RE.sub("", title)
    return re.sub(r"[^0-9a-z가-힣+./ -]+", " ", title).strip()


def _tokens(article: dict) -> set[str]:
    return {
        token for token in _TOKEN_RE.findall(normalize_title(article.get("title"), article.get("source")))
        if token.lower() not in _CLUSTER_STOP_TOKENS
    }


def _is_same_story(first: dict, second: dict) -> tuple[bool, str]:
    """Return a conservative near-duplicate decision and evidence string."""
    first_title = normalize_title(first.get("title"), first.get("source"))
    second_title = normalize_title(second.get("title"), second.get("source"))
    if not first_title or not second_title:
        return False, ""
    if first_title == second_title:
        return True, "normalized_title_exact"

    first_tokens = _tokens(first)
    second_tokens = _tokens(second)
    if not first_tokens or not second_tokens:
        return False, ""
    overlap = len(first_tokens & second_tokens)
    union = len(first_tokens | second_tokens)
    jaccard = overlap / union if union else 0.0
    sequence = SequenceMatcher(None, first_title, second_title).ratio()
    # Strictly greater than 0.75 avoids grouping distinct named products that
    # otherwise share generic wording such as "FDA approves ... drug".
    if overlap >= 3 and jaccard > 0.75 and sequence >= 0.88:
        return True, f"title_jaccard={jaccard:.2f}; title_sequence={sequence:.2f}"
    return False, ""


def _article_rank(article: dict) -> tuple[int, int, int]:
    return (
        int(article.get("importance") or 0),
        1 if article.get("content_status") == "fulltext" else 0,
        len(str(article.get("content") or "")),
    )


def _related_link(article: dict) -> dict:
    return {
        "title": article.get("title", ""),
        "source": article.get("source", ""),
        "url": article.get("url", ""),
        "published_time": article.get("published_time") or article.get("time", ""),
        "importance": article.get("importance", 0),
        "content_status": article.get("content_status", ""),
    }


def assign_story_clusters(categories: dict, date_str: str) -> dict:
    """Annotate every article with a story cluster without dropping any URL.

    The input is the collector's ``category`` mapping.  Every article receives
    ``story_id``, ``story_primary`` and ``related_count``.  Only canonical
    articles contain a ``related_articles`` link list for report rendering.
    """
    articles: list[dict] = []
    for section in categories.values():
        if not isinstance(section, dict):
            continue
        for items in section.values():
            if isinstance(items, list):
                articles.extend(item for item in items if isinstance(item, dict))

    parent = list(range(len(articles)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    pair_reasons: dict[tuple[int, int], str] = {}
    for left in range(len(articles)):
        for right in range(left + 1, len(articles)):
            same, reason = _is_same_story(articles[left], articles[right])
            if same:
                union(left, right)
                pair_reasons[(left, right)] = reason

    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(articles)):
        groups[find(index)].append(index)

    ordered_groups = sorted(
        groups.values(),
        key=lambda indices: max(_article_rank(articles[index]) for index in indices),
        reverse=True,
    )
    grouped_articles = 0
    for number, indices in enumerate(ordered_groups, 1):
        story_id = f"{date_str}-story-{number:03d}"
        primary_index = max(indices, key=lambda index: _article_rank(articles[index]))
        primary = articles[primary_index]
        related_indices = [index for index in indices if index != primary_index]
        if related_indices:
            grouped_articles += len(related_indices)
        related_links = []
        suppressed_duplicate_count = 0
        primary_key = (
            re.sub(r'[^0-9a-z가-힣]', '', str(primary.get('source') or '').lower()),
            normalize_title(primary.get('title'), primary.get('source') or ''),
        )
        seen_coverage_keys = {primary_key}
        for index in sorted(related_indices, key=lambda index: _article_rank(articles[index]), reverse=True):
            candidate = articles[index]
            coverage_key = (
                re.sub(r'[^0-9a-z가-힣]', '', str(candidate.get('source') or '').lower()),
                normalize_title(candidate.get('title'), candidate.get('source') or ''),
            )
            if coverage_key in seen_coverage_keys:
                suppressed_duplicate_count += 1
                continue
            seen_coverage_keys.add(coverage_key)
            related_links.append(_related_link(candidate))

        for index in indices:
            article = articles[index]
            article["story_id"] = story_id
            article["story_primary"] = index == primary_index
            article["related_count"] = len(related_links) if index == primary_index else 0
            article["suppressed_duplicate_count"] = suppressed_duplicate_count if index == primary_index else 0
            article["story_size"] = len(indices)
            if index == primary_index:
                article["related_articles"] = related_links
                reasons = [reason for (left, right), reason in pair_reasons.items() if left in indices and right in indices]
                article["cluster_reason"] = "; ".join(sorted(set(reasons))) or "single_article"
            else:
                article.pop("related_articles", None)
                article["cluster_reason"] = "related_to:" + primary.get("url", "")

    return {
        "total_articles": len(articles),
        "unique_stories": len(ordered_groups),
        "grouped_articles": grouped_articles,
        "multi_article_stories": sum(1 for indices in ordered_groups if len(indices) > 1),
    }
