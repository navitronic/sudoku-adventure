#!/usr/bin/env python3
"""Import Sudoku Adventure spreadsheet rows into Hugo posts."""

import argparse
import csv
import io
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

SHEET_URL = "https://docs.google.com/spreadsheets/d/1y4BYBEuXbzReb_tx3bTUdKwynL2JveL3ob55g6c-D-Y/export?format=csv&gid=0"
CONTENT = Path(__file__).resolve().parents[1] / "content" / "puzzles"
REQUIRED = ("Puzzle Number", "Title", "Setter", "Puzzle Link", "Video Link")


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
        return response.read().decode("utf-8")


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
    html = fetch(f"https://www.youtube.com/watch?v={identifier}")
    match = re.search(r'"publishDate":"([^" ]+)"', html)
    if not match:
        raise ValueError(f"Could not find publication time for YouTube video {identifier}")
    date = datetime.fromisoformat(match.group(1))
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
    tags = list(dict.fromkeys(part.strip() for part in row["Constraints"].split(",") if part.strip()))
    identifier = video_id(row["Video Link"])
    # JSON string literals are valid TOML strings for the values used here.
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    fields = [
        f'title = {quote("Puzzle #" + number + " - " + title + " by " + row["Setter"])}',
        f'date = {quote(date)}',
        f'slug = {quote(permalink_slug)}',
        f'tags = {quote(tags)}',
    ]
    if row["alias"]:
        fields.append(f'aliases = ["/{number}/"]')
    puzzle = row["Puzzle Link"]
    parsed = urlparse(puzzle)
    if parsed.scheme != "https" or parsed.hostname not in ("sudokupad.app", "www.sudokupad.app", "beta.sudokupad.app"):
        raise ValueError(f"Invalid SudokuPad link: {puzzle}")
    body = [f'**[Play this puzzle on SudokuPad]({puzzle})**', "", "## Constraints", ""]
    body.extend(f"- {tag}" for tag in tags)
    if not tags:
        body.append("No constraints listed.")
    body.extend(["", "## Video", "", f'{{{{< youtube id="{identifier}" >}}}}', ""])
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
