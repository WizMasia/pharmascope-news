# 📄 PharmaScope Paper Pipeline — 계획서 (DRAFT)

## 개요

PharmaScope가 매일 수집한 의약업계 뉴스 기사에서 **키워드를 추출**하여,
관련 **학술 논문**을 PubMed/CrossRef/arXiv 등에서 검색, 일일 논문 리포트 생성.

---

## 아키텍처

```
PharmaScope Daily Collection
         │
         ▼
    뉴스 기사 (raw.json)
         │
         ▼
    [Phase A] 키워드 추출
    ┌─────────────────────┐
    │  각 기사 title +     │
    │  snippet → LLM      │
    │  키워드 3~5개 추출   │
    └─────────┬───────────┘
              │
              ▼
    [Phase B] 논문 검색 (병렬)
    ┌──────────┬──────────┬──────────┐
    │ PubMed   │CrossRef  │ arXiv    │
    │ REST API │ REST API │ REST API │
    └────┬─────┴────┬────┴────┬─────┘
         │          │        │
         ▼          ▼        ▼
    논문 메타데이터 수집 (title, author, journal, DOI, abstract)
         │
         ▼
    [Phase C] 중복 제거 + 랭킹
    ┌─────────────────────────┐
    │  DOI 기준 중복 제거      │
    │  관련성 점수 매기기      │
    │  상위 10~15편 선정       │
    └──────────┬──────────────┘
               │
               ▼
    [Phase D] 일일 논문 리포트 생성
    ┌─────────────────────────┐
    │  논문 제목 (한글 번역)   │
    │  저자 · 저널 · DOI 링크 │
    │  초록 요약 (2~3문장)    │
    │  관련 뉴스 기사 링크    │
    └─────────────────────────┘
```

---

## 상세 설계

### Phase A — 키워드 추출

**방식:** Python (NLP) + LLM

| 방법 | 설명 | 비고 |
|------|------|------|
| **1차:** 기사 title + snippet → LLM | 각 기사당 3~5개 키워드 추출 | `delegate_task` 병렬 처리 |
| **2차:** 중복 키워드 병합 | 전체 기사 키워드 집계, 빈도순 정렬 | Python dict |
| **3차:** PubMed Mesh/Query 변환 | 키워드 → PubMed 검색어 포맷팅 | `"drug"[Mesh] AND "2026"[Date]` |

**LLM 비용 절감:** 기사가 많을 경우 상위 20개 기사만 키워드 추출 대상

### Phase B — 논문 검색

**API 후보:**

| 저장소 | API | 제한 | 비고 |
|--------|-----|------|------|
| **PubMed** | E-utilities (esummary/esearch) | 10 req/s | 무료, 생의학 최적 |
| **CrossRef** | REST API | 50 req/s | 모든 학술지, DOI 확보 |
| **arXiv** | API | 1 req/3s | CS/AI/수학, 일부 의약 |
| **OpenAlex** | REST API | 100k req/day | 오픈 학술 그래프 |
| **Semantic Scholar** | REST API | 100 req/s | AI 기반 관련성 점수 |

**추천 조합:**
- PubMed + CrossRef (의약 업계에 최적)
- arXiv (컴퓨터공학/약물 발견 관련)
- 필요시 Semantic Scholar (관련성 순 정렬)

**검색 전략:**
```
키워드 1개당 1회 API 호출 → 최대 5개 키워드 × 3개 저장소 = 15회 API 호출
결과 합산 → DOI 기준 중복 제거
```

### Phase C — 중복 제거 + 랭킹

```python
# 의사코드
papers = []
for source in [pubmed, crossref, arxiv]:
    papers.extend(search(keyword, source))

# 중복 제거 (DOI 기준)
seen_dois = set()
unique = []
for p in sorted(papers, key=lambda x: x['score'], reverse=True):
    if p['doi'] not in seen_dois:
        seen_dois.add(p['doi'])
        unique.append(p)

# 상위 15편 선택
return unique[:15]
```

### Phase D — 리포트 생성

**포맷:**
```markdown
## 📄 오늘의 논문 (YYYY-MM-DD)

관련 뉴스 기사: N건 → 추출 키워드: keyword1, keyword2, ...

### 🔬 주요 논문

1. **논문 제목** (번역: 한글 제목)
   👤 저자 외 3인 | 📰 Nature (2026)
   🔗 DOI: 10.xxxx/xxxxx
   📋 초록: ... (2~3문장 요약)
   📎 관련 기사: [기사제목](./daily/.../report.md)

...
```

---

## 구현 우선순위

| 단계 | 작업 | 예상 시간 | 의존성 |
|------|------|-----------|--------|
| 1 | 키워드 추출 모듈 (LLM + Python) | 1일 | pharmascope_collect.py |
| 2 | PubMed API 연동 | 0.5일 | NCBI API 키 (선택) |
| 3 | CrossRef API 연동 | 0.5일 | 없음 (무료) |
| 4 | 중복 제거 + 랭킹 | 0.5일 | Phase 1~3 완료 |
| 5 | 리포트 생성 + 저장 | 0.5일 | Phase 4 완료 |
| 6 | Telegram 전달 포맷팅 | 0.5일 | Phase 5 완료 |
| 7 | 크론잡 통합 | 0.5일 | 전체 완료 |

**총 예상:** 3~4일

---

## 저장 구조

```bash
~/workspace/mywiki/news/pharmascope/
├── daily/YYYY-MM-DD/
│   ├── report.md          # (기존) 뉴스 리포트
│   ├── raw.json           # (기존) 원시 뉴스 데이터
│   └── papers.md          # (신규) 논문 리포트
├── scripts/
│   ├── pharmascope_collect.py
│   ├── pharmascope_papers.py   # (신규) 논문 수집기
│   └── pharmascope_aggregate.py
└── README.md
```

---

## 리스크

| 리스크 | 대응 |
|--------|------|
| PubMed API rate limit | 지연(retry) + 캐싱 |
| 논문과 뉴스의 관련성 부족 | 키워드 정밀도 튜닝, LLM 관련성 필터 |
| API 키 필요 (NCBI) | 공개 API로도 가능 (3 req/s) |
| 수집 시간 증가 (현재 5분 → 7~8분) | 병렬 API 호출로 최소화 |
