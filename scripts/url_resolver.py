#!/usr/bin/env python3
"""
PharmaScope URL Resolver
========================
Google News RSS URL → 브라우저로 실제 기사 URL 변환

사용법:
  1. 수집 후: python3 url_resolver.py extract    → urls_to_resolve.json 생성
  2. LLM 크론: 브라우저로 각 URL 접속 → 최종URL 추출 → resolved_urls.json 저장
  3. 병합:   python3 url_resolver.py merge      → report.md 업데이트

출력 파일:
  - urls_to_resolve.json: { "articles": [ { "idx": 0, "url": "...", "cbm_id": "...", "title": "...", "source": "..." }, ... ] }
  - resolved_urls.json:   { "resolved": [ { "idx": 0, "original_url": "...", "actual_url": "..." }, ... ] }
  
  모든 파일은 daily/YYYY-MM-DD/ 에 저장됨.
"""
import json, os, sys, re
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
DATE_STR = NOW.strftime('%Y-%m-%d')
BASE_DIR = os.path.expanduser("~/workspace/mywiki/news/pharmascope")
DAILY_DIR = os.path.join(BASE_DIR, 'daily', DATE_STR)


def extract_urls_for_resolution():
    """
    raw.json → urls_to_resolve.json 생성
    Google RSS로 수집된 CBM URL만 추출 (Bing은 직접 URL이므로 제외)
    """
    raw_path = os.path.join(DAILY_DIR, 'raw.json')
    if not os.path.exists(raw_path):
        # 오늘 데이터 없으면 최신 일자 찾기
        daily_root = os.path.join(BASE_DIR, 'daily')
        dates = sorted(os.listdir(daily_root), reverse=True)
        for d in dates:
            p = os.path.join(daily_root, d, 'raw.json')
            if os.path.exists(p):
                raw_path = p
                break
        else:
            print("❌ raw.json not found")
            return []
    
    with open(raw_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    articles_needing_resolve = []
    idx = 0
    
    def scan_articles(items, section, category):
        nonlocal idx
        for item in items:
            cbm_id = item.get('cbm_id', '')
            url = item.get('url', '')
            # Google RSS URL (CBM 포함)이면서 아직 직접 URL이 아닌 경우
            if cbm_id and 'google.com' in url:
                source = item.get('source', '')
                lang_hint = 'en-US'
                if section == 'korean':
                    lang_hint = 'ko'
                elif section == 'multilingual':
                    lang_hint = 'en-US'
                
                rss_url = f"https://news.google.com/rss/articles/{cbm_id}?oc=5&hl={lang_hint}&gl=US&ceid=US:{lang_hint[:2]}"
                
                articles_needing_resolve.append({
                    'idx': idx,
                    'cbm_id': cbm_id,
                    'rss_url': rss_url,
                    'url': url,  # original URL
                    'title': item.get('title', ''),
                    'source': source,
                    'section': section,
                    'category': category,
                    'published_time': item.get('published_time') or item.get('time', ''),
                    'modified_time': item.get('modified_time') or item.get('updated_time', ''),
                    'body_summary': item.get('body_summary') or item.get('snippet', ''),
                })
                idx += 1
    
    categories = data.get('category', {})
    for section_name, section_data in categories.items():
        if isinstance(section_data, dict):
            for cat_name, items in section_data.items():
                scan_articles(items, section_name, cat_name)
    
    # Save
    os.makedirs(DAILY_DIR, exist_ok=True)
    out_path = os.path.join(DAILY_DIR, 'urls_to_resolve.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({'articles': articles_needing_resolve, 'meta': {
            'date': DATE_STR,
            'total': len(articles_needing_resolve),
            'instructions': 'For each article: browser_navigate(rss_url) → browser_console("window.location.href") → save actual_url'
        }}, f, ensure_ascii=False, indent=2)
    
    print(f"✅ urls_to_resolve.json → {len(articles_needing_resolve)}건 (브라우저 URL 변환 필요)")
    print(f"   저장: {out_path}")
    return articles_needing_resolve


def merge_resolved():
    """
    resolved_urls.json → raw.json + report.md 업데이트
    """
    resolve_path = os.path.join(DAILY_DIR, 'resolved_urls.json')
    raw_path = os.path.join(DAILY_DIR, 'raw.json')
    
    if not os.path.exists(resolve_path):
        print("❌ resolved_urls.json not found — run browser resolution first")
        return
    
    with open(resolve_path, 'r', encoding='utf-8') as f:
        resolved_data = json.load(f)
    
    # Build idx→url and cbm_id→url maps
    resolved_map_url = {}
    resolved_map_cbm = {}
    for item in resolved_data.get('resolved', []):
        idx = item['idx']
        resolved_map_url[idx] = item['actual_url']
        if item.get('cbm_id'):
            resolved_map_cbm[item['cbm_id']] = item['actual_url']
    
    if not os.path.exists(raw_path):
        print("❌ raw.json not found")
        return
    
    with open(raw_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Update URLs in raw.json
    updated_count = 0
    def update_article(items):
        nonlocal updated_count
        if not items:
            return
        for item in items:
            if isinstance(item, dict):
                # URL이 google.com을 포함하고 있으면 resolved_urls에서 찾아서 교체
                url = item.get('url', '')
                if 'google.com' in url:
                    cbm = item.get('cbm_id', '')
                    if cbm and cbm in resolved_map_cbm:
                        item['url'] = resolved_map_cbm[cbm]
                        item['url_resolved'] = True
                        updated_count += 1
                    else:
                        # Try idx match as fallback
                        ridx = item.get('_resolve_idx', -1)
                        if ridx in resolved_map_url:
                            item['url'] = resolved_map_url[ridx]
                            item['url_resolved'] = True
                            updated_count += 1
    
    categories = data.get('category', {})
    for section_data in categories.values():
        if isinstance(section_data, dict):
            for items in section_data.values():
                update_article(items)
    
    # Save updated raw.json
    with open(raw_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ raw.json 업데이트 완료 — {updated_count}건 URL 변환")
    
    # Regenerate report
    regenerate_report(data)
    return updated_count


def regenerate_report(data):
    """raw.json → report.md 재생성 (변환된 URL 반영)"""
    from html import unescape
    
    stats = data.get('stats', {})
    total_all = stats.get('total', 0)
    
    L = []
    L.append(f"# 🔬 PharmaScope — 글로벌 의약업계 동향 일일 리포트")
    L.append(f"**수집일:** {DATE_STR}  |  **브라우저 URL 변환 적용**  |  **총 {total_all}건**")
    L.append(f"**평가:** ⭐⭐⭐⭐⭐(85↑) ⭐⭐⭐⭐(65↑) ⭐⭐⭐(45↑) ⭐⭐(25↑) ⭐(0↑)  |  **정수 계산**")
    L.append("")
    
    kr_emoji = {'의약품': '💊', '의약산업': '🏭', '의약정책': '📋', '의약단체': '🤝',
                 '의약관련정부기관': '🏛️', '의료현장': '🏥', '약국·약사': '💊',
                 '의료정책·인력': '🩺', '전통의학': '🌿', '감염·보건': '🔬'}
    en_emoji = {'Drugs & Therapies': '💊', 'Pharma Industry': '🏭', 'Pharma Policy': '📋',
                 'Pharma Associations': '🤝', 'Regulatory Agencies': '🏛️',
                 'Traditional & Complementary Medicine': '🌿'}
    
    def write_section(data_items, emoji_map):
        for cat_name, items in data_items.items():
            emoji = emoji_map.get(cat_name, '📌')
            L.append(f"\n### {emoji} {cat_name} ({len(items)}건)")
            if not items:
                L.append("- _(수집된 뉴스 없음)_")
                continue
            sorted_items = sorted(items, key=lambda x: x.get('importance', 0), reverse=True)
            for i, item in enumerate(sorted_items, 1):
                t = item.get('title', '')
                imp = item.get('importance', 50)
                stars = item.get('stars', '⭐⭐⭐')
                resolved_tag = ' 🔄' if item.get('url_resolved') else ''
                source = item.get('source', '') or '-'
                uploaded = item.get('published_time') or item.get('time') or '-'
                modified = item.get('modified_time') or item.get('updated_time') or '-'
                summary = (item.get('body_summary') or item.get('snippet') or item.get('title', '') or '').strip()[:200] or '-'
                L.append(f"{i}. {stars} **[{imp}점]** {t}{resolved_tag}")
                L.append(f"   📰 출처: {source}")
                L.append(f"   ⏫ 업로드: {uploaded} | ♻️ 갱신: {modified}")
                L.append(f"   🧾 요약: {summary}")
                L.append(f"   📊 {item.get('evidence','')}")
                L.append(f"   🔗 {item['url']}")
    
    L.append("## 🇰🇷 국내 (한국어)")
    write_section(data['category'].get('korean', {}), kr_emoji)
    L.append("\n---")
    L.append("## 🌐 글로벌 (영어)")
    write_section(data['category'].get('english', {}), en_emoji)
    L.append("\n---")
    L.append("## 🌏 다국어 뉴스")
    lang_emoji = {'French / 프랑스어': '🇫🇷', 'German / 독일어': '🇩🇪', 'Spanish / 스페인어': '🇪🇸', 'Italian / 이탈리아어': '🇮🇹',
                  'Portuguese / 포르투갈어': '🇵🇹', 'Dutch / 네덜란드어': '🇳🇱', 'Swedish / 스웨덴어': '🇸🇪',
                  'Polish / 폴란드어': '🇵🇱', 'Turkish / 터키어': '🇹🇷', 'Russian / 러시아어': '🇷🇺',
                  'Japanese / 일본어': '🇯🇵', 'Chinese Simplified / 중국어': '🇨🇳', 'Chinese Traditional / 대만': '🇹🇼',
                  'Vietnamese / 베트남어': '🇻🇳', 'Thai / 태국어': '🇹🇭', 'Indonesian / 인도네시아어': '🇮🇩',
                  'Hindi / 힌디어': '🇮🇳', 'Arabic / 아랍어': '🇸🇦', 'Hebrew / 히브리어': '🇮🇱', 'Persian / 페르시아어': '🇮🇷'}
    for label, items in data['category'].get('multilingual', {}).items():
        emoji = lang_emoji.get(label, '🌏')
        L.append(f"\n### {emoji} {label} ({len(items)}건)")
        if not items:
            L.append("- _(수집된 뉴스 없음)_")
            continue
        for item in items[:5]:
            imp = item.get('importance', 50)
            stars = item.get('stars', '⭐⭐⭐')
            resolved_tag = ' 🔄' if item.get('url_resolved') else ''
            source = item.get('source', '') or '-'
            uploaded = item.get('published_time') or item.get('time') or '-'
            modified = item.get('modified_time') or item.get('updated_time') or '-'
            summary = (item.get('body_summary') or item.get('snippet') or item.get('title', '') or '').strip()[:200] or '-'
            L.append(f"- {stars} **[{imp}점]** {item['title'][:80]}{resolved_tag}")
            L.append(f"  📰 출처: {source}")
            L.append(f"  ⏫ 업로드: {uploaded} | ♻️ 갱신: {modified}")
            L.append(f"  🧾 요약: {summary}")
            L.append(f"  🔗 {item['url']}")
    
    L.append("\n---")
    L.append("## 📊 수집 통계")
    for section, sk, label in [('korean', 'korean', '🇰🇷 한국어'), ('english', 'english', '🌐 영어'), ('multilingual', 'multilingual', '🌏 다국어')]:
        section_data = data['category'].get(section, {})
        section_total = sum(len(v) for v in section_data.values())
        L.append(f"### {label} ({section_total}건)")
        for cat_name, items in section_data.items():
            avg = sum(a.get('importance', 0) for a in items) // max(len(items), 1) if items else 0
            L.append(f"- {cat_name}: {len(items)}건 (평균 {avg}점)")
    
    L.append(f"\n**📊 총계: {total_all}건 (브라우저 URL 변환 적용)**")
    L.append(f"**💾 저장:** `{DAILY_DIR}/`")
    L.append(f"**🔗 GitHub:** https://github.com/WizMasia/pharmascope-news")
    L.append(f"**⚡ 수집:** {DATE_STR} | v3 Adapter Pattern + Browser URL Resolution")
    
    report_path = os.path.join(DAILY_DIR, 'report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print(f"✅ report.md 재생성 완료: {report_path}")


# ===================================================================
# MAIN
# ===================================================================
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"사용법:")
        print(f"  python3 url_resolver.py extract    → urls_to_resolve.json 생성")
        print(f"  python3 url_resolver.py merge      → 변환된 URL 반영 + report 재생성")
        print(f"  python3 url_resolver.py check      → 현재 URL 상태 확인")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == 'extract':
        extract_urls_for_resolution()
    elif action == 'merge':
        merge_resolved()
    elif action == 'check':
        resolve_path = os.path.join(DAILY_DIR, 'resolved_urls.json')
        raw_path = os.path.join(DAILY_DIR, 'raw.json')
        print(f"📂 daily/{DATE_STR}/")
        print(f"   raw.json: {'✅' if os.path.exists(raw_path) else '❌'}")
        print(f"   urls_to_resolve.json: {'✅' if os.path.exists(os.path.join(DAILY_DIR, 'urls_to_resolve.json')) else '❌'}")
        print(f"   resolved_urls.json: {'✅' if os.path.exists(resolve_path) else '❌'}")
        if os.path.exists(resolve_path):
            with open(resolve_path) as f:
                data = json.load(f)
            print(f"   resolved: {len(data.get('resolved', []))}건")
    else:
        print(f"❌ 알 수 없는 명령: {action}")
