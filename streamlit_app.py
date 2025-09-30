"""
SHiFT Code Finder + Streamlit UI

This improved app actively scrapes configured public tracker sites, extracts SHiFT codes,
checks their likely status (ACTIVE/EXPIRED/UNKNOWN) using keywords, deduplicates them, and presents them as easy-to-copy lists.
"""

import re
import io
import time
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd

# ---------------------- Configuration ----------------------
REQUEST_TIMEOUT = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ShiftFinder/2.0; +https://github.com/yourrepo)",
}

TRACKERS = [
    "https://mentalmars.com/tag/shift-codes/",
    "https://shiftcodestk.com/",
    "https://game8.co/games/Borderlands-4/archives/",
    "https://www.reddit.com/r/Borderlands/comments/",
]

CODE_RE = re.compile(r"[A-Z0-9]{5}(?:[- ]?[A-Z0-9]{5}){4}|[A-Z0-9]{25}", re.IGNORECASE)

# ---------------------- Helpers ----------------------

def normalize_code(s: str) -> str:
    s = s.strip().upper()
    chars = re.sub(r"[^A-Z0-9]", "", s)
    if len(chars) == 25:
        parts = [chars[i:i+5] for i in range(0, 25, 5)]
        return "-".join(parts)
    m = re.search(r"([A-Z0-9]{5})[- ]?([A-Z0-9]{5})[- ]?([A-Z0-9]{5})[- ]?([A-Z0-9]{5})[- ]?([A-Z0-9]{5})", s)
    if m:
        return "-".join(m.groups())
    return chars


def fetch_page(url: str) -> Tuple[str, str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return url, r.text
    except Exception:
        return url, ""


def extract_codes_and_status_from_html(html: str) -> List[Dict[str, str]]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")
    found = CODE_RE.findall(text)

    results = []
    text_lower = text.lower()
    for f in found:
        code = normalize_code(f)
        idx = text_lower.find(code.lower())
        snippet = text_lower[idx:idx+200] if idx != -1 else ""
        if "expired" in snippet:
            status = "EXPIRED"
        elif "active" in snippet or "valid" in snippet:
            status = "ACTIVE"
        else:
            status = "UNKNOWN"
        results.append({"code": code, "status": status})
    return results


def scan_trackers(urls: List[str], max_workers: int = 6) -> Dict[str, List[Dict[str, str]]]:
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch_page, url): url for url in urls}
        for fut in as_completed(futures):
            url = futures[fut]
            try:
                _, html = fut.result()
            except Exception:
                html = ""
            codes_with_status = extract_codes_and_status_from_html(html)
            results[url] = codes_with_status
            time.sleep(0.1)
    return results

# ---------------------- Streamlit UI ----------------------

def main():
    st.set_page_config(page_title="SHiFT Code Finder", layout="wide")
    st.title("SHiFT Code Finder — Streamlit")

    st.markdown("""
        This app **finds SHiFT codes** by scraping public tracker pages and estimating status.
        Codes are deduplicated and shown as an easy-to-copy list. Use responsibly.
    """)

    st.sidebar.header("Settings")
    workers = st.sidebar.slider("Concurrent workers", 2, 20, 6)
    add_url = st.sidebar.text_input("Add custom tracker URL")
    seed_urls = st.sidebar.text_area("Tracker URLs (one per line)", value="\n".join(TRACKERS), height=180)

    urls = [u.strip() for u in seed_urls.splitlines() if u.strip()]
    if add_url:
        urls.append(add_url.strip())

    if st.button("Scan trackers now"):
        with st.spinner("Scanning trackers..."):
            scanned = scan_trackers(urls, max_workers=workers)

        rows = []
        for url, items in scanned.items():
            for item in items:
                rows.append({"source": url, "code": item["code"], "status": item["status"]})

        df = pd.DataFrame(rows).drop_duplicates().sort_values(by=["code"])

        col1, col2 = st.columns([2, 1])
        with col1:
            st.subheader(f"Found codes ({len(df)})")
            st.dataframe(df)

            st.markdown("**Deduplicated list with status**")
            dedup = df.drop_duplicates(subset=["code"]).sort_values("code")
            output = "\n".join([f"{row.code} ({row.status})" for _, row in dedup.iterrows()])
            st.code(output or "(none)")

            buf = io.StringIO()
            df.to_csv(buf, index=False)
            st.download_button("Download CSV", buf.getvalue(), file_name="shift_found_codes.csv")

        with col2:
            st.subheader("Tracker summary")
            for url, items in scanned.items():
                st.markdown(f"- {url} — {len(items)} codes")

            st.markdown("---")
            st.markdown("**Notes**")
            st.markdown(
                "- This tool collects codes from public tracker pages only.\n- It does NOT redeem codes or sign into SHiFT accounts.\n- Status is estimated from nearby keywords."
            )

if __name__ == '__main__':
    main()