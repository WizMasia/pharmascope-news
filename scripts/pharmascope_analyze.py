#!/usr/bin/env python3
"""
|PharmaScope Daily Deep Analysis — 데이터 준비 스크립트
=====================================================
daily_summary.json + raw.json → 기사 클러스터링 + 분석용 데이터 준비.

사용법:
  python3 pharmascope_analyze.py [--date YYYY-MM-DD] [--day-before N]
  python3 pharmascope_analyze.py --start=2026-06-19T06:30:00 --end=2026-06-20T06:29:59
    --date: 분석할 날짜 (기본: 오늘)
    --day-before: N일 전 데이터도 함께 로드 (기본: 1)
    --start: ISO 시작시각 (KST). --end와 함께 사용
    --end: ISO 종료시각 (KST). --start와 함께 사용
    --start/--end 사용 시 해당 시간 범위 내 기사만 필터링

출력:
  daily/YYYY-MM-DD/analysis_ready.json  — LLM 분석용 구조화 데이터
"""
import email.utils
import json, os, sys, re
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
BASE_DIR = os.path.expanduser("~/workspace/mywiki/news/pharmascope")


# ===== 시간 유틸 =====
def parse_time_to_dt(time_str, default_dt=None):
    """기사 time 필드를 datetime으로 변환 (상대시간/절대시간 모두 지원)"""
    if not time_str:
        return default_dt
    ts = time_str.strip()
    now = default_dt or NOW

    # 분 단위
    m = re.search(r'(\d+)\s*분', ts)
    if m:
        return now - timedelta(minutes=int(m.group(1)))

    # 시간 단위
    h = re.search(r'(\d+)\s*시간', ts)
    if h:
        return now - timedelta(hours=int(h.group(1)))

    # 일 단위
    d = re.search(r'(\d+)\s*일', ts)
    if d:
        return now - timedelta(days=int(d.group(1)))

    # 주
    w = re.search(r'(\d+)\s*주', ts)
    if w:
        return now - timedelta(weeks=int(w.group(1)))

    # 개월 (30일 기준)
    mo = re.search(r'(\d+)\s*개월', ts)
    if mo:
        return now - timedelta(days=int(mo.group(1)) * 30)

    # 어제
    if '어제' in ts or 'yesterday' in ts:
        return now - timedelta(days=1)

    # RFC 2822 pubDate
    try:
        return email.utils.parsedate_to_datetime(ts)
    except Exception:
        pass

    return default_dt


def filter_articles_by_time(articles, start_dt, end_dt):
    """기사 리스트에서 start~end 범위 내의 것만 필터링"""
    result = []
    for a in articles:
        pub_dt = parse_time_to_dt(a.get('time', ''))
        if pub_dt and start_dt <= pub_dt <= end_dt:
            result.append(a)
        elif not pub_dt:
            # 시간 정보 없으면 보수적으로 포함
            result.append(a)
    return result

# ===== Pharma 키워드 목록 (daily_summary와 동일) =====
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

# 불용어 (클러스터링 시 제외)
STOP_WORDS_KR = {'위', '및', '등', '관련', '통해', '대한', '위한', '있는', '있는', '라는',
                  '까지', '에서', '으로', '으로부터', '것으로', '해야', '된다', '한다',
                  '때문', '이후', '이번', '지난해', '올해', '내년', '오늘', '어제',
                  '첫', '새', '최대', '최소', '최고', '최신', '주요', '본격',
                  '또', '더', '진짜', '진단', '가능', '확보'}
STOP_WORDS_EN = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
                  'and', 'or', 'but', 'is', 'are', 'was', 'were', 'be', 'been',
                  'has', 'have', 'had', 'do', 'does', 'did', 'will', 'would',
                  'could', 'should', 'may', 'might', 'can', 'new', 'first',
                  'last', 'next', 'over', 'into', 'than', 'its', 'their'}


def load_daily_summary(date_str):
    """daily_summary.json 로드"""
    path = os.path.join(BASE_DIR, 'daily', date_str, 'daily_summary.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def load_raw_articles(date_str):
    """raw.json에서 전체 기사 리스트 추출"""
    path = os.path.join(BASE_DIR, 'daily', date_str, 'raw.json')
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    articles = []
    cats = data.get('category', {})
    for section_name, section_data in cats.items():
        if isinstance(section_data, dict):
            for cat_name, items in section_data.items():
                if isinstance(items, list):
                    for a in items:
                        a['_section'] = section_name
                        a['_category'] = cat_name
                        articles.append(a)
    return articles

def extract_significant_words(title, lang='kr'):
    """제목에서 의미 있는 단어 추출 (클러스터링용)"""
    # 영어/숫자/한글 분리
    words = set()
    # 영어 키워드
    for kw in PHARMA_KEYWORDS_EN:
        if kw.lower() in title.lower():
            words.add(kw.lower())
    # 한국어 키워드
    for kw in PHARMA_KEYWORDS_KR:
        if kw in title:
            words.add(kw)
    # 일반 한글 단어 (2글자 이상, 불용어 제외)
    korean_parts = re.findall(r'[가-힣]{2,}', title)
    for w in korean_parts:
        if w not in STOP_WORDS_KR and len(w) >= 2:
            words.add(w)
    # 일반 영어 단어 (3글자 이상, 불용어 제외)
    english_parts = re.findall(r'[a-zA-Z]{3,}', title)
    for w in english_parts:
        wl = w.lower()
        if wl not in STOP_WORDS_EN:
            words.add(wl)
    # 숫자 포함 단어
    compounds = re.findall(r'[가-힣a-zA-Z]+[-/][가-힣a-zA-Z]+', title)
    for w in compounds:
        words.add(w.lower())

    # 불용어 최종 필터
    words = {w for w in words if w.lower() not in STOP_WORDS_KR
             and w.lower() not in STOP_WORDS_EN and len(w) >= 2}
    return words


def cluster_articles(articles, min_cluster_size=2, min_overlap=2):
    """
    제목 내 공통 키워드 기반 기사 클러스터링.
    같은 키워드를 min_overlap개 이상 공유하면 같은 클러스터.
    """
    if not articles:
        return [], []

    # 각 기사 → 단어 집합
    article_words = []
    for i, a in enumerate(articles):
        title = a.get('title', '')
        words = extract_significant_words(title)
        article_words.append((i, a, words))

    # 클러스터링: 단어 공유 기반 그래프 연결
    n = len(article_words)
    cluster_of = list(range(n))  # Union-Find

    def find(x):
        while cluster_of[x] != x:
            cluster_of[x] = cluster_of[cluster_of[x]]
            x = cluster_of[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            cluster_of[ry] = rx

    for i in range(n):
        _, _, words_i = article_words[i]
        for j in range(i + 1, n):
            _, _, words_j = article_words[j]
            overlap = len(words_i & words_j)
            if overlap >= min_overlap:
                union(i, j)

    # 클러스터 수집
    clusters = defaultdict(list)
    for i in range(n):
        root = find(i)
        clusters[root].append(i)

    # 정렬: 큰 클러스터 우선
    sorted_clusters = sorted(clusters.values(), key=lambda x: -len(x))

    result_clusters = []
    unclustered = []

    for group in sorted_clusters:
        items = [article_words[i][1] for i in group]
        if len(items) >= min_cluster_size:
            # 클러스터 대표 키워드 (공통 단어 중 빈도 높은 순)
            all_words = [article_words[i][2] for i in group]
            word_freq = Counter()
            for wset in all_words:
                for w in wset:
                    word_freq[w] += 1
            common_words = [w for w, c in word_freq.most_common(20) if c >= max(2, len(group) * 0.3)]
            result_clusters.append({
                'size': len(items),
                'keywords': common_words[:10],
                'articles': items,
            })
        else:
            unclustered.extend(items)

    return result_clusters, unclustered


def prepare_analysis_data(date_str, day_before=1, start_dt=None, end_dt=None):
    """분석용 데이터 준비"""
    summary = load_daily_summary(date_str)
    if not summary:
        print(f"❌ No data for {date_str}")
        return None

    raw_articles = load_raw_articles(date_str)
    
    # 시간 범위 필터링
    if start_dt and end_dt:
        before = len(raw_articles)
        raw_articles = filter_articles_by_time(raw_articles, start_dt, end_dt)
        dropped = before - len(raw_articles)
        if dropped:
            print(f"⏰ 시간 필터: {dropped}건 드롭됨 ({start_dt.strftime('%H:%M')}~{end_dt.strftime('%H:%M')})")
    
    print(f"📦 raw.json: {len(raw_articles)} articles" + (f" (시간필터 적용)" if start_dt else ""))

    # 전체 기사를 중요도순 정렬
    sorted_articles = sorted(raw_articles, key=lambda x: x.get('importance', 0), reverse=True)

    # Top 50 기사로 클러스터링
    top_articles = sorted_articles[:50]
    clusters, unclustered = cluster_articles(top_articles)

    # 전날 데이터 로드 (비교용)
    yesterday_str = (datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=KST) - timedelta(days=1)).strftime('%Y-%m-%d')
    yesterday_summary = load_daily_summary(yesterday_str)
    yesterday_issues = []
    if yesterday_summary:
        # 전날 analysis.json이 있으면 로드
        yesterday_analysis_path = os.path.join(BASE_DIR, 'daily', yesterday_str, 'analysis.json')
        if os.path.exists(yesterday_analysis_path):
            with open(yesterday_analysis_path, 'r', encoding='utf-8') as f:
                ya = json.load(f)
                yesterday_issues = [issue.get('topic', '') for issue in ya.get('issues', [])]

    # ===== 카테고리 분포 변화 =====
    kr_stats = summary.get('korean', {})
    en_stats = summary.get('english', {})
    ml_stats = summary.get('multilingual', {})

    # ===== 주요 출처 =====
    kr_sources = kr_stats.get('top_sources', [])
    en_sources = en_stats.get('top_sources', [])

    # ===== 구성 =====
    result = {
        'date': date_str,
        'total_articles': summary.get('total', 0),
        'language_breakdown': {
            'korean': {'total': kr_stats.get('total', 0), 'categories': kr_stats.get('categories', {})},
            'english': {'total': en_stats.get('total', 0), 'categories': en_stats.get('categories', {})},
            'multilingual': {'total': ml_stats.get('total', 0), 'languages': ml_stats.get('languages', {})},
        },
        'top_kr_keywords': [{'keyword': kw, 'count': cnt} for kw, cnt in kr_stats.get('top_keywords', [])[:15]],
        'top_en_keywords': [{'keyword': kw, 'count': cnt} for kw, cnt in en_stats.get('top_keywords', [])[:10]],
        'top_kr_sources': [{'source': src, 'count': cnt} for src, cnt in kr_sources[:10]],
        'top_en_sources': [{'source': src, 'count': cnt} for src, cnt in en_sources[:10]],
        'yesterday_issues': yesterday_issues[:5],
        'clusters': [],
        'uncategorized_articles': [],
        'cross_language_candidates': [],
    }

    # 클러스터 상세
    for ci, cluster in enumerate(clusters):
        cluster_data = {
            'cluster_id': ci + 1,
            'size': cluster['size'],
            'keywords': cluster['keywords'],
            'articles': [],
        }
        for a in cluster['articles']:
            cluster_data['articles'].append({
                'title': a.get('title', ''),
                'source': a.get('source', ''),
                'importance': a.get('importance', 0),
                'stars': a.get('stars', ''),
                'snippet': (a.get('snippet', '') or '')[:300],
                'section': a.get('_section', ''),
                'category': a.get('_category', ''),
                'time': a.get('time', ''),
                'url': a.get('url', ''),
            })
        result['clusters'].append(cluster_data)

    # 클러스터되지 않은 기사 (Top 10만)
    for a in unclustered[:10]:
        result['uncategorized_articles'].append({
            'title': a.get('title', ''),
            'source': a.get('source', ''),
            'importance': a.get('importance', 0),
            'snippet': (a.get('snippet', '') or '')[:200],
            'url': a.get('url', ''),
        })

    # 한영 동일 이슈 후보 (같은 키워드가 KR/EN에 동시 출현)
    kr_keyword_set = set(kw for kw, _ in kr_stats.get('top_keywords', []))
    en_keyword_set = set(kw.lower() for kw, _ in en_stats.get('top_keywords', []))
    # 공통 키워드 찾기
    kr_to_en = {
        'FDA': 'FDA', 'GMP': 'GMP', 'biosimilar': '바이오시밀러',
        'vaccine': '백신', 'patent': '특허', 'approval': '허가',
        'clinical trial': '임상', 'pricing': '약가',
    }
    for en_kw, kr_kw in kr_to_en.items():
        if en_kw in en_keyword_set and kr_kw in kr_keyword_set:
            result['cross_language_candidates'].append({
                'keyword': kr_kw,
                'kr_count': next((c for k, c in kr_stats.get('top_keywords', []) if k == kr_kw), 0),
                'en_count': next((c for k, c in en_stats.get('top_keywords', []) if k == en_kw), 0),
            })

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description='PharmaScope Daily Analysis Data Prep')
    parser.add_argument('--date', default=None, help='분석할 날짜 (YYYY-MM-DD)')
    parser.add_argument('--day-before', type=int, default=1, help='N일 전 데이터도 참조')
    parser.add_argument('--start', default=None, help='ISO 시작시각 (KST, 예: 2026-06-19T06:30:00)')
    parser.add_argument('--end', default=None, help='ISO 종료시각 (KST, 예: 2026-06-20T06:29:59)')
    args = parser.parse_args()

    # 시간 범위 파싱
    start_dt = end_dt = None
    if args.start and args.end:
        start_dt = datetime.fromisoformat(args.start).replace(tzinfo=KST)
        end_dt = datetime.fromisoformat(args.end).replace(tzinfo=KST)
        date_str = start_dt.strftime('%Y-%m-%d')
        print(f"🔬 PharmaScope Deep Analysis — {date_str} ({start_dt.strftime('%H:%M')}~{end_dt.strftime('%H:%M')})")
    else:
        date_str = args.date or NOW.strftime('%Y-%m-%d')
        print(f"🔬 PharmaScope Deep Analysis — Data Prep ({date_str})")

    print("=" * 50)

    result = prepare_analysis_data(date_str, args.day_before, start_dt, end_dt)
    if not result:
        sys.exit(1)

    # 저장
    daily_dir = os.path.join(BASE_DIR, 'daily', date_str)
    os.makedirs(daily_dir, exist_ok=True)

    out_path = os.path.join(daily_dir, 'analysis_ready.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n✅ analysis_ready.json 저장 완료: {os.path.getsize(out_path)} bytes")

    # 요약 출력
    print(f"\n📊 분석 데이터 요약:")
    print(f"   날짜: {date_str}")
    print(f"   총 기사: {result['total_articles']}건")
    print(f"   클러스터: {len(result['clusters'])}개")
    for c in result['clusters']:
        kw_str = ', '.join(c['keywords'][:5])
        print(f"     [{c['cluster_id']}] {c['size']}건 — {kw_str}")
    print(f"   미분류: {len(result['uncategorized_articles'])}건")
    if result['cross_language_candidates']:
        print(f"   한영 공통 이슈: {len(result['cross_language_candidates'])}개")
        for c in result['cross_language_candidates']:
            print(f"     - {c['keyword']}: KR {c['kr_count']} / EN {c['en_count']}")
    print(f"\n   💾 {out_path}")


if __name__ == '__main__':
    main()
