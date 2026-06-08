#!/usr/bin/env python3
"""
PharmaScope Aggregator — 주간/월간/분기/연간 집계 리포트 생성
Usage: python3 pharmascope_aggregate.py <period> [--date YYYY-MM-DD]
  period: weekly|monthly|quarterly|yearly
"""
import json, os, sys, subprocess
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

BASE_DIR = os.path.expanduser("~/workspace/mywiki/news/pharmascope")
MYWIKI_DIR = os.path.expanduser("~/workspace/mywiki")
KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)

def git_commit(message):
    """Commit and push changes to mywiki git repo."""
    try:
        add = subprocess.run(['git', 'add', '-A'], cwd=MYWIKI_DIR, capture_output=True, text=True, timeout=30)
        if add.returncode != 0:
            print(f"⚠️ git add failed: {add.stderr.strip()}")
            return
        diff = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=MYWIKI_DIR, capture_output=True, timeout=30)
        if diff.returncode == 0:
            print("📎 No new changes to commit")
            return
        commit = subprocess.run(['git', 'commit', '-m', message], cwd=MYWIKI_DIR, capture_output=True, text=True, timeout=30)
        if commit.returncode == 0:
            print(f"✅ Git commit: {commit.stdout.strip()}")
            push = subprocess.run(['git', 'push', 'origin', 'main', '--force'], cwd=MYWIKI_DIR, capture_output=True, text=True, timeout=30)
            if push.returncode == 0:
                print(f"✅ Git push: {push.stdout.strip()}")
        else:
            print(f"⚠️ git commit: {commit.stderr.strip()}")
    except Exception as e:
        print(f"⚠️ Git error: {e}")

# PharmaScope 5 categories (Korean)
KR_CATEGORIES = ['의약품', '의약산업', '의약정책', '의약단체', '의약관련정부기관']
EN_CATEGORIES = ['Drugs & Therapies', 'Pharma Industry', 'Pharma Policy',
                 'Pharma Associations', 'Regulatory Agencies']

def get_date_range(period, anchor=None):
    d = anchor or NOW
    if period == 'weekly':
        start = d - timedelta(days=d.weekday())
        end = start + timedelta(days=6)
        return start, end, f"Week {d.isocalendar()[1]}", start.strftime('%Y-W%W')
    elif period == 'monthly':
        start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if d.month == 12:
            end = d.replace(year=d.year+1, month=1, day=1) - timedelta(seconds=1)
        else:
            end = d.replace(month=d.month+1, day=1) - timedelta(seconds=1)
        return start, end, d.strftime('%B %Y'), d.strftime('%Y-%m')
    elif period == 'quarterly':
        quarter = (d.month - 1) // 3 + 1
        start_month = (quarter - 1) * 3 + 1
        start = d.replace(month=start_month, day=1)
        if quarter == 4:
            end = d.replace(year=d.year+1, month=1, day=1) - timedelta(seconds=1)
        else:
            end = d.replace(month=start_month+3, day=1) - timedelta(seconds=1)
        return start, end, f"Q{quarter} {d.year}", f"{d.year}-Q{quarter}"
    elif period == 'yearly':
        start = d.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = d.replace(year=d.year+1, month=1, day=1) - timedelta(seconds=1)
        return start, end, str(d.year), str(d.year)
    return None, None, None, None

def get_data_safe(data, *keys):
    """Safely traverse nested dict."""
    for k in keys:
        if isinstance(data, dict) and k in data:
            data = data[k]
        else:
            return {}
    return data if isinstance(data, dict) else {}

def load_daily_data(date_str):
    path = os.path.join(BASE_DIR, 'daily', date_str, 'raw.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def count_items(cat_dict):
    return sum(len(v) for v in cat_dict.values() if isinstance(v, list))

def generate_aggregate_report(period, anchor=None):
    start, end, label, folder_name = get_date_range(period, anchor)
    if not start:
        print(f"Unknown period: {period}")
        return

    output_dir = os.path.join(BASE_DIR, period, folder_name)
    os.makedirs(output_dir, exist_ok=True)

    current = start
    daily_data = []
    dates_covered = []

    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        data = load_daily_data(date_str)
        if data:
            daily_data.append(data)
            dates_covered.append(date_str)
        current += timedelta(days=1)

    total_days = len(dates_covered)
    if total_days == 0:
        print(f"No data found for {period} {folder_name}")
        return

    # Aggregation counters
    total_articles = 0
    kr_count = 0
    en_count = 0
    ml_count = 0
    kr_cat_counts = Counter()
    en_cat_counts = Counter()
    source_hits = Counter()
    lang_hits = Counter()

    # Pharma-specific keyword tracking
    kr_keywords = Counter()
    en_keywords = Counter()
    all_titles = []

    for data in daily_data:
        cats = get_data_safe(data, 'category')

        # --- Korean ---
        kr = get_data_safe(cats, 'korean')
        for cat_name, items in kr.items():
            if isinstance(items, list):
                kr_cat_counts[cat_name] += len(items)
                kr_count += len(items)
                for item in items:
                    total_articles += 1
                    title = item.get('title', '')
                    all_titles.append(title)
                    src = item.get('source', '') or (title.split(' - ')[-1] if ' - ' in title else '')
                    if src:
                        source_hits[src] += 1
                    # Pharma keyword tracking
                    for kw in ['비만', 'GLP-1', '위고비', '마운자로', '오남용', 'GMP', '실사',
                               '허가', '심사', '신약', '제네릭', '바이오시밀러', '약가', '급여',
                               '한약', '생약', '천연물', '임상', 'ADC', '항암',
                               'FDA', '식약처', 'MFDS', '원료의약품', '공급망',
                               '백신', '특허', 'CRO', 'CDMO', 'R&D', '수출']:
                        if kw in title:
                            kr_keywords[kw] += 1

        # --- English ---
        en = get_data_safe(cats, 'english')
        for cat_name, items in en.items():
            if isinstance(items, list):
                en_cat_counts[cat_name] += len(items)
                en_count += len(items)
                for item in items:
                    total_articles += 1
                    title = item.get('title', '')
                    all_titles.append(title)
                    src = item.get('source', '')
                    if src:
                        source_hits[src] += 1
                    for kw in ['GLP-1', 'obesity', 'FDA', 'GMP', 'shortage', 'biosimilar',
                               'clinical trial', 'approval', 'generic', 'vaccine',
                               'inspection', 'regulation', 'pricing', 'patent',
                               'manufacturing', 'quality', 'recall', 'safety']:
                        if kw.lower() in title.lower():
                            en_keywords[kw] += 1

        # --- Multilingual ---
        ml = get_data_safe(cats, 'multilingual')
        for label, items in ml.items():
            if isinstance(items, list):
                ml_count += len(items)
                lang_name = label.split('/')[1].strip() if '/' in label else label
                lang_hits[lang_name] += len(items)
                for item in items:
                    total_articles += 1
                    all_titles.append(item.get('title', ''))

    # ===== REPORT =====
    lines = []
    lines.append(f"# 🔬 PharmaScope — {period.capitalize()} 리포트 — {label}")
    lines.append(f"**기간:** {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}  |  ")
    lines.append(f"**수집일수:** {total_days}일  |  **총 기사:** {total_articles}건")
    lines.append("")

    # Overview
    lines.append("## 📈 개요")
    lines.append(f"- **파이프라인:** PharmaScope (의약스코프)")
    lines.append(f"- **기간:** {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    lines.append(f"- **수집 일수:** {total_days}일")
    lines.append(f"- **총 기사:** {total_articles}건")
    lines.append(f"- **한국어:** {kr_count}건 (5개 카테고리)")
    lines.append(f"- **영어권:** {en_count}건 (5개 카테고리)")
    lines.append(f"- **다국어:** {ml_count}건 (20개 언어)")
    lines.append(f"- **검색 언어:** 23개 (한국어+영어+20개)")
    lines.append("")

    # Korean category breakdown
    lines.append("## 🇰🇷 국내 카테고리별 분포")
    for cat in KR_CATEGORIES:
        cnt = kr_cat_counts.get(cat, 0)
        bar = '█' * min(cnt, 30) + (' ' * max(30 - min(cnt, 30), 0))
        lines.append(f"- {cat}: {cnt}건")
    lines.append(f"**합계: {kr_count}건**")
    lines.append("")

    # English category breakdown
    lines.append("## 🌐 글로벌 카테고리별 분포")
    for cat in EN_CATEGORIES:
        cnt = en_cat_counts.get(cat, 0)
        lines.append(f"- {cat}: {cnt}건")
    lines.append(f"**합계: {en_count}건**")
    lines.append("")

    # Top Korean keywords
    lines.append("## 🔑 국내 주요 키워드")
    for kw, count in kr_keywords.most_common(20):
        lines.append(f"- {kw}: {count}회")
    lines.append("")

    # Top English keywords
    lines.append("## 🔑 글로벌 주요 키워드")
    for kw, count in en_keywords.most_common(15):
        lines.append(f"- {kw}: {count}회")
    lines.append("")

    # Top sources
    if source_hits:
        lines.append("## 📰 주요 언론사")
        for src, count in source_hits.most_common(15):
            lines.append(f"- {src}: {count}건")
        lines.append("")

    # Language breakdown
    if lang_hits:
        lines.append("## 🌏 다국어 언어별 기사 수")
        for lang, count in lang_hits.most_common():
            lines.append(f"- {lang}: {count}건")
        lines.append("")

    # Dates covered
    lines.append("## 📅 수집 일자")
    lines.append(", ".join(dates_covered))
    lines.append("")

    # Trend analysis for monthly+
    if period in ('monthly', 'quarterly', 'yearly'):
        lines.append("## 📊 일별 기사 수 추이")
        current = start
        while current <= end:
            ds = current.strftime('%Y-%m-%d')
            day_data = load_daily_data(ds)
            count = 0
            if day_data:
                cats = get_data_safe(day_data, 'category')
                for lang_key in ['korean', 'english', 'multilingual']:
                    cat_dict = get_data_safe(cats, lang_key)
                    count += count_items(cat_dict)
            if count > 0:
                bar = '█' * min(count, 40)
                lines.append(f"- {ds}: {count}건 {bar}")
            current += timedelta(days=1)
        lines.append("")

    # Save
    report_content = '\n'.join(lines)
    report_path = os.path.join(output_dir, f'report_{period}_{folder_name}.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)

    # Stats JSON
    stats = {
        'pipeline': 'pharmascope',
        'period': period,
        'label': label,
        'folder': folder_name,
        'start': start.strftime('%Y-%m-%d'),
        'end': end.strftime('%Y-%m-%d'),
        'days_covered': total_days,
        'dates': dates_covered,
        'total_articles': total_articles,
        'korean': {'total': kr_count, 'categories': dict(kr_cat_counts.most_common())},
        'english': {'total': en_count, 'categories': dict(en_cat_counts.most_common())},
        'multilingual': {'total': ml_count, 'languages': dict(lang_hits.most_common())},
        'top_kr_keywords': kr_keywords.most_common(30),
        'top_en_keywords': en_keywords.most_common(20),
        'top_sources': source_hits.most_common(20),
    }
    stats_path = os.path.join(output_dir, f'stats_{period}_{folder_name}.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"✅ PharmaScope {period.capitalize()} report generated: {report_path}")
    print(f"   📅 {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')} ({total_days}일)")
    print(f"   📊 총 {total_articles}건 (🇰🇷{kr_count} / 🌐{en_count} / 🌏{ml_count})")
    print(f"   💾 저장: {output_dir}/")

    # Git commit
    git_commit(f"[PharmaScope] {period.capitalize()} 집계 — {label} — {total_articles}건 (🇰🇷{kr_count} / 🌐{en_count} / 🌏{ml_count})")

if __name__ == '__main__':
    period = sys.argv[1] if len(sys.argv) > 1 else 'weekly'
    anchor = None
    if len(sys.argv) > 2 and sys.argv[2].startswith('--date='):
        anchor = datetime.strptime(sys.argv[2].split('=')[1], '%Y-%m-%d').replace(tzinfo=KST)
    generate_aggregate_report(period, anchor)
