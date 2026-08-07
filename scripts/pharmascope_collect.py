#!/usr/bin/env python3
"""
PharmaScope (의약스코프) - v4 Google Discovery + Bing Direct URL
==============================================
Google News RSS로 기사 메타데이터를 발견하고, Google URL은 Bing News
제목·출처 매칭으로 직접 언론사 URL을 확보한 뒤 정적 HTML 본문을 추출한다.
Bing News HTML은 수집 부족 시 보조 소스이기도 하다.
Adapter Pattern + 중요도 평가(정수)
"""
import html
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters import *
from google_bing_bridge import resolve_via_bing
from html import unescape
from datetime import datetime, timedelta, timezone
import json, subprocess, re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed



def normalize_url(url: str) -> str:
    if not url:
        return ''
    return str(url).strip().strip('"\'').replace('\n', '').replace('	', '')


def normalize_text(text: str) -> str:
    if not text:
        return ''
    t = text.replace('\r', '\n').replace('\t', ' ')
    t = re.sub(r'\n{3,}', '\n\n', t)
    t = re.sub(r' {2,}', ' ', t)
    t = re.sub(r'\s+\n', '\n', t)
    return t.strip()


def _strip_html(body: str) -> str:
    if not body:
        return ''
    body = re.sub(r'(?is)<script.*?>.*?</script>', ' ', body)
    body = re.sub(r'(?is)<style.*?>.*?</style>', ' ', body)
    body = re.sub(r'(?is)<noscript.*?>.*?</noscript>', ' ', body)
    body = re.sub(r'(?is)<header.*?>.*?</header>', ' ', body)
    body = re.sub(r'(?is)<footer.*?>.*?</footer>', ' ', body)
    body = re.sub(r'(?is)<nav.*?>.*?</nav>', ' ', body)
    body = re.sub(r'(?is)<aside.*?>.*?</aside>', ' ', body)
    body = re.sub(r'(?is)<(br|p|div|li|ul|ol|tr|h[1-6]|article|section|main)[^>]*>', '\n', body)
    body = re.sub(r'(?is)</(p|div|li|ul|ol|tr|h[1-6]|article|section|main)>', '\n', body)
    body = re.sub(r'(?is)<[^>]+>', ' ', body)
    body = html.unescape(body)
    return normalize_text(body)


def _extract_meta_description(body: str) -> str:
    if not body:
        return ''
    patterns = [
        r'<meta[^>]+property="og:description"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="description"[^>]+content="([^"]+)"',
        r'<meta[^>]+name="twitter:description"[^>]+content="([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            return html.unescape(m.group(1)).strip()
    return ''


def resolve_final_url(raw_url: str) -> str:
    url = normalize_url(raw_url)
    if not url:
        return url
    try:
        cmd = [
            'curl', '-sSL', '-o', '/dev/null',
            '-w', '%{url_effective}',
            '--max-time', '12', '--connect-timeout', '8',
            '-A', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=16)
        if proc.returncode == 0:
            final = (proc.stdout or '').strip()
            if final.startswith(('http://', 'https://')):
                return final
    except Exception:
        pass
    return url


def fetch_fulltext(url: str, fallback: str = '') -> str:
    url = normalize_url(url)
    if not url:
        return normalize_text(fallback)
    try:
        proc = subprocess.run(
            [
                'curl', '-sL', '--compressed',
                '--max-time', '15', '--connect-timeout', '8',
                '--max-filesize', '3000000',
                '-A', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                url,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        body = proc.stdout or ''
    except Exception:
        body = ''

    if not body:
        return normalize_text(fallback)
    if '<html' not in body.lower() and '<body' not in body.lower():
        text = body.strip()
    else:
        text = _strip_html(body)
        if not text:
            text = _extract_meta_description(body)
    text = normalize_text(text)
    if not text or text.lower() in {'google news', 'google news', 'google news\u202f: what\'s happening', 'home'}:
        text = ''
    if text and len(text) <= 20:
        # 너무 짧은 페이지 단독 텍스트는 본문으로 보기 어렵다고 판단하고 패스
        text = ''
    return text or normalize_text(fallback)


def summarize_to_five_lines(text: str, title: str = ''):
    raw = normalize_text(text)
    if not raw:
        raw = normalize_text(title)

    lines = []
    if raw:
        raw = re.sub(r'(?<=[.!?。！？])\s+', '\n', raw)
        raw = re.sub(r'\n{2,}', '\n', raw)
        for item in raw.split('\n'):
            s = normalize_text(item)
            if len(s) < 12:
                continue
            if not any(ch.isalnum() for ch in s):
                continue
            lines.append(s)
            if len(lines) >= 5:
                break

    if not lines:
        words = normalize_text(text).split(' ')
        if words:
            for i in range(0, len(words), 20):
                chunk = ' '.join(words[i:i+20])
                if chunk:
                    lines.append(chunk)
                if len(lines) >= 5:
                    break

    while len(lines) < 5:
        lines.append('요약문 생성 불가')

    return lines[:5]


def enrich_articles(all_data: dict):
    """Resolve URLs, crawl full text and generate 5-line summaries for all articles."""
    stats = {
        'processed': 0,
        'url_resolved': 0,
        'fulltext_ok': 0,
        'bing_attempted': 0,
        'bing_matched': 0,
        'bing_failed': 0,
    }
    articles = []

    for section_data in all_data.values():
        if not isinstance(section_data, dict):
            continue
        for items in section_data.values():
            if not isinstance(items, list):
                continue
            for art in items:
                if not isinstance(art, dict):
                    continue
                original_url = normalize_url(art.get('url', '') or art.get('source_url', ''))
                if not original_url:
                    continue
                if 'source_url' not in art:
                    art['source_url'] = art.get('source_url') or art.get('url', '')
                # 수집용 URL은 원본 기사 URL을 유지
                if art.get('url'):
                    art['url'] = original_url
                articles.append(art)

    def _enrich(art):
        original_url = normalize_url(art.get('url', ''))
        final_url = original_url
        url_source = 'original_direct'
        bing_match = None
        if 'news.google.com/rss/articles/' in original_url:
            stats['bing_attempted'] += 1
            try:
                bing_match = resolve_via_bing(art, threshold=70)
            except Exception:
                bing_match = None
            if bing_match:
                final_url = bing_match['url']
                url_source = 'bing_match'
                stats['bing_matched'] += 1
            else:
                stats['bing_failed'] += 1
                final_url = resolve_final_url(original_url)
                url_source = 'google_url_fallback'
        changed = False
        if final_url and final_url != original_url:
            changed = True
        fallback = art.get('title', '')
        content = fetch_fulltext(final_url or original_url, fallback=fallback)
        title_len = len((art.get('title') or '').strip())
        # Google RSS URL에서 실제 본문 미확인 시 title fallback가 사용될 수 있음
        if 'news.google.com/rss/articles/' in original_url and len(content) <= max(30, title_len + 10):
            content_source = 'title_fallback'
        else:
            content_source = 'fetched'
        summary_lines = summarize_to_five_lines(content, title=art.get('title', ''))
        return {
            'art': art,
            'original_url': original_url,
            'final_url': final_url or original_url,
            'changed': changed,
            'url_source': url_source,
            'bing_match': bing_match,
            'content': content,
            'summary_lines': summary_lines,
            'content_source': content_source,
        }

    workers = 8
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(_enrich, art) for art in articles]
        for f in as_completed(futures):
            result = f.result()
            art = result['art']
            stats['processed'] += 1
            final_url = result['final_url']
            if final_url:
                art['url'] = final_url
            if result['changed']:
                art['url_resolved'] = True
                art['url_resolved_from'] = result['url_source']
                stats['url_resolved'] += 1
            art['url_source'] = result['url_source']
            if result['bing_match']:
                art['url_match_score'] = result['bing_match'].get('score', 0)
                art['url_match_title'] = result['bing_match'].get('match_title', '')

            content = result['content']
            art['content'] = content
            art['content_length'] = len(content)
            art['content_source'] = result['content_source']
            if content:
                if result['content_source'] != 'title_fallback':
                    stats['fulltext_ok'] += 1
                    art['content_status'] = 'fulltext'
                else:
                    art['content_status'] = 'title_only'
            else:
                art['content_status'] = 'failed'

            summary_lines = result['summary_lines']
            art['body_summary_lines'] = summary_lines
            art['summary_lines'] = summary_lines
            art['body_summary'] = ' | '.join(summary_lines)
            art['snippet'] = art['body_summary'][:220]

    return stats




def _flatten_articles(data_dict):
    """all_data['category']를 평탄화해 analysis 계산에 사용한다."""
    out = []
    for section_name, section_data in data_dict.get('category', {}).items():
        if not isinstance(section_data, dict):
            continue
        for cat_name, items in section_data.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                clone = dict(item)
                clone['_section'] = section_name
                clone['_category'] = cat_name
                out.append(clone)
    return out


def _is_text_present(v):
    return isinstance(v, str) and v.strip() != ''


def generate_quality_analysis(all_data, daily_dir, date_str):
    """analysis.md에 정량 지표(존재율/누락률/요약 5줄 분포/항목 diff) 기록한다."""
    articles = _flatten_articles(all_data)
    total = len(articles)
    fields = [
        'title', 'url', 'source', 'source_url', 'time', 'published_time',
        'modified_time', 'body_summary', 'snippet', 'cbm_id', 'importance',
        'content', 'content_length', 'body_summary_lines', 'summary_lines',
        'content_source', 'content_status', 'url_source', 'evidence'
    ]

    # 현재 상태
    presence = {f: 0 for f in fields}
    empty_content = 0
    missing = 0
    summary_len_dist = {i: 0 for i in range(0, 8)}
    exact5 = 0
    content_urls = 0
    google_urls = 0
    resolved = 0
    title_fallback = 0

    for a in articles:
        for f in fields:
            if f in a and a.get(f) not in (None, ''):
                if f in ('body_summary_lines', 'summary_lines'):
                    if isinstance(a.get(f), list):
                        presence[f] += 1
                else:
                    presence[f] += 1
        if not _is_text_present(a.get('content', '')):
            missing += 1
        else:
            if isinstance(a.get('content_length', 0), int) and a.get('content_length', 0) > 0:
                content_urls += 1
        slen = a.get('body_summary_lines')
        if isinstance(slen, list):
            l = len(slen)
            if l >= 7:
                summary_len_dist[7] += 1
            else:
                summary_len_dist.setdefault(l, 0)
                summary_len_dist[l] += 1
            if l == 5:
                exact5 += 1
        else:
            summary_len_dist[0] += 1

        if a.get('url_resolved'):
            resolved += 1
        if 'google.com' in a.get('url', ''):
            google_urls += 1
        if a.get('content_source') == 'title_fallback':
            title_fallback += 1

    def pct(a, b):
        return (a / b * 100) if b else 0.0

    # 직전일 diff
    prev_total = 0
    prev_presence = {f: 0 for f in fields}
    prev_missing = 0
    prev_exact5 = 0
    prev_title_fallback = 0
    try:
        # find latest previous day (기본 KST)
        from datetime import datetime, timedelta
        from datetime import timezone
        from pathlib import Path as _P
        d = datetime.strptime(date_str, '%Y-%m-%d')
        prev_date = (d - timedelta(days=1)).strftime('%Y-%m-%d')
        prev_path = _P('/root/workspace/mywiki/news/pharmascope/daily') / prev_date / 'raw.json'
        if prev_path.exists():
            import json as _json
            prev_json = _json.loads(prev_path.read_text(encoding='utf-8'))
            prev_articles = _flatten_articles(prev_json)
            prev_total = len(prev_articles)
            for a in prev_articles:
                for f in fields:
                    if f in a and a.get(f) not in (None, ''):
                        if f in ('body_summary_lines', 'summary_lines'):
                            if isinstance(a.get(f), list):
                                prev_presence[f] += 1
                        else:
                            prev_presence[f] += 1
                if not _is_text_present(a.get('content', '')):
                    prev_missing += 1
                sl = a.get('body_summary_lines')
                if isinstance(sl, list) and len(sl) == 5:
                    prev_exact5 += 1
                if a.get('content_source') == 'title_fallback':
                    prev_title_fallback += 1
    except Exception:
        pass

    # Render
    lines = []
    lines.append(f'# 📊 PharmaScope 정량 검증 리포트 ({date_str})')
    lines.append('')
    lines.append(f'- 총 기사: **{total}건**')
    lines.append(f'- 구간 비교: prev **{prev_date if prev_total else "-"}** -> **{date_str}**')
    lines.append('')

    lines.append('## 1) 기본 지표')
    lines.append(f'- 총 기사 수: {total} (이전 대비: {total - prev_total:+d}건)')
    lines.append(f'- 본문 미수집 기사: {missing}건 (누락률 {(pct(missing, total)):.2f}%) / 이전 대비 {(missing-prev_missing):+d}건')
    lines.append(f'- Google RSS 잔존 URL: {google_urls}건')
    lines.append(f'- title fallback 기사 수: {title_fallback}건 (이전 대비 {title_fallback - prev_title_fallback:+d}건)')
    lines.append(f'- url_resolved 건수: {resolved}건')
    lines.append('')

    lines.append('## 2) 필드 존재율 / 누락률')
    lines.append('| 필드 | 존재 | 존재율 | 누락률 |')
    lines.append('|---|---:|---:|---:|')
    for f in fields:
        exist = presence[f]
        miss = total - exist
        lines.append(f"| `{f}` | {exist}건 | {pct(exist, total):.2f}% | {pct(miss, total):.2f}% |")
    lines.append('')

    lines.append('## 3) 5줄 요약 강제 분포')
    lines.append('| 요약 줄 수 | 기사 수 | 비율 |')
    lines.append('|---|---:|---:|')
    for k in sorted(summary_len_dist.keys()):
        v = summary_len_dist[k]
        if v:
            lines.append(f"| {k if k < 7 else '7+'} | {v} | {pct(v, total):.2f}% |")
    lines.append(f'- 정확히 5줄: {exact5}건 ({pct(exact5, total):.2f}%)')
    lines.append(f'- 이전 대비 5줄: {exact5 - prev_exact5:+d}건')
    lines.append('')

    lines.append('## 4) 항목 존재/누락 diff (전일 대비)')
    lines.append('| 항목 | 현재 | 이전 | diff |')
    lines.append('|---|---:|---:|---:|')
    lines.append(f"| 총 기사 | {total} | {prev_total} | {total - prev_total:+d} |")
    lines.append(f"| content 누락 | {missing} | {prev_missing} | {missing - prev_missing:+d} |")
    for f in fields:
        lines.append(f"| {f} 존재 | {presence[f]} | {prev_presence[f]} | {presence[f]-prev_presence[f]:+d} |")
    lines.append('')

    (Path(daily_dir) / 'analysis.md').write_text('\n'.join(lines), encoding='utf-8')

# ===== GIT CONFIG =====
REAL_HOME = "/home/wizmasia"
MYWIKI_DIR = os.path.join(REAL_HOME, "workspace/mywiki")
BASE_DIR = os.path.join(REAL_HOME, "workspace/mywiki/news/pharmascope")
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


def article_source(item):
    return item.get('source', '') or '-'


def article_uploaded(item):
    return item.get('published_time') or item.get('time') or '-'


def article_modified(item):
    return item.get('modified_time') or item.get('updated_time') or '-'


def article_summary(item, limit=None):
    text = item.get('body_summary_lines')
    if isinstance(text, list) and text:
        text = ' | '.join(str(s).strip() for s in text if str(s).strip())
    else:
        text = item.get('body_summary') or item.get('snippet') or item.get('title', '') or ''
    text = re.sub(r'\s+', ' ', str(text)).strip()
    if not text:
        return '-'
    if isinstance(limit, int) and limit > 0:
        return text[:limit]
    return text

# ===================================================================
# GIT PUSH
# ===================================================================
def git_commit(message):
    """Commit and push only to pharmascope-news (GitHub)."""
    repo_dir = os.path.abspath(os.path.join(BASE_DIR, '..'))
    label = 'pharmascope-news'
    try:
        subprocess.run(['git', 'add', '-A'], cwd=repo_dir, capture_output=True, text=True, timeout=30)
        diff = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=repo_dir, capture_output=True, timeout=30)
        if diff.returncode == 0:
            log(f"  📎 ({label}) No new changes")
            return
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
log(f"🚀 PharmaScope v4 (Google 발견 → Bing 직접 URL) — {DATE_STR}")
log(f"   전략: Google RSS 발견, Bing 동일 기사 매칭, 직접 URL 본문 수집")

all_data = {'category': {}, '_meta': {
    'pipeline': 'pharmascope-v4-google-bing-bridge',
    'version': '4.0.0',
    'collection_date': DATE_STR,
    'collected_at': NOW.isoformat(),
}}

# ===================================================================
# 1. 🇰🇷 KOREAN — 10 categories
#    메인: Google News RSS 발견 → Bing 직접 URL 매칭
#    보조: Bing News HTML (목표 수량 미달 시)
# ===================================================================
log("="*50)
log("🇰🇷 국내 뉴스 (Google 발견 → Bing 직접 URL 매칭)")

kr_categories = {
    '의약품': {'keywords': ['의약품 치료제 신약', '의약품허가 품목허가 신약승인', '제네릭 바이오시밀러 복제약', '백신 항암제 희귀의약품', '의약품안전 의약품부작용', '신약개발 임상시험']},
    '의약산업': {'keywords': ['제약산업 제약바이오 제약사', '의약품시장 제약매출 의약품수출', '제약R&D 신약개발투자 임상시험', '바이오텍 CRO CDMO 위탁생산', '제약사 경영실적 매출', '글로벌 의약품 라이선스']},
    '의약정책': {'keywords': ['의약품정책 약가 약가인하 약가제도', '건강보험 보험급여 약제급여', '의약품규제 약사법 의약품법', '의약품특허 자료보호 의약품허가특허', '약가협상 약가재평가', '보험등재 급여확대']},
    '의약단체': {'keywords': ['한국제약바이오협회 KPBMA', '한국다국적의약산업협회 KRPIA', '대한약사회 한국약사회 약사', '제약단체 의약단체 제약협회', '제약바이오협회', '의약단체 동향']},
    '의약관련정부기관': {'keywords': ['식약처 MFDS 식품의약품안전처', '의약품안전 의약품심사 GMP 실사', '의약품부작용 의약품안전정보', '의약품수거 의약품회수 식약처조사', 'FDA 승인 규제', '의약품허가 심사']},
    '의료현장': {'keywords': ['의료현장 병원경영 진료과목 임상현장', '의료사고 의료분쟁 의료소송', '전공의 수련 전문의 인증', '의료질 환자경험 의료서비스', '병원 간호사 의사', '진료과 의료진']},
    '약국·약사': {'keywords': ['약국운영 조제실 일반의약품', '복약지도 의약품안전사용 DUR', '약사면허 약사교육 약사직능', '약국경영 지역약국 체인약국', '약국 조제료', '일반약 전문약']},
    '의료정책·인력': {'keywords': ['의료개혁 필수의료 의료체계', '의사인력 전공의 정원 간호사', '의료법 의료제도 건강보험', '원격의료 의료인력수급', '보건복지부 의료정책', '의료인력 수급']},
    '전통의학': {'keywords': ['한의사 한의원 한약 한방치료', '침술 약침 추나 한의학임상', '한의약정책 한약재 한의학연구', '한방산업 한의사면허 한의보험', '한약사 한약조제', '한의학 해외진출']},
    '감염·보건': {'keywords': ['감염병 항생제내성 감염관리', '예방접종 국가예방접종', '공중보건 보건복지 지역보건', '환자안전 의료감염 손위생', '코로나19 독감 인플루엔자', '전염병 방역']},
}

kr_primary = GoogleNewsRSSAdapter()
kr_secondary = [BingNewsHTMLAdapter()]  # Google RSS 메인, Bing 백업

kr_data = {}
for cat_name, cfg in kr_categories.items():
    results = hybrid_collect(kr_primary, kr_secondary, cfg['keywords'],
                              {'lang': 'ko-kr', 'region': 'kr'}, min_count=25)
    kr_data[cat_name] = results
    avg = sum(a.get('importance', 0) for a in results) // max(len(results), 1) if results else 0
    log(f"  [{cat_name}] {len(results)}건 (평균 {avg}점)")

all_data['category']['korean'] = kr_data

# ===================================================================
# 2. 🇺🇸🇬🇧 ENGLISH — 6 categories
#    메인: Google News RSS 발견 → Bing 직접 URL 매칭
#    보조: Bing News HTML (목표 수량 미달 시)
# ===================================================================
log("="*50)
log("🇺🇸🇬🇧 영어권 (Google 발견 → Bing 직접 URL 매칭)")

en_categories = {
    'Drugs & Therapies': {'keywords': ['drug approval new drug therapy pharmaceutical', 'generic drug biosimilar vaccine development', 'oncology drug rare disease treatment', 'antibiotic clinical trial drug discovery']},
    'Pharma Industry': {'keywords': ['pharmaceutical industry biotech company', 'pharma market drug development investment', 'clinical trial CRO CDMO drug manufacturing', 'pharma R&D drug sales pharma partnership']},
    'Pharma Policy': {'keywords': ['drug pricing pharmaceutical policy reform', 'drug reimbursement health insurance drug', 'pharmaceutical regulation patent drug', 'Inflation Reduction Act drug price negotiation']},
    'Pharma Associations': {'keywords': ['PhRMA pharmaceutical association', 'EFPIA International pharma federation', 'industry group pharmaceutical manufacturers', 'pharma trade association drug industry group']},
    'Regulatory Agencies': {'keywords': ['FDA regulation drug approval regulatory', 'EMA approval MHRA drug safety authority', 'GMP inspection pharmaceutical compliance', 'drug recall safety warning regulatory action']},
    'Traditional & Complementary Medicine': {'keywords': ['traditional medicine herbal remedy natural', 'Ayurveda Unani Siddha traditional Indian medicine', 'Kampo traditional Chinese medicine TCM acupuncture', 'Sowa-Rigpa Tibetan medicine complementary medicine']},
}

en_primary = GoogleNewsRSSAdapter()
en_secondary = [BingNewsHTMLAdapter()]  # Google RSS 메인, Bing 백업

en_data = {}
for cat_name, cfg in en_categories.items():
    results = hybrid_collect(en_primary, en_secondary, cfg['keywords'],
                              {'lang': 'en-us', 'region': 'US'}, min_count=25)
    en_data[cat_name] = results
    avg = sum(a.get('importance', 0) for a in results) // max(len(results), 1) if results else 0
    log(f"  [{cat_name}] {len(results)}건 (평균 {avg}점)")

all_data['category']['english'] = en_data

# ===================================================================
# 3. 🌏 MULTILINGUAL — 20 languages
# ===================================================================
log("="*50)
log("🌏 다국어 (Google 발견 → Bing 직접 URL 매칭)")

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

ml_primary = GoogleNewsRSSAdapter()
ml_secondary = [BingNewsHTMLAdapter()]  # Google RSS 메인, Bing 백업

ml_data = {}
for keywords, lang, region, label in lang_configs:
    results = hybrid_collect(ml_primary, ml_secondary, keywords,
                              {'lang': lang, 'region': region}, min_count=10)
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
# RAW ENRICH
# ===================================================================
log("📄 본문 수집/요약(5줄) 강화 실행 중...")
enrich_stats = enrich_articles(all_data['category'])
all_data['stats']['enrichment'] = enrich_stats
log(f"  ✅ enrichment 완료: 처리 {enrich_stats.get('processed', 0)}건, URL해석 {enrich_stats.get('url_resolved', 0)}건, 본문취득 {enrich_stats.get('fulltext_ok', 0)}건")

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
L.append(f"**수집일:** {DATE_STR}  |  **소스:** Google 발견 → Bing 직접 URL → 본문 수집  |  **총 {total_all}건**")
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
            source = article_source(item)
            uploaded = article_uploaded(item)
            modified = article_modified(item)
            summary = article_summary(item)
            L.append(f"{i}. {stars} **[{imp}점]** {t}{assn_tag}")
            L.append(f"   📰 출처: {source}")
            L.append(f"   ⏫ 업로드: {uploaded} | ♻️ 갱신: {modified}")
            L.append(f"   🧾 요약: {summary}")
            L.append(f"   📊 {item.get('evidence','')}")
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
        source = article_source(item)
        uploaded = article_uploaded(item)
        modified = article_modified(item)
        summary = article_summary(item)
        L.append(f"- {stars} **[{imp}점]** {item['title'][:80]}")
        L.append(f"  📰 출처: {source}")
        L.append(f"  ⏫ 업로드: {uploaded} | ♻️ 갱신: {modified}")
        L.append(f"  🧾 요약: {summary}")
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
L.append(f"**⚡ 수집:** {NOW.strftime('%Y-%m-%d %H:%M')} KST | Google RSS 발견 + Bing 직접 URL 매칭 + 정적 본문 추출")

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
            'snippet': (a.get('body_summary') or a.get('snippet', '') or '')[:220],
            'summary_lines': a.get('body_summary_lines', []),
            'content': a.get('content', '')[:5000],
            'content_length': a.get('content_length', 0),
            'published_time': a.get('published_time') or a.get('time', ''),
            'modified_time': a.get('modified_time') or a.get('updated_time', ''),
            'time': a.get('time', ''),
            'url': a.get('url', ''),
            'source_url': a.get('source_url', a.get('url', '')),
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

generate_quality_analysis(all_data, DAILY_DIR, DATE_STR)

# ===================================================================
# README
# ===================================================================
readme_path = os.path.join(BASE_DIR, 'README.md')
with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(f"""# 🔬 PharmaScope — 의약업계 글로벌 동향

**마지막 갱신:** {NOW.strftime('%Y-%m-%d %H:%M')} KST
**아키텍처:** Google RSS Discovery + Bing Direct URL Matching
**평가:** 정수 중요도 0~100

## 수집 전략

| 언어 | 메인 소스 | 보조 소스 | 비고 |
|------|----------|----------|------|
| 🇰🇷 한국어 | Google News 발견 | Bing News 직접 URL | 동일 기사 제목·출처 매칭 |
| 🇺🇸 영어 | Google News 발견 | Bing News 직접 URL | 동일 기사 제목·출처 매칭 |
| 🌏 다국어 | Google News 발견 | Bing News 직접 URL | 매칭 실패 시 Google URL fallback |

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
│   ├── url_resolver.py           # Google RSS 브라우저 해석/병합
│   └── pharmascope_collect.py    # 메인 파이프라인
├── daily/
│   └── {DATE_STR}/
│       ├── report.md
│       ├── raw.json
│       └── urls_to_resolve.json
└── AGENTS.md
```

*PharmaScope v4 — Google Discovery + Bing Direct URL Matching | 정수 중요도*
""")

log(f"✅ README.md 갱신 완료")

# ===================================================================
# URL 검증 — Google RSS 제거로 CBM URL 없음 확인
# ===================================================================
cbm_count = 0
for section_name, section_data in all_data.get('category', {}).items():
    if isinstance(section_data, dict):
        for items in section_data.values():
            if isinstance(items, list):
                for art in items:
                    if art.get('cbm_id', '') and 'google.com' in art.get('url', ''):
                        cbm_count += 1

log("Google RSS 브라우저 해석 대기열 생성 중...")
from url_resolver import extract_urls_for_resolution, merge_resolved
needs = extract_urls_for_resolution()
log(f"   → 브라우저 단계에서 {len(needs)}건 최종 URL/본문 해석 필요")
resolved_path = os.path.join(DAILY_DIR, 'resolved_urls.json')
if os.path.exists(resolved_path):
    merge_resolved()
    log("   → resolved_urls.json 반영 완료")

# ===================================================================
# GIT PUSH
# ===================================================================
log("="*50)
log("📤 Git push")
git_commit(f"🚀 PharmaScope v4 {DATE_STR} — Google discovery + Bing direct URL {total_all}건 수집")
log("="*50)
log(f"🎉 완료! 총 {total_all}건")
