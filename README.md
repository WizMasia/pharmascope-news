# 🔬 PharmaScope — 의약업계 글로벌 동향

**마지막 갱신:** 2026-06-19 09:04 KST
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
│   └── 2026-06-19/
│       ├── report.md
│       └── raw.json
└── AGENTS.md
```

*PharmaScope v3 — Adapter Pattern | 정수 중요도 | 다중 소스 하이브리드*
