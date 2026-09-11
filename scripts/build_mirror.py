#!/usr/bin/env python3
"""Build a deployable static mirror of yamunabuilders.com from the archive.

Input : archive/yamunabuilders.com/  (pages/, assets/, web-media/, manifest.json)
Output: dist/  — drop onto any static host (Cloudflare Pages, Netlify, Vercel static, GitHub Pages)

    python scripts/build_mirror.py [--out dist] [--site-url https://example.com] [--max-file-mb 25]

Environment overrides: MIRROR_SITE_URL, WEB3FORMS_KEY (form relay), MIRROR_MAX_FILE_MB.
The result keeps the WordPress/Salient markup, CSS and JS exactly as served, with every
absolute link and asset pointed at the mirror itself, and with the parts that need a
WordPress backend (Contact Form 7 + OTP + Turnstile, comments, service worker, REST links)
replaced or removed so nothing on the page errors.
"""
import argparse
import json
import os
import re
import shutil
import sys
import urllib.parse
from datetime import datetime, timezone

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "archive", "yamunabuilders.com")
HOST_RE = re.compile(r"https?://(?:www\.)?yamunabuilders\.com")
HOST_ESC_RE = re.compile(r"https?:\\/\\/(?:www\.)?yamunabuilders\.com")
PROTO_REL_RE = re.compile(r"(?<=['\"(])//(?:www\.)?yamunabuilders\.com")
RESIZED_RE = re.compile(r"(/wp-content/uploads/[^\s\"'()<>?]+?)-(\d{2,5})x(\d{2,5})(\.(?:webp|jpe?g|png|gif|avif))", re.I)
TEXT_EXT = (".css", ".js", ".json", ".svg", ".xml", ".txt", ".html")
# Adobe Fonts (Typekit kit nmv4gyz) families -> free look-alikes served by Google Fonts
FONT_MAP = {
    "ofelia-display": '"Nunito Sans", "Helvetica Neue", Arial, sans-serif',   # body, nav, h4-h6
    "the-seasons": '"Cormorant Garamond", Georgia, "Times New Roman", serif',  # h1-h3 display serif
}
FONT_RE = re.compile(r"(?<![\w-])(ofelia-display|the-seasons)(?![\w-])", re.I)
GOOGLE_FONTS_CSS = ("https://fonts.googleapis.com/css2?family=Nunito+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400"
                    "&family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap")

FORMS_JS = r"""
/* Static-mirror replacement for Contact Form 7 (no WordPress backend behind this copy). */
(function () {
  var CFG = window.MIRROR_FORMS || {};
  function hideWrap(name, form) {
    form.querySelectorAll('[data-name="' + name + '"]').forEach(function (w) {
      var p = w.closest('p, label, .form-row, .wpb_wrapper > div') || w;
      // only hide the immediate line that contains just this field
      if (p.querySelectorAll('.wpcf7-form-control-wrap').length <= 1) p.style.display = 'none';
      else w.style.display = 'none';
    });
  }
  function prep(form) {
    hideWrap('verification-otp', form);
    form.querySelectorAll('.wpcf7-turnstile, .cf-turnstile, .evcf7_send_otp, .evcf7-send-otp, [class*="evcf7"]').forEach(function (el) { el.style.display = 'none'; });
    form.querySelectorAll('[name="verification-otp"]').forEach(function (i) { i.required = false; i.classList.remove('wpcf7-validates-as-required'); });
  }
  function msg(form, text, ok) {
    var out = form.querySelector('.wpcf7-response-output');
    if (!out) { out = document.createElement('div'); out.className = 'wpcf7-response-output'; form.appendChild(out); }
    out.textContent = text;
    out.style.display = 'block';
    out.style.borderColor = ok ? '#46b450' : '#dc3232';
    form.classList.remove('init');
    form.classList.add(ok ? 'sent' : 'failed');
  }
  function submit(e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement) || !form.classList.contains('wpcf7-form')) return;
    e.preventDefault(); e.stopImmediatePropagation();
    var data = {}, missing = false;
    form.querySelectorAll('input, textarea, select').forEach(function (i) {
      if (!i.name || i.name.charAt(0) === '_' || i.type === 'submit' || i.type === 'hidden') return;
      if (i.name === 'verification-otp') return;
      var v = (i.value || '').trim();
      if (i.classList.contains('wpcf7-validates-as-required') && !v) missing = true;
      data[i.name === 'verification' ? 'email' : i.name] = v;
    });
    if (missing) { msg(form, 'Please fill in all the required fields.', false); return; }
    var isBrochure = /brochure/i.test((form.querySelector('.wpcf7-submit') || {}).value || '');
    var btn = form.querySelector('.wpcf7-submit'); if (btn) btn.disabled = true;
    function done(ok) {
      if (btn) btn.disabled = false;
      if (ok) {
        msg(form, isBrochure ? 'Thank you. Opening the brochure…' : 'Thank you for your message. It has been sent.', true);
        form.reset();
        if (isBrochure && CFG.brochureUrl) setTimeout(function () { window.location.href = CFG.brochureUrl; }, 900);
      } else {
        msg(form, 'Sorry, the form could not be sent right now. Please call ' + (CFG.phone || '') +
          ' or WhatsApp us — the buttons are on this page.', false);
      }
    }
    if (isBrochure && CFG.brochureUrl && !CFG.web3formsKey) { done(true); return; }
    if (!CFG.web3formsKey) {
      // No relay configured: hand the enquiry to the visitor's e-mail app, pre-filled.
      var lines = [];
      Object.keys(data).forEach(function (k) { if (data[k]) lines.push(k.replace(/^your-/, '').replace(/-/g, ' ') + ': ' + data[k]); });
      lines.push('', 'Sent from ' + location.href);
      var subject = (isBrochure ? 'Brochure request' : 'Website enquiry') + (data['your-subject'] ? ' - ' + data['your-subject'] : '');
      window.location.href = 'mailto:' + (CFG.email || '') + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(lines.join('\n'));
      msg(form, 'Your e-mail app should open with the details filled in. If it does not, please e-mail ' + (CFG.email || '') + ', call ' + (CFG.phone || '') + ' or use the WhatsApp button.', true);
      if (btn) btn.disabled = false;
      return;
    }
    var payload = Object.assign({
      access_key: CFG.web3formsKey,
      subject: (isBrochure ? 'Brochure request' : 'Website enquiry') + ' — yamunabuilders.com',
      from_name: 'yamunabuilders.com website',
      page: location.href
    }, data);
    fetch('https://api.web3forms.com/submit', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (r) { return r.json(); }).then(function (j) { done(!!j.success); }).catch(function () { done(false); });
  }
  document.addEventListener('submit', submit, true);
  function init() { document.querySelectorAll('form.wpcf7-form').forEach(prep); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  // popups / ajax-loaded forms
  new MutationObserver(init).observe(document.documentElement, { childList: true, subtree: true });
})();
"""

POSTGRID_JS = r"""
/* Static-mirror replacement for Salient's post-grid AJAX (filters + load more).
   Every post is pre-rendered at build time, so filtering is done in the browser. */
(function () {
  function apply(wrap, slug) {
    wrap.querySelectorAll('.nectar-post-grid-item').forEach(function (it) {
      var cats = ' ' + (it.getAttribute('data-categories') || '') + ' ';
      var show = slug === '-1' || cats.indexOf(' ' + slug + ' ') !== -1;
      it.style.display = show ? '' : 'none';
    });
    var grid = wrap.querySelector('.nectar-post-grid');
    if (grid) window.dispatchEvent(new Event('resize'));
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest('.nectar-post-grid-filters a');
    if (!a) return;
    e.preventDefault(); e.stopImmediatePropagation();
    var wrap = a.closest('.nectar-post-grid-wrap');
    wrap.querySelectorAll('.nectar-post-grid-filters a').forEach(function (x) { x.classList.remove('active'); });
    a.classList.add('active');
    apply(wrap, a.getAttribute('data-filter'));
  }, true);
  document.addEventListener('click', function (e) {
    if (e.target.closest('.load-more-wrap')) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);
})();
"""

MIRROR_CSS = """
/* static mirror: hide backend-only controls */
.wpcf7-turnstile, .cf-turnstile, [data-name="verification-otp"], .evcf7_send_otp, .evcf7-send-otp { display: none !important; }
/* all posts are pre-rendered; the theme's load-more button has nothing to fetch */
.nectar-post-grid-wrap .load-more-wrap { display: none !important; }
"""


def log(*a):
    print(*a, flush=True)


def url_path(u):
    p = urllib.parse.urlparse(u)
    return p.path


def page_dest(out, url):
    path = urllib.parse.urlparse(url).path
    if path in ("", "/"):
        return os.path.join(out, "index.html")
    return os.path.join(out, path.strip("/"), "index.html")


def rewrite_text(txt, mirror_paths, site_url):
    """Point every yamunabuilders.com reference at the mirror and swap missing resized images."""
    txt = HOST_ESC_RE.sub("", txt)
    txt = HOST_RE.sub(lambda m: "/" if _bare(txt, m) else "", txt)
    txt = PROTO_REL_RE.sub("", txt)

    def fix_img(m):
        variant = m.group(0)
        if variant in mirror_paths:
            return variant
        original = m.group(1) + m.group(4)
        return original if original in mirror_paths else variant
    txt = RESIZED_RE.sub(fix_img, txt)
    txt = FONT_RE.sub(lambda m: FONT_MAP[m.group(1).lower()], txt)
    # Popup Maker analytics would POST to the WordPress REST API on every popup open
    txt = txt.replace('"analytics_enabled":"1"', '"analytics_enabled":"0"')
    return txt


def _bare(txt, m):
    """True when the host is followed by a quote/space (a link to the homepage itself)."""
    end = m.end()
    return end >= len(txt) or txt[end] in "\"' <)"


AVATARS = {
    "Yamuna Builders": "https://secure.gravatar.com/avatar/a3dfc3a93d2b34cc07c6e140bfe4e60d1c6ac34fd0c38101094b733097227e46",
    "Hazrath Mohammed": "https://secure.gravatar.com/avatar/f1b8a84b9af65469361f1859dd3da9aaca00c10d22324863f19ac0634083f062",
}
_WP = {}


def wp_data():
    """Posts, users, categories and media from the archived REST API dumps."""
    if not _WP:
        api = os.path.join(SRC, "api")
        def load(n):
            f = os.path.join(api, n + ".json")
            return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else []
        _WP["posts"] = sorted(load("posts"), key=lambda x: x["date"], reverse=True)
        _WP["users"] = {u["id"]: u for u in load("users")}
        _WP["cats"] = {c["id"]: c for c in load("categories")}
        _WP["media"] = {m["id"]: m for m in load("media")}
    return _WP


def complete_post_grids(soup, mirror_paths):
    """Salient post grids paginate/filter through WordPress AJAX. Pre-render every post so the
    static copy needs neither, and tag items with their category slugs for client-side filters."""
    import copy
    import html as htmlmod
    changed = False
    for wrap in soup.select(".nectar-post-grid-wrap"):
        try:
            settings = json.loads(wrap.get("data-el-settings", "{}"))
            query = json.loads(wrap.get("data-query", "{}"))
        except ValueError:
            continue
        if query.get("post_type") != "post":
            continue
        grid = wrap.select_one(".nectar-post-grid")
        items = wrap.select(".nectar-post-grid-item")
        if grid is None or not items:
            continue
        data = wp_data()
        # tag existing items with category slugs (from the category button's class)
        for it in items:
            slugs = [c for a in it.select(".meta-category a") for c in a.get("class", []) if c != "style-button"]
            it["data-categories"] = " ".join(slugs)
        if settings.get("pagination") != "load-more":
            continue
        have = {it.get("data-post-id") for it in items}
        template = items[0]
        for post in data["posts"]:
            pid = str(post["id"])
            if pid in have:
                continue
            it = copy.copy(template)
            it["data-post-id"] = pid
            title = htmlmod.unescape(post["title"]["rendered"])
            link = url_path(post["link"])
            m = data["media"].get(post.get("featured_media"))
            img = it.select_one("img.nectar-post-grid-item-bg__media")
            if m and img is not None:
                full = url_path(m["source_url"])
                sizes = (m.get("media_details") or {}).get("sizes", {})
                cands = []
                for sz in sizes.values():
                    pth = url_path(sz["source_url"])
                    if pth in mirror_paths and sz.get("width"):
                        cands.append((int(sz["width"]), pth))
                if full in mirror_paths:
                    w = (m.get("media_details") or {}).get("width") or 1920
                    cands.append((int(w), full))
                cands = sorted(set(cands))
                if cands:
                    best = max(cands, key=lambda c: c[0] if c[0] <= 1200 else 0)
                    img["data-nectar-img-src"] = best[1]
                    img["data-nectar-img-srcset"] = ", ".join(f"{p} {w}w" for w, p in cands)
                    img["alt"] = m.get("alt_text") or ""
                    md = m.get("media_details") or {}
                    if md.get("width") and md.get("height"):
                        img["width"], img["height"] = str(md["width"]), str(md["height"])
                        img["src"] = ("data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D'http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg'"
                                      f"%20viewBox%3D'0%200%20{md['width']}%20{md['height']}'%2F%3E")
                it["data-has-img"] = "true"
            elif img is not None:
                it["data-has-img"] = "false"
            a = it.select_one("a.nectar-post-grid-link")
            if a is not None:
                a["href"] = link
                sr = a.select_one(".screen-reader-text")
                if sr is not None:
                    sr.string = title
            h = it.select_one(".post-heading span") or it.select_one(".post-heading")
            if h is not None:
                h.string = title
            cats = [data["cats"][c] for c in post.get("categories", []) if c in data["cats"] and data["cats"][c]["slug"] != "uncategorized"]
            mc = it.select_one(".meta-category")
            if mc is not None:
                mc.clear()
                for c in cats[:1]:
                    ca = soup.new_tag("a", href=f"/category/{c['slug']}/")
                    ca["class"] = [c["slug"], "style-button"]
                    ca.string = htmlmod.unescape(c["name"])
                    mc.append(ca)
            it["data-categories"] = " ".join(c["slug"] for c in cats)
            author = data["users"].get(post.get("author"), {}).get("name", "")
            an = it.select_one(".meta-author-name")
            if an is not None:
                an.string = author
            av = it.select_one(".meta-author img")
            if av is not None and author in AVATARS:
                av["alt"] = author
                av["src"] = AVATARS[author] + "?s=40&d=mm&r=g"
                av["srcset"] = AVATARS[author] + "?s=80&d=mm&r=g 2x"
            rt = it.select_one(".meta-reading-time")
            if rt is not None:
                words = len(BeautifulSoup(post["content"]["rendered"], "lxml").get_text(" ").split())
                rt.string = f"{max(1, round(words / 200))} min"
            grid.append(it)
            changed = True
    return changed


def clean_html(html, page_url, site_url, cfg, mirror_paths=frozenset()):
    soup = BeautifulSoup(html, "lxml")
    grids_completed = complete_post_grids(soup, mirror_paths)
    # WordPress backend links that make no sense on a static host
    for sel in ['link[rel="https://api.w.org/"]', 'link[rel="alternate"][type="application/json"]',
                'link[rel="EditURI"]', 'link[rel="wlwmanifest"]', 'link[rel="shortlink"]',
                'link[rel="alternate"][type="application/rss+xml"]', 'link[rel="pingback"]',
                'link[rel="manifest"]', 'link[rel="prefetch"][href$="superpwa-manifest.json"]',
                'script#superpwa-register-sw-js', 'script#superpwa-register-sw-js-extra',
                'link[rel="alternate"][type="application/json+oembed"]', 'link[rel="alternate"][type="text/xml+oembed"]',
                'meta[name="generator"]',
                # Contact Form 7 stack: needs WordPress REST; replaced by /mirror/forms.js
                'script#contact-form-7-js', 'script#contact-form-7-js-before', 'script#swv-js',
                'script#evcf7-front-script-js', 'script#evcf7-front-script-js-extra',
                'script#wpcf7-redirect-script-js', 'script#wpcf7-redirect-script-js-extra',
                'script#cloudflare-turnstile-js', 'script#cloudflare-turnstile-js-after',
                'script#akismet-frontend-js', 'link#evcf7-front-style-css', 'link#wpcf7-redirect-script-frontend-css',
                # Adobe Fonts kit (domain-restricted) -> replaced by Google Fonts below
                'link[href*="use.typekit.net"]', 'link[href*="typekit.net"]']:
        for el in soup.select(sel):
            el.decompose()
    # comment forms post to wp-comments-post.php
    for el in soup.select("#respond, form#commentform, .comment-respond"):
        el.decompose()
    # canonical / og:url
    if site_url:
        for el in soup.select('link[rel="canonical"], meta[property="og:url"]'):
            key = "href" if el.name == "link" else "content"
            v = el.get(key, "")
            if v.startswith("/"):
                el[key] = site_url.rstrip("/") + v
    # mirror helpers
    head = soup.head or soup
    first_css = head.find("link", rel="stylesheet")
    pre1 = soup.new_tag("link", rel="preconnect", href="https://fonts.googleapis.com")
    pre2 = soup.new_tag("link", rel="preconnect", href="https://fonts.gstatic.com", crossorigin="")
    gf = soup.new_tag("link", rel="stylesheet", href=GOOGLE_FONTS_CSS, id="mirror-google-fonts")
    for tag in (gf, pre2, pre1):
        if first_css is not None:
            first_css.insert_before(tag)
        else:
            head.append(tag)
    style = soup.new_tag("style", id="mirror-css"); style.string = MIRROR_CSS
    head.append(style)
    body = soup.body or soup
    conf = soup.new_tag("script", id="mirror-forms-config")
    conf.string = "window.MIRROR_FORMS=" + json.dumps(cfg) + ";"
    body.append(conf)
    js = soup.new_tag("script", src="/mirror/forms.js", id="mirror-forms-js")
    body.append(js)
    if soup.select_one(".nectar-post-grid-wrap"):
        pg = soup.new_tag("script", src="/mirror/postgrid.js", id="mirror-postgrid-js")
        body.append(pg)
    note = f"<!-- static mirror of {page_url} built {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} -->"
    return str(soup).replace("</html>", note + "\n</html>", 1)


REF_RE = re.compile(r"/wp-(?:content|includes)/[^\s\"'()<>\\]+")


def _candidates(path):
    """Alternative archive names for a referenced upload: unsized, -scaled, and non-webp twins."""
    out = []
    m = RESIZED_RE.match(path)
    base = (m.group(1) + m.group(4)) if m else path
    for b in (path, base):
        out.append(b)
        for ext in (".webp", ".jpg", ".jpeg", ".png"):
            if b.lower().endswith(ext):
                stem = b[: -len(ext)]
                out.append(stem + "-scaled" + ext)
                if stem.lower().endswith((".jpg", ".jpeg", ".png")):
                    out.append(stem)                        # x.jpg.webp -> x.jpg
                    s2 = stem[: stem.rfind(".")]
                    out.append(s2 + "-scaled" + stem[stem.rfind("."):] + ext)
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c); res.append(c)
    return res


def prune_uploads(out, manifest, mirror_paths):
    """Walk HTML -> CSS/JS -> referenced files; delete uploads nothing points at."""
    archive_files = {url_path(u): os.path.join(SRC, r["file"]) for u, r in manifest["assets"].items()
                     if r.get("file") and not r.get("file_parts")}
    referenced, queue = set(), []
    for root, _, files in os.walk(out):
        for fn in files:
            if fn.endswith(".html"):
                queue.append(os.path.join(root, fn))
    scanned = set()
    while queue:
        f = queue.pop()
        if f in scanned:
            continue
        scanned.add(f)
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for ref in REF_RE.findall(txt):
            ref = ref.split("?")[0].split("#")[0].replace("\\/", "/")
            if "*" in ref:
                continue
            referenced.add(ref)
            if ref.lower().endswith((".css", ".js")):
                queue.append(os.path.join(out, ref.lstrip("/")))
    missing = []
    for ref in sorted(referenced):
        dest = os.path.join(out, ref.lstrip("/"))
        if os.path.exists(dest) or not ref.startswith("/wp-content/uploads/"):
            continue
        for cand in _candidates(ref):
            src = archive_files.get(cand)
            if src and os.path.exists(src):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copyfile(src, dest)
                mirror_paths.add(ref)
                break
        else:
            missing.append(ref)
    # any referenced resized name whose twin we also hold: keep the twin (galleries derive names)
    keep = set(referenced)
    for ref in list(referenced):
        for cand in _candidates(ref):
            keep.add(cand)
    kept = 0
    up = os.path.join(out, "wp-content", "uploads")
    for root, _, files in os.walk(up):
        for fn in files:
            full = os.path.join(root, fn)
            rel = "/" + os.path.relpath(full, out).replace(os.sep, "/")
            if rel in keep or "/uploads/pum/" in rel:
                kept += 1
            else:
                os.remove(full)
    for root, dirs, files in os.walk(up, topdown=False):
        if not os.listdir(root):
            os.rmdir(root)
    return kept, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--site-url", default=os.environ.get("MIRROR_SITE_URL", ""))
    ap.add_argument("--max-file-mb", type=float, default=float(os.environ.get("MIRROR_MAX_FILE_MB", "25")))
    args = ap.parse_args()
    out = args.out
    max_bytes = int(args.max_file_mb * 1024 * 1024)
    manifest = json.load(open(os.path.join(SRC, "manifest.json"), encoding="utf-8"))
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    # ---- assets -------------------------------------------------------------------------
    mirror_paths = set()
    skipped_big, copied = [], 0
    web_media = os.path.join(SRC, "web-media")
    for u, rec in manifest["assets"].items():
        if not rec.get("file"):
            continue
        dest_rel = url_path(u)
        if not dest_rel.startswith(("/wp-content/", "/wp-includes/")) or dest_rel.endswith("/"):
            continue
        dest = os.path.join(out, dest_rel.lstrip("/"))
        if dest_rel in mirror_paths:
            continue
        src = os.path.join(SRC, rec["file"])
        if rec.get("file_parts"):
            alt = os.path.join(web_media, os.path.basename(rec["file"]))
            if os.path.exists(alt):
                src = alt
            else:
                skipped_big.append((u, rec["bytes"], "no web-sized version yet"))
                continue
        elif rec.get("bytes", 0) > max_bytes:
            skipped_big.append((u, rec["bytes"], "over host limit"))
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
        mirror_paths.add(dest_rel)
        copied += 1
    log("assets copied:", copied, "| skipped:", len(skipped_big))

    # rewrite absolute references inside CSS / JS / SVG / JSON
    for root, _, files in os.walk(out):
        for fn in files:
            if fn.lower().endswith(TEXT_EXT):
                p = os.path.join(root, fn)
                try:
                    txt = open(p, encoding="utf-8").read()
                except UnicodeDecodeError:
                    continue
                new = rewrite_text(txt, mirror_paths, args.site_url)
                if new != txt:
                    open(p, "w", encoding="utf-8").write(new)

    # ---- pages --------------------------------------------------------------------------
    phone = "+91 88844 39155"
    cfg = {"web3formsKey": os.environ.get("WEB3FORMS_KEY", ""), "phone": phone,
           "email": os.environ.get("MIRROR_CONTACT_EMAIL", "yamunahomes16@gmail.com"),
           "brochureUrl": "/sky-city-brochure/"}
    pages, redirects = [], []
    for u, p in manifest["pages"].items():
        if p.get("redirected_to"):
            redirects.append((url_path(u), url_path(p["redirected_to"])))
            continue
        if not p.get("html_file"):
            continue
        html = open(os.path.join(SRC, p["html_file"]), encoding="utf-8", errors="ignore").read()
        html = rewrite_text(html, mirror_paths, args.site_url)
        html = clean_html(html, p["final_url"], args.site_url, cfg, mirror_paths)
        dest = page_dest(out, p["final_url"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "w", encoding="utf-8").write(html)
        pages.append(url_path(p["final_url"]))
    log("pages written:", len(pages))

    # ---- helpers, redirects, sitemap, robots, 404 ---------------------------------------
    os.makedirs(os.path.join(out, "mirror"), exist_ok=True)
    open(os.path.join(out, "mirror", "forms.js"), "w", encoding="utf-8").write(FORMS_JS)
    open(os.path.join(out, "mirror", "postgrid.js"), "w", encoding="utf-8").write(POSTGRID_JS)
    # WordPress AJAX endpoint: answer "0" like WordPress does for unknown actions, never a page
    os.makedirs(os.path.join(out, "wp-admin"), exist_ok=True)
    open(os.path.join(out, "wp-admin", "admin-ajax.php"), "w").write("0")
    with open(os.path.join(out, "_redirects"), "w") as f:
        for a, b in redirects:
            f.write(f"{a} {b} 301\n")
        f.write("/index.html / 301\n")
        # WordPress / Rank Math sitemap URLs Google already knows -> the mirror's sitemap
        for old in ("/sitemap_index.xml", "/post-sitemap.xml", "/page-sitemap.xml",
                    "/uig_image_gallery-sitemap.xml", "/wp-sitemap.xml", "/sitemap.xml.gz"):
            f.write(f"{old} /sitemap.xml 301\n")
        f.write("/feed/ / 302\n")
        f.write("/wp-login.php / 302\n")
    with open(os.path.join(out, "_headers"), "w") as f:
        f.write("/wp-content/*\n  Cache-Control: public, max-age=31536000, immutable\n")
        f.write("/wp-includes/*\n  Cache-Control: public, max-age=31536000, immutable\n")
    base = args.site_url.rstrip("/")
    with open(os.path.join(out, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for path in sorted(pages):
            if "/page/" in path or path.startswith(("/author/", "/uig_image_gallery/")):
                continue
            f.write(f"  <url><loc>{base}{path}</loc></url>\n")
        f.write("</urlset>\n")
    open(os.path.join(out, "robots.txt"), "w").write(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")
    open(os.path.join(out, "404.html"), "w", encoding="utf-8").write(
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='robots' content='noindex'><title>Page not found - Yamuna Homes and Design</title>"
        "<style>body{margin:0;font-family:'Nunito Sans',Helvetica,Arial,sans-serif;background:#fff;color:#222;display:flex;"
        "min-height:100vh;align-items:center;justify-content:center;text-align:center}main{padding:40px}h1{font-weight:400;"
        "font-size:28px}a{color:#a11d1d}</style></head><body><main><h1>Page not found</h1>"
        "<p>The page you were looking for is not here.</p><p><a href='/'>Go to the homepage</a> · "
        "<a href='/insights/'>Insights</a> · <a href='/contact/'>Contact</a></p></main></body></html>")
    # ---- keep only the media the pages actually use; resolve names scripts derive -------
    kept, missing = prune_uploads(out, manifest, mirror_paths)
    log(f"uploads kept: {kept} | referenced but unavailable: {len(missing)}")
    for m in missing[:20]:
        log("  missing:", m)

    # ---- report -------------------------------------------------------------------------
    total = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(out) for f in fs)
    nfiles = sum(len(fs) for _, _, fs in os.walk(out))
    log(f"dist: {nfiles} files, {total/1e6:.0f} MB")
    for u, b, why in skipped_big:
        log(f"  skipped {u} ({b/1e6:.0f} MB): {why}")
    if not cfg["web3formsKey"]:
        log(f"note: forms hand enquiries to the visitor's e-mail app addressed to {cfg['email']} (set WEB3FORMS_KEY to relay silently instead)")


if __name__ == "__main__":
    main()
