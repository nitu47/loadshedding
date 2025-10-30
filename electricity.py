"""
fetch_and_build_real_data.py

- Downloads NEA announcement PDFs (best-effort).
- Extracts text with pdfplumber.
- Attempts to parse load-shedding schedules into rows:
    date, start_time, end_time, district, affected_area, reason
- Writes data/loadshedding_real.csv
- Falls back to synthetic sample if nothing parseable found.

References: NEA homepage and supportive docs where schedules are published.
"""
import os
import re
import requests
import pdfplumber
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import pandas as pd
from tqdm import tqdm
from datetime import datetime, timedelta
from dateutil.parser import parse as dateparse

BASE_NEA = "https://www.nea.org.np/"
DATA_DIR = "data"
OUT_CSV = os.path.join(DATA_DIR, "loadshedding_real.csv")
SAMPLE_FALLBACK = os.path.join(DATA_DIR, "loadshedding_sample.csv")
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {"User-Agent": "LoadsheddingScraper/1.0 (+https://example)"}

# -------------------------
#  Utilities
# -------------------------
def fetch_page(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text

def find_pdf_links_from_nea_home():
    """
    Go to NEA homepage and look for links to PDFs or announcements.
    This picks up supportive_docs and other PDF links.
    """
    try:
        html = fetch_page(BASE_NEA)
    except Exception as e:
        print("Failed to fetch NEA homepage:", e)
        return []
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Accept absolute or relative pdf links
        if href.lower().endswith(".pdf"):
            links.append(urljoin(BASE_NEA, href))
    # Also try predictable supportive_docs folder
    # (observed path used on NEA site in example PDF)
    support_url = urljoin(BASE_NEA, "/admin/assets/uploads/supportive_docs/")
    # Attempt listing (may 404 if directory listing disabled)
    try:
        html2 = fetch_page(support_url)
        soup2 = BeautifulSoup(html2, "html.parser")
        for a in soup2.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf"):
                links.append(urljoin(support_url, href))
    except Exception:
        # ignore
        pass
    # deduplicate
    unique = []
    for u in links:
        if u not in unique:
            unique.append(u)
    return unique

def download_pdf(url, dest_folder="data/pdfs"):
    os.makedirs(dest_folder, exist_ok=True)
    parsed = urlparse(url)
    name = os.path.basename(parsed.path)
    dest = os.path.join(dest_folder, name)
    if os.path.exists(dest):
        return dest
    print("Downloading", url)
    r = requests.get(url, headers=HEADERS, stream=True, timeout=30)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return dest

# -------------------------
#  PDF text extraction
# -------------------------
def extract_text_from_pdf(path):
    texts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                texts.append(t)
    except Exception as e:
        print("pdfplumber failed for", path, ":", e)
    return "\n\n".join(texts)

# -------------------------
#  Parsing heuristics
# -------------------------
# This block implements multiple regex attempts to find schedules.
_DATE_PAT = r"(?:(?:\d{4}[-/]\d{1,2}[-/]\d{1,2})|(?:\d{1,2}[-/]\w+[-/]\d{4})|(?:\d{1,2}\s+\w+\s+\d{4}))"
_TIME_PAT = r"(?:[01]?\d|2[0-3])[:.][0-5]\d"
# Common pair like "06:00-09:00" or "06:00 - 09:00"
#_TIME_RANGE = rf"({TIME_PAT})\s*[-–to]{1,3}\s*({TIME_PAT})"
_TIME_RANGE = rf"({_TIME_PAT})\s*[-–to]{1,3}\s*({_TIME_PAT})"

# lines like "Kathmandu: 06:00-09:00, 18:00-22:00"
_DIST_LINE = re.compile(rf"(?P<district>[A-Za-z\u0900-\u097F\s/-]+)[:\-]\s*(?P<times>.+)", re.UNICODE)

def parse_schedule_text(text):
    """
    Attempt to parse schedule text into rows.
    Heuristics:
      - find dates in text, then find lines nearby with districts and time ranges.
      - capture multiple ranges per district by splitting on commas/semicolon.
    Returns list of dict rows.
    """
    rows = []
    if not text or len(text) < 20:
        return rows
    # Split into paragraphs
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    for para in paragraphs:
        # find a date anchor in the paragraph or preceding lines
        date_match = re.search(_DATE_PAT, para)
        if date_match:
            # try to parse date text
            date_str = date_match.group(0)
            try:
                base_date = dateparse(date_str, dayfirst=True).date()
            except Exception:
                base_date = None
        else:
            # try to find date in previous sentence inside huge para
            base_date = None

        # split paragraph into lines and scan for district: times
        lines = [l.strip() for l in re.split(r"[\n\r]+", para) if l.strip()]
        for line in lines:
            m = _DIST_LINE.match(line)
            if m:
                district = m.group("district").strip()
                times_part = m.group("times")
                # split possible multiple ranges separated by comma / ;
                parts = re.split(r"[;,]| and ", times_part)
                for p in parts:
                    p = p.strip()
                    tr = re.search(_TIME_RANGE, p)
                    if tr:
                        st, et = tr.group(1), tr.group(2)
                        # if date found, use it; otherwise leave None (later we'll try to infer)
                        rows.append({
                            "date": base_date.isoformat() if base_date else None,
                            "start_time": st.replace(".", ":"),
                            "end_time": et.replace(".", ":"),
                            "district": district,
                            "affected_area": "",
                            "reason": "published_notice"
                        })
            else:
                # fallback: detect explicit time ranges with no district
                for tr in re.finditer(_TIME_RANGE, line):
                    st, et = tr.group(1), tr.group(2)
                    rows.append({
                        "date": base_date.isoformat() if base_date else None,
                        "start_time": st.replace(".", ":"),
                        "end_time": et.replace(".", ":"),
                        "district": "",
                        "affected_area": "",
                        "reason": "published_notice"
                    })
    # post-process: try to fill missing dates by propagating nearest found date in text
    # Extract dates from whole text in order and their positions
    date_positions = []
    for m in re.finditer(_DATE_PAT, text):
        try:
            d = dateparse(m.group(0), dayfirst=True).date()
            date_positions.append((m.start(), d))
        except Exception:
            continue
    if date_positions:
        # for every row with no date, try to find nearest date anchor by searching position of occurrence
        for i, r in enumerate(rows):
            if r["date"] is None:
                # find nearest date by naive approach: assign first date found
                rows[i]["date"] = date_positions[0][1].isoformat()
    # remove obviously invalid rows
    cleaned = []
    for r in rows:
        if r.get("start_time") and r.get("end_time"):
            cleaned.append(r)
    return cleaned

# -------------------------
#  High-level flow
# -------------------------
def build_from_nea():
    print("Scanning NEA for PDFs...")
    pdf_links = find_pdf_links_from_nea_home()
    if not pdf_links:
        print("No PDF links discovered automatically on NEA home. Trying known supportive_docs path...")
        pdf_links = [urljoin(BASE_NEA, "/admin/assets/uploads/supportive_docs/60896609.pdf")]
    downloaded = []
    for url in pdf_links:
        try:
            p = download_pdf(url)
            downloaded.append(p)
        except Exception as e:
            print("Failed to download", url, ":", e)
    all_rows = []
    for pdf_path in downloaded:
        print("Extracting text from:", pdf_path)
        text = extract_text_from_pdf(pdf_path)
        rows = parse_schedule_text(text)
        if rows:
            print(f"Parsed {len(rows)} rows from {os.path.basename(pdf_path)}")
            all_rows.extend(rows)
        else:
            print("No parseable rows in", pdf_path)
    # write CSV if we have anything
    if all_rows:
        df = pd.DataFrame(all_rows)
        # normalize date/time and expand multi-day if needed (basic)
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        df = df.dropna(subset=["date"])
        df.to_csv(OUT_CSV, index=False)
        print("Wrote", OUT_CSV)
        return True
    else:
        print("No valid schedule rows parsed from NEA PDFs.")
        return False

# -------------------------
#  Fallback: generate sample if nothing found
# -------------------------
def generate_sample(path=SAMPLE_FALLBACK, days=180):
    print("Generating fallback synthetic sample:", path)
    base = datetime(2024,1,1)
    districts = ["Kathmandu","Lalitpur","Bhaktapur","Nuwakot","Chitwan"]
    records = []
    import random
    random.seed(42)
    for i in range(days):
        date = base + timedelta(days=i)
        for _ in range(random.randint(1,3)):
            district = random.choice(districts)
            start = random.randint(6,21)
            dur = round(random.uniform(1.0,4.0),1)
            end = (start + dur) % 24
            records.append({
                "date": date.date().isoformat(),
                "start_time": f"{int(start):02d}:00",
                "end_time": f"{int(end):02d}:00",
                "district": district,
                "affected_area": "",
                "reason": "synthetic"
            })
    pd.DataFrame(records).to_csv(path, index=False)
    print("Sample written:", path)
    return path

if __name__ == "__main__":
    ok = False
    try:
        ok = build_from_nea()
    except Exception as e:
        print("Exception during NEA fetch:", e)
    if not ok:
        # fallback to synthetic sample so downstream app continues working
        sample = generate_sample()
        # copy fallback to loadshedding_real.csv
        df = pd.read_csv(sample)
        df.to_csv(OUT_CSV, index=False)
        print("Fallback CSV created at", OUT_CSV)
