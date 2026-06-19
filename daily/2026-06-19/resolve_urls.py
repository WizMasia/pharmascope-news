#!/usr/bin/env python3
"""Resolve Google News RSS CBM URLs to actual article URLs using HTTP redirect following."""
import json
import urllib.request
import urllib.error
import ssl
import time
import sys

INPUT_FILE = "/home/wizmasia/workspace/mywiki/news/pharmascope/daily/2026-06-19/resolve_v3_batch_0.json"
OUTPUT_FILE = "/home/wizmasia/workspace/mywiki/news/pharmascope/daily/2026-06-19/resolve_v3_batch_0_output.json"

# Load input
with open(INPUT_FILE, "r") as f:
    data = json.load(f)

articles = data["articles"]
results = []

# Create SSL context that doesn't verify (some sites have cert issues)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

for article in articles:
    idx = article["idx"]
    cbm_id = article["cbm_id"]
    rss_url = article["rss_url"]
    title = article["title"]
    
    print(f"[{idx}] Resolving: {rss_url[:80]}...", flush=True)
    
    actual_url = None
    final_title = title  # fallback to input title
    
    try:
        req = urllib.request.Request(
            rss_url,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        actual_url = resp.geturl()  # Final URL after all redirects
        
        # Try to extract title from HTML
        html = resp.read(65536)  # Read up to 64KB
        # Simple title extraction
        try:
            html_str = html.decode("utf-8", errors="replace")
            import re
            m = re.search(r'<title[^>]*>(.*?)</title>', html_str, re.IGNORECASE | re.DOTALL)
            if m:
                extracted = m.group(1).strip()
                if extracted:
                    final_title = extracted
        except:
            pass
            
        print(f"  -> {actual_url}")
        print(f"  -> Title: {final_title[:80]}...")
        
    except Exception as e:
        print(f"  ERROR: {e}", flush=True)
        # If redirect fails, maybe try with the 'url' field (without extra params)
        try:
            fallback_url = article.get("url", rss_url)
            req = urllib.request.Request(
                fallback_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                }
            )
            resp = urllib.request.urlopen(req, timeout=30, context=ctx)
            actual_url = resp.geturl()
            html = resp.read(65536)
            try:
                html_str = html.decode("utf-8", errors="replace")
                import re
                m = re.search(r'<title[^>]*>(.*?)</title>', html_str, re.IGNORECASE | re.DOTALL)
                if m:
                    extracted = m.group(1).strip()
                    if extracted:
                        final_title = extracted
            except:
                pass
            print(f"  -> (fallback) {actual_url}")
        except Exception as e2:
            print(f"  FALLBACK ERROR: {e2}", flush=True)
            actual_url = rss_url
    
    results.append({
        "idx": idx,
        "cbm_id": cbm_id,
        "actual_url": actual_url or rss_url,
        "title": final_title
    })
    
    # Small delay to be polite
    time.sleep(1)

# Write output
with open(OUTPUT_FILE, "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\nDone! Wrote {len(results)} results to {OUTPUT_FILE}")
