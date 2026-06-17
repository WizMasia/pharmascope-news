#!/usr/bin/env python3
"""
PharmaScope (의약스코프) — 글로벌 의약업계·의료현장 동향 수집기
========================================================
10개 카테고리 × 23개 언어 확장 검색

카테고리:
  1. 의약품 (Drugs & Therapies)
  2. 의약산업 (Pharma Industry)
  3. 의약정책 (Pharma Policy)
  4. 의약단체 (Pharma Associations)
  5. 의약관련정부기관 (Regulatory Agencies)
  6. 의료현장 (Clinical Practice)
  7. 약국·약사 (Pharmacy)
  8. 의료정책·인력 (Healthcare Policy & Workforce)
  9. 전통의학 (Traditional Medicine)
  10. 감염·보건 (Infection & Public Health)
  + English: Traditional & Complementary Medicine
"""
import urllib.parse, urllib.request, subprocess, json, re, os, sys
from html import unescape
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# ===== Import Hermes 공용 도구 =====
_HERMES_SCRIPTS = os.path.expanduser("~/.hermes/scripts")
if _HERMES_SCRIPTS not in sys.path:
    sys.path.insert(0, _HERMES_SCRIPTS)
try:
    from shorten_url import shorten_one, set_enabled
except ImportError:
    # Fallback: standalone 함수 (모듈 없을 때)
    import urllib.request as _ur
    _FALLBACK_CACHE = {}
    def shorten_one(url):
        if url in _FALLBACK_CACHE:
            return _FALLBACK_CACHE[url]
        try:
            p = urllib.parse.urlencode({"url": url})
            req = urllib.request.Request(f"https://tinyurl.com/api-create.php?{p}",
                headers={"User-Agent": "Mozilla/5.0 (pharmascope)"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                short = resp.read().decode().strip()
                if short and short.startswith("http"):
                    _FALLBACK_CACHE[url] = short
                    return short
        except Exception:
            pass
        _FALLBACK_CACHE[url] = url
        return url
    def set_enabled(state): pass

# ===== URL SHORTENER CONFIG (via ~/.hermes/scripts/shorten_url.py) =====
SHORTEN_URLS = True          # False = disable URL shortening
if not SHORTEN_URLS:
    set_enabled(False)

# ===== GIT CONFIG =====
MYWIKI_DIR = os.path.expanduser("~/workspace/mywiki")

def git_commit(message):
    """Commit and push changes to mywiki git repo."""
    try:
        add = subprocess.run(['git', 'add', '-A'], cwd=MYWIKI_DIR, capture_output=True, text=True, timeout=30)
        if add.returncode != 0:
            log(f"⚠️ git add failed: {add.stderr.strip()}")
            return
        # Only commit if there are staged changes
        diff = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=MYWIKI_DIR, capture_output=True, timeout=30)
        if diff.returncode == 0:
            log("📎 No new changes to commit")
            return
        commit = subprocess.run(['git', 'commit', '-m', message], cwd=MYWIKI_DIR, capture_output=True, text=True, timeout=30)
        if commit.returncode == 0:
            log(f"✅ Git commit: {commit.stdout.strip()}")
            push = subprocess.run(['git', 'push', 'origin', 'main', '--force'], cwd=MYWIKI_DIR, capture_output=True, text=True, timeout=30)
            if push.returncode == 0:
                log(f"✅ Git push: {push.stdout.strip()}")
            else:
                log(f"⚠️ git push: {push.stderr.strip()}")
        else:
            log(f"⚠️ git commit: {commit.stderr.strip()}")
    except Exception as e:
        log(f"⚠️ Git error: {e}")

# ===== CONFIG =====
BASE_DIR = os.path.expanduser("~/workspace/mywiki/news/pharmascope")
KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
YESTERDAY = NOW - timedelta(hours=24)
DATE_FILTER = YESTERDAY.strftime('%Y-%m-%d')
DATE_STR = NOW.strftime('%Y-%m-%d')
DAILY_DIR = os.path.join(BASE_DIR, 'daily', DATE_STR)

# ===== ASSOCIATION MEDIA (협회 발행 언론 — 직역 대표성 바이어스 있음) =====
ASSOCIATION_MEDIA = [
    '약사공론',         # 대한약사회
    '의협신문',         # 대한의사협회
    '한의신문',         # 대한한의사협회
    '메디팜투데이',     # 약사
    '데일리팜',         # 약사
    '팜뉴스',          # 약사
    '메디칼타임즈',     # 의사
    '메디파나뉴스',     # 의사
    '닥터스뉴스',       # 의사
    '치협신문',         # 대한치과의사협회
    '간협신문',         # 대한간호협회
]

def is_association_media(source):
    """Check if source is an association-affiliated publication."""
    if not source:
        return False
    source_lower = source.lower()
    for name in ASSOCIATION_MEDIA:
        if name.lower() in source_lower:
            return True
    return False


# ===== SEARCH FUNCTION =====
def search_google_news_rss(query, gl='US', hl='en', max_items=4):
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
                'association_media': is_association_media(
                    unescape(source_m.group(1)).strip() if source_m else ''
                ),
            })
            if len(results) >= max_items:
                break
    return results

def search_multi(keywords, gl, hl, label, max_items=4):
    """Search multiple keywords under one label, deduplicate."""
    seen_titles = set()
    combined = []
    for kw in keywords:
        results = search_google_news_rss(kw, gl=gl, hl=hl, max_items=max_items)
        for r in results:
            title_key = r['title'][:60]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                combined.append(r)
        if len(combined) >= max_items * 2:
            break
    return combined[:max_items * 2]

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

log(f"🚀 PharmaScope collection started — {DATE_STR} (filter: since {DATE_FILTER})")

all_data = {'category': {}, '_meta': {
    'pipeline': 'pharmascope',
    'version': '1.0.0',
    'collection_date': DATE_STR,
    'collected_at': NOW.isoformat(),
}}

# =======================================================================
# 1. 🇰🇷 KOREAN — 11 categories × multiple keywords
# =======================================================================
log("="*50)
log("🇰🇷 국내 뉴스 (한국어, 11개 카테고리)")

kr_categories = {
    '의약품': {
        'keywords': [
            '의약품 치료제 신약',
            '의약품허가 품목허가 신약승인',
            '제네릭 바이오시밀러 복제약',
            '백신 항암제 희귀의약품',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
    '의약산업': {
        'keywords': [
            '제약산업 제약바이오 제약사',
            '의약품시장 제약매출 의약품수출',
            '제약R&D 신약개발투자 임상시험',
            '바이오텍 CRO CDMO 위탁생산',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
    '의약정책': {
        'keywords': [
            '의약품정책 약가 약가인하 약가제도',
            '건강보험 보험급여 약제급여',
            '의약품규제 약사법 의약품법',
            '의약품특허 자료보호 의약품허가특허',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
    '의약단체': {
        'keywords': [
            '한국제약바이오협회 KPBMA',
            '한국다국적의약산업협회 KRPIA',
            '대한약사회 한국약사회 약사',
            '제약단체 의약단체 제약협회',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
    '의약관련정부기관': {
        'keywords': [
            '식약처 MFDS 식품의약품안전처',
            '의약품안전 의약품심사 GMP 실사',
            '의약품부작용 의약품안전정보',
            '의약품수거 의약품회수 식약처조사',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
    # --- 신규: 의료현장 ---
    '의료현장': {
        'keywords': [
            '의료현장 병원경영 진료과목 임상현장',
            '의료사고 의료분쟁 의료소송',
            '전공의 수련 전문의 인증',
            '의료질 환자경험 의료서비스',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
    # --- 신규: 약국·약사 ---
    '약국·약사': {
        'keywords': [
            '약국운영 조제실 일반의약품',
            '복약지도 의약품안전사용 DUR',
            '약사면허 약사교육 약사직능',
            '약국경영 지역약국 체인약국',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
    # --- 신규: 의료정책·인력 ---
    '의료정책·인력': {
        'keywords': [
            '의료개혁 필수의료 의료체계',
            '의사인력 전공의 정원 간호사',
            '의료법 의료제도 건강보험',
            '원격의료 의료인력수급',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
    # --- 신규: 전통의학 ---
    '전통의학': {
        'keywords': [
            '한의사 한의원 한약 한방치료',
            '침술 약침 추나 한의학임상',
            '한의약정책 한약재 한의학연구',
            '한방산업 한의사면허 한의보험',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
    # --- 신규: 감염·보건 ---
    '감염·보건': {
        'keywords': [
            '감염병 항생제내성 감염관리',
            '예방접종 국가예방접종',
            '공중보건 보건복지 지역보건',
            '환자안전 의료감염 손위생',
        ],
        'gl': 'KR', 'hl': 'ko',
    },
}

kr_data = {}
for cat_name, cfg in kr_categories.items():
    results = search_multi(cfg['keywords'], cfg['gl'], cfg['hl'], cat_name, max_items=4)
    kr_data[cat_name] = results
    log(f"  [{cat_name}] {len(results)}건")

all_data['category']['korean'] = kr_data

# =======================================================================
# 2. 🇺🇸🇬🇧 ENGLISH — 6 categories × multiple keywords
# =======================================================================
log("="*50)
log("🇺🇸🇬🇧 영어권 뉴스 (6개 카테고리)")

en_categories = {
    'Drugs & Therapies': {
        'keywords': [
            'drug approval new drug therapy pharmaceutical',
            'generic drug biosimilar vaccine development',
            'oncology drug rare disease treatment',
            'antibiotic clinical trial drug discovery',
        ],
        'gl': 'US', 'hl': 'en',
    },
    'Pharma Industry': {
        'keywords': [
            'pharmaceutical industry biotech company',
            'pharma market drug development investment',
            'clinical trial CRO CDMO drug manufacturing',
            'pharma R&D drug sales pharma partnership',
        ],
        'gl': 'US', 'hl': 'en',
    },
    'Pharma Policy': {
        'keywords': [
            'drug pricing pharmaceutical policy reform',
            'drug reimbursement health insurance drug',
            'pharmaceutical regulation patent drug',
            'Inflation Reduction Act drug price negotiation',
        ],
        'gl': 'US', 'hl': 'en',
    },
    'Pharma Associations': {
        'keywords': [
            'PhRMA pharmaceutical association',
            'EFPIA International pharma federation',
            'industry group pharmaceutical manufacturers',
            'pharma trade association drug industry group',
        ],
        'gl': 'US', 'hl': 'en',
    },
    'Regulatory Agencies': {
        'keywords': [
            'FDA regulation drug approval regulatory',
            'EMA approval MHRA drug safety authority',
            'GMP inspection pharmaceutical compliance',
            'drug recall safety warning regulatory action',
        ],
        'gl': 'GB', 'hl': 'en',
    },
    # --- 신규: Traditional & Alternative Medicine ---
    'Traditional & Complementary Medicine': {
        'keywords': [
            'traditional medicine herbal remedy natural',
            'Ayurveda Unani Siddha traditional Indian medicine',
            'Kampo traditional Chinese medicine TCM acupuncture',
            'Sowa-Rigpa Tibetan medicine complementary medicine',
        ],
        'gl': 'US', 'hl': 'en',
    },
}

en_data = {}
for cat_name, cfg in en_categories.items():
    results = search_multi(cfg['keywords'], cfg['gl'], cfg['hl'], cat_name, max_items=4)
    en_data[cat_name] = results
    log(f"  [{cat_name}] {len(results)}건")

all_data['category']['english'] = en_data

# =======================================================================
# 3. 🌏 MULTILINGUAL — 20 languages
# =======================================================================
log("="*50)
log("🌏 다국어 뉴스 (20개 언어)")

# Combined keyword sets per language group for broader coverage
lang_configs = [
    # European — pharma
    (['médicament pharmacie industrie pharmaceutique', 'médecine traditionnelle phytothérapie'], 'FR', 'fr', 'French / 프랑스어'),
    (['Arzneimittel Pharmaindustrie Medikamentenzulassung', 'traditionelle Medizin Naturheilkunde'], 'DE', 'de', 'German / 독일어'),
    (['medicamento farmacia industria farmacéutica', 'medicina tradicional fitoterapia'], 'ES', 'es', 'Spanish / 스페인어'),
    (['farmaco medicinali industria farmaceutica', 'medicina tradizionale fitoterapia'], 'IT', 'it', 'Italian / 이탈리아어'),
    (['medicamento farmácia indústria farmacêutica', 'medicina tradicional fitoterapia'], 'BR', 'pt', 'Portuguese / 포르투갈어'),
    (['geneesmiddel farmaceutische industrie', 'traditionele geneeskunde fytotherapie'], 'NL', 'nl', 'Dutch / 네덜란드어'),
    (['läkemedel läkemedelsindustri', 'traditionell medicin naturläkemedel'], 'SE', 'sv', 'Swedish / 스웨덴어'),
    (['leki przemysł farmaceutyczny', 'medycyna tradycyjna ziołolecznictwo'], 'PL', 'pl', 'Polish / 폴란드어'),
    (['ilaç ecza ilaç endüstrisi', 'geleneksel tıp bitkisel ilaç'], 'TR', 'tr', 'Turkish / 터키어'),
    # Eastern
    (['фармацевтика лекарственные препараты', 'традиционная медицина фитотерапия'], 'RU', 'ru', 'Russian / 러시아어'),
    # East Asian
    (['医薬品 製薬 薬事 ニュース', '漢方 Kampo 漢方薬 東洋医学'], 'JP', 'ja', 'Japanese / 일본어'),
    (['药品 制药 医药 新闻 政策', '中医 中药 传统医学 中西医结合'], 'CN', 'zh-cn', 'Chinese Simplified / 중국어'),
    (['藥物 藥品 製藥 醫藥 政策', '中醫 中藥 傳統醫學 針灸'], 'TW', 'zh-tw', 'Chinese Traditional / 대만'),
    # Southeast Asian
    (['dược phẩm thuốc ngành dược', 'y học cổ truyền thuốc nam'], 'VN', 'vi', 'Vietnamese / 베트남어'),
    (['ยา อุตสาหกรรมยา เภสัชกรรม', 'การแพทย์แผนไทย สมุนไพร'], 'TH', 'th', 'Thai / 태국어'),
    (['obat farmasi industri farmasi', 'pengobatan tradisional jamu herbal'], 'ID', 'id', 'Indonesian / 인도네시아어'),
    # South Asian
    (['दवा फार्मास्युटिकल उद्योग', 'आयुर्वेद योग प्राकृतिक चिकित्सा यूनानी सिद्ध'], 'IN', 'hi', 'Hindi / 힌디어'),
    # Middle Eastern
    (['صناعة الأدوية المستحضرات الصيدلانية', 'الطب التقليدي الأعشاب الطبية'], 'SA', 'ar', 'Arabic / 아랍어'),
    (['תרופות תעשיית התרופות', 'רפואה מסורתית צמחי מרפא'], 'IL', 'iw', 'Hebrew / 히브리어'),
    (['دارو صنعت داروسازی', 'طب سنتی گیاهان دارویی'], 'AE', 'fa', 'Persian / 페르시아어'),
]

ml_data = {}
for keywords, gl, hl, label in lang_configs:
    results = search_multi(keywords, gl, hl, label, max_items=3)
    ml_data[label] = results
    log(f"  [{label}] {len(results)}건")

all_data['category']['multilingual'] = ml_data

# =======================================================================
# STATS
# =======================================================================
kr_total = sum(len(v) for v in kr_data.values())
en_total = sum(len(v) for v in en_data.values())
ml_total = sum(len(v) for v in ml_data.values())
total_all = kr_total + en_total + ml_total

stats = {
    'korean': {'total': kr_total, 'categories': {k: len(v) for k, v in kr_data.items()}},
    'english': {'total': en_total, 'categories': {k: len(v) for k, v in en_data.items()}},
    'multilingual': {'total': ml_total, 'languages': {k: len(v) for k, v in ml_data.items()}},
    'total': total_all,
    'total_languages_covered': 23,
}
all_data['stats'] = stats

# =======================================================================
# SAVE RAW DATA
# =======================================================================
os.makedirs(DAILY_DIR, exist_ok=True)
raw_path = os.path.join(DAILY_DIR, 'raw.json')
with open(raw_path, 'w', encoding='utf-8') as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)

# =======================================================================
# GENERATE REPORT
# =======================================================================
lines = []
lines.append(f"# 🔬 PharmaScope — 글로벌 의약업계 동향 일일 리포트")
lines.append(f"**수집일:** {DATE_STR}  |  **필터:** 24시간 이내  |  **10개 카테고리 × 23개 언어**  |  **총 {total_all}건**")
lines.append("")

# --- Korean ---
lines.append("## 🇰🇷 국내 (한국어)")
for cat_name, items in kr_data.items():
    if items:
        # Category emoji
        cat_emoji = {'의약품': '💊', '의약산업': '🏭', '의약정책': '📋', '의약단체': '🤝',
                      '의약관련정부기관': '🏛️', '의료현장': '🏥', '약국·약사': '💊',
                      '의료정책·인력': '🩺', '전통의학': '🌿', '감염·보건': '🔬'}
        emoji = cat_emoji.get(cat_name, '📌')
        lines.append(f"\n### {emoji} {cat_name}")
        for i, item in enumerate(items[:5], 1):
            t = item['title'].split(' - ')[0].strip() if ' - ' in item['title'] else item['title']
            assn_tag = ' *(협회지)*' if item.get('association_media') else ''
            lines.append(f"{i}. {t}{assn_tag}")
            lines.append(f"   📰 {item.get('source','')} | 🕐 {item.get('date','')[:25]}")
            if item.get('snippet'):
                lines.append(f"   💬 {item['snippet'][:100]}")
            lines.append(f"   🔗 {shorten_one(item['url'])}")
    else:
        lines.append(f"\n### {cat_name}")
        lines.append("- _(수집된 뉴스 없음)_")

# --- English ---
lines.append("\n---")
lines.append("## 🌐 글로벌 (영어)")
en_emoji = {'Drugs & Therapies': '💊', 'Pharma Industry': '🏭', 'Pharma Policy': '📋',
             'Pharma Associations': '🤝', 'Regulatory Agencies': '🏛️',
             'Traditional & Complementary Medicine': '🌿'}
for cat_name, items in en_data.items():
    if items:
        emoji = en_emoji.get(cat_name, '📌')
        lines.append(f"\n### {emoji} {cat_name}")
        for item in items[:4]:
            lines.append(f"- {item['title'][:100]}")
            lines.append(f"  📰 {item.get('source','')} | 🕐 {item.get('date','')[:25]}")
            lines.append(f"  🔗 {shorten_one(item['url'])}")
    else:
        lines.append(f"\n### {cat_name}")
        lines.append("- _(No news collected)_")

# --- Multilingual ---
lines.append("\n---")
lines.append("## 🌏 다국어 뉴스 (20개 언어)")
for label, items in ml_data.items():
    if items:
        lang_emoji = {'French / 프랑스어': '🇫🇷', 'German / 독일어': '🇩🇪', 'Spanish / 스페인어': '🇪🇸',
                      'Italian / 이탈리아어': '🇮🇹', 'Portuguese / 포르투갈어': '🇵🇹',
                      'Dutch / 네덜란드어': '🇳🇱', 'Swedish / 스웨덴어': '🇸🇪',
                      'Polish / 폴란드어': '🇵🇱', 'Turkish / 터키어': '🇹🇷',
                      'Russian / 러시아어': '🇷🇺', 'Japanese / 일본어': '🇯🇵',
                      'Chinese Simplified / 중국어': '🇨🇳', 'Chinese Traditional / 대만': '🇹🇼',
                      'Vietnamese / 베트남어': '🇻🇳', 'Thai / 태국어': '🇹🇭',
                      'Indonesian / 인도네시아어': '🇮🇩', 'Hindi / 힌디어': '🇮🇳',
                      'Arabic / 아랍어': '🇸🇦', 'Hebrew / 히브리어': '🇮🇱',
                      'Persian / 페르시아어': '🇮🇷'}
        emoji = lang_emoji.get(label, '🌏')
        lines.append(f"\n### {emoji} {label} ({len(items)}건)")
        for item in items[:3]:  # 최대 3개 기사
            lines.append(f"- {item['title'][:100]}")
            lines.append(f"  📰 {item.get('source','')} | 🕐 {item.get('date','')[:25]}")
            lines.append(f"  🔗 {shorten_one(item['url'])}")
    else:
        lines.append(f"\n### 🌏 {label}")
        lines.append(f"- _(수집된 뉴스 없음)_")

# --- Stats ---
lines.append(f"\n---")
lines.append(f"## 📊 수집 통계")
lines.append(f"### 🇰🇷 한국어 ({kr_total}건)")
for cat, cnt in stats['korean']['categories'].items():
    lines.append(f"- {cat}: {cnt}건")
lines.append(f"### 🌐 영어 ({en_total}건)")
for cat, cnt in stats['english']['categories'].items():
    lines.append(f"- {cat}: {cnt}건")
lines.append(f"### 🌏 다국어 ({ml_total}건 / 20개 언어)")
for lang, cnt in stats['multilingual']['languages'].items():
    lines.append(f"- {lang}: {cnt}건")
lines.append(f"")
lines.append(f"**📊 총계: {total_all}건 (한국어 {kr_total} + 영어 {en_total} + 다국어 {ml_total})**")
lines.append(f"**💾 저장 위치:** `{DAILY_DIR}/`")

report_content = '\n'.join(lines)
report_path = os.path.join(DAILY_DIR, 'report.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write(report_content)

log(f"✅ 저장 완료: {DAILY_DIR}/")
log(f"   - raw.json ({os.path.getsize(raw_path)} bytes)")
log(f"   - report.md")

# ===== UPDATE README =====
def update_readme(stats, date_str):
    """Update README.md with latest crawl summary."""
    import glob
    lines = []
    lines.append("# 📰 PharmaScope News")
    lines.append("")
    lines.append("글로벌 의약업계 · 의료현장 · 전통의학 동향 뉴스 수집 파이프라인")
    lines.append(f"**최종 수집일:** {date_str}  |  **총계:** {stats['total']}건  |  **언어:** 23개")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(f"## 📄 오늘의 리포트")
    lines.append(f"- [📊 {date_str} 일일 리포트](./daily/{date_str}/report.md)")
    lines.append(f"- [💾 원시 데이터 (JSON)](./daily/{date_str}/raw.json)")
    lines.append("")
    lines.append("### 수집 통계")
    lines.append("| 언어 | 건수 |")
    lines.append("|------|------|")
    lines.append(f"| 🇰🇷 한국어 | {stats['korean']['total']}건 (11개 카테고리) |")
    for cat, cnt in stats['korean']['categories'].items():
        lines.append(f"| &nbsp;&nbsp;{cat} | {cnt}건 |")
    lines.append(f"| 🌐 영어 | {stats['english']['total']}건 (6개 카테고리) |")
    for cat, cnt in stats['english']['categories'].items():
        lines.append(f"| &nbsp;&nbsp;{cat} | {cnt}건 |")
    lines.append(f"| 🌏 다국어 | {stats['multilingual']['total']}건 (20개 언어) |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📅 최근 수집 이력")
    lines.append("| 날짜 | 총계 | 한국어 | 영어 | 다국어 |")
    lines.append("|------|------|--------|------|--------|")
    for d in sorted(glob.glob(os.path.join(BASE_DIR, 'daily', '2*')))[-14:]:
        day = os.path.basename(d)
        rp = os.path.join(d, 'report.md')
        if os.path.exists(rp):
            with open(rp, 'rb') as f2:
                f2.seek(0, 2)  # end
                size = f2.tell()
                f2.seek(max(0, size - 1024))  # last 1KB
                h = f2.read().decode('utf-8', errors='replace')
            lines.append(
                f"| {day} | {re.search(r'총\D*(\d+)', h).group(1) if re.search(r'총\D*(\d+)', h) else '-'}건 | "
                f"{re.search(r'한국어 (\d+)', h).group(1) if re.search(r'한국어 (\d+)', h) else '-'}건 | "
                f"{re.search(r'영어 (\d+)', h).group(1) if re.search(r'영어 (\d+)', h) else '-'}건 | "
                f"{re.search(r'다국어 (\d+)', h).group(1) if re.search(r'다국어 (\d+)', h) else '-'}건 |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🛠️ 정보")
    lines.append("- **수집 시간:** 매일 06:30 KST")
    lines.append("- **카테고리:** 의약품 · 의약산업 · 의약정책 · 의약단체 · 규제기관 · 의료현장 · 약국 · 의료정책 · 전통의학 · 감염보건")
    lines.append("- **언어:** 한국어 + 영어 + 21개 다국어")
    lines.append("- **URL:** TinyURL 자동 단축")
    lines.append("- **파이프라인:** Python 수집 → 멀티에이전트 포맷팅 → Telegram 전달")
    lines.append("- **저장소:** [WizMasia/pharmascope-news](https://github.com/WizMasia/pharmascope-news)")
    p = os.path.join(BASE_DIR, 'README.md')
    with open(p, 'w') as f2:
        f2.write('\n'.join(lines))
    log(f"✅ README.md 업데이트 완료 ({os.path.getsize(p)} bytes)")

update_readme(stats, DATE_STR)

# ===== GIT COMMIT (mywiki) =====
git_commit(f"[PharmaScope] 일일 수집 {DATE_STR} — {total_all}건 (한국어 {kr_total} + 영어 {en_total} + 다국어 {ml_total})")

# ===== GIT PUSH (pharmascope-news 저장소) =====
def git_push_self():
    """Commit and push to the pharmascope-news repository (current dir)."""
    import subprocess as _sp
    try:
        _sp.run(['git', 'add', '-A'], capture_output=True, text=True, timeout=30)
        diff = _sp.run(['git', 'diff', '--cached', '--quiet'], capture_output=True, timeout=30)
        if diff.returncode != 0:
            msg = f"[PharmaScope] 일일 수집 {DATE_STR} -- {total_all}건"
            cm = _sp.run(['git', 'commit', '-m', msg], capture_output=True, text=True, timeout=30)
            if cm.returncode == 0:
                log(f"✅ pharmascope-news 커밋: {cm.stdout.strip()}")
                ph = _sp.run(['git', 'push', 'origin', 'main'], capture_output=True, text=True, timeout=30)
                log(f"✅ pharmascope-news 푸시 완료" if ph.returncode == 0 else f"⚠️ pharmascope-news 푸시 실패: {ph.stderr.strip()}")
            else:
                log(f"⚠️ pharmascope-news 커밋 실패: {cm.stderr.strip()}")
        else:
            log("📎 pharmascope-news: 변경사항 없음")
    except Exception as e:
        log(f"⚠️ pharmascope-news git 오류: {e}")



git_push_self()

# ===== Print summary for cron output =====
print(f"\n{'='*60}")
print(f"  🔬 PHARMASCOPE DAILY REPORT — {DATE_STR}")
print(f"  {'='*50}")
print(f"  📊 총 {total_all}건")
print(f"  🇰🇷 한국어: {kr_total}건 (11개 카테고리)")
for cat, cnt in stats['korean']['categories'].items():
    print(f"     - {cat}: {cnt}건")
print(f"  🌐 영어: {en_total}건 (6개 카테고리)")
for cat, cnt in stats['english']['categories'].items():
    print(f"     - {cat}: {cnt}건")
print(f"  🌏 다국어: {ml_total}건")
print(f"  💾 저장: {DAILY_DIR}/")
print(f"{'='*60}")
