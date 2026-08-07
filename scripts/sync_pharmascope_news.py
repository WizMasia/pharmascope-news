#!/usr/bin/env python3
"""
PharmaScope — mywiki → pharmascope-news GitHub 동기화
=======================================================
daily/weekly/monthly 데이터를 pharmascope-news 저장소로 복사하고
README.md를 자동 갱신한 후 GitHub에 push합니다.

사용법:
    python3 scripts/sync_pharmascope_news.py              # 오늘 날짜
    python3 scripts/sync_pharmascope_news.py --date=2026-06-22
    python3 scripts/sync_pharmascope_news.py --message="[Deep Analysis] 2026-06-22"
"""
import os, sys, json, subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

REAL_HOME = os.path.expanduser("~")
MYWIKI_BASE = os.path.join(REAL_HOME, "workspace/mywiki/news/pharmascope")
PHARMA_NEWS = os.path.join(REAL_HOME, "workspace/pharmascope-news")
KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)

def log(msg):
    print(f"[{NOW.strftime('%H:%M:%S')}] {msg}")

def parse_args():
    args = {}
    for a in sys.argv[1:]:
        if a.startswith('--date='):
            args['date'] = a.split('=', 1)[1]
        elif a.startswith('--message='):
            args['message'] = a.split('=', 1)[1]
    return args

def get_daily_dirs(base, target_date=None):
    """Get list of daily dirs, optionally filtered by date."""
    daily = os.path.join(base, 'daily')
    if not os.path.isdir(daily):
        return []
    if target_date:
        d = os.path.join(daily, target_date)
        return [d] if os.path.isdir(d) else []
    return sorted([os.path.join(daily, d) for d in os.listdir(daily)
                   if os.path.isdir(os.path.join(daily, d))], reverse=True)

def get_weekly_dirs(base):
    w = os.path.join(base, 'weekly')
    if not os.path.isdir(w):
        return []
    return sorted([os.path.join(w, d) for d in os.listdir(w)
                   if os.path.isdir(os.path.join(w, d))], reverse=True)

def copy_to_pharmanews(src_dir, dest_base, rel_subdir):
    """Copy files from mywiki to pharmascope-news, preserving relative path."""
    date_or_week = os.path.basename(src_dir)
    dest_dir = os.path.join(dest_base, rel_subdir, date_or_week)
    os.makedirs(dest_dir, exist_ok=True)
    for fname in os.listdir(src_dir):
        src = os.path.join(src_dir, fname)
        if os.path.isfile(src):
            dst = os.path.join(dest_dir, fname)
            with open(src, 'rb') as sf:
                with open(dst, 'wb') as df:
                    df.write(sf.read())
    log(f"  ✅ 복사: {rel_subdir}/{date_or_week}/ ({len(os.listdir(src_dir))}개 파일)")

def update_readme(pharma_news_dir):
    """Update README.md with latest stats."""
    daily_dir = os.path.join(pharma_news_dir, 'daily')
    recent_days = []
    if os.path.isdir(daily_dir):
        days = sorted([d for d in os.listdir(daily_dir)
                       if os.path.isdir(os.path.join(daily_dir, d))], reverse=True)[:14]
        for d in days:
            summary_path = os.path.join(daily_dir, d, 'daily_summary.json')
            analysis_path = os.path.join(daily_dir, d, 'analysis.md')
            if os.path.exists(summary_path):
                with open(summary_path) as f:
                    summary = json.load(f)
                kr = summary.get('korean', {}).get('total', 0)
                en = summary.get('english', {}).get('total', 0)
                ml = summary.get('multilingual', {}).get('total', 0)
                total = summary.get('total', kr + en + ml)
                has_analysis = ' ✅' if os.path.exists(analysis_path) else ''
                recent_days.append((d, kr, en, ml, total, has_analysis))

    today_stats = recent_days[0] if recent_days else ('-', 0, 0, 0, 0, '')
    kr_total = sum(d[1] for d in recent_days)
    en_total = sum(d[2] for d in recent_days)
    ml_total = sum(d[3] for d in recent_days)

    readme_content = f"""# 🔬 PharmaScope — 의약업계 글로벌 동향 수집

**마지막 갱신:** {NOW.strftime('%Y-%m-%d %H:%M')} KST  
**소스:** Bing News (직접 URL, CBM 0건)  
**평가:** 정수 중요도 0~100 (⭐~⭐⭐⭐⭐⭐)

---

## 오늘의 수집 요약 ({today_stats[0]})

| 🇰🇷 한국어 | 🌐 영어 | 🌏 다국어 | 총계 |
|:---------:|:-------:|:---------:|:----:|
| {today_stats[1]}건 | {today_stats[2]}건 | {today_stats[3]}건 | **{today_stats[4]}건** |

📄 [전체 리포트 보기](daily/{today_stats[0]}/report.md){today_stats[5]}

---

## 최근 수집 현황

| 날짜 | 🇰🇷 | 🌐 | 🌏 | 총계 | 분석 |
|:----:|:--:|:--:|:--:|:---:|:----:|
"""
    for d, kr, en, ml, total, has_analysis in recent_days:
        readme_content += f"| [{d}](daily/{d}/report.md) | {kr} | {en} | {ml} | **{total}** |{has_analysis}|\n"

    readme_content += f"""
---

## 통계

| 항목 | 값 |
|------|:---:|
| 최근 14일 총계 | {kr_total + en_total + ml_total}건 |
| 🇰🇷 한국어 | {kr_total}건 |
| 🌐 영어 | {en_total}건 |
| 🌏 다국어 | {ml_total}건 |
| 소스 | Bing News HTML (직접 URL) |
| 수집 시간 | 매일 06:30 KST |
| 분석 시간 | 매일 07:30 KST |

---

*PharmaScope v4 — Bing Only (100% Direct URLs, No CBM)*
"""
    readme_path = os.path.join(pharma_news_dir, 'README.md')
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    log(f"  ✅ README.md 갱신 완료 ({len(readme_content)}자)")

def git_push(pharma_news_dir, message):
    """Git add-commit-push to pharmascope-news only."""
    ALLOWED_ORIGIN = 'https://github.com/WizMasia/pharmascope-news.git'
    try:
        # 1) stage
        subprocess.run(['git', 'add', '-A'], cwd=pharma_news_dir, capture_output=True, text=True, timeout=30)
        diff = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=pharma_news_dir, capture_output=True, timeout=30)
        if diff.returncode == 0:
            log("  📎 No new changes to pharmascope-news")
            return

        # 2) check upstream branch
        upstream = subprocess.run(['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'], cwd=pharma_news_dir,
                                 capture_output=True, text=True)
        if upstream.returncode != 0:
            log("  ⚠️ Upstream is not set for pharmascope-news/main. Run: git branch --set-upstream-to=origin/main main")
            return

        # 3) enforce GitHub whitelist
        origin_url = subprocess.run(['git', 'config', '--get', 'remote.origin.url'], cwd=pharma_news_dir,
                                   capture_output=True, text=True).stdout.strip()
        if origin_url != ALLOWED_ORIGIN:
            log(f"  ⚠️ Origin whitelist mismatch: {origin_url}")
            return

        # 4) detect ahead/behind
        upstream_ref = upstream.stdout.strip()
        cmp = subprocess.run(
            ['git', 'rev-list', '--left-right', '--count', f'HEAD...{upstream_ref}'],
            cwd=pharma_news_dir, capture_output=True, text=True, timeout=30
        )
        if cmp.returncode == 0:
            raw = (cmp.stdout or '').strip().split()
            ahead, behind = map(int, raw[:2]) if len(raw) >= 2 else (0, 0)
            log(f"  📏 Ahead/Behind vs {upstream_ref}: {ahead}/{behind}")
            if behind > 0:
                log("  ⚠️ 로컬에 뒤처짐(behind) 존재 — pull/rebase 필요")
                return
            if ahead == 0:
                log("  ℹ️ No local-only commits before staged data commit")

        commit = subprocess.run(['git', 'commit', '-m', message], cwd=pharma_news_dir, capture_output=True, text=True, timeout=30)
        if commit.returncode != 0:
            log(f"  ⚠️ git commit 실패: {commit.stderr.strip()}")
            return

        log(f"  ✅ git commit (pharmascope-news)")
        push = subprocess.run(['git', 'push', 'origin', 'main'], cwd=pharma_news_dir, capture_output=True, text=True, timeout=30)
        if push.returncode == 0:
            log(f"  ✅ git push to GitHub (pharmascope-news)")
        else:
            log(f"  ⚠️ git push 실패: {push.stderr.strip()}")
    except Exception as e:
        log(f"  ⚠️ Git error: {e}")

def main():
    args = parse_args()
    target_date = args.get('date')
    commit_msg = args.get('message', f'🚀 PharmaScope {target_date or NOW.strftime("%Y-%m-%d")} — 수집 동기화')

    log(f"🔄 PharmaScope → pharmascope-news 동기화")

    # 1. Check repos exist
    if not os.path.isdir(MYWIKI_BASE):
        log(f"❌ mywiki pharmascope base not found: {MYWIKI_BASE}")
        sys.exit(1)
    if not os.path.isdir(PHARMA_NEWS):
        log(f"❌ pharmascope-news not found: {PHARMA_NEWS}")
        sys.exit(1)

    # 2. Copy daily data
    daily_dirs = get_daily_dirs(MYWIKI_BASE, target_date)
    log(f"📋 일일 데이터: {len(daily_dirs)}개 디렉토리")
    for d in daily_dirs:
        copy_to_pharmanews(d, PHARMA_NEWS, 'daily')

    # 3. Copy weekly data
    weekly_dirs = get_weekly_dirs(MYWIKI_BASE)
    log(f"📋 주간 데이터: {len(weekly_dirs)}개 디렉토리")
    for w in weekly_dirs:
        copy_to_pharmanews(w, PHARMA_NEWS, 'weekly')

    # 4. Update README
    log("📝 README.md 갱신 중...")
    update_readme(PHARMA_NEWS)

    # 5. Git push
    log("📤 GitHub push 중...")
    git_push(PHARMA_NEWS, commit_msg)

    log("🎉 동기화 완료!")

if __name__ == '__main__':
    main()
