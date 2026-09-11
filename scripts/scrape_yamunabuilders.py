#!/usr/bin/env python3
"""Full-site archiver for https://yamunabuilders.com/ (WordPress).

Produces archive/yamunabuilders.com/ containing:
  SITE-CONTENT.md   every page's text, headings, links, images, forms, JSON-LD (human readable)
  manifest.json     machine readable index of pages, assets and where they are stored locally
  pages/*.html      raw HTML of every page exactly as served
  api/*.json        WordPress REST API dumps (pages, posts, media, menus, ...)
  assets/...        images, PDFs, CSS, JS and fonts served from yamunabuilders.com
  README.md         how the archive is organised

Run: python scripts/scrape_yamunabuilders.py [--no-assets]
Requires: requests, beautifulsoup4, html2text, lxml
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
from collections import OrderedDict
from datetime import datetime, timezone

import html2text
import requests
from bs4 import BeautifulSoup

BASE = "https://yamunabuilders.com"
HOST = "yamunabuilders.com"
OUT = os.path.join("archive", "yamunabuilders.com")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0.0.0 Safari/537.36")
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}
WAYBACK = "https://web.archive.org"
MODE = {"source": "live", "cdx": {}}  # switched to "wayback" if the live site blocks us
MAX_FILE_BYTES = 95 * 1024 * 1024  # GitHub hard limit is 100 MB per file
PART_BYTES = 90 * 1024 * 1024      # bigger files are stored as <name>.part-NN chunks
SLEEP = 0.25
SEEDS = [
    BASE + "/",
    # Legacy static-site paths seen in search engines (may 404 today, tried anyway)
    BASE + "/yamuna-garden/yamuna-garden-overview.html",
    BASE + "/index.html",
]
PAGE_SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".mp4", ".webm",
                 ".css", ".js", ".ico", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".zip",
                 ".xml", ".json", ".avif", ".mp3", ".txt", ".xsl")
RESIZED_RE = re.compile(r"-(\d{2,5})x(\d{2,5})(\.[A-Za-z0-9]+)$")
ASSET_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".avif", ".ico", ".bmp", ".tif", ".tiff",
             ".pdf", ".mp4", ".webm", ".mov", ".mp3", ".wav", ".css", ".js", ".woff", ".woff2", ".ttf",
             ".eot", ".otf", ".zip", ".xml", ".json", ".txt", ".xsl", ".csv", ".doc", ".docx", ".xls",
             ".xlsx", ".ppt", ".pptx", ".webmanifest")
# Indian mobile numbers, optionally with +91, not embedded in a longer digit run
PHONE_RE = re.compile(r"(?<![\d/.-])(?:\+91[\s-]?)?0?[6-9]\d{4}[\s-]?\d{5}(?![\d-])")


def is_asset_url(u):
    """True for real files worth downloading (media, PDFs, CSS/JS, fonts); False for feeds,
    shortlinks (?p=), REST responses and other dynamic URLs that only duplicate the pages."""
    p = urllib.parse.urlparse(u)
    path = p.path.lower()
    if any(b in path for b in ("/wp-json/", "/xmlrpc.php", "/feed", "/comments/", "/wp-admin/", "/wp-login")):
        return False
    if path.startswith(("/wp-content/", "/wp-includes/")):
        return True
    if p.query:
        return False
    return path.endswith(ASSET_EXT)

session = requests.Session()
session.headers.update(BROWSER_HEADERS)


def log(*a):
    print(*a, flush=True)


def _raw_get(url, timeout):
    return session.get(url, timeout=timeout, allow_redirects=True)


def wayback_url(url):
    """Map a live URL to the Wayback Machine raw-content URL for its latest 200 snapshot."""
    key = url.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
    ts = MODE["cdx"].get(key) or MODE["cdx"].get(key + "/") or "2"
    return f"{WAYBACK}/web/{ts}id_/{url}"


class WaybackResponse:
    """Minimal requests.Response look-alike so the crawler code is source-agnostic."""

    def __init__(self, original_url, r):
        self.url = original_url
        self.status_code = r.status_code
        self.headers = r.headers
        self.content = r.content
        self.text = r.text
        self._json = r.json

    def json(self):
        return self._json()


def fetch(url, timeout=60, retries=4):
    """GET with backoff. 429/403/5xx are retried; in wayback mode the request is rerouted."""
    last = None
    for i in range(retries):
        try:
            if MODE["source"] == "wayback":
                r = _raw_get(wayback_url(url), timeout=timeout)
                if r.status_code in (429, 503) and i < retries - 1:
                    time.sleep(10 * (i + 1))
                    continue
                return WaybackResponse(url, r)
            r = _raw_get(url, timeout=timeout)
            if r.status_code in (429, 403, 503, 502) and i < retries - 1:
                wait = [5, 15, 30, 60][min(i, 3)]
                ra = r.headers.get("Retry-After")
                if ra and ra.isdigit():
                    wait = min(int(ra), 120)
                log(f"HTTP {r.status_code} for {url}; retrying in {wait}s")
                time.sleep(wait)
                continue
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    if last:
        raise last
    return r


def probe_live_site():
    """Return True if the live site serves the homepage; log diagnostics otherwise."""
    try:
        r = _raw_get(BASE + "/", timeout=60)
    except Exception as e:  # noqa: BLE001
        log("probe error:", e)
        return False
    log("probe:", r.status_code, dict(r.headers))
    log("probe body head:", r.text[:600].replace("\n", " "))
    if r.status_code == 200 and "html" in r.headers.get("Content-Type", ""):
        return True
    for wait in (20, 60):
        log(f"live site refused ({r.status_code}); waiting {wait}s and probing again")
        time.sleep(wait)
        try:
            r = _raw_get(BASE + "/", timeout=60)
            log("probe:", r.status_code)
            if r.status_code == 200 and "html" in r.headers.get("Content-Type", ""):
                return True
        except Exception as e:  # noqa: BLE001
            log("probe error:", e)
    return False


def load_wayback_index():
    """Fill MODE['cdx'] with url -> latest timestamp of a 200 snapshot, from the CDX API."""
    u = (f"{WAYBACK}/cdx/search/cdx?url={HOST}/*&output=json&fl=original,timestamp,statuscode,mimetype"
         "&filter=statuscode:200&collapse=urlkey&limit=20000")
    for attempt in range(4):
        try:
            r = _raw_get(u, timeout=180)
            if r.status_code == 200:
                rows = r.json()
                break
            log("cdx", r.status_code)
        except Exception as e:  # noqa: BLE001
            log("cdx error", e)
        time.sleep(15 * (attempt + 1))
    else:
        rows = []
    seen_pages = []
    for row in rows[1:]:
        original, ts, status, mime = row[0], row[1], row[2], row[3]
        key = original.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
        if ts > MODE["cdx"].get(key, ""):
            MODE["cdx"][key] = ts
        n = norm(original)
        if n and "html" in mime:
            seen_pages.append(n)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "wayback-cdx.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f)
    log("wayback index:", len(MODE["cdx"]), "urls;", len(seen_pages), "html pages")
    return seen_pages


def norm(u):
    """Normalise a URL to canonical https://yamunabuilders.com/... or None if external."""
    if not u:
        return None
    u = u.strip().split("#")[0]
    if not u:
        return None
    p = urllib.parse.urlparse(u)
    if p.scheme not in ("http", "https"):
        return None
    host = p.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != HOST:
        return None
    path = p.path or "/"
    return BASE + path + (("?" + p.query) if p.query else "")


def is_page_url(u):
    if "?" in u:
        return False
    low = u.lower()
    if low.endswith(PAGE_SKIP_EXT):
        return False
    for bad in ("/wp-json/", "/wp-admin/", "/wp-login", "/feed/", "/feed", "/xmlrpc.php",
                "/wp-content/", "/wp-includes/", "/comments/"):
        if bad in low:
            return False
    return True


def local_path_for(url):
    p = urllib.parse.urlparse(url)
    path = p.path.lstrip("/")
    if not path or path.endswith("/"):
        path += "index"
    if p.query:
        path += "__" + re.sub(r"[^A-Za-z0-9._-]", "_", p.query)[:80]
    return os.path.join(OUT, "assets", path)


def page_slug(url):
    path = urllib.parse.urlparse(url).path.strip("/")
    return re.sub(r"[^A-Za-z0-9._-]", "_", path.replace("/", "__")) or "index"


# --------------------------------------------------------------------------- sitemaps
def collect_sitemap_urls():
    found, sitemaps = OrderedDict(), []

    def walk(u, depth=0):
        if depth > 4:
            return
        try:
            r = fetch(u)
        except Exception as e:  # noqa: BLE001
            log("sitemap fail", u, e)
            return
        if r.status_code != 200:
            log("sitemap", u, r.status_code)
            return
        sitemaps.append({"url": u, "status": r.status_code})
        os.makedirs(os.path.join(OUT, "sitemaps"), exist_ok=True)
        with open(os.path.join(OUT, "sitemaps", os.path.basename(urllib.parse.urlparse(u).path) or "sitemap.xml"), "wb") as f:
            f.write(r.content)
        txt = r.text
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", txt)
        if "<sitemapindex" in txt:
            for l in locs:
                walk(l.strip(), depth + 1)
        else:
            for l in locs:
                n = norm(l.strip())
                if n:
                    found[n] = u
    for u in (BASE + "/sitemap_index.xml", BASE + "/sitemap.xml", BASE + "/wp-sitemap.xml"):
        walk(u)
    return found, sitemaps


# --------------------------------------------------------------------------- REST API
def dump_api():
    api_dir = os.path.join(OUT, "api")
    os.makedirs(api_dir, exist_ok=True)
    result = {}
    for ep in ["pages", "posts", "media", "categories", "tags", "users", "comments",
               "menus", "menu-items", "menu-locations", "uig_image_gallery", "elementor_library",
               "block-types", "types", "taxonomies", "settings"]:
        items = []
        for page in range(1, 100):
            u = f"{BASE}/wp-json/wp/v2/{ep}?per_page=100&page={page}"
            try:
                r = fetch(u)
            except Exception as e:  # noqa: BLE001
                log("api", ep, "error", e)
                break
            if r.status_code != 200:
                if page == 1:
                    log("api", ep, r.status_code)
                break
            try:
                j = r.json()
            except Exception:  # noqa: BLE001
                break
            if isinstance(j, dict):
                items = j
                break
            if not j:
                break
            items += j
            if len(j) < 100:
                break
            time.sleep(SLEEP)
        if items:
            with open(os.path.join(api_dir, f"{ep}.json"), "w", encoding="utf-8") as f:
                json.dump(items, f, indent=1, ensure_ascii=False)
            result[ep] = len(items) if isinstance(items, list) else 1
            log("api", ep, result[ep])
    for extra in ["/wp-json/", "/wp-json/wp/v2/", "/wp-json/wp-site-health/v1",
                  "/superpwa-manifest.json", "/wp-json/rankmath/v1/", "/?rest_route=/wp/v2/types"]:
        try:
            r = fetch(BASE + extra)
            if r.status_code == 200:
                name = re.sub(r"[^A-Za-z0-9]+", "_", extra.strip("/")) or "root"
                with open(os.path.join(api_dir, f"{name}.json"), "wb") as f:
                    f.write(r.content)
        except Exception as e:  # noqa: BLE001
            log("api extra", extra, e)
    return result


# --------------------------------------------------------------------------- pages
def extract_page(url, html):
    soup = BeautifulSoup(html, "lxml")
    info = {"url": url}
    info["title"] = soup.title.get_text(strip=True) if soup.title else ""
    meta = {}
    for m in soup.find_all("meta"):
        k = m.get("name") or m.get("property") or m.get("http-equiv")
        if k and m.get("content") is not None:
            meta[k] = m["content"]
    info["meta"] = meta
    canon = soup.find("link", rel="canonical")
    info["canonical"] = canon.get("href") if canon else ""
    info["jsonld"] = []
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            info["jsonld"].append(json.loads(s.string or ""))
        except Exception:  # noqa: BLE001
            info["jsonld"].append((s.string or "").strip())
    info["headings"] = [{"level": h.name, "text": h.get_text(" ", strip=True)}
                        for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
                        if h.get_text(strip=True)]
    links = []
    for a in soup.find_all("a", href=True):
        href = urllib.parse.urljoin(url, a["href"].strip())
        txt = a.get_text(" ", strip=True)
        img = a.find("img")
        if not txt and img is not None:
            txt = "[image] " + (img.get("alt") or "")
        links.append({"text": txt, "href": href})
    info["links"] = links
    images = []
    for im in soup.find_all(["img", "source"]):
        src = im.get("src") or im.get("data-src") or im.get("data-lazy-src")
        srcset = im.get("srcset") or im.get("data-srcset")
        if src and not src.startswith("data:"):
            images.append({"src": urllib.parse.urljoin(url, src), "alt": im.get("alt", ""),
                           "srcset": srcset or "", "width": im.get("width", ""), "height": im.get("height", "")})
    info["images"] = images
    media = []
    for v in soup.find_all(["video", "audio", "iframe", "embed", "object"]):
        src = v.get("src") or v.get("data") or v.get("data-src")
        sources = [s.get("src") for s in v.find_all("source") if s.get("src")]
        media.append({"tag": v.name, "src": urllib.parse.urljoin(url, src) if src else "",
                      "sources": [urllib.parse.urljoin(url, s) for s in sources], "poster": v.get("poster", "")})
    info["media"] = media
    forms = []
    for fm in soup.find_all("form"):
        fields = []
        for inp in fm.find_all(["input", "textarea", "select", "button"]):
            fields.append({"tag": inp.name, "type": inp.get("type", ""), "name": inp.get("name", ""),
                           "placeholder": inp.get("placeholder", ""), "value": inp.get("value", ""),
                           "options": [o.get_text(strip=True) for o in inp.find_all("option")] if inp.name == "select" else [],
                           "label": inp.get_text(" ", strip=True) if inp.name == "button" else ""})
        forms.append({"action": fm.get("action", ""), "method": fm.get("method", ""), "id": fm.get("id", ""),
                      "class": " ".join(fm.get("class", [])), "fields": fields})
    info["forms"] = forms
    # Stylesheets / scripts (for reference when rebuilding)
    info["stylesheets"] = [urllib.parse.urljoin(url, l["href"]) for l in soup.find_all("link", rel="stylesheet", href=True)]
    info["scripts"] = [urllib.parse.urljoin(url, s["src"]) for s in soup.find_all("script", src=True)]
    # Text as markdown
    for t in soup(["script", "style", "noscript", "template", "svg"]):
        t.decompose()
    body = soup.body or soup
    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_images = False
    h.ignore_links = False
    h.protect_links = True
    h.unicode_snob = True
    md = h.handle(str(body))
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    info["markdown"] = md
    info["plain_text"] = re.sub(r"\n{3,}", "\n\n", body.get_text("\n", strip=True))
    return info


def collect_asset_urls_from_html(url, html):
    urls = set()
    for m in re.findall(r"https?:\\?/\\?/(?:www\.)?yamunabuilders\.com\\?/[^\s\"'<>()]+", html):
        urls.add(m.replace("\\/", "/"))
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["img", "source", "video", "audio", "link", "script", "iframe", "embed", "object", "a"]):
        for k in ("src", "data-src", "data-lazy-src", "href", "data-bg", "poster", "data", "data-background"):
            v = tag.get(k)
            if v and not v.startswith("data:"):
                urls.add(urllib.parse.urljoin(url, v))
        for k in ("srcset", "data-srcset"):
            v = tag.get(k)
            if v:
                for part in v.split(","):
                    part = part.strip().split(" ")[0]
                    if part:
                        urls.add(urllib.parse.urljoin(url, part))
    for m in re.findall(r"url\((['\"]?)(.*?)\1\)", html):
        if m[1] and not m[1].startswith("data:"):
            urls.add(urllib.parse.urljoin(url, m[1]))
    for tag in soup.find_all(attrs={"data-settings": True}):
        for m in re.findall(r"https?:\\?/\\?/[^\s\"'<>()]+", tag["data-settings"]):
            urls.add(m.replace("\\/", "/"))
    out = set()
    for u in urls:
        n = norm(u.split("#")[0])
        if n and is_asset_url(n):
            out.add(n)
    return out


def crawl_pages(seed_urls):
    pages_dir = os.path.join(OUT, "pages")
    os.makedirs(pages_dir, exist_ok=True)
    queue = list(seed_urls)
    seen, pages, assets, external_links = set(), OrderedDict(), set(), set()
    while queue:
        u = queue.pop(0)
        if u in seen:
            continue
        seen.add(u)
        if not is_page_url(u):
            if is_asset_url(u):
                assets.add(u)
            continue
        try:
            r = fetch(u)
        except Exception as e:  # noqa: BLE001
            pages[u] = {"url": u, "error": str(e)}
            log("ERR", u, e)
            continue
        final = norm(r.url) or r.url
        ct = r.headers.get("Content-Type", "")
        if r.status_code != 200 or "html" not in ct:
            pages[u] = {"url": u, "status": r.status_code, "content_type": ct, "final_url": final}
            log("SKIP", u, r.status_code, ct)
            if r.status_code == 200 and is_asset_url(u):
                assets.add(u)
            continue
        if final != u and final in seen and final in pages:
            pages[u] = {"url": u, "status": r.status_code, "redirected_to": final}
            continue
        html = r.text
        slug = page_slug(final if final != u else u)
        fn = os.path.join(pages_dir, slug + ".html")
        with open(fn, "wb") as f:
            f.write(r.content)
        info = extract_page(final, html)
        info.update({"requested_url": u, "final_url": final, "status": r.status_code,
                     "html_file": os.path.relpath(fn, OUT), "bytes": len(r.content),
                     "fetched_at": datetime.now(timezone.utc).isoformat()})
        pages[u] = info
        if final != u:
            seen.add(final)
        for l in info["links"]:
            n = norm(l["href"])
            if n:
                if n not in seen:
                    queue.append(n)
            else:
                external_links.add(l["href"])
        assets |= collect_asset_urls_from_html(final, html)
        log("OK", u, len(r.content), "queue", len(queue))
        time.sleep(SLEEP)
    return pages, assets, external_links


# --------------------------------------------------------------------------- assets
def choose_original(url):
    """WordPress serves many resized copies (name-300x200.jpg). Prefer the original."""
    m = RESIZED_RE.search(url)
    if m:
        return url[: m.start()] + m.group(3)
    return url


def download_assets(asset_urls, download=True):
    records = OrderedDict()
    css_queue = []
    asset_urls = {u for u in asset_urls if is_asset_url(u)}
    originals = {choose_original(u) for u in asset_urls}
    # originals first so resized variants can be skipped once the original is saved
    todo = sorted(originals | set(asset_urls), key=lambda x: (RESIZED_RE.search(x) is not None, x))
    done = set()
    total = 0
    while todo:
        u = todo.pop(0)
        if u in done:
            continue
        done.add(u)
        rec = {"url": u, "original_of": None}
        orig = choose_original(u)
        if orig != u:
            rec["resized_variant_of"] = orig
        if not download:
            records[u] = rec
            continue
        # Only download resized variants when the original failed
        if orig != u and orig in records and records[orig].get("file"):
            rec["skipped"] = "original downloaded instead"
            records[u] = rec
            continue
        try:
            r = fetch(u, timeout=120)
        except Exception as e:  # noqa: BLE001
            rec["error"] = str(e)
            records[u] = rec
            log("ASSET ERR", u, e)
            continue
        rec["status"] = r.status_code
        rec["content_type"] = r.headers.get("Content-Type", "")
        if r.status_code != 200:
            records[u] = rec
            log("ASSET", r.status_code, u)
            continue
        data = r.content
        rec["bytes"] = len(data)
        lp = local_path_for(u)
        os.makedirs(os.path.dirname(lp), exist_ok=True)
        if len(data) > MAX_FILE_BYTES:
            # Too big for one git blob: store as numbered parts, joinable with `cat`.
            rec["sha256"] = hashlib.sha256(data).hexdigest()
            parts = []
            for i in range(0, len(data), PART_BYTES):
                pp = f"{lp}.part-{i // PART_BYTES:02d}"
                with open(pp, "wb") as f:
                    f.write(data[i:i + PART_BYTES])
                parts.append(os.path.relpath(pp, OUT))
            rec["file"] = os.path.relpath(lp, OUT)
            rec["file_parts"] = parts
            log("ASSET SPLIT", u, len(data), "->", len(parts), "parts")
        else:
            with open(lp, "wb") as f:
                f.write(data)
            rec["file"] = os.path.relpath(lp, OUT)
        total += len(data)
        records[u] = rec
        if "css" in rec["content_type"] or u.lower().endswith(".css"):
            txt = data.decode("utf-8", "ignore")
            for m in re.findall(r"url\((['\"]?)(.*?)\1\)", txt):
                ref = m[1].strip()
                if ref and not ref.startswith("data:"):
                    n = norm(urllib.parse.urljoin(u, ref).split("#")[0].split("?")[0])
                    if n and n not in done:
                        todo.append(n)
            for m in re.findall(r"@import\s+(?:url\()?['\"]?([^'\")\s]+)", txt):
                n = norm(urllib.parse.urljoin(u, m))
                if n and n not in done:
                    todo.append(n)
        log("ASSET OK", u, len(data), "total MB", round(total / 1e6, 1))
        time.sleep(0.1)
    return records, total


# --------------------------------------------------------------------------- report
def write_markdown(pages, assets, external_links, api_counts, sitemaps):
    lines = []
    lines.append("# yamunabuilders.com — full site archive\n")
    captured = MODE.get("captured_at") or datetime.now(timezone.utc).isoformat()
    lines.append(f"Captured: {captured[:16].replace('T', ' ')} UTC  ")
    lines.append("Source: https://yamunabuilders.com/ (WordPress + Elementor, Rank Math SEO)  ")
    lines.append(f"Fetched via: {'the live site' if MODE['source'] == 'live' else 'the Internet Archive Wayback Machine (live site blocked the crawler)'}\n")
    lines.append("This file contains the complete textual content of every page on the site, "
                 "plus its headings, links, images, forms and structured data, so the website "
                 "can be rebuilt without access to the original. Raw HTML is in `pages/`, "
                 "downloaded media in `assets/`, WordPress API dumps in `api/`, and a machine "
                 "readable index in `manifest.json`.\n")
    ok_pages = [p for p in pages.values() if p.get("html_file")]
    lines.append("## Contents\n")
    lines.append("| # | Page title | URL | Raw HTML |")
    lines.append("|---|---|---|---|")
    for i, p in enumerate(ok_pages, 1):
        lines.append(f"| {i} | {p['title'].replace('|', '/')} | {p['final_url']} | `{p['html_file']}` |")
    lines.append("")
    others = [p for p in pages.values() if not p.get("html_file")]
    if others:
        lines.append("### URLs that did not return an HTML page\n")
        for p in others:
            lines.append(f"- {p['url']} → {p.get('status', p.get('error', ''))} {p.get('redirected_to', p.get('content_type', ''))}")
        lines.append("")

    # Contact details found anywhere on the site
    alltext = "\n".join(p.get("plain_text", "") + "\n" + p.get("markdown", "") for p in ok_pages)
    by_digits = {}
    for ph in PHONE_RE.findall(alltext):
        by_digits.setdefault(re.sub(r"\D", "", ph)[-10:], re.sub(r"\s+", " ", ph).strip())
    phones = sorted(by_digits.values())
    emails = sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", alltext)))
    tel_links = sorted({l["href"] for p in ok_pages for l in p["links"] if l["href"].startswith(("tel:", "mailto:", "https://wa.me", "https://api.whatsapp.com"))})
    socials = sorted({l["href"] for p in ok_pages for l in p["links"]
                      if re.search(r"(facebook|instagram|youtube|linkedin|twitter|x\.com|pinterest|maps\.google|goo\.gl/maps|google\.com/maps)", l["href"], re.I)})
    lines.append("## Site-wide facts\n")
    lines.append("### Phone numbers / emails found in page text\n")
    for ph in phones:
        lines.append(f"- {ph}")
    for em in emails:
        lines.append(f"- {em}")
    lines.append("\n### tel:/mailto:/WhatsApp links\n")
    for t in tel_links:
        lines.append(f"- {t}")
    lines.append("\n### Social / map links\n")
    for s in socials:
        lines.append(f"- {s}")
    lines.append("")

    # Navigation from the homepage
    home = next((p for p in ok_pages if p["final_url"].rstrip("/") == BASE), None)
    if home:
        soup = BeautifulSoup(open(os.path.join(OUT, home["html_file"]), "rb").read(), "lxml")
        lines.append("## Navigation menus (as found on the homepage)\n")
        for nav in soup.find_all(["nav", "ul"], class_=re.compile(r"(menu|nav)", re.I)):
            items = [(a.get_text(' ', strip=True), urllib.parse.urljoin(BASE, a.get('href', ''))) for a in nav.find_all("a", href=True)]
            if not items:
                continue
            lines.append(f"**{nav.name}.{' '.join(nav.get('class', []))}**\n")
            for t, h in items:
                lines.append(f"- {t} → {h}")
            lines.append("")
        footer = soup.find("footer")
        if footer:
            h = html2text.HTML2Text(); h.body_width = 0
            lines.append("## Footer (homepage)\n")
            lines.append(h.handle(str(footer)).strip())
            lines.append("")

    lines.append("---\n")
    lines.append("# Pages\n")
    for i, p in enumerate(ok_pages, 1):
        lines.append(f"\n\n## {i}. {p['title'] or p['final_url']}\n")
        lines.append(f"- URL: {p['final_url']}")
        if p["requested_url"] != p["final_url"]:
            lines.append(f"- Requested as: {p['requested_url']}")
        lines.append(f"- Raw HTML: `{p['html_file']}` ({p['bytes']} bytes)")
        for k in ("description", "og:title", "og:description", "og:image", "og:type", "og:updated_time",
                  "article:published_time", "article:modified_time", "robots"):
            if p["meta"].get(k):
                lines.append(f"- meta {k}: {p['meta'][k]}")
        lines.append("\n### Heading outline\n")
        for h in p["headings"]:
            lines.append(f"- {h['level'].upper()}: {h['text']}")
        lines.append("\n### Full page content (markdown)\n")
        lines.append(p["markdown"])
        if p["forms"]:
            lines.append("\n### Forms\n")
            for fm in p["forms"]:
                lines.append(f"- form id=`{fm['id']}` class=`{fm['class']}` action=`{fm['action']}` method=`{fm['method']}`")
                for fd in fm["fields"]:
                    lines.append(f"  - {fd['tag']} type={fd['type']} name=`{fd['name']}` placeholder=\"{fd['placeholder']}\" "
                                 f"{('label=' + fd['label']) if fd['label'] else ''} {('options=' + str(fd['options'])) if fd['options'] else ''}")
        lines.append("\n### Images on this page\n")
        seen_img = set()
        for im in p["images"]:
            if im["src"] in seen_img:
                continue
            seen_img.add(im["src"])
            lines.append(f"- {im['src']}  alt=\"{im['alt']}\"" + (f" ({im['width']}x{im['height']})" if im['width'] else ""))
        if p["media"]:
            lines.append("\n### Video / iframe / embeds\n")
            for m in p["media"]:
                lines.append(f"- {m['tag']}: {m['src'] or m['sources']} poster={m['poster']}")
        lines.append("\n### Links on this page\n")
        seen_l = set()
        for l in p["links"]:
            key = (l["text"], l["href"])
            if key in seen_l:
                continue
            seen_l.add(key)
            lines.append(f"- [{l['text']}]({l['href']})")
        if p["jsonld"]:
            lines.append("\n### Structured data (JSON-LD)\n")
            lines.append("```json")
            lines.append(json.dumps(p["jsonld"], indent=1, ensure_ascii=False))
            lines.append("```")
        lines.append("\n### Stylesheets / scripts used\n")
        for s in p["stylesheets"]:
            lines.append(f"- css: {s}")
        for s in p["scripts"]:
            lines.append(f"- js: {s}")

    split = [(u, r) for u, r in assets.items() if r.get("file_parts")]
    if split:
        lines.append("\n\n---\n\n# Large files stored in parts\n")
        lines.append("These exceed GitHub's 100 MB per-file limit and are stored as 90 MB chunks. "
                     "Join them (from the archive root) and verify with the sha256:\n")
        lines.append("```sh")
        for u, r in split:
            lines.append(f"cat {r['file']}.part-* > {r['file']}   # {u} ({r['bytes']} bytes)")
            lines.append(f"echo '{r['sha256']}  {r['file']}' | sha256sum -c")
        lines.append("```")
    lines.append("\n\n---\n\n# Assets\n")
    lines.append(f"{len(assets)} asset URLs referenced from the site. Local copies (where downloaded) are under `assets/`.\n")
    for u, rec in assets.items():
        state = rec.get("file") or rec.get("skipped") or rec.get("error") or rec.get("status", "")
        if rec.get("file_parts"):
            state += f" (in {len(rec['file_parts'])} parts, see 'Large files stored in parts')"
        lines.append(f"- {u} → {state}")
    lines.append("\n\n# External links referenced\n")
    for e in sorted(external_links):
        lines.append(f"- {e}")
    lines.append("\n\n# WordPress REST API dumps\n")
    for k, v in api_counts.items():
        lines.append(f"- `api/{k}.json`: {v} items")
    lines.append("\n\n# Sitemaps fetched\n")
    for s in sitemaps:
        lines.append(f"- {s['url']} ({s['status']})")
    with open(os.path.join(OUT, "SITE-CONTENT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


README = """# yamunabuilders.com archive

Offline snapshot of https://yamunabuilders.com/ taken so the website can be rebuilt if the
original goes down. Generated by `scripts/scrape_yamunabuilders.py`
(GitHub Actions workflow: `.github/workflows/scrape-yamunabuilders.yml`).

| Path | What it is |
|---|---|
| `SITE-CONTENT.md` | **Start here.** Every page's full text, headings, links, images, forms, JSON-LD, plus site-wide contact details and navigation. |
| `manifest.json` | Machine-readable index: every page (with extracted data) and every asset with its local path. |
| `pages/*.html` | Raw HTML of every page exactly as served (Elementor markup, inline CSS/JS). |
| `api/*.json` | WordPress REST API dumps: pages, posts, media library, categories, etc. `content.rendered` holds the page HTML. |
| `assets/wp-content/uploads/...` | Original images / PDFs / videos from the media library and every page. Files over 95 MB are stored as `<name>.part-NN` chunks; `SITE-CONTENT.md` ("Large files stored in parts") gives the `cat` command and sha256 to rebuild each one. |
| `assets/wp-content/themes|plugins/...` | CSS/JS/fonts the site loads from its own domain (theme look and feel). |
| `sitemaps/` | The XML sitemaps the site published. |
| `run.log` | Crawl log. |

## Refreshing / rebuilding

- A push that touches `scripts/scrape_yamunabuilders.py` or the workflow file re-runs the crawl on
  GitHub Actions and commits a fresh snapshot (about 25 minutes; the media library is ~340 MB).
  Once the workflow is on the default branch it can also be started by hand from the Actions tab.
- `python scripts/scrape_yamunabuilders.py --report-only` rebuilds `SITE-CONTENT.md` and this file
  from `manifest.json` without touching the network.
- The site (LiteSpeed on Hostinger) answers HTTP 429 to any User-Agent containing "bot"; the
  crawler therefore identifies as a normal desktop browser. If the live site is gone, the script
  falls back to the Internet Archive automatically (`FORCE_WAYBACK=1` forces it).

## Rebuilding the website from this archive

- Copy, structure and page hierarchy: `SITE-CONTENT.md` (navigation, footer, every page's headings
  and body text, forms, links) and `api/pages.json` / `api/posts.json` (`content.rendered`).
- Imagery: `assets/wp-content/uploads/` holds the original files; `api/media.json` maps each to its
  title, alt text and caption. Brochure PDFs and the site video are there too.
- Look and feel: theme CSS/JS/fonts under `assets/wp-content/themes/salient/` and the inline Elementor
  styles inside each `pages/*.html`.
"""


def rebuild_report():
    mp = os.path.join(OUT, "manifest.json")
    manifest = json.load(open(mp, encoding="utf-8"))
    MODE["source"] = manifest.get("fetched_via", "live")
    MODE["captured_at"] = manifest.get("captured_at", "")
    kept, removed = OrderedDict(), 0
    for u, rec in manifest["assets"].items():
        if is_asset_url(u):
            kept[u] = rec
            continue
        removed += 1
        f = rec.get("file")
        if f and os.path.exists(os.path.join(OUT, f)):
            os.remove(os.path.join(OUT, f))
    # drop directories emptied by the pruning
    for root, dirs, files in os.walk(os.path.join(OUT, "assets"), topdown=False):
        if not os.listdir(root):
            os.rmdir(root)
    manifest["assets"] = kept
    manifest["assets_total_bytes"] = sum(r.get("bytes", 0) for r in kept.values() if r.get("file"))
    log("assets kept", len(kept), "pruned", removed)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    write_markdown(manifest["pages"], kept, set(manifest["external_links"]),
                   manifest["api_counts"], manifest["sitemaps"])
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as f:
        f.write(README)
    log("report rebuilt")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-assets", action="store_true", help="only record asset URLs, do not download")
    ap.add_argument("--report-only", action="store_true",
                    help="no network: rebuild SITE-CONTENT.md and README.md from the existing manifest.json, "
                         "pruning asset records/files that are not real files")
    args = ap.parse_args()
    if args.report_only:
        return rebuild_report()
    os.makedirs(OUT, exist_ok=True)
    started = time.time()

    log("== probing live site")
    wayback_pages = []
    if os.environ.get("FORCE_WAYBACK") == "1" or not probe_live_site():
        log("!! live site not reachable with a browser UA from this network; falling back to the Wayback Machine")
        MODE["source"] = "wayback"
        wayback_pages = load_wayback_index()
    global SLEEP
    if MODE["source"] == "wayback":
        SLEEP = 1.0

    log("== sitemaps")
    sm_urls, sitemaps = collect_sitemap_urls()
    log("sitemap urls:", len(sm_urls))

    log("== REST API")
    api_counts = dump_api()
    api_urls = []
    for ep in ("pages", "posts"):
        fp = os.path.join(OUT, "api", f"{ep}.json")
        if os.path.exists(fp):
            for it in json.load(open(fp, encoding="utf-8")):
                n = norm(it.get("link", ""))
                if n:
                    api_urls.append(n)

    log("== crawling pages")
    seeds = SEEDS + list(sm_urls.keys()) + api_urls + wayback_pages
    pages, asset_urls, external_links = crawl_pages(seeds)
    log("pages:", len(pages), "asset urls:", len(asset_urls))

    # Media library originals (everything ever uploaded, even if not on a page)
    mp = os.path.join(OUT, "api", "media.json")
    if os.path.exists(mp):
        for it in json.load(open(mp, encoding="utf-8")):
            n = norm(it.get("source_url", ""))
            if n:
                asset_urls.add(n)
            for sz in (it.get("media_details") or {}).get("sizes", {}).values():
                n = norm(sz.get("source_url", ""))
                if n:
                    asset_urls.add(n)

    log("== assets", len(asset_urls))
    assets, total = download_assets(asset_urls, download=not args.no_assets)
    log("assets downloaded MB:", round(total / 1e6, 1))

    manifest = {
        "source": BASE,
        "fetched_via": MODE["source"],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - started),
        "sitemaps": sitemaps,
        "sitemap_urls": sm_urls,
        "api_counts": api_counts,
        "pages": pages,
        "assets": assets,
        "assets_total_bytes": total,
        "external_links": sorted(external_links),
    }
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    write_markdown(pages, assets, external_links, api_counts, sitemaps)
    with open(os.path.join(OUT, "README.md"), "w", encoding="utf-8") as f:
        f.write(README)
    log("DONE in", round(time.time() - started), "s")


if __name__ == "__main__":
    main()
