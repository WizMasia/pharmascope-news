"""
PharmaScope — News Source Adapters
====================================
각 뉴스 소스별 크롤러를 Adapter Pattern으로 분리.
모든 Adapter는 동일한 인터페이스: search(query, lang, region, max_count) → List[Article]

Article = {
  'title': str,
  'url': str,         # 실제 기사 URL (직접 접근 가능)
  'source': str,       # 출처명
  'time': str,         # 상대시간 (예: "2시간", "3일")
  'snippet': str,      # 요약
  'cbm_id': str,       # Google News CBM ID (있는 경우)
}
"""
import urllib.parse, subprocess, json, re, os, sys, time
from html import unescape
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)

# ===================================================================
# 공용 유틸
# ===================================================================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def dedup(articles):
    """URL + 제목 기반 중복제거"""
    seen_urls = set()
    seen_titles = set()
    result = []
    for a in articles:
        if a['url'] in seen_urls:
            continue
        title_key = re.sub(r'[^a-zA-Z0-9가-힣]', '', a['title'])[:40]
        if title_key in seen_titles:
            continue
        seen_urls.add(a['url'])
        seen_titles.add(title_key)
        result.append(a)
    return result

# ===================================================================
# Adapter 1: Google News RSS (curl, fast, CBM URLs)
# ===================================================================
class GoogleNewsRSSAdapter:
    """Google News RSS 피드 — 빠른 메타데이터 수집, URL은 CBM 프록시"""
    
    def search(self, query, lang='ko', region='KR', max_count=30):
        quoted = urllib.parse.quote(query + f' after:{(NOW-timedelta(hours=24)).strftime("%Y-%m-%d")}')
        url = f'https://news.google.com/rss/search?q={quoted}&hl={lang}&gl={region}&ceid={region}:{lang[:2]}'
        
        try:
            r = subprocess.run(['curl', '-sL', '--max-time', '15', url,
                '-H', 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            ], capture_output=True, text=True, timeout=20)
        except Exception as e:
            log(f"  ⚠️ Google RSS error: {e}")
            return []
        
        items = re.findall(r'<item>(.*?)</item>', r.stdout, re.DOTALL)
        results = []
        for item in items:
            title_m = re.search(r'<title>(.*?)</title>', item)
            link_m = re.search(r'<link>(.*?)</link>', item)
            source_m = re.search(r'<source>(.*?)</source>', item)
            date_m = re.search(r'<pubDate>(.*?)</pubDate>', item)
            snippet_m = re.search(r'<description>(.*?)(?:\[\...\]|\.\.\.|</a>|$)', item, re.DOTALL)
            
            if not (title_m and link_m):
                continue
            
            title = unescape(re.sub(r'<[^>]+>', '', title_m.group(1))).strip()
            article_url = link_m.group(1).strip()
            source = unescape(source_m.group(1)).strip() if source_m else ''
            snippet = ''
            if snippet_m:
                snip = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip()
                snippet = unescape(snip)[:200]
            
            # CBM ID 추출
            cbm_id = ''
            cbm_m = re.search(r'/articles/(CBM[^?&]+)', article_url)
            if cbm_m:
                cbm_id = cbm_m.group(1)
            
            results.append({
                'title': title,
                'url': article_url,
                'source': source,
                'time': date_m.group(1) if date_m else '',
                'snippet': snippet,
                'cbm_id': cbm_id,
            })
            
            if len(results) >= max_count * 3:  # RSS는 넉넉히 수집 (나중에 중요도로 커팅)
                break
        
        return results

# ===================================================================
# Adapter 2: Google News Browser (직접 URL, 브라우저 필요)
# ===================================================================
class GoogleNewsBrowserAdapter:
    """
    Google News RSS → 브라우저 → 실제 기사 URL로 변환
    browser_navigate + browser_console 로 JS 리다이렉트 후 최종 URL 추출
    
    ※ 이 어댑터는 cron 내 LLM Phase에서 브라우저 도구로 실행됨
      (Python 스크립트 직접 실행이 아닌, 크론 프롬프트 내에서 호출)
    
    search()는 메타데이터를 반환하고, resolve_urls()가 URL을 변환한다.
    """
    
    def search(self, query, lang='ko', region='KR', max_count=30):
        """RSS로 메타데이터 수집 (URL 미변환 상태)"""
        adapter = GoogleNewsRSSAdapter()
        return adapter.search(query, lang, region, max_count)
    
    @staticmethod
    def make_rss_url(cbm_id, lang='en-US', region='US'):
        """CBM ID → Google News RSS article URL 생성"""
        return f"https://news.google.com/rss/articles/{cbm_id}?oc=5&hl={lang}&gl={region}&ceid={region}:{lang[:2]}"
    
    @staticmethod
    def make_search_url(query, lang='ko', region='KR'):
        """Google News 검색 URL 생성 (브라우저용)"""
        quoted = urllib.parse.quote(query)
        return f"https://news.google.com/search?q={quoted}&hl={lang}&gl={region}&ceid={region}:{lang[:2]}"

# ===================================================================
# Adapter 3: Bing News HTML (curl, 직접 URL)
# ===================================================================
class BingNewsHTMLAdapter:
    """Bing News HTML 검색 — curl로 파싱, 직접 URL"""
    
    def search(self, query, lang='ko-kr', region='kr', max_count=30):
        quoted = urllib.parse.quote(query)
        url = f"https://www.bing.com/news/search?q={quoted}&setlang={lang}&cc={region}"
        
        try:
            r = subprocess.run(['curl', '-sL', '--max-time', '15', url,
                '-H', 'User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            ], capture_output=True, text=True, timeout=20)
        except Exception as e:
            log(f"  ⚠️ Bing error: {e}")
            return []
        
        html = r.stdout
        if 'news-card' not in html:
            return []
        
        cards = re.findall(
            r'<div class="news-card newsitem cardcommon[^"]*"[^>]*>.*?</div>\s*</div>\s*</div>',
            html, re.DOTALL
        )
        
        results = []
        for card in cards:
            url_m = re.search(r'\surl="([^"]*)"', card)
            auth_m = re.search(r'data-author="([^"]*)"', card)
            h2_m = re.search(r'<h2[^>]*>(.*?)</h2>', card, re.DOTALL)
            data_title_m = re.search(r'data-title="([^"]*)"', card)
            time_m = re.search(r'<div class="ns_sc_tm"[^>]*>(.*?)</div>', card)
            snippet_m = re.search(r'<div class="snippet"[^>]*>(.*?)</div>', card)
            
            if not (url_m and (h2_m or data_title_m)):
                continue
            
            title = re.sub(r'<[^>]+>', '', h2_m.group(1)).strip() if h2_m else unescape(data_title_m.group(1))
            snippet = ''
            if snippet_m:
                snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip()[:200]
            
            results.append({
                'title': title,
                'url': url_m.group(1),
                'source': unescape(auth_m.group(1)) if auth_m else '',
                'time': time_m.group(1).strip() if time_m else '',
                'snippet': snippet,
                'cbm_id': '',
            })
            
            if len(results) >= max_count:
                break
        
        return results

# ===================================================================
# Adapter 4: Naver News (브라우저 필요)
# ===================================================================
class NaverNewsBrowserAdapter:
    """
    Naver News 검색 — 브라우저 필요 (SPA)
    ※ 크론 LLM Phase에서 브라우저로 실행
    """
    
    @staticmethod
    def make_search_url(query):
        quoted = urllib.parse.quote(query)
        return f"https://search.naver.com/search.naver?where=news&query={quoted}&sm=tab_opt&sort=1"
    
    def search(self, query, lang='ko', region='KR', max_count=30):
        """Naver News — 브라우저 기반이므로 메타데이터만 반환"""
        # curl로는 SPA 데이터 추출 불가 → 브라우저 Phase에서 처리
        return []  # 브라우저 Phase에서 직접 호출

# ===================================================================
# Adapter 5: Daum (Kakao) News (브라우저 필요)
# ===================================================================
class DaumNewsBrowserAdapter:
    """Daum News 검색 — 브라우저 필요"""
    
    @staticmethod
    def make_search_url(query):
        quoted = urllib.parse.quote(query)
        return f"https://search.daum.net/search?w=news&q={quoted}&DA=NTB"
    
    def search(self, query, lang='ko', region='KR', max_count=30):
        return []  # 브라우저 Phase에서 처리

# ===================================================================
# Factory: 소스별 Adapter 생성
# ===================================================================
def get_adapter(source_name):
    adapters = {
        'google_rss': GoogleNewsRSSAdapter(),
        'google_browser': GoogleNewsBrowserAdapter(),
        'bing': BingNewsHTMLAdapter(),
        'naver': NaverNewsBrowserAdapter(),
        'daum': DaumNewsBrowserAdapter(),
    }
    return adapters.get(source_name, BingNewsHTMLAdapter())

# ===================================================================
# 점수 계산 (정수)
# ===================================================================
SOURCE_TIERS = {
    'yna.co.kr': 30, 'yonhap': 30, 'newsis': 28,
    'chosun': 28, 'joins': 28, 'donga': 28,
    'hani': 28, 'khan': 28, 'hankyung': 28, 'mk.co.kr': 28, 'sedaily': 28,
    'fnnews': 28, 'asiae': 28, 'edaily': 28,
    'reuters': 30, 'bloomberg': 30, 'ap.org': 30, 'fda.gov': 30,
    'pharmacist': 24, 'yakup': 24, 'dailypharm': 24, 'hitnews': 24,
    'medipana': 24, 'medicopharma': 24, 'ebn.co.kr': 24, 'betanews': 24,
    'fiercepharma': 24, 'endpoints': 24, 'biopharmadive': 24,
    'kpanews': 18, 'medicaltimes': 18, 'hkn24': 18,
}
DEFAULT_SOURCE_SCORE = 10

def calc_importance(article, keywords, position):
    """정수 중요도 계산 (0~100)"""
    s = source_score(article['source'], article['url'])
    r = recency_score(article.get('time', ''))
    rel = relevance_score(article['title'], keywords)
    rk = rank_score(position)
    total = s + r + rel + rk
    
    article['importance'] = total
    evidence_parts = [
        f"출처:{article['source']}+{s}",
        f"최신:{article.get('time','')}+{r}",
        f"키워드+{rel}",
        f"순위:{position}위+{rk}",
    ]
    article['evidence'] = ' | '.join(evidence_parts)
    
    if total >= 85: article['stars'] = '⭐⭐⭐⭐⭐'
    elif total >= 65: article['stars'] = '⭐⭐⭐⭐'
    elif total >= 45: article['stars'] = '⭐⭐⭐'
    elif total >= 25: article['stars'] = '⭐⭐'
    else: article['stars'] = '⭐'
    
    return article

def source_score(source, url):
    s = (source + ' ' + url).lower()
    for kw, score in SOURCE_TIERS.items():
        if kw in s:
            return score
    return DEFAULT_SOURCE_SCORE

def recency_score(time_str):
    if not time_str:
        return 5
    h = re.search(r'(\d+)\s*시간', time_str)
    if h:
        v = int(h.group(1))
        return 20 if v <= 6 else (15 if v <= 12 else (10 if v <= 24 else 5))
    if re.search(r'\d+\s*분', time_str): return 20
    d = re.search(r'(\d+)\s*일', time_str)
    if d:
        v = int(d.group(1))
        return 10 if v <= 1 else (5 if v <= 3 else (3 if v <= 7 else 2))
    if re.search(r'\d+\s*주', time_str): return 2
    if re.search(r'\d+\s*개월', time_str): return 1
    return 5

def relevance_score(title, keywords):
    tl = title.lower()
    cnt = sum(1 for kw in keywords for w in kw.lower().split() if len(w) >= 2 and w in tl)
    return 30 if cnt >= 5 else (25 if cnt >= 3 else (20 if cnt >= 2 else (10 if cnt >= 1 else 5)))

def rank_score(pos):
    return 20 if pos <= 3 else (18 if pos <= 5 else (15 if pos <= 10 else (10 if pos <= 15 else (5 if pos <= 20 else 2))))

# ===================================================================
# 하이브리드 수집
# ===================================================================
def hybrid_collect(primary, secondaries, keywords, lang_config, min_count=30):
    """
    primary Adapter로 1차 수집, 부족분을 secondary로 보충
    
    Args:
        primary: NewsSourceAdapter (메인)
        secondaries: list of NewsSourceAdapter (보조)
        keywords: list of str (검색 키워드)
        lang_config: dict with 'lang', 'region'
        min_count: 최소 수집 목표
    
    Returns:
        list of Article (중요도 정렬, 점수 포함)
    """
    all_articles = []
    
    # 1차: Primary
    for kw in keywords:
        try:
            results = primary.search(kw, lang_config.get('lang', 'ko'), 
                                      lang_config.get('region', 'KR'), 
                                      max_count=min_count)
            all_articles.extend(results)
            log(f"    {primary.__class__.__name__} '{kw[:20]}...' → {len(results)}건")
        except Exception as e:
            log(f"    ⚠️ {primary.__class__.__name__} 오류: {e}")
    
    all_articles = dedup(all_articles)
    
    # 부족분 보충
    if len(all_articles) < min_count:
        needed = min_count - len(all_articles)
        for secondary in secondaries:
            for kw in keywords:
                try:
                    more = secondary.search(kw, lang_config.get('lang', 'ko'),
                                            lang_config.get('region', 'KR'),
                                            max_count=needed)
                    all_articles.extend(more)
                    all_articles = dedup(all_articles)
                    log(f"    +{secondary.__class__.__name__} '{kw[:20]}...' → +{len(more)}건")
                    if len(all_articles) >= min_count:
                        break
                except Exception as e:
                    log(f"    ⚠️ {secondary.__class__.__name__} 오류: {e}")
            if len(all_articles) >= min_count:
                break
    
    # 중요도 평가
    position = 0
    for kw in keywords:
        for article in all_articles:
            position += 1
            calc_importance(article, keywords, position)
    
    # 중요도 정렬
    all_articles.sort(key=lambda x: x.get('importance', 0), reverse=True)
    
    return all_articles[:min_count]
