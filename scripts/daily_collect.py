#!/usr/bin/env python3
"""
GMP News Daily Collector — 매일 의약품·한약·생약 글로벌 뉴스 수집
- 24시간 이내 기사만 검색 (Google News RSS)
- 한국어 + 영어 + 20개 다국어 (총 23개 언어)
- JSON raw data + 요약 리포트 저장
"""

import urllib.parse, subprocess, json, re, os, sys
from html import unescape
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# ===== CONFIG =====
BASE_DIR = os.path.expanduser("~/workspace/idea/gmp-inspection-report/news")
NOW = datetime.now(timezone.utc)
YESTERDAY = NOW - timedelta(hours=24)
DATE_FILTER = YESTERDAY.strftime('%Y-%m-%d')
DATE_STR = NOW.strftime('%Y-%m-%d')
# Daily output dir
DAILY_DIR = os.path.join(BASE_DIR, 'daily', DATE_STR)

# ===== SEARCH FUNCTION =====
def search_google_news_rss(query, gl='US', hl='en', max_items=8):
    """Search Google News RSS with region/language"""
    quoted = urllib.parse.quote(query + f' after:{DATE_FILTER}')
    url = f'https://news.google.com/rss/search?q={quoted}&hl={hl}&gl={gl}&ceid={gl}:{hl[:2]}'
    
    cmd = [
        'curl', '-sL', '--max-time', '15', url,
        '-H', 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    content = r.stdout
    
    items = re.findall(r'<item>(.*?)</item>', content, re.DOTALL)
    results = []
    
    for item in items:
        title_m = re.search(r'<title>(.*?)</title>', item)
        link_m = re.search(r'<link>(.*?)</link>', item)
        source_m = re.search(r'<source>(.*?)</source>', item)
        date_m = re.search(r'<pubDate>(.*?)</pubDate>', item)
        snippet_m = re.search(r'<description>(.*?)(?:\[\.\.\.\]|\.\.\.|<\/a>|$)', item, re.DOTALL)
        
        if title_m and link_m:
            title = unescape(re.sub(r'<[^>]+>', '', title_m.group(1))).strip()
            url = link_m.group(1).strip()
            
            snippet = ''
            if snippet_m:
                snip = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip()
                snippet = unescape(snip)[:200]
            
            results.append({
                'title': title,
                'url': url,
                'source': unescape(source_m.group(1)).strip() if source_m else '',
                'date': date_m.group(1) if date_m else '',
                'snippet': snippet,
            })
            
            if len(results) >= max_items:
                break
    
    return results

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ===== SEARCH CONFIGURATIONS =====
log(f"Starting daily news collection for {DATE_STR} (filter: since {DATE_FILTER})")

all_data = {}

# 1. KOREAN
log("=== 국내 뉴스 (한국어) ===")
kr_queries = [
    ('의약품', 'Pharmaceutical'),
    ('한약 생약', 'Herbal Medicine'),
    ('식약처 GMP', 'MFDS GMP'),
    ('제약바이오', 'Pharma Bio'),
]
kr_results = {}
for q, label in kr_queries:
    results = search_google_news_rss(q, gl='KR', hl='ko', max_items=8)
    kr_results[label] = results
    log(f"  [{label}] {len(results)}건")
all_data['korean'] = kr_results

# 2. ENGLISH
log("=== 영어권 뉴스 ===")
en_configs = [
    ('pharmaceutical drug approval regulation', 'US', 'en', 'USA'),
    ('pharmaceutical GMP manufacturing quality', 'US', 'en', 'USA - GMP'),
    ('FDA drug news pharmaceutical industry', 'GB', 'en', 'FDA/UK/Europe'),
    ('herbal medicine natural remedy clinical', 'AU', 'en', 'Herbal/Natural'),
    ('generic drug pharma clinical trial', 'IN', 'en', 'India/Clinical'),
]
en_results = {}
for q, gl, hl, label in en_configs:
    results = search_google_news_rss(q, gl=gl, hl=hl, max_items=5)
    en_results[label] = results
    log(f"  [{label}] {len(results)}건")
all_data['english'] = en_results

# 3. MULTILINGUAL
log("=== 다국어 뉴스 (20개 언어) ===")
lang_configs = [
    ('pharmacie médicament', 'FR', 'fr', 'French / 프랑스어'),
    ('Arzneimittel Pharmazie', 'DE', 'de', 'German / 독일어'),
    ('farmacia medicamentos', 'ES', 'es', 'Spanish / 스페인어'),
    ('farmaci medicinali', 'IT', 'it', 'Italian / 이탈리아어'),
    ('farmácia medicamentos', 'BR', 'pt', 'Portuguese / 포르투갈어'),
    ('geneesmiddel farmacie', 'NL', 'nl', 'Dutch / 네덜란드어'),
    ('läkemedel apotek', 'SE', 'sv', 'Swedish / 스웨덴어'),
    ('leki farmacja', 'PL', 'pl', 'Polish / 폴란드어'),
    ('ilac eczane', 'TR', 'tr', 'Turkish / 터키어'),
    ('фармацевтика лекарства', 'RU', 'ru', 'Russian / 러시아어'),
    ('医薬品 薬 ニュース', 'JP', 'ja', 'Japanese / 일본어'),
    ('药品 制药 新闻', 'CN', 'zh-cn', 'Chinese (Simplified) / 중국어'),
    ('藥物 藥品 新聞', 'TW', 'zh-tw', 'Chinese (Traditional) / 대만'),
    ('dược phẩm thuốc', 'VN', 'vi', 'Vietnamese / 베트남어'),
    ('ยา เภสัชกรรม', 'TH', 'th', 'Thai / 태국어'),
    ('obat farmasi', 'ID', 'id', 'Indonesian / 인도네시아어'),
    ('दवा फार्मेसी', 'IN', 'hi', 'Hindi / 힌디어'),
    ('الصيدلة الأدوية', 'SA', 'ar', 'Arabic / 아랍어'),
    ('תרופות רפואה', 'IL', 'iw', 'Hebrew / 히브리어'),
    ('دارو داروسازی', 'AE', 'fa', 'Persian / 페르시아어'),
]
ml_results = {}
for q, gl, hl, label in lang_configs:
    results = search_google_news_rss(q, gl=gl, hl=hl, max_items=3)
    ml_results[label] = results
    log(f"  [{label}] {len(results)}건")
all_data['multilingual'] = ml_results

# ===== SAVE RAW DATA =====
os.makedirs(DAILY_DIR, exist_ok=True)
raw_path = os.path.join(DAILY_DIR, 'raw.json')
with open(raw_path, 'w', encoding='utf-8') as f:
    json.dump({
        'collection_date': DATE_STR,
        'date_filter': DATE_FILTER,
        'collected_at': NOW.isoformat(),
        'data': all_data,
        'stats': {
            'korean': sum(len(v) for v in kr_results.values()),
            'english': sum(len(v) for v in en_results.values()),
            'multilingual': sum(len(v) for v in ml_results.values()),
            'total_languages': 23,
        }
    }, f, ensure_ascii=False, indent=2)

# ===== GENERATE SUMMARY REPORT =====
total = sum(len(v) for v in kr_results.values()) + sum(len(v) for v in en_results.values()) + sum(len(v) for v in ml_results.values())
lines = []
lines.append(f"# 📰 글로벌 의약품·한약·생약 뉴스 일일 리포트")
lines.append(f"**수집일:** {DATE_STR}  |  **필터:** 24시간 이내  |  **검색 언어:** 23개  |  **총 {total}건**")
lines.append("")

# Korean summary
lines.append("## 🇰🇷 국내 뉴스")
for label, items in kr_results.items():
    if items:
        lines.append(f"\n### {label}")
        for i, item in enumerate(items[:6], 1):
            t = item['title'].split(' - ')[0].strip() if ' - ' in item['title'] else item['title']
            lines.append(f"{i}. {t}")
            lines.append(f"   📰 {item.get('source','')} | 🕐 {item.get('date','')[:25]}")
            lines.append(f"   🔗 {item['url']}")

# English summary
lines.append("\n## 🇺🇸🇬🇧 영어권 뉴스")
for label, items in en_results.items():
    if items:
        lines.append(f"\n### {label}")
        for item in items[:4]:
            lines.append(f"- {item['title'][:90]}")
            lines.append(f"  📰 {item.get('source','')} | 🕐 {item.get('date','')[:25]}")
            lines.append(f"  🔗 {item['url']}")

# Multilingual
lines.append("\n## 🌏 다국어 뉴스 (20개 언어)")
lines.append("| 언어 | 건수 | 주요 기사 |")
lines.append("|------|------|----------|")
for label, items in ml_results.items():
    first_title = items[0]['title'][:50] if items else '-'
    lines.append(f"| {label} | {len(items)}건 | {first_title} |")

# Stats
lines.append(f"\n## 📊 수집 통계")
lines.append(f"- 한국어: {sum(len(v) for v in kr_results.values())}건")
lines.append(f"- 영어권: {sum(len(v) for v in en_results.values())}건")
lines.append(f"- 다국어 (20개 언어): {sum(len(v) for v in ml_results.values())}건")
lines.append(f"- **총계: {total}건**")
lines.append(f"- 저장 위치: `{DAILY_DIR}/`")

report_content = '\n'.join(lines)

report_path = os.path.join(DAILY_DIR, 'report.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report_content)

log(f"✅ 저장 완료: {DAILY_DIR}/")
log(f"   - raw.json ({os.path.getsize(raw_path)} bytes)")
log(f"   - report.md")

# Print summary for cron output
print(f"\n{'='*60}")
print(f"  📰 GMP NEWS DAILY REPORT — {DATE_STR}")
print(f"  총 {total}건 수집 (한국어 {sum(len(v) for v in kr_results.values())}건 + 영어 {sum(len(v) for v in en_results.values())}건 + 다국어 {sum(len(v) for v in ml_results.values())}건)")
print(f"  저장: {DAILY_DIR}/")
print(f"{'='*60}")
