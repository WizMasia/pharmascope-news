#!/usr/bin/env python3
"""
GMP News Aggregator — 주간/월간/분기/연간 뉴스 집계 리포트 생성
Usage: python3 aggregate.py <period> [--date YYYY-MM-DD]
  period: weekly|monthly|quarterly|yearly
"""

import json, os, sys, re
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

BASE_DIR = os.path.expanduser("~/workspace/idea/gmp-inspection-report/news")
NOW = datetime.now(timezone.utc)

def get_date_range(period, anchor=None):
    """Get start/end date range for period"""
    d = anchor or NOW
    
    if period == 'weekly':
        # Monday of current week
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

def load_daily_data(date_str):
    """Load raw.json for a specific date"""
    path = os.path.join(BASE_DIR, 'daily', date_str, 'raw.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def generate_aggregate_report(period, anchor=None):
    """Generate aggregate report for the given period"""
    start, end, label, folder_name = get_date_range(period, anchor)
    if not start:
        print(f"Unknown period: {period}")
        return
    
    output_dir = os.path.join(BASE_DIR, period, folder_name)
    os.makedirs(output_dir, exist_ok=True)
    
    # Collect all daily data in range
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
    
    # Aggregate stats
    total_articles = 0
    kr_count = 0
    en_count = 0
    ml_count = 0
    
    # Keyword tracking
    keyword_hits = Counter()
    source_hits = Counter()
    lang_hits = Counter()
    
    # Korean categories
    kr_categories = Counter()
    
    all_titles = []
    
    for data in daily_data:
        d = data.get('data', {})
        
        # Korean
        for label, items in d.get('korean', {}).items():
            kr_categories[label] += len(items)
            kr_count += len(items)
            for item in items:
                total_articles += 1
                title = item.get('title', '')
                all_titles.append(title)
                src = item.get('source', '') or (title.split(' - ')[-1] if ' - ' in title else '')
                if src:
                    source_hits[src] += 1
                # Track keywords
                for kw in ['비만', 'GLP-1', '위고비', '마운자로', '오남용', 'GMP', '허가', '240일',
                           '한약', '생약', '천연물', '바이오시밀러', 'ADC', '임상', 'FDA', '식약처',
                           '제네릭', '약가', '원료의약품', '공급망']:
                    if kw in title:
                        keyword_hits[kw] += 1
        
        # English
        for label, items in d.get('english', {}).items():
            en_count += len(items)
            for item in items:
                total_articles += 1
                title = item.get('title', '')
                all_titles.append(title)
                src = item.get('source', '')
                if src:
                    source_hits[src] += 1
                for kw in ['GLP-1', 'obesity', 'FDA', 'GMP', 'shortage', 'biosimilar',
                           'clinical trial', 'approval', 'generic']:
                    if kw.lower() in title.lower():
                        keyword_hits[kw] += 1
        
        # Multilingual
        for label, items in d.get('multilingual', {}).items():
            ml_count += len(items)
            lang_name = label.split('/')[1].strip() if '/' in label else label
            lang_hits[lang_name] += len(items)
            for item in items:
                total_articles += 1
                all_titles.append(item.get('title', ''))
    
    # Generate report
    lines = []
    lines.append(f"# 📊 GMP News {period.capitalize()} Report — {label}")
    lines.append(f"**기간:** {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}  |  ")
    lines.append(f"**수집일수:** {total_days}일  |  **총 기사:** {total_articles}건")
    lines.append("")
    
    # Overview
    lines.append("## 📈 개요")
    lines.append(f"| 항목 | 수치 |")
    lines.append(f"|------|------|")
    lines.append(f"| 수집 기간 | {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')} |")
    lines.append(f"| 수집 일수 | {total_days}일 |")
    lines.append(f"| 총 기사 수 | {total_articles}건 |")
    lines.append(f"| 한국어 뉴스 | {kr_count}건 |")
    lines.append(f"| 영어권 뉴스 | {en_count}건 |")
    lines.append(f"| 다국어 뉴스 (20개 언어) | {ml_count}건 |")
    lines.append(f"| 검색 언어 | 23개 (한국어+영어+20개) |")
    lines.append("")
    
    # Korean category breakdown
    lines.append("## 🇰🇷 국내 뉴스 분야별 분포")
    lines.append(f"| 분야 | 기사 수 |")
    lines.append(f"|------|--------|")
    for label, count in kr_categories.most_common():
        lines.append(f"| {label} | {count}건 |")
    lines.append("")
    
    # Top keywords
    lines.append("## 🔑 주요 키워드 순위")
    lines.append(f"| 키워드 | 언급 횟수 |")
    lines.append(f"|--------|----------|")
    for kw, count in keyword_hits.most_common(20):
        lines.append(f"| {kw} | {count}회 |")
    lines.append("")
    
    # Top sources
    lines.append("## 📰 주요 언론사 순위")
    lines.append(f"| 언론사 | 기사 수 |")
    lines.append(f"|--------|--------|")
    for src, count in source_hits.most_common(15):
        lines.append(f"| {src} | {count}건 |")
    lines.append("")
    
    # Multilingual language breakdown
    if lang_hits:
        lines.append("## 🌏 다국어 언어별 기사 수")
        lines.append(f"| 언어 | 기사 수 |")
        lines.append(f"|------|--------|")
        for lang, count in lang_hits.most_common():
            lines.append(f"| {lang} | {count}건 |")
        lines.append("")
    
    # Dates covered
    lines.append("## 📅 수집 일자")
    lines.append(", ".join(dates_covered))
    lines.append("")
    
    # Trend analysis
    lines.append("## 📊 기간 내 트렌드 분석")
    
    # Identify top trends
    top_keywords = [kw for kw, _ in keyword_hits.most_common(5)]
    lines.append(f"### 주요 화제 키워드: {', '.join(top_keywords)}")
    lines.append("")
    
    # Month-over-month comparisons for monthly+
    if period in ('monthly', 'quarterly', 'yearly'):
        # Daily article count trend
        lines.append("### 일별 기사 수 추이")
        day_counts = []
        current = start
        while current <= end:
            ds = current.strftime('%Y-%m-%d')
            day_data = load_daily_data(ds)
            count = 0
            if day_data:
                d = day_data.get('data', {})
                for cat in ['korean', 'english', 'multilingual']:
                    for items in d.get(cat, {}).values():
                        count += len(items)
            day_counts.append((ds, count))
            current += timedelta(days=1)
        
        lines.append("| 일자 | 기사 수 |")
        lines.append("|------|--------|")
        for ds, cnt in day_counts:
            if cnt > 0:
                lines.append(f"| {ds} | {cnt}건 |")
        lines.append("")
    
    # Save report
    report_content = '\n'.join(lines)
    report_path = os.path.join(output_dir, f'report_{period}_{folder_name}.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    # Save stats JSON
    stats = {
        'period': period,
        'label': label,
        'folder': folder_name,
        'start': start.strftime('%Y-%m-%d'),
        'end': end.strftime('%Y-%m-%d'),
        'days_covered': total_days,
        'dates': dates_covered,
        'total_articles': total_articles,
        'korean': kr_count,
        'english': en_count,
        'multilingual': ml_count,
        'top_keywords': keyword_hits.most_common(30),
        'top_sources': source_hits.most_common(20),
    }
    stats_path = os.path.join(output_dir, f'stats_{period}_{folder_name}.json')
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ {period.capitalize()} report generated: {report_path}")
    print(f"   기간: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')} ({total_days}일)")
    print(f"   총 {total_articles}건 (한국어 {kr_count}건, 영어 {en_count}건, 다국어 {ml_count}건)")
    print(f"   저장: {output_dir}/")

if __name__ == '__main__':
    period = sys.argv[1] if len(sys.argv) > 1 else 'weekly'
    anchor = None
    if len(sys.argv) > 2 and sys.argv[2].startswith('--date='):
        anchor = datetime.strptime(sys.argv[2].split('=')[1], '%Y-%m-%d').replace(tzinfo=timezone.utc)
    
    generate_aggregate_report(period, anchor)
