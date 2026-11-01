#!/usr/bin/env python3
"""Fill the homepage's LinkedIn feed (data/linkedin.json) from a LinkedIn data export.

LinkedIn does not let other sites list a member's posts, but its data export does:
LinkedIn > Settings & Privacy > Data privacy > Get a copy of your data > "Posts" (or the
full archive). The export (a .zip) contains Shares.csv with every post: date, link, text,
attached media and visibility. This keeps the public posts (only those can be embedded),
newest first, and estimates each embed's height from its text and media.

Posts already in data/linkedin.json keep their height, so a height you tuned by hand
survives a re-import; posts that are no longer in the export are dropped.

    python import_linkedin.py ~/Downloads/Basic_LinkedInDataExport_11-01-2026.zip
    python import_linkedin.py Shares.csv
"""
import csv, io, json, math, os, re, sys, urllib.parse, zipfile

OUT = os.path.join("data", "linkedin.json")


def rows(path):
    if path.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            name = next((n for n in z.namelist() if n.split("/")[-1].lower() == "shares.csv"), None)
            if not name:
                raise SystemExit("No Shares.csv in the export; request the archive with Posts included")
            text = z.read(name).decode("utf-8-sig")
    else:
        text = open(path, encoding="utf-8-sig").read()
    return list(csv.DictReader(io.StringIO(text)))


def urn(link):
    """'https://www.linkedin.com/feed/update/urn%3Ali%3Ashare%3A7...' -> 'urn:li:share:7...'"""
    m = re.search(r"urn:li:(?:share|ugcPost|activity):\d+", urllib.parse.unquote(link or ""))
    return m.group(0) if m else None


def height(r):
    """Rough embed height in pixels: header and actions, wrapped text, then any media or link card."""
    text = r.get("ShareCommentary") or ""
    lines = sum(max(1, math.ceil(len(par) / 70)) for par in text.split("\n"))
    h = 190 + min(lines, 30) * 21
    if (r.get("MediaUrl") or "").strip():
        h += 420
    elif (r.get("SharedUrl") or "").strip():
        h += 300
    return int(min(1100, h))


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    old = json.load(open(OUT)) if os.path.exists(OUT) else {"profile": "https://www.linkedin.com/in/hatamimatt/", "posts": []}
    kept = {p["urn"]: p for p in old.get("posts", [])}
    posts, skipped = [], 0
    for r in rows(sys.argv[1]):
        u = urn(r.get("ShareLink"))
        vis = (r.get("Visibility") or "PUBLIC").upper()
        if not u or vis not in ("PUBLIC", "MEMBER_NETWORK", ""):
            skipped += 1
            continue
        date = (r.get("Date") or "")[:10]
        posts.append({"urn": u, "date": date, "height": kept.get(u, {}).get("height") or height(r)})
    posts.sort(key=lambda p: p["date"], reverse=True)
    out = {"profile": old.get("profile"), "posts": posts}
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    span = f"{posts[-1]['date']} to {posts[0]['date']}" if posts else "none"
    print(f"Wrote {OUT}: {len(posts)} posts ({span}); skipped {skipped} without a public link")


if __name__ == "__main__":
    sys.exit(main())
