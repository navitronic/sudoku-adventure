#!/usr/bin/env python3
"""Import Sudoku Adventure spreadsheet rows into Hugo posts."""

import argparse
import csv
import io
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

SHEET_URL = "https://docs.google.com/spreadsheets/d/1y4BYBEuXbzReb_tx3bTUdKwynL2JveL3ob55g6c-D-Y/export?format=csv&gid=0"
PLAYLIST_FEED_URL = "https://www.youtube.com/feeds/videos.xml?playlist_id=PL7B_esJLNuKNhaog5LkEuiBdOXnWxtaFQ"
CONTENT = Path(__file__).resolve().parents[1] / "content" / "puzzles"
REQUIRED = ("Puzzle Number", "Title", "Setter", "Puzzle Link", "Video Link")
CONSTRAINT_ALIASES = json.loads(Path(__file__).with_name("constraint_aliases.json").read_text(encoding="utf-8"))
SETTER_ALIASES = json.loads(Path(__file__).with_name("setter_aliases.json").read_text(encoding="utf-8"))


def normalize_constraints(labels):
    normalized = []
    for label in labels:
        value = CONSTRAINT_ALIASES.get(label.strip(), label.strip())
        normalized.extend(value if isinstance(value, list) else [value])
    return list(dict.fromkeys(label for label in normalized if label))


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
        return response.read().decode("utf-8")


def fetch_json(url, data):
    request = Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def video_id(link):
    parsed = urlparse(link)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        value = parsed.path.strip("/")
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        value = parse_qs(parsed.query).get("v", [""])[0] if parsed.path == "/watch" else parsed.path.removeprefix("/shorts/") if parsed.path.startswith("/shorts/") else ""
    else:
        value = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        raise ValueError(f"Invalid YouTube link: {link}")
    return value


def published_at(identifier):
    urls = (
        f"https://www.youtube.com/watch?v={identifier}&hl=en",
        f"https://m.youtube.com/watch?v={identifier}&hl=en",
    )
    patterns = (
        r'"(?:publishDate|uploadDate)"\s*:\s*"([^" ]+)"',
        r'<meta[^>]+itemprop="(?:datePublished|uploadDate)"[^>]+content="([^" ]+)"',
    )
    value = None
    for url in urls:
        html = fetch(url)
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                value = match.group(1)
                break
        if value:
            break
    if not value:
        feed = ET.fromstring(fetch(PLAYLIST_FEED_URL))
        namespaces = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        for entry in feed.findall("atom:entry", namespaces):
            if entry.findtext("yt:videoId", namespaces=namespaces) == identifier:
                value = entry.findtext("atom:published", namespaces=namespaces)
                break
    if not value:
        player = fetch_json(
            "https://www.youtube.com/youtubei/v1/player",
            {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00", "hl": "en"}}, "videoId": identifier},
        )
        metadata = player.get("microformat", {}).get("playerMicroformatRenderer", {})
        value = metadata.get("publishDate") or metadata.get("uploadDate")
    if not value:
        raise ValueError(f"Could not find publication time for YouTube video {identifier}")
    date = datetime.fromisoformat(value)
    if date.tzinfo is None:
        raise ValueError(f"YouTube publication time has no timezone: {identifier}")
    return date.isoformat()


def slug(text):
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", plain)) or "puzzle"


def rows(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    if not set(REQUIRED + ("Constraints",)).issubset(reader.fieldnames or []):
        raise ValueError("Spreadsheet is missing required columns")
    result = []
    seen = set()
    first_by_number = {}
    for row_number, row in enumerate(reader, 2):
        if not any((row.get(field) or "").strip() for field in REQUIRED):
            continue
        if any(not (row.get(field) or "").strip() for field in REQUIRED):
            raise ValueError(f"Incomplete puzzle on spreadsheet row {row_number}")
        number = row["Puzzle Number"].strip()
        if not number.isdecimal():
            raise ValueError(f"Invalid puzzle number on spreadsheet row {row_number}")
        key = (number, row["Title"].strip(), row["Puzzle Link"].strip())
        if key in seen:
            continue
        seen.add(key)
        row["Puzzle Number"] = number
        row["Title"] = row["Title"].strip()
        row["Setter"] = row["Setter"].strip()
        row["Puzzle Link"] = row["Puzzle Link"].strip()
        row["Video Link"] = row["Video Link"].strip()
        row["alias"] = number not in first_by_number
        first_by_number.setdefault(number, key)
        result.append(row)
    return result


def post(row, date, permalink_slug):
    number = row["Puzzle Number"]
    title = row["Title"]
    constraints = normalize_constraints(row["Constraints"].split(","))
    identifier = video_id(row["Video Link"])
    puzzle = row["Puzzle Link"]
    parsed = urlparse(puzzle)
    if parsed.scheme != "https" or parsed.hostname not in ("sudokupad.app", "www.sudokupad.app", "beta.sudokupad.app"):
        raise ValueError(f"Invalid SudokuPad link: {puzzle}")
    # JSON string literals are valid TOML strings for the values used here.
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    fields = [
        f'title = {quote("Puzzle #" + number + " - " + title + " by " + row["Setter"])}',
        f'date = {quote(date)}',
        f'slug = {quote(permalink_slug)}',
        f'constraints = {quote(constraints)}',
        f'setters = [{quote(SETTER_ALIASES.get(row["Setter"], row["Setter"]))}]',
        f'puzzle_url = {quote(puzzle)}',
    ]
    if row["alias"]:
        fields.append(f'aliases = ["/{number}/"]')
    body = [f'**[Play this puzzle on SudokuPad]({puzzle})**', "", "## Constraints", "", "{{< constraint-links >}}", "", "## Video", "", f'{{{{< youtube id="{identifier}" >}}}}', ""]
    return "+++\n" + "\n".join(fields) + "\n+++\n\n" + "\n".join(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("import", "append"))
    parser.add_argument("--csv", type=Path, help="Read a local CSV instead of downloading the spreadsheet")
    parser.add_argument("--content", type=Path, default=CONTENT, help="Hugo puzzle content directory")
    args = parser.parse_args()
    source = args.csv.read_text(encoding="utf-8-sig") if args.csv else fetch(SHEET_URL)
    puzzles = rows(source)
    paths = []
    used_slugs = set()
    for row in puzzles:
        base = f'{row["Puzzle Number"]}-{slug(row["Title"])}'
        permalink_slug = base
        suffix = 2
        while permalink_slug in used_slugs:
            permalink_slug = f"{base}-{suffix}"
            suffix += 1
        used_slugs.add(permalink_slug)
        paths.append((row, args.content / f"{permalink_slug}.md", permalink_slug))
    created = 0
    for row, path, permalink_slug in reversed(paths) if args.mode == "append" else paths:
        if path.exists():
            if args.mode == "append":
                break
            continue
        date = published_at(video_id(row["Video Link"]))
        text = post(row, date, permalink_slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidental overwrites on repeat runs.
        with path.open("x", encoding="utf-8") as output:
            output.write(text)
        created += 1
    print(f"Created {created} posts")


if __name__ == "__main__":
    main()
