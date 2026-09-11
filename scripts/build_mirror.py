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

MIRROR_CSS = """
/* static mirror: hide backend-only controls */
.wpcf7-turnstile, .cf-turnstile, [data-name="verification-otp"], .evcf7_send_otp, .evcf7-send-otp { display: none !important; }
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
    return txt


def _bare(txt, m):
    """True when the host is followed by a quote/space (a link to the homepage itself)."""
    end = m.end()
    return end >= len(txt) or txt[end] in "\"' <)"


def clean_html(html, page_url, site_url, cfg):
    soup = BeautifulSoup(html, "lxml")
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
        html = clean_html(html, p["final_url"], args.site_url, cfg)
        dest = page_dest(out, p["final_url"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "w", encoding="utf-8").write(html)
        pages.append(url_path(p["final_url"]))
    log("pages written:", len(pages))

    # ---- helpers, redirects, sitemap, robots, 404 ---------------------------------------
    os.makedirs(os.path.join(out, "mirror"), exist_ok=True)
    open(os.path.join(out, "mirror", "forms.js"), "w", encoding="utf-8").write(FORMS_JS)
    with open(os.path.join(out, "_redirects"), "w") as f:
        for a, b in redirects:
            f.write(f"{a} {b} 301\n")
        f.write("/index.html / 301\n")
        f.write("/feed/ / 302\n")
        f.write("/wp-admin/* / 302\n")
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
    home = open(os.path.join(out, "index.html"), encoding="utf-8").read()
    open(os.path.join(out, "404.html"), "w", encoding="utf-8").write(
        home.replace("<title>", "<title>Page not found - ", 1))
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
