#!/usr/bin/env python3
"""
PharmaScope (의약스코프) — v3 Adapter Pattern
================================================
하이브리드 수집: Google News (메인) + Bing News (보조)
Adapter Pattern으로 각 소스 분리, 중요도 평가(정수)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import *
from html import unescape
from datetime import datetime, timedelta, timezone
import json, subprocess, re

# ===== GIT CONFIG =====
MYWIKI_DIR = os.path.expanduser("~/workspace/mywiki")
BASE_DIR = os.path.expanduser("~/workspace/mywiki/news/pharmascope")
KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
YESTERDAY = NOW - timedelta(hours=24)
DATE_STR = NOW.strftime('%Y-%m-%d')
DAILY_DIR = os.path.join(BASE_DIR, 'daily', DATE_STR)

# ===== ASSOCIATION MEDIA =====
ASSOCIATION_MEDIA = [
    '약사공론', '의협신문', '한의신문', '메디팜투데이',
    '데일리팜', '팜뉴스', '메디칼타임즈', '메디파나뉴스',
    '닥터스뉴스', '치협신문', '간협신문',
]
def is_association_media(source):
    return any(name.lower() in (source or '').lower() for name in ASSOCIATION_MEDIA)

# ===================================================================
# GIT PUSH
# ===================================================================
def git_commit(message):
    for repo_dir, label in [(MYWIKI_DIR, 'mywiki'),
                            (os.path.join(BASE_DIR, '..'), 'pharmascope-news')]:
        repo_dir = os.path.abspath(repo_dir)
        try:
            subprocess.run(['git', 'add', '-A'], cwd=repo_dir, capture_output=True, text=True, timeout=30)
            diff = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=repo_dir, capture_output=True, timeout=30)
            if diff.returncode == 0:
                log(f"  📎 ({label}) No new changes")
                continue
            commit = subprocess.run(['git', 'commit', '-m', message], cwd=repo_dir, capture_output=True, text=True, timeout=30)
            if commit.returncode == 0:
                log(f"  ✅ git commit ({label})")
                push = subprocess.run(['git', 'push', 'origin', 'main'], cwd=repo_dir, capture_output=True, text=True, timeout=30)
                if push.returncode == 0:
                    log(f"  ✅ git push ({label})")
                else:
                    log(f"  ⚠️ git push ({label}) 실패: {push.stderr.strip()}")
            else:
                log(f"  ⚠️ git commit ({label}): {commit.stderr.strip()}")
        except Exception as e:
            log(f"  ⚠️ Git error ({label}): {e}")

# ===================================================================
# MAIN
# ===================================================================
log(f"🚀 PharmaScope v3 (Adapter Pattern) — {DATE_STR}")
log(f"   전략: 언어별 메인/보조 소스, 중요도 평가 포함")

all_data = {'category': {}, '_meta': {
    'pipeline': 'pharmascope-v3',
    'version': '3.0.0',
    'collection_date': DATE_STR,
    'collected_at': NOW.isoformat(),
}}

# ===================================================================
# 1. 🇰🇷 KOREAN — 11 categories
#    메인: Bing News (직접 URL, curl)
#    보조: Google RSS (향후 브라우저 URL 변환)
# ===================================================================
log("="*50)
log("🇰🇷 국내 뉴스 (메인:Bing + 보조:Google)")

kr_categories = {
    '의약품': {'keywords': ['의약품 치료제 신약', '의약품허가 품목허가 신약승인', '제네릭 바이오시밀러 복제약', '백신 항암제 희귀의약품']},
    '의약산업': {'keywords': ['제약산업 제약바이오 제약사', '의약품시장 제약매출 의약품수출', '제약R&D 신약개발투자 임상시험', '바이오텍 CRO CDMO 위탁생산']},
    '의약정책': {'keywords': ['의약품정책 약가 약가인하 약가제도', '건강보험 보험급여 약제급여', '의약품규제 약사법 의약품법', '의약품특허 자료보호 의약품허가특허']},
    '의약단체': {'keywords': ['한국제약바이오협회 KPBMA', '한국다국적의약산업협회 KRPIA', '대한약사회 한국약사회 약사', '제약단체 의약단체 제약협회']},
    '의약관련정부기관': {'keywords': ['식약처 MFDS 식품의약품안전처', '의약품안전 의약품심사 GMP 실사', '의약품부작용 의약품안전정보', '의약품수거 의약품회수 식약처조사']},
    '의료현장': {'keywords': ['의료현장 병원경영 진료과목 임상현장', '의료사고 의료분쟁 의료소송', '전공의 수련 전문의 인증', '의료질 환자경험 의료서비스']},
    '약국·약사': {'keywords': ['약국운영 조제실 일반의약품', '복약지도 의약품안전사용 DUR', '약사면허 약사교육 약사직능', '약국경영 지역약국 체인약국']},
    '의료정책·인력': {'keywords': ['의료개혁 필수의료 의료체계', '의사인력 전공의 정원 간호사', '의료법 의료제도 건강보험', '원격의료 의료인력수급']},
    '전통의학': {'keywords': ['한의사 한의원 한약 한방치료', '침술 약침 추나 한의학임상', '한의약정책 한약재 한의학연구', '한방산업 한의사면허 한의보험']},
    '감염·보건': {'keywords': ['감염병 항생제내성 감염관리', '예방접종 국가예방접종', '공중보건 보건복지 지역보건', '환자안전 의료감염 손위생']},
}

kr_primary = BingNewsHTMLAdapter()
kr_secondary = [GoogleNewsRSSAdapter()]

kr_data = {}
for cat_name, cfg in kr_categories.items():
    results = hybrid_collect(kr_primary, kr_secondary, cfg['keywords'],
                              {'lang': 'ko-kr', 'region': 'kr'}, min_count=30)
    kr_data[cat_name] = results
    avg = sum(a.get('importance', 0) for a in results) // max(len(results), 1) if results else 0
    log(f"  [{cat_name}] {len(results)}건 (평균 {avg}점)")

all_data['category']['korean'] = kr_data

# ===================================================================
# 2. 🇺🇸🇬🇧 ENGLISH — 6 categories
#    메인: Bing News + Google RSS
# ===================================================================
log("="*50)
log("🇺🇸🇬🇧 영어권 (메인:Bing + 보조:Google)")

en_categories = {
    'Drugs & Therapies': {'keywords': ['drug approval new drug therapy pharmaceutical', 'generic drug biosimilar vaccine development', 'oncology drug rare disease treatment', 'antibiotic clinical trial drug discovery']},
    'Pharma Industry': {'keywords': ['pharmaceutical industry biotech company', 'pharma market drug development investment', 'clinical trial CRO CDMO drug manufacturing', 'pharma R&D drug sales pharma partnership']},
    'Pharma Policy': {'keywords': ['drug pricing pharmaceutical policy reform', 'drug reimbursement health insurance drug', 'pharmaceutical regulation patent drug', 'Inflation Reduction Act drug price negotiation']},
    'Pharma Associations': {'keywords': ['PhRMA pharmaceutical association', 'EFPIA International pharma federation', 'industry group pharmaceutical manufacturers', 'pharma trade association drug industry group']},
    'Regulatory Agencies': {'keywords': ['FDA regulation drug approval regulatory', 'EMA approval MHRA drug safety authority', 'GMP inspection pharmaceutical compliance', 'drug recall safety warning regulatory action']},
    'Traditional & Complementary Medicine': {'keywords': ['traditional medicine herbal remedy natural', 'Ayurveda Unani Siddha traditional Indian medicine', 'Kampo traditional Chinese medicine TCM acupuncture', 'Sowa-Rigpa Tibetan medicine complementary medicine']},
}

en_primary = BingNewsHTMLAdapter()
en_secondary = [GoogleNewsRSSAdapter()]

en_data = {}
for cat_name, cfg in en_categories.items():
    results = hybrid_collect(en_primary, en_secondary, cfg['keywords'],
                              {'lang': 'en-us', 'region': 'US'}, min_count=30)
    en_data[cat_name] = results
    avg = sum(a.get('importance', 0) for a in results) // max(len(results), 1) if results else 0
    log(f"  [{cat_name}] {len(results)}건 (평균 {avg}점)")

all_data['category']['english'] = en_data

# ===================================================================
# 3. 🌏 MULTILINGUAL — 20 languages
# ===================================================================
log("="*50)
log("🌏 다국어 (메인:Bing + 보조:Google)")

lang_configs = [
    (['médicament pharmacie industrie pharmaceutique', 'médecine traditionnelle phytothérapie'], 'fr-fr', 'FR', 'French / 프랑스어'),
    (['Arzneimittel Pharmaindustrie Medikamentenzulassung', 'traditionelle Medizin Naturheilkunde'], 'de-de', 'DE', 'German / 독일어'),
    (['medicamento farmacia industria farmacéutica', 'medicina tradicional fitoterapia'], 'es-es', 'ES', 'Spanish / 스페인어'),
    (['farmaco medicinali industria farmaceutica', 'medicina tradizionale fitoterapia'], 'it-it', 'IT', 'Italian / 이탈리아어'),
    (['medicamento farmácia indústria farmacêutica', 'medicina tradicional fitoterapia'], 'pt-br', 'BR', 'Portuguese / 포르투갈어'),
    (['geneesmiddel farmaceutische industrie', 'traditionele geneeskunde fytotherapie'], 'nl-nl', 'NL', 'Dutch / 네덜란드어'),
    (['läkemedel läkemedelsindustri', 'traditionell medicin naturläkemedel'], 'sv-se', 'SE', 'Swedish / 스웨덴어'),
    (['leki przemysł farmaceutyczny', 'medycyna tradycyjna ziołolecznictwo'], 'pl-pl', 'PL', 'Polish / 폴란드어'),
    (['ilaç ecza ilaç endüstrisi', 'geleneksel tıp bitkisel ilaç'], 'tr-tr', 'TR', 'Turkish / 터키어'),
    (['фармацевтика лекарственные препараты', 'традиционная медицина фитотерапия'], 'ru-ru', 'RU', 'Russian / 러시아어'),
    (['医薬品 製薬 薬事 ニュース', '漢方 Kampo 漢方薬 東洋医学'], 'ja-jp', 'JP', 'Japanese / 일본어'),
    (['药品 制药 医药 新闻 政策', '中医 中药 传统医学 中西医结合'], 'zh-cn', 'CN', 'Chinese Simplified / 중국어'),
    (['藥物 藥品 製藥 醫藥 政策', '中醫 中藥 傳統醫學 針灸'], 'zh-tw', 'TW', 'Chinese Traditional / 대만'),
    (['dược phẩm thuốc ngành dược', 'y học cổ truyền thuốc nam'], 'vi-vn', 'VN', 'Vietnamese / 베트남어'),
    (['ยา อุตสาหกรรมยา เภสัชกรรม', 'การแพทย์แผนไทย สมุนไพร'], 'th-th', 'TH', 'Thai / 태국어'),
    (['obat farmasi industri farmasi', 'pengobatan tradisional jamu herbal'], 'id-id', 'ID', 'Indonesian / 인도네시아어'),
    (['दवा फार्मास्युटिकल उद्योग', 'आयुर्वेद योग प्राकृतिक चिकित्सा यूनानी सिद्ध'], 'hi-in', 'IN', 'Hindi / 힌디어'),
    (['صناعة الأدوية المستحضرات الصيدلانية', 'الطب التقليدي الأعشاب الطبية'], 'ar-sa', 'SA', 'Arabic / 아랍어'),
    (['תרופות תעשיית התרופות', 'רפואה מסורתית צמחי מרפא'], 'he-il', 'IL', 'Hebrew / 히브리어'),
    (['دارو صنعت داروسازی', 'طب سنتی گیاهان دارویی'], 'fa-ir', 'IR', 'Persian / 페르시아어'),
]

ml_primary = BingNewsHTMLAdapter()
ml_secondary = [GoogleNewsRSSAdapter()]

ml_data = {}
for keywords, lang, region, label in lang_configs:
    results = hybrid_collect(ml_primary, ml_secondary, keywords,
                              {'lang': lang, 'region': region}, min_count=15)
    ml_data[label] = results
    log(f"  [{label}] {len(results)}건")

all_data['category']['multilingual'] = ml_data

# ===================================================================
# STATS
# ===================================================================
kr_total = sum(len(v) for v in kr_data.values())
en_total = sum(len(v) for v in en_data.values())
ml_total = sum(len(v) for v in ml_data.values())
total_all = kr_total + en_total + ml_total

all_data['stats'] = {
    'korean': {'total': kr_total, 'categories': {k: len(v) for k, v in kr_data.items()}},
    'english': {'total': en_total, 'categories': {k: len(v) for k, v in en_data.items()}},
    'multilingual': {'total': ml_total, 'languages': {k: len(v) for k, v in ml_data.items()}},
    'total': total_all,
}

# ===================================================================
# SAVE
# ===================================================================
os.makedirs(DAILY_DIR, exist_ok=True)
with open(os.path.join(DAILY_DIR, 'raw.json'), 'w', encoding='utf-8') as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)

# ===================================================================
# REPORT
# ===================================================================
L = []
L.append(f"# 🔬 PharmaScope — 글로벌 의약업계 동향 일일 리포트")
L.append(f"**수집일:** {DATE_STR}  |  **소스:** Bing News 메인 + Google 보조  |  **어댑터 패턴**  |  **총 {total_all}건**")
L.append(f"**평가:** ⭐⭐⭐⭐⭐(85↑) ⭐⭐⭐⭐(65↑) ⭐⭐⭐(45↑) ⭐⭐(25↑) ⭐(0↑)  |  **정수 계산**")
L.append("")

kr_emoji = {'의약품': '💊', '의약산업': '🏭', '의약정책': '📋', '의약단체': '🤝',
             '의약관련정부기관': '🏛️', '의료현장': '🏥', '약국·약사': '💊',
             '의료정책·인력': '🩺', '전통의학': '🌿', '감염·보건': '🔬'}
en_emoji = {'Drugs & Therapies': '💊', 'Pharma Industry': '🏭', 'Pharma Policy': '📋',
             'Pharma Associations': '🤝', 'Regulatory Agencies': '🏛️',
             'Traditional & Complementary Medicine': '🌿'}

def write_section(data, emoji_map):
    for cat_name, items in data.items():
        emoji = emoji_map.get(cat_name, '📌')
        L.append(f"\n### {emoji} {cat_name} ({len(items)}건)")
        if not items:
            L.append("- _(수집된 뉴스 없음)_")
            continue
        sorted_items = sorted(items, key=lambda x: x.get('importance', 0), reverse=True)
        for i, item in enumerate(sorted_items, 1):
            t = item['title']
            assn_tag = ' *(협회지)*' if is_association_media(item.get('source','')) else ''
            imp = item.get('importance', 50)
            stars = item.get('stars', '⭐⭐⭐')
            L.append(f"{i}. {stars} **[{imp}점]** {t}{assn_tag}")
            L.append(f"   📰 {item.get('source','')} | 🕐 {item.get('time','')}")
            L.append(f"   📊 {item.get('evidence','')}")
            if item.get('snippet'):
                L.append(f"   💬 {item['snippet'][:100]}")
            L.append(f"   🔗 {item['url']}")

L.append("## 🇰🇷 국내 (한국어)")
write_section(kr_data, kr_emoji)

L.append("\n---")
L.append("## 🌐 글로벌 (영어)")
write_section(en_data, en_emoji)

L.append("\n---")
L.append("## 🌏 다국어 뉴스 (20개 언어)")
lang_emoji = {'French / 프랑스어': '🇫🇷', 'German / 독일어': '🇩🇪', 'Spanish / 스페인어': '🇪🇸', 'Italian / 이탈리아어': '🇮🇹',
              'Portuguese / 포르투갈어': '🇵🇹', 'Dutch / 네덜란드어': '🇳🇱', 'Swedish / 스웨덴어': '🇸🇪',
              'Polish / 폴란드어': '🇵🇱', 'Turkish / 터키어': '🇹🇷', 'Russian / 러시아어': '🇷🇺',
              'Japanese / 일본어': '🇯🇵', 'Chinese Simplified / 중국어': '🇨🇳', 'Chinese Traditional / 대만': '🇹🇼',
              'Vietnamese / 베트남어': '🇻🇳', 'Thai / 태국어': '🇹🇭', 'Indonesian / 인도네시아어': '🇮🇩',
              'Hindi / 힌디어': '🇮🇳', 'Arabic / 아랍어': '🇸🇦', 'Hebrew / 히브리어': '🇮🇱', 'Persian / 페르시아어': '🇮🇷'}
for label, items in ml_data.items():
    emoji = lang_emoji.get(label, '🌏')
    L.append(f"\n### {emoji} {label} ({len(items)}건)")
    if not items:
        L.append("- _(수집된 뉴스 없음)_")
        continue
    for item in items[:5]:
        imp = item.get('importance', 50)
        stars = item.get('stars', '⭐⭐⭐')
        L.append(f"- {stars} **[{imp}점]** {item['title'][:80]}")
        L.append(f"  📰 {item.get('source','')} | 🕐 {item.get('time','')}")
        L.append(f"  🔗 {item['url']}")

L.append("\n---")
L.append("## 📊 수집 통계")
L.append(f"### 🇰🇷 한국어 ({kr_total}건)")
for cat_name, items in kr_data.items():
    avg = sum(a.get('importance', 0) for a in items) // max(len(items), 1) if items else 0
    L.append(f"- {cat_name}: {len(items)}건 (평균 {avg}점)")
L.append(f"### 🌐 영어 ({en_total}건)")
for cat_name, items in en_data.items():
    avg = sum(a.get('importance', 0) for a in items) // max(len(items), 1) if items else 0
    L.append(f"- {cat_name}: {len(items)}건 (평균 {avg}점)")
L.append(f"### 🌏 다국어 ({ml_total}건 / 20개 언어)")
for label, items in ml_data.items():
    if items:
        avg = sum(a.get('importance', 0) for a in items) // max(len(items), 1)
        L.append(f"- {label}: {len(items)}건 (평균 {avg}점)")
    else:
        L.append(f"- {label}: 0건")

L.append(f"\n**📊 총계: {total_all}건**")
L.append(f"**💾 저장:** `{DAILY_DIR}/`")
L.append(f"**🔗 GitHub:** https://github.com/WizMasia/pharmascope-news")
L.append(f"**⚡ 수집:** {NOW.strftime('%Y-%m-%d %H:%M')} KST | v3 Adapter Pattern")

report = '\n'.join(L)
with open(os.path.join(DAILY_DIR, 'report.md'), 'w', encoding='utf-8') as f:
    f.write(report)
log(f"✅ 리포트 저장 완료: {len(report)}자")

# Summary
with open(os.path.join(DAILY_DIR, 'summary.txt'), 'w', encoding='utf-8') as f:
    f.write(f"🔬 PharmaScope {DATE_STR}\n")
    f.write(f"총 {total_all}건 | 🇰🇷{kr_total} 🌐{en_total} 🌏{ml_total}\n")
    f.write(f"📄 https://github.com/WizMasia/pharmascope-news/blob/main/daily/{DATE_STR}/report.md\n")

# ===================================================================
# DAILY SUMMARY JSON — 주간/월간 집계용 구조화 요약
# ===================================================================
log("📊 daily_summary.json 생성 중...")
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

def count_title_keywords(titles, keywords):
    """제목 내 키워드 카운트 (정수)"""
    counts = {}
    for kw in keywords:
        cnt = sum(1 for t in titles if kw.lower() in t.lower())
        if cnt > 0:
            counts[kw] = cnt
    return sorted(counts.items(), key=lambda x: -x[1])

def build_lang_summary(lang_data, top_n, keywords, name_field='categories'):
    """언어별 요약 데이터 구성"""
    total = sum(len(v) for v in lang_data.values())
    cat_counts = {k: len(v) for k, v in lang_data.items()}
    all_titles = []
    all_articles = []
    source_hits = {}
    for cat_name, items in lang_data.items():
        for a in items:
            all_titles.append(a.get('title', ''))
            all_articles.append(a)
            src = a.get('source', '')
            if src:
                source_hits[src] = source_hits.get(src, 0) + 1
    # 상위 중요도 기사
    sorted_articles = sorted(all_articles, key=lambda x: x.get('importance', 0), reverse=True)
    top_articles = []
    for a in sorted_articles[:top_n]:
        top_articles.append({
            'title': a.get('title', ''),
            'source': a.get('source', ''),
            'importance': a.get('importance', 0),
            'stars': a.get('stars', ''),
            'evidence': a.get('evidence', ''),
            'snippet': (a.get('snippet', '') or '')[:200],
            'time': a.get('time', ''),
            'url': a.get('url', ''),
        })
    return {
        'total': total,
        name_field: cat_counts,
        'top_articles': top_articles,
        'top_keywords': count_title_keywords(all_titles, keywords)[:20],
        'top_sources': sorted(source_hits.items(), key=lambda x: -x[1])[:15],
    }

daily_summary = {
    'date': DATE_STR,
    'total': total_all,
    'version': 1,
    'generated_at': NOW.isoformat(),
    'korean': build_lang_summary(kr_data, 10, PHARMA_KEYWORDS_KR),
    'english': build_lang_summary(en_data, 10, PHARMA_KEYWORDS_EN, 'categories'),
    'multilingual': build_lang_summary(ml_data, 5, [], 'languages'),  # 다국어는 키워드 분석 생략
}

summary_path = os.path.join(DAILY_DIR, 'daily_summary.json')
with open(summary_path, 'w', encoding='utf-8') as f:
    json.dump(daily_summary, f, ensure_ascii=False, indent=2)
log(f"✅ daily_summary.json 저장 완료: {len(json.dumps(daily_summary, ensure_ascii=False))}자")

# ===================================================================
# README
# ===================================================================
readme_path = os.path.join(BASE_DIR, 'README.md')
with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(f"""# 🔬 PharmaScope — 의약업계 글로벌 동향

**마지막 갱신:** {NOW.strftime('%Y-%m-%d %H:%M')} KST
**아키텍처:** Adapter Pattern (다중 소스, 언어별 전략)
**평가:** 정수 중요도 0~100

## 수집 전략

| 언어 | 메인 소스 | 보조 소스 | 비고 |
|------|----------|----------|------|
| 🇰🇷 한국어 | Bing News | Google News | Naver/Daum (향후 브라우저 추가) |
| 🇺🇸 영어 | Bing News | Google News | |
| 🌏 다국어 | Bing News | Google News | 20개 언어 |

## 중요도 평가 (정수)

| 요소 | 배점 |
|------|------|
| 📰 출처권위 | 0~30 |
| ⏰ 최신성 | 0~20 |
| 🎯 키워드적중 | 0~30 |
| 📌 검색순위 | 0~20 |
| **총점** | **0~100 (정수)** |

## 디렉토리

```
pharmascope/
├── README.md
├── scripts/
│   ├── adapters.py               # News Source Adapters
│   └── pharmascope_collect.py    # 메인 파이프라인
├── daily/
│   └── {DATE_STR}/
│       ├── report.md
│       └── raw.json
└── AGENTS.md
```

*PharmaScope v3 — Adapter Pattern | 정수 중요도 | 다중 소스 하이브리드*
""")

log(f"✅ README.md 갱신 완료")

# ===================================================================
# URL RESOLVER — Google RSS CBM URL → 브라우저 변환 대기
# ===================================================================
from url_resolver import extract_urls_for_resolution
needs_resolve = extract_urls_for_resolution()
log(f"🔗 URL 변환 대기: {len(needs_resolve)}건 (브라우저 Phase 2에서 처리)")

# ===================================================================
# GIT PUSH
# ===================================================================
log("="*50)
log("📤 Git push")
git_commit(f"🚀 PharmaScope v3 {DATE_STR} — Adapter Pattern {total_all}건 수집")
log("="*50)
log(f"🎉 완료! 총 {total_all}건")
