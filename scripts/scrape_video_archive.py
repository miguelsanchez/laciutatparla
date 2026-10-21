#!/usr/bin/env python3
"""Scrape the city's video archive and map each recording to its plenary session.

The session pages on valencia.es no longer publish the per-session recording link:
they only embed the generic live player, so the recordings are unrecoverable from
there. They are still listed in the video archive, one page per year:

    https://aytovlc.web.enetres.net/va/plens/plens{YY}     (YY = 11..26, paginated ?p=N)

This script scrapes those pages, parses the date out of each video title, matches
videos to sessions, and writes the unambiguous matches to

    data/corrections/session_videos.yml

which script 07 overlays on top of the scraped session metadata. Ambiguous days are
reported but never guessed: they belong in the YAML only after a human decides.

Usage:
    python3 scrape_video_archive.py            # scrape, then match
    python3 scrape_video_archive.py --offline  # reuse data/raw/video_archive.json
    python3 scrape_video_archive.py --dry-run  # report only, do not write the YAML
"""
from __future__ import annotations

import collections
import json
import re
import sys
import time
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent.parent
SESSIONS_META = ROOT / "data" / "raw" / "sessions_metadata.json"
ARCHIVE_CACHE = ROOT / "data" / "raw" / "video_archive.json"
OUT_YAML = ROOT / "data" / "corrections" / "session_videos.yml"

BASE = "https://aytovlc.web.enetres.net/va/plens/plens{yy}"
VIDEO_URL = "https://aytovlc.web.enetres.net/video?videoId={vid}"
# The archive 403s the default python-requests User-Agent.
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}
LIVE_MARKER = "players.cdn.enetres.net/live"
MAX_PAGES = 30

MESOS = {
    "gener": 1, "enero": 1, "febrer": 2, "febrero": 2, "marc": 3, "març": 3, "marzo": 3,
    "abril": 4, "maig": 5, "mayo": 5, "juny": 6, "junio": 6, "juliol": 7, "julio": 7,
    "agost": 8, "agosto": 8, "setembre": 9, "septiembre": 9, "octubre": 10,
    "novembre": 11, "noviembre": 11, "desembre": 12, "diciembre": 12,
}


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape_year(yy: int) -> dict[str, str]:
    """Return {videoId: title} for one year page, walking its pagination."""
    base = BASE.format(yy=f"{yy:02d}")
    found: dict[str, str] = {}
    page = 1
    while page <= MAX_PAGES:
        resp = requests.get(f"{base}?p={page}", headers=UA, timeout=40)
        if resp.status_code != 200:
            print(f"    p={page}: HTTP {resp.status_code}, stopping")
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        new = 0
        for a in soup.select('a[href*="videoId="]'):
            m = re.search(r"videoId=([\w-]+)", a["href"])
            img = a.find("img")
            if not m or not img:
                continue
            title = " ".join((img.get("alt") or "").split())
            if not title or m.group(1) in found:
                continue
            found[m.group(1)] = title
            new += 1
        # The archive keeps serving the last page past the end, so stop when a
        # page adds nothing new rather than when it is empty.
        if new == 0:
            break
        page += 1
        time.sleep(0.3)
    return found


def scrape_all() -> dict[str, dict[str, str]]:
    archive: dict[str, dict[str, str]] = {}
    for yy in range(11, 27):
        year = f"20{yy:02d}"
        print(f"  {year}...", end=" ", flush=True)
        items = scrape_year(yy)
        archive[year] = items
        print(f"{len(items)} videos")
    return archive


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_date(title: str) -> str | None:
    """Extract an ISO date from a video title. Seven formats occur in the archive."""
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", title)               # 2018-12-20
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", title)                     # pleno20121102Ext_
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", title)     # 29/04/2016
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
    m = re.search(                                                        # 24 de octubre 2023
        r"\b(\d{1,2})\s*(?:de\s*)?([A-Za-zçÇàèéíòóúÀÈÉÍÒÓÚ]+)\s*(?:de\s*)?(20\d{2})\b", title
    )
    if m and m.group(2).lower() in MESOS:
        return "%s-%02d-%02d" % (m.group(3), MESOS[m.group(2).lower()], int(m.group(1)))
    m = re.search(r"\b(\d{2})-(\d{2})-(\d{2})\b", title)                 # 17-10-19
    if m:
        return f"20{m.group(3)}-{m.group(2)}-{m.group(1)}"
    m = re.search(r"\b(\d{2})(\d{2})(\d{2})(?=\b|-\d{6})", title)        # 291020-045303
    if m:
        dd, mm, yy = m.groups()
        if 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31:
            return f"20{yy}-{mm}-{dd}"
    return None


def parse_video(vid: str, title: str) -> dict:
    part = re.search(r"Part(?:e)?\s*(\d)", title, re.I)
    ordinal = re.search(r"\b(\d)\s*ª?\s+Ple\b", title, re.I)
    # A title naming BOTH kinds ("Ple Ordinari i Extraordinari", "Pleno Ordinario y
    # Extra Ordinario") covers the two sessions of the day, so it is not a hint at all.
    extra = re.search(r"extra\s*ordinari", title, re.I)
    ordi = re.search(r"(?<!extra)(?<!extra )ordinari", title, re.I)
    if extra and ordi:
        tipus = None
    elif extra:
        tipus = "extraordinaria"
    elif ordi:
        tipus = "ordinaria"
    else:
        tipus = None
    # Many titles carry the start time, either as ddmmyy-hhmmss or as hh:mm:ss.
    ts = re.search(r"\d{6}-(\d{6})\b", title) or re.search(r"\b(\d{2}):(\d{2}):(\d{2})\b", title)
    if ts and ts.re.groups == 1:
        hora = ts.group(1)
    elif ts:
        hora = "".join(ts.groups())
    else:
        hora = None
    return {
        "vid": vid,
        "title": title,
        "fecha": parse_date(title),
        "part": int(part.group(1)) if part else (int(ordinal.group(1)) if ordinal else None),
        "tipus": tipus,
        "hora": hora,
        # Video ids are NOT chronological within a day; used only as a last tiebreak.
        "num": int(re.sub(r"\D", "", vid) or 0),
    }


def acta_time(session: dict) -> str:
    """Session start time from the acta filename (A_00001_20200924_0945_...) for ordering."""
    m = re.search(r"_\d{8}_(\d{4})_", session.get("url_acta") or "")
    return m.group(1) if m else "9999"


# ── Matching ──────────────────────────────────────────────────────────────────

def order_videos(videos: list[dict]) -> list[dict]:
    """Chronological order within a day.

    A video with no explicit "Part N" is the first part, not the last: on 2020-07-30
    the unlabelled video is part 1 and only its sequel says "Part 2". Start time comes
    next, because video ids do not run in chronological order within a day (on
    2020-06-25, e-118 is 04:42 and e-117 is 06:05).
    """
    return sorted(
        videos,
        key=lambda v: (v["part"] if v["part"] is not None else 1, v["hora"] or "", v["num"]),
    )


def match(sessions: list[dict], videos: list[dict]) -> tuple[dict, list]:
    """Assign videos to sessions. Returns (assignments, ambiguous_days).

    Only unambiguous rules are applied:
      A  one session that day        → all of that day's videos belong to it
      B  tipo hints partition the sessions uniquely
      C  as many ordered parts as sessions → assign in chronological order
    Anything else is reported for a human to resolve.
    """
    assignments: dict[str, dict] = {}
    ambiguous: list[dict] = []

    by_date_s = collections.defaultdict(list)
    for s in sessions:
        by_date_s[s["fecha"]].append(s)
    by_date_v = collections.defaultdict(list)
    for v in videos:
        if v["fecha"]:
            by_date_v[v["fecha"]].append(v)

    for fecha, sess in sorted(by_date_s.items()):
        vids = order_videos(by_date_v.get(fecha, []))
        if not vids:
            continue
        sess = sorted(sess, key=acta_time)

        if len(sess) == 1:
            assignments[sess[0]["id"]] = {"videos": vids, "rule": "A: unica sessio del dia"}
            continue

        # Rule C first: explicit part numbers are stronger evidence than a tipo word,
        # and a recording split in parts covers the day's sessions in order.
        parts = [v for v in vids if v["part"] is not None]
        if len(parts) == len(sess) and len({v["part"] for v in parts}) == len(parts):
            for s, v in zip(sess, order_videos(parts)):
                assignments[s["id"]] = {"videos": [v], "rule": f"C: part {v['part']} per ordre horari"}
            continue

        # Rule B: tipo hints that partition the sessions one-to-one.
        by_tipus = collections.defaultdict(list)
        for v in vids:
            if v["tipus"]:
                by_tipus[v["tipus"]].append(v)
        s_tipus = collections.Counter(s["tipo"] for s in sess)
        if by_tipus and all(
            len(by_tipus.get(t, [])) >= 1 and s_tipus[t] == 1 for t in by_tipus
        ) and set(by_tipus) <= set(s_tipus):
            used = True
            for t, tv in by_tipus.items():
                target = next(s for s in sess if s["tipo"] == t)
                assignments[target["id"]] = {"videos": order_videos(tv), "rule": f"B: titol diu {t}"}
            unmatched = [s for s in sess if s["id"] not in assignments]
            if unmatched:
                ambiguous.append({
                    "fecha": fecha, "motiu": "sessions sense video despres de la regla B",
                    "sessions": [s["id"] for s in unmatched],
                    "videos": [v["vid"] for v in vids],
                })
            if used:
                continue

        ambiguous.append({
            "fecha": fecha, "motiu": "cap regla neta aplica",
            "sessions": [f"{s['id']} ({s['tipo']}, {acta_time(s)})" for s in sess],
            "videos": [f"{v['vid']} part={v['part']} tipus={v['tipus']} | {v['title'][:60]}" for v in vids],
        })

    return assignments, ambiguous


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    offline = "--offline" in sys.argv
    dry_run = "--dry-run" in sys.argv

    if offline:
        if not ARCHIVE_CACHE.exists():
            print(f"Error: {ARCHIVE_CACHE} not found; run without --offline first.")
            raise SystemExit(1)
        archive = json.loads(ARCHIVE_CACHE.read_text())
        print(f"Using cached archive: {sum(len(v) for v in archive.values())} videos")
    else:
        print("Scraping the video archive...")
        archive = scrape_all()
        ARCHIVE_CACHE.write_text(json.dumps(archive, ensure_ascii=False, indent=2))
        print(f"  cached → {ARCHIVE_CACHE}")

    videos = [parse_video(vid, title) for items in archive.values() for vid, title in items.items()]
    undated = [v for v in videos if not v["fecha"]]
    print(f"\nVideos: {len(videos)} | with a parsed date: {len(videos) - len(undated)} | undated: {len(undated)}")
    for v in undated:
        print(f"    no date: {v['vid']:8} {v['title'][:64]!r}")

    sessions = json.loads(SESSIONS_META.read_text())
    assignments, ambiguous = match(sessions, videos)

    cur = {s["id"]: (s.get("url_video") or "") for s in sessions}
    has_rec = lambda sid: bool(cur.get(sid)) and LIVE_MARKER not in cur[sid]

    # Entries a human added for an ambiguous day must survive a regeneration.
    manual: dict[str, dict] = {}
    if OUT_YAML.exists():
        for e in yaml.safe_load(OUT_YAML.read_text(encoding="utf-8")) or []:
            if str(e.get("rule", "")).lower().startswith("manual"):
                manual[e["session_id"]] = e
    if manual:
        print(f"\nPreserving {len(manual)} manual entries: {', '.join(sorted(manual))}")

    entries, conflicts = [], []
    for sid, info in sorted(assignments.items()):
        if sid in manual:
            continue  # a human already decided this one
        urls = [VIDEO_URL.format(vid=v["vid"]) for v in info["videos"]]
        entry = {
            "session_id": sid,
            "url_video": urls[0],
            # Per project convention: only populated when the session has several parts.
            "url_videos": urls if len(urls) > 1 else [],
            "rule": info["rule"],
        }
        entries.append(entry)
        if has_rec(sid) and cur[sid] != urls[0]:
            conflicts.append((sid, cur[sid], urls[0]))

    filled = [e for e in entries if not has_rec(e["session_id"])]
    multi = [e for e in entries if e["url_videos"]]
    print(f"\nAssignments: {len(entries)}")
    print(f"  sessions that gain a recording: {len(filled)}")
    print(f"  sessions with several parts:    {len(multi)}")
    print(f"  disagrees with the recording already stored: {len(conflicts)}")
    for sid, old, new in conflicts:
        print(f"    {sid}: stored {old[-12:]} vs archive {new[-12:]}")

    print(f"\nAmbiguous days needing a human decision: {len(ambiguous)}")
    for a in ambiguous:
        print(f"  {a['fecha']} — {a['motiu']}")
        for s in a["sessions"]:
            print(f"      session {s}")
        for v in a["videos"]:
            print(f"      video   {v}")

    no_video = [s["id"] for s in sessions
                if LIVE_MARKER in cur[s["id"]] and s["id"] not in assignments]
    print(f"\nStill without a recording (day absent from the archive): {len(no_video)}")

    if dry_run:
        print("\n--dry-run: nothing written.")
        return

    OUT_YAML.write_text(
        "# Session → recording URL, from the city's video archive.\n"
        "# Generated by scripts/scrape_video_archive.py; script 07 overlays it on the\n"
        "# scraped session metadata, which only carries the generic live-player URL.\n"
        "#\n"
        "# url_video  : the session's recording (first part when it is split).\n"
        "# url_videos : every part, in order. Empty when there is only one video.\n"
        "# rule       : which matching rule assigned it (A/B/C, see the script).\n"
        "#\n"
        "# Ambiguous days are resolved by hand: add the entry with a rule starting with\n"
        "# 'manual', and regenerating this file will preserve it.\n\n"
        + yaml.dump(
            sorted(entries + list(manual.values()), key=lambda e: e["session_id"]),
            allow_unicode=True, sort_keys=False, default_flow_style=False,
        )
    )
    print(f"\nWrote {len(entries) + len(manual)} entries "
          f"({len(entries)} matched + {len(manual)} manual) → {OUT_YAML}")


if __name__ == "__main__":
    main()
