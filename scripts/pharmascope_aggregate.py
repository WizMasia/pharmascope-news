#!/usr/bin/env python3
"""
PharmaScope Aggregator v2 — daily_summary 기반 집계 + LLM 요약 리포트
========================================================================
주간/월간/분기/연간 집계 리포트 생성. daily_summary.json 활용.

Usage:
  python3 pharmascope_aggregate.py <period> [--date YYYY-MM-DD] [--summary-only]
    period: weekly|monthly|quarterly|yearly
    --date: 기준일 (기본: 오늘)
    --summary-only: LLM 요약 없이 통계 리포트만 생성 (크론 기본)

크론 프롬프트 (LLM 모드):
  Run the aggregate, then read the report and generate a Telegram summary
  using the top articles as source material.
"""
import json, os, sys, subprocess
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

BASE_DIR = os.path.expanduser("~/workspace/mywiki/news/pharmascope")
KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)

# ===== 키워드 목록 (daily_summary와 동일 유지) =====
PHARMA_KEYWORDS_KR = [
    '비만', 'GLP-1', '위고비', '마운자로', '오남용', 'GMP', '실사',
    '허가', '심사', '신약', '제네릭', '바이오시밀러', '약가', '급여',
    '한약', '생약', '천연물', '임상', 'ADC', '항암',
    'FDA', '식약처', 'MFDS', '원료의약품', '공급망',
    '백신', '특허', 'CRO', 'CDMO', 'R&D', '수출'
]
PHARMA_KEYWORDS_EN = [
    'GLP-1', 'obesity', 'FDA', 'GMP', 'shortage', 'biosimilar',
    'clinical trial', 'approval', 'generic', 'vaccine',
    'inspection', 'regulation', 'pricing', 'patent',
    'manufacturing', 'quality', 'recall', 'safety'
]

KR_CATEGORIES = ['의약품', '의약산업', '의약정책', '의약단체', '의약관련정부기관',
                 '의료현장', '약국·약사', '의료정책·인력', '전통의학', '감염·보건']
EN_CATEGORIES = ['Drugs & Therapies', 'Pharma Industry', 'Pharma Policy',
                 'Pharma Associations', 'Regulatory Agencies',
                 'Traditional & Complementary Medicine']

# ===== GIT =====
def git_commit(message):
    try:
        add = subprocess.run(['git', 'add', '-A'], cwd=BASE_DIR, capture_output=True, text=True, timeout=30)
        if add.returncode != 0:
            print(f"⚠️ git add failed: {add.stderr.strip()}")
            return
        diff = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=BASE_DIR, capture_output=True, timeout=30)
        if diff.returncode == 0:
            print("📎 No new changes to commit")
            return
        commit = subprocess.run(['git', 'commit', '-m', message], cwd=BASE_DIR,
                                capture_output=True, text=True, timeout=30)
        if commit.returncode == 0:
            print(f"✅ Git commit: {message[:60]}")
            push = subprocess.run(['git', 'push', 'origin', 'main', '--force'],
                                  cwd=BASE_DIR, capture_output=True, text=True, timeout=60)
            print(f"✅ Git push: {push.stdout.strip()[:100] if push.stdout else 'ok'}")
        else:
            print(f"⚠️ git commit: {commit.stderr.strip()}")
    except Exception as e:
        print(f"⚠️ Git error: {e}")

# ===== 날짜 범위 =====
def get_date_range(period, anchor=None):
    d = anchor or NOW
    if period == 'weekly':
        start = d - timedelta(days=d.weekday())
        end = start + timedelta(days=6)
        return start, end, f"Week {d.isocalendar()[1]}", d.strftime('%Y-W%W')
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

# ===== 데이터 로드 =====
def load_daily_summary(date_str):
    """daily_summary.json 우선, 없으면 raw.json fallback"""
    path = os.path.join(BASE_DIR, 'daily', date_str, 'daily_summary.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    # Fallback: raw.json에서 daily_summary 형식으로 변환
    raw_path = os.path.join(BASE_DIR, 'daily', date_str, 'raw.json')
    if os.path.exists(raw_path):
        return convert_raw_to_summary(raw_path, date_str)
    return None

def convert_raw_to_summary(raw_path, date_str):
    """raw.json → daily_summary.json 변환 (과거 데이터 호환용)"""
    with open(raw_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    stats = data.get('stats', {})
    total = stats.get('total', 0)
    categories = data.get('category', {})

    def count_keywords(titles, keywords):
        counts = {}
        for kw in keywords:
            cnt = sum(1 for t in titles if kw.lower() in t.lower())
            if cnt > 0:
                counts[kw] = cnt
        return sorted(counts.items(), key=lambda x: -x[1])[:20]

    def build_from_raw(lang_key, top_n, keywords):
        lang_data = categories.get(lang_key, {})
        total = sum(len(v) for v in lang_data.values() if isinstance(v, list))
        cat_counts = {k: len(v) for k, v in lang_data.items() if isinstance(v, list)}
        all_articles = []
        all_titles = []
        source_hits = Counter()
        for items in lang_data.values():
            if isinstance(items, list):
                for a in items:
                    all_articles.append(a)
                    all_titles.append(a.get('title', ''))
                    src = a.get('source', '')
                    if src:
                        source_hits[src] += 1
        sorted_a = sorted(all_articles, key=lambda x: x.get('importance', 0), reverse=True)
        top = [{
            'title': a.get('title', ''),
            'source': a.get('source', ''),
            'importance': a.get('importance', 0),
            'stars': a.get('stars', ''),
            'evidence': a.get('evidence', ''),
            'snippet': (a.get('snippet', '') or '')[:200],
            'time': a.get('time', ''),
            'url': a.get('url', ''),
        } for a in sorted_a[:top_n]]
        return {
            'total': total,
            'categories': cat_counts,
            'top_articles': top,
            'top_keywords': count_keywords(all_titles, keywords),
            'top_sources': sorted(source_hits.items(), key=lambda x: -x[1])[:15],
        }

    return {
        'date': date_str,
        'total': total,
        'version': 1,
        'generated_at': date_str,
        'korean': build_from_raw('korean', 10, PHARMA_KEYWORDS_KR),
        'english': build_from_raw('english', 10, PHARMA_KEYWORDS_EN),
        'multilingual': build_from_raw('multilingual', 5, []),
    }

# ===== 집계 =====
def merge_summaries(summaries):
    """여러 daily_summary를 병합 → 기간 통합 데이터"""
    merged = {
        'period': None,
        'dates_covered': [],
        'total_articles': 0,
        'total_days': 0,
        'korean': {'total': 0, 'categories': Counter(), 'top_articles': [],
                    'top_keywords': Counter(), 'top_sources': Counter()},
        'english': {'total': 0, 'categories': Counter(), 'top_articles': [],
                     'top_keywords': Counter(), 'top_sources': Counter()},
        'multilingual': {'total': 0, 'languages': Counter(), 'top_articles': [],
                          'top_keywords': Counter(), 'top_sources': Counter()},
    }
    for s in summaries:
        date = s.get('date', '')
        merged['dates_covered'].append(date)
        merged['total_articles'] += s.get('total', 0)
        merged['total_days'] += 1

        for lang in ['korean', 'english', 'multilingual']:
            ls = s.get(lang, {})
            merged[lang]['total'] += ls.get('total', 0)
            # Categories/languages
            for k, v in ls.get('categories', ls.get('languages', {})).items():
                merged[lang]['categories' if lang != 'multilingual' else 'languages'][k] += v
            # Top articles (collect all, will sort later)
            merged[lang]['top_articles'].extend(ls.get('top_articles', []))
            # Keywords
            for kw, cnt in ls.get('top_keywords', []):
                merged[lang]['top_keywords'][kw] += cnt
            # Sources
            for src, cnt in ls.get('top_sources', []):
                merged[lang]['top_sources'][src] += cnt

    # Sort top articles by importance across the period
    for lang in ['korean', 'english', 'multilingual']:
        merged[lang]['top_articles'] = sorted(
            merged[lang]['top_articles'],
            key=lambda x: x.get('importance', 0), reverse=True
        )[:20]  # Top 20 per language across the period

    # Sort keywords/sources
    for lang in ['korean', 'english', 'multilingual']:
        merged[lang]['top_keywords'] = sorted(
            merged[lang]['top_keywords'].items(),
            key=lambda x: -x[1]
        )[:30]
        merged[lang]['top_sources'] = sorted(
            merged[lang]['top_sources'].items(),
            key=lambda x: -x[1]
        )[:20]

    return merged

# ===== 리포트 생성 =====
def generate_report(merged, period, label, start, end, folder_name):
    """통계 기반 마크다운 리포트 생성"""
    dates_covered = merged['dates_covered']
    total_days = merged['total_days']
    total_all = merged['total_articles']

    kr = merged['korean']
    en = merged['english']
    ml = merged['multilingual']

    lines = []
    lines.append(f"# 🔬 PharmaScope — {period.capitalize()} 리포트 — {label}")
    lines.append(f"**기간:** {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    lines.append(f"**수집일수:** {total_days}일  |  **총 기사:** {total_all}건  |  **v2 집계 (daily_summary 기반)**")
    lines.append("")

    # === 개요 ===
    lines.append("## 📈 개요")
    lines.append(f"- **파이프라인:** PharmaScope (의약스코프) v3 Adapter Pattern")
    lines.append(f"- **기간:** {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    lines.append(f"- **수집일수:** {total_days}일")
    lines.append(f"- **총 기사:** {total_all}건")
    lines.append(f"- **한국어:** {kr['total']}건 (10개 카테고리)")
    lines.append(f"- **영어권:** {en['total']}건 (6개 카테고리)")
    lines.append(f"- **다국어:** {ml['total']}건 (20개 언어)")
    lines.append(f"- **일평균:** {total_all // max(total_days, 1)}건")
    lines.append("")

    # === 🇰🇷 국내 ===
    lines.append("## 🇰🇷 국내 카테고리별 분포 ({0}건)".format(kr['total']))
    for cat in KR_CATEGORIES:
        cnt = kr['categories'].get(cat, 0)
        pct = cnt * 100 // max(kr['total'], 1) if cnt else 0
        bar = '█' * min(cnt // 2 + 1, 30)
        lines.append(f"- {cat}: {cnt}건 ({pct}%) {bar}")
    lines.append(f"**합계: {kr['total']}건**")
    lines.append("")

    # === 🌐 영어 ===
    lines.append("## 🌐 글로벌 카테고리별 분포 ({0}건)".format(en['total']))
    for cat in EN_CATEGORIES:
        cnt = en['categories'].get(cat, 0)
        pct = cnt * 100 // max(en['total'], 1) if cnt else 0
        bar = '█' * min(cnt // 2 + 1, 20)
        lines.append(f"- {cat}: {cnt}건 ({pct}%) {bar}")
    lines.append(f"**합계: {en['total']}건**")
    lines.append("")

    # === 🔑 Top Keywords ===
    lines.append("## 🔑 주요 키워드")
    lines.append("### 🇰🇷 국내")
    for kw, cnt in kr['top_keywords'][:20]:
        lines.append(f"- **{kw}**: {cnt}회")
    lines.append("")
    lines.append("### 🌐 글로벌")
    for kw, cnt in en['top_keywords'][:15]:
        lines.append(f"- **{kw}**: {cnt}회")
    lines.append("")

    # === 📰 주요 언론사 ===
    lines.append("## 📰 주요 언론사")
    all_sources = Counter()
    for src, cnt in kr['top_sources']:
        all_sources[src] += cnt
    for src, cnt in en['top_sources']:
        all_sources[src] += cnt
    if all_sources:
        for src, cnt in all_sources.most_common(15):
            lines.append(f"- **{src}**: {cnt}건")
    else:
        lines.append("- _(데이터 없음)_")
    lines.append("")

    # === 🌏 다국어 ===
    if ml['languages']:
        lines.append("## 🌏 다국어 언어별 기사 수")
        for lang, cnt in sorted(ml['languages'].items(), key=lambda x: -x[1]):
            lines.append(f"- {lang}: {cnt}건")
        lines.append("")

    # === ⭐ 기간 내 중요도 Top 기사 ===
    lines.append("## ⭐ 기간 내 주요 기사 (Top 20)")
    all_top = sorted(kr['top_articles'][:10] + en['top_articles'][:10],
                     key=lambda x: x.get('importance', 0), reverse=True)
    for i, a in enumerate(all_top[:20], 1):
        imp = a.get('importance', 50)
        stars = a.get('stars', '⭐⭐⭐')
        src = a.get('source', '')
        title = a.get('title', '')
        snippet = (a.get('snippet', '') or '')[:100]
        lines.append(f"{i}. {stars} **[{imp}점]** {title}")
        lines.append(f"   📰 {src}")
        if snippet:
            lines.append(f"   💬 {snippet}")
    lines.append("")

    # === 📅 수집 일자 ===
    lines.append("## 📅 수집 일자")
    lines.append(", ".join(dates_covered))
    lines.append("")

    # === 📊 일별 추이 (월간+) ===
    if period in ('monthly', 'quarterly', 'yearly'):
        lines.append("## 📊 일별 기사 수 추이")
        current = start
        while current <= end:
            ds = current.strftime('%Y-%m-%d')
            day_data = None
            for s in summaries:
                if s.get('date') == ds:
                    day_data = s
                    break
            count = day_data.get('total', 0) if day_data else 0
            if count > 0:
                bar = '█' * min(count // 10 + 1, 40)
                lines.append(f"- {ds}: {count}건 {bar}")
            current += timedelta(days=1)
        lines.append("")

    # === 🤖 LLM 요약용 원시 데이터 ===
    lines.append("## 🤖 LLM 요약 데이터 (크론 전용)")
    lines.append("---")
    lines.append("### 기간 요약 (LLM 입력용)")
    lines.append("아래 데이터를 바탕으로 {period} {label} 의약업계 동향을 자연어로 요약하세요.".format(period=period, label=label))
    lines.append("")
    lines.append(f"기간: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    lines.append(f"총 {total_all}건 수집")
    lines.append(f"주요 국내 키워드: {', '.join(f'{kw}({cnt}회)' for kw, cnt in kr['top_keywords'][:10])}")
    lines.append(f"주요 글로벌 키워드: {', '.join(f'{kw}({cnt}회)' for kw, cnt in en['top_keywords'][:10])}")
    lines.append(f"주요 언론사: {', '.join(f'{src}({cnt}건)' for src, cnt in all_sources.most_common(10))}")
    lines.append("")
    lines.append("### 상위 5개 기사 (LLM 요약 재료)")
    for i, a in enumerate(all_top[:5], 1):
        lines.append(f"[{i}] {a.get('title', '')} — {a.get('source', '')} ({a.get('importance', 0)}점)")
        lines.append(f"    {a.get('url', '')}")
    lines.append("")

    report_content = '\n'.join(lines)
    output_dir = os.path.join(BASE_DIR, period, folder_name)
    os.makedirs(output_dir, exist_ok=True)

    report_path = os.path.join(output_dir, f'report_{period}_{folder_name}.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    print(f"✅ PharmaScope {period.capitalize()} report: {report_path}")

    # Stats JSON
    stats = {
        'pipeline': 'pharmascope-v2-aggregate',
        'period': period,
        'label': label,
        'folder': folder_name,
        'start': start.strftime('%Y-%m-%d'),
        'end': end.strftime('%Y-%m-%d'),
        'total_articles': total_all,
        'total_days': total_days,
        'dates_covered': dates_covered,
        'korean': {
            'total': kr['total'],
            'categories': dict(kr['categories'].most_common()),
            'top_keywords': kr['top_keywords'][:30],
        },
        'english': {
            'total': en['total'],
            'categories': dict(en['categories'].most_common()),
            'top_keywords': en['top_keywords'][:20],
        },
        'multilingual': {
            'total': ml['total'],
            'languages': dict(sorted(ml['languages'].items(), key=lambda x: -x[1])),
        },
    }
    stats_path = os.path.join(output_dir, f'stats_{period}_{folder_name}.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"✅ Stats saved: {stats_path}")

    print(f"   📅 {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')} ({total_days}일)")
    print(f"   📊 총 {total_all}건 (🇰🇷{kr['total']} / 🌐{en['total']} / 🌏{ml['total']})")
    print(f"   💾 {output_dir}/")
    return report_path, stats_path

# ===== 메인 =====
def generate_aggregate_report(period, anchor=None):
    start, end, label, folder_name = get_date_range(period, anchor)
    if not start:
        print(f"Unknown period: {period}")
        return

    # Load daily_summary.json files for the period
    global summaries
    summaries = []
    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        s = load_daily_summary(date_str)
        if s:
            summaries.append(s)
        current += timedelta(days=1)

    if not summaries:
        print(f"No data found for {period} {folder_name}")
        return

    merged = merge_summaries(summaries)
    report_path, stats_path = generate_report(merged, period, label, start, end, folder_name)

    # Git push
    total_all = merged['total_articles']
    kr_total = merged['korean']['total']
    en_total = merged['english']['total']
    ml_total = merged['multilingual']['total']
    git_commit(f"[PharmaScope] {period.capitalize()} 집계 v2 — {label} — {total_all}건 (🇰🇷{kr_total} / 🌐{en_total} / 🌏{ml_total})")

    # LLM 요약용 출력
    print("=" * 50)
    print(f"📋 LLM 요약용 데이터 (크론 프롬프트에서 활용)")
    print(f"기간: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
    print(f"총 {total_all}건")
    for lang, label_emoji in [('korean', '🇰🇷'), ('english', '🌐'), ('multilingual', '🌏')]:
        ls = merged[lang]
        kw_str = ', '.join(f'{kw}({cnt})' for kw, cnt in ls['top_keywords'][:5])
        print(f"{label_emoji} 주요 키워드: {kw_str}")
    print(f"📄 리포트: {report_path}")
    print("=" * 50)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    period = sys.argv[1]
    anchor = None
    summary_only = False

    for arg in sys.argv[2:]:
        if arg.startswith('--date='):
            anchor = datetime.strptime(arg.split('=', 1)[1], '%Y-%m-%d').replace(tzinfo=KST)
        elif arg == '--summary-only':
            summary_only = True

    generate_aggregate_report(period, anchor)
