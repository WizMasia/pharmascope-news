# PharmaScope 뉴스 크롤러 운영 문서

> **기준일:** 2026-08-07  
> **진실의 원천:** `scripts/pharmascope_collect.py`, `scripts/adapters.py`, `scripts/google_bing_bridge.py`, Hermes cron 설정  
> 이 문서는 현재 실행 코드의 동작을 설명한다. 과거 문서에 있던 “Bing 단독 수집”, “Google RSS는 legacy”라는 설명은 현행 코드와 일치하지 않는다.

## 1. 목적과 범위

PharmaScope는 국내·영어권·다국어권의 **의약품, 제약산업, 규제, GMP, 의료현장, 약국·약사, 감염·보건, 전통의학** 뉴스를 일 단위로 수집·정리하는 파이프라인이다.

각 기사는 제목, 출처, 발행 시각, URL 출처, 본문 확보 상태, 중요도, 근거 문자열, 요약을 구조화해 보관한다. 단순히 기사를 많이 모으는 것이 아니라, Google News 중간 URL을 직접 언론사 URL로 바꾸고 본문 품질 상태를 드러내는 것을 목표로 한다.

## 2. 현재 아키텍처

```text
Google News RSS 검색 (발견·메타데이터)
        │
        ├─ 24시간/UTC 동일 날짜 필터
        ├─ URL·제목 중복 제거
        └─ 범주별 중요도 점수화
        │
        ▼
Google RSS 기사별 Bing News 재검색
        │
        ├─ 제목 유사도 + 출처 일치 + 직접 URL 점수화
        ├─ 70점 이상이면 언론사 직접 URL 채택
        └─ 실패 시 Google RSS URL을 fallback 상태로 보존
        │
        ▼
직접 URL 정적 HTML(curl) 본문 추출
        │
        ├─ HTML 본문 텍스트 추출
        ├─ og:description/meta description 보조
        └─ 본문·제목 fallback 여부 상태 기록
        │
        ▼
raw.json / report.md / daily_summary.json / analysis.md 저장
        │
        ▼
GitHub `WizMasia/pharmascope-news` 동기화
```

### 소스의 역할

| 단계 | 실제 구현 | 역할 |
|---|---|---|
| 기사 발견 | `GoogleNewsRSSAdapter` | 검색어별 RSS에서 제목·출처·발행시각·snippet·Google RSS URL 획득 |
| 수량 보충 | `BingNewsHTMLAdapter` | Google 결과가 범주별 목표 수에 못 미칠 때 보조 수집 |
| 직접 URL 확보 | `google_bing_bridge.resolve_via_bing()` | Google 기사 제목을 Bing News에서 재검색해 동일 기사 후보 선택 |
| 본문 수집 | `fetch_fulltext()` | `curl`로 정적 HTML을 받고 불필요 태그 제거 후 텍스트화 |

따라서 현행 구조는 **Google 발견 → Bing 직접 URL 매칭 → 정적 본문 추출**이다. Bing은 최초 수집의 보조 소스이면서 Google URL을 교체하는 URL 확보 소스이다.

## 3. 수집 주제와 검색 구성

### 3.1 국내 뉴스 — 10개 범주

각 범주는 6개 검색식을 사용하며, 수집 목표는 범주당 최대 25건이다.

| 범주 | 주요 검색 주제 |
|---|---|
| 의약품 | 신약·치료제·품목허가, 제네릭·바이오시밀러, 백신·항암제·희귀의약품, 안전성·이상반응, 임상시험 |
| 의약산업 | 제약·바이오 기업, 시장·매출·수출, R&D·투자, CRO·CDMO, 제조, 라이선스 |
| 의약정책 | 약가·약가제도, 건강보험·급여, 약사법·규제, 특허·자료보호, 약가협상·재평가 |
| 의약단체 | KPBMA, KRPIA, 대한약사회, 제약·바이오 및 의약 단체 동향 |
| 의약관련정부기관 | 식약처(MFDS), 의약품 심사·안전, GMP 실사, 회수·수거, FDA 승인·규제 |
| 의료현장 | 병원경영·임상현장, 의료사고·분쟁, 전공의 수련, 의료질·환자경험, 의료진 |
| 약국·약사 | 약국 운영·조제, 복약지도·DUR, 약사 면허·교육, 약국경영·조제료, 일반·전문의약품 |
| 의료정책·인력 | 의료개혁·필수의료, 의사·간호사 인력, 의료법·원격의료, 보건복지부 정책 |
| 전통의학 | 한의사·한의원·한약, 침·약침·추나, 한의약 정책·연구·산업 |
| 감염·보건 | 감염병·항생제 내성·감염관리, 예방접종, 공중보건, 환자안전, 코로나·독감·방역 |

### 3.2 영어권 뉴스 — 6개 범주

각 범주는 4개 검색식을 사용하며, 범주당 최대 25건을 목표로 한다.

- Drugs & Therapies: 신약 승인, 제네릭·바이오시밀러, 백신, 항암·희귀질환, 임상시험
- Pharma Industry: 제약산업, 바이오텍, 시장·투자, CRO·CDMO, 제조, R&D, 파트너십
- Pharma Policy: 약가, 급여, 규제, 특허, IRA 약가협상
- Pharma Associations: PhRMA, EFPIA 등 제약산업 협회
- Regulatory Agencies: FDA, EMA, MHRA, GMP 실사, 의약품 회수, 안전성 경고
- Traditional & Complementary Medicine: 약초·보완의학, Ayurveda, Unani, Siddha, Kampo, TCM, 침술 등

### 3.3 다국어 뉴스 — 20개 언어

프랑스어, 독일어, 스페인어, 이탈리아어, 포르투갈어, 네덜란드어, 스웨덴어, 폴란드어, 터키어, 러시아어, 일본어, 중국어 간체·번체, 베트남어, 태국어, 인도네시아어, 힌디어, 아랍어, 히브리어, 페르시아어를 수집한다.

언어별 검색식은 **의약품·제약산업**과 **전통의학** 2개이며, 언어당 최대 10건을 목표로 한다.

## 4. 필터링·중복 제거·중요도 평가

### 시간 필터

`article_passes_time_policy()`는 발행/갱신 시각 후보를 해석하여 아래 중 하나면 통과시킨다.

- 현재 시점 기준 24시간 이내
- UTC 날짜가 현재 UTC 날짜와 동일

Google RSS 검색어 자체에도 `after:YYYY-MM-DD`가 붙는다. 이중 필터를 통해 오래된 기사를 줄인다.

### 중복 제거

`dedup()`은 아래 두 기준으로만 중복을 제거한다.

1. 동일 URL
2. **같은 출처**에서 제목 정규화 앞 40자가 동일한 기사

서로 다른 언론사가 같은 제목 또는 거의 같은 사건을 보도한 경우에는 제거하지 않는다. 원문 URL을 모두 보존한 뒤, 다음 단계의 이슈 클러스터링이 대표 기사와 관련 링크로 정리한다.

### 이슈 클러스터링과 관련 링크

본문·요약 처리 후 `story_cluster.assign_story_clusters()`가 전체 범주의 기사를 보수적으로 묶는다. 같은 정규화 제목은 같은 이슈로 묶고, 제목이 약간 다른 경우에도 제목 토큰 Jaccard 유사도 0.75 초과·문자열 유사도 0.88 이상·공통 토큰 3개 이상일 때만 묶는다.

- 원문 기사는 삭제하지 않고 모두 `raw.json`에 보존한다.
- 클러스터 대표 기사는 중요도, `fulltext` 확보 여부, 본문 길이 순으로 선정한다.
- 대표 기사에는 `story_id`, `story_primary`, `related_count`, `related_articles`, `cluster_reason`을 기록한다.
- `report.md`는 대표 기사 한 건을 표시하고 그 아래에 관련 언론사의 제목·출처·직접 링크를 모두 표시한다.
- 단순히 `FDA`, `신약`처럼 일반 단어만 겹치는 서로 다른 제품·사건은 묶지 않도록 보수적으로 처리한다.

### 중요도 점수

기사 중요도는 LLM이 아닌 정수 기반 점수(0~100)다.

| 구성 | 최대 점수 |
|---|---:|
| 출처 권위 | 30 |
| 최신성 | 20 |
| 검색 키워드 적중 | 30 |
| 검색 결과 위치 | 20 |

최종적으로 점수 내림차순 정렬 후 범주별 목표 수만 남긴다.

## 5. Google→Bing URL 매칭

Google News RSS의 `news.google.com/rss/articles/CBM...` 주소는 실제 기사 URL이 아니라 중간 주소일 수 있다. 따라서 각 Google RSS 기사는 Bing News에서 제목으로 다시 검색한다.

Bing 후보 점수는 다음과 같다.

| 기준 | 점수 |
|---|---:|
| 제목 유사도 | 최대 60 |
| Google 출처와 Bing 후보의 출처·제목·도메인 일치 | 30 |
| `news.google.com`이 아닌 HTTP(S) 직접 URL | 10 |
| 채택 임계값 | **70점 이상** |

70점 이상 후보만 `url_source: "bing_match"`로 채택한다. 매칭되지 않은 기사는 `url_source: "google_url_fallback"`으로 남기며 직접 URL로 간주하지 않는다.

## 6. 본문·요약 품질 상태

직접 URL 또는 기존 직접 URL에는 정적 HTML 요청을 시도한다. 스크립트는 `script`, `style`, `header`, `footer`, `nav`, `aside` 등을 제거한 뒤 텍스트를 추출하고, 텍스트가 비면 Open Graph·일반 meta description을 보조로 사용한다.

| 필드/상태 | 의미 |
|---|---|
| `url_source=bing_match` | Bing 매칭으로 직접 언론사 URL 확보 |
| `url_source=original_direct` | 처음부터 직접 URL |
| `url_source=google_url_fallback` | Bing 매칭 실패로 Google RSS URL이 남음 |
| `content_status=fulltext` | 제목보다 충분한 길이의 본문 확보 |
| `content_status=title_only` | 본문 확보 실패 또는 제목 수준 텍스트만 존재 |
| `content_status=failed` | URL/본문 처리 실패 |
| `story_id`, `story_primary`, `related_count` | 보존된 원문을 어떤 이슈로 묶었는지와 대표 기사 여부 |
| `related_articles` | 대표 기사에 표시하는 같은 이슈의 다른 언론사 링크 목록 |
| `content_source` | 실제 본문, meta description, snippet, title fallback 등 내용 출처 |

`analysis.md`는 Google URL 잔존 수, 본문 미수집 수, title fallback 수, 필드 존재율, 5줄 요약 분포를 기록한다. `stats.clustering`은 원문 기사 수, 고유 이슈 수, 관련 기사로 묶인 원문 수를 기록한다.

## 7. 산출물과 GitHub 동기화

일일 실행은 `daily/YYYY-MM-DD/`에 아래 파일을 만든다.

| 파일 | 역할 |
|---|---|
| `raw.json` | 모든 기사와 URL·본문·상태·점수의 원본 데이터 |
| `report.md` | 사람용 일일 리포트 |
| `summary.txt` | 간단한 요약 및 GitHub 링크 |
| `daily_summary.json` | 주간·월간 집계용 구조화 데이터 |
| `analysis.md` | 정량 품질 분석 |
| `urls_to_resolve.json` | Google RSS URL이 남은 기사 목록(있는 경우) |

일일 크론은 수집 뒤 `scripts/sync_pharmascope_news.py`를 실행해 일일 산출물을 `WizMasia/pharmascope-news`로 커밋·푸시한다.

## 8. 관련 크론 작업

| 작업 | cron 표현식 | 역할 |
|---|---|---|
| `pharmascope-daily` | `30 6 * * *` | 수집·URL 매칭·본문 추출·품질 카운터 확인·GitHub 동기화 |
| `pharmascope-daily-analysis` | `30 7 * * *` | 일일 산출물을 바탕으로 심층 분석 결과 생성 |
| `pharmascope-weekly` | `0 8 * * 0` | 주간 집계와 서술형 요약 생성(새 수집은 하지 않음) |
| `pharmascope-monthly` | `0 8 1 * *` | 월간 집계와 추세·규제 동향 요약 생성(새 수집은 하지 않음) |

스케줄러가 표시하는 `next_run_at`은 UTC 오프셋을 포함하므로 실제 실행 시각 판단에는 Hermes cron 상태값을 우선한다.

## 9. 운영 확인 절차

일일 작업이 끝나면 다음을 확인한다.

```bash
cd /root/rpi_home_archive/workspace/mywiki/news/pharmascope
python3 - <<'PY'
import json
p = 'daily/YYYY-MM-DD/raw.json'
d = json.load(open(p))
print(d['stats']['enrichment'])
PY
```

최소 확인 항목:

- `bing_attempted`, `bing_matched`, `bing_failed`
- `url_source`별 건수
- `content_status`별 건수
- Google RSS URL 잔존 건수
- `fulltext_ok`
- `urls_to_resolve.json` 존재 여부
- GitHub 동기화 커밋 및 원격 push 결과

## 10. 현재 한계와 해석 원칙

- Bing이 모든 Google 발견 기사를 재색인하지는 않으므로 `google_url_fallback`은 발생할 수 있다.
- 정적 HTML만으로는 JavaScript 렌더링, 유료벽, CAPTCHA, 로그인·지역 제한 기사 본문을 확보하지 못할 수 있다.
- `fulltext`와 `bing_match` 수치를 확인하기 전에는 “모든 기사가 직접 URL” 또는 “100% 본문 확보”라고 표현하지 않는다.
- Google RSS URL·제목 fallback·본문 실패는 숨기지 않고 상태값과 품질 리포트에 남긴다.
