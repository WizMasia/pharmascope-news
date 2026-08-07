# PharmaScope News Crawler — 운영 기준

이 저장소는 PharmaScope 뉴스 산출물의 공개·동기화 저장소다. 실제 수집 코드는 `/root/rpi_home_archive/workspace/mywiki/news/pharmascope/`에 있고, 실행 진실의 원천은 해당 코드와 Hermes cron 설정이다.

## 현재 수집 구조

```text
Google News RSS 발견 → 시간/중복 필터 → Bing 동일 기사 매칭
→ 직접 언론사 URL 정적 HTML 본문 추출 → 일일 산출물 → GitHub 동기화
```

- Google News RSS: 기사 발견과 메타데이터 수집
- Bing News: Google RSS 기사와 동일한 직접 언론사 URL 확보, 수집 부족 시 보조 소스
- 본문 수집: `curl` 정적 HTML 우선
- 중요도: 정수 기반 0~100점
- URL 매칭: 제목 유사도·출처 일치·직접 URL을 합산하고 70점 이상만 채택

## 운영 문서

수집 범주, 시간 필터, 중복 제거, URL 상태값, 산출물, 크론별 역할과 한계는 [뉴스 크롤러 운영 문서](docs/NEWS_CRAWLER_OPERATION.md)를 따른다.

## 품질 원칙

1. Google RSS URL이 남은 기사는 `google_url_fallback`으로 표시하며 직접 URL로 주장하지 않는다.
2. `title_only`, `failed`, 본문 미수집 상태는 숨기지 않는다.
3. 일일 결과에서는 `bing_attempted`, `bing_matched`, `bing_failed`, `url_source`, `content_status`, `fulltext_ok`를 확인한다.
4. 일일 원본·리포트·분석 파일을 동기화한 뒤 GitHub push 결과를 확인한다.
