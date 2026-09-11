#!/usr/bin/env python3
"""Health check for the yamunabuilders.com mirror (production and staging).

    python3 scripts/site_check.py                 # production: https://yamunabuilders.com
    python3 scripts/site_check.py --staging       # preview Worker
    python3 scripts/site_check.py --base http://localhost:8080 --no-dns   # a local build

Exit code 0 = all checks passed, 1 = something failed. Requires: requests (pip install requests).
Optional: playwright (pip install playwright; playwright install chromium) for the render checks.
"""
import argparse
import json
import re
import socket
import sys
import time

import requests

PROD = "https://yamunabuilders.com"
STAGING = "https://yamunabuilders-staging.yamunabuilders-mirror.workers.dev"
OLD_SERVER_IP = "147.93.24.97"
PAGES = ["/", "/about/", "/contact/", "/projects/", "/projects/ongoing-projects/", "/projects/completed-projects/",
         "/yamuna-sky-city/", "/yamuna-kamaldeep-twin-tower/", "/insights/", "/gallery/", "/plans/",
         "/other-services/", "/top-smart-home-features-mangalore-apartments/", "/category/yamuna-sky-city/"]
ASSETS = ["/wp-content/uploads/2024/12/YAMUNA_LOGO-png.webp", "/wp-content/themes/salient/css/build/style.css",
          "/mirror/forms.js", "/mirror/postgrid.js", "/wp-content/uploads/2026/04/2774-sky-city-digital-brochure-020.mp4"]
UA = "Mozilla/5.0 (site-check) yamunabuilders-mirror"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)


def get(url, **kw):
    kw.setdefault("timeout", 30)
    kw.setdefault("headers", {"User-Agent": UA})
    kw.setdefault("allow_redirects", False)
    return requests.get(url, **kw)


def dns_checks(host):
    try:
        ips = sorted({ai[4][0] for ai in socket.getaddrinfo(host, 443, socket.AF_INET)})
    except Exception as e:  # noqa: BLE001
        check("DNS resolves", False, str(e)); return
    check("DNS resolves", bool(ips), ", ".join(ips))
    check("DNS does not point at the old Hostinger server", OLD_SERVER_IP not in ips, OLD_SERVER_IP)
    cf = all(ip.startswith(("104.", "172.", "162.", "108.", "141.", "188.", "190.", "197.", "198.")) for ip in ips)
    check("DNS points at Cloudflare", cf, ", ".join(ips))


def http_checks(base, is_prod):
    host = base.split("//")[1]
    if is_prod:
        r = get("http://" + host + "/")
        check("http:// redirects to https://", r.status_code in (301, 302, 307, 308) and r.headers.get("Location", "").startswith("https://"),
              f"{r.status_code} -> {r.headers.get('Location', '')}")
        r = get("https://www." + host + "/")
        check("www redirects to root", r.status_code in (301, 302, 307, 308) and "://" + host in r.headers.get("Location", ""),
              f"{r.status_code} -> {r.headers.get('Location', '')}")
    r = get(base + "/", allow_redirects=True)
    check("Served by Cloudflare", "cf-ray" in {k.lower() for k in r.headers}, r.headers.get("server", ""))


def page_checks(base, is_prod, canonical_base):
    bad = []
    for p in PAGES:
        try:
            r = get(base + p, allow_redirects=True)
            html = r.text
            ok = r.status_code == 200 and "static mirror of" in html and "<title>" in html
            if not ok:
                bad.append(f"{p} -> {r.status_code}")
            if p == "/":
                check("Homepage title", "Yamuna" in html.split("<title>", 1)[1].split("</title>", 1)[0])
                check("No links back to the old WordPress host", "https://yamunabuilders.com/wp-admin" not in html)
                check("Contact details present", "+91 88844 39155" in html and "yamunahomes16@gmail.com" in html)
                canon = re.search(r'<link href="([^"]+)" rel="canonical"', html)
                check("Canonical points at the right host", bool(canon) and canon.group(1).startswith(canonical_base), canon.group(1) if canon else "missing")
                noindex = bool(re.search(r'<meta[^>]*noindex', html))
                check("Indexing flag matches environment", noindex != is_prod, "noindex present" if noindex else "indexable")
                check("Analytics tags present", "GTM-NXVV44J6" in html and "G-YWB3RH6HGV" in html)
            if p == "/insights/":
                n = html.count('class="nectar-post-grid-item"')
                check("Insights grid has all 35 posts", n == 35, str(n))
                check("Insights uses client-side grid script", "/mirror/postgrid.js" in html)
            if p == "/contact/":
                check("Contact form present", 'class="wpcf7-form' in html)
                check("OTP field hidden by mirror CSS", '[data-name="verification-otp"]' in html and "display: none" in html)
                check("Form hand-off script present", "/mirror/forms.js" in html and "MIRROR_FORMS" in html)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{p} -> {e}")
        time.sleep(0.2)
    check(f"All {len(PAGES)} key pages return 200 from the mirror", not bad, "; ".join(bad))


def asset_checks(base):
    bad = []
    for a in ASSETS:
        try:
            r = requests.head(base + a, timeout=30, headers={"User-Agent": UA}, allow_redirects=True)
            if r.status_code != 200:
                bad.append(f"{a} -> {r.status_code}")
        except Exception as e:  # noqa: BLE001
            bad.append(f"{a} -> {e}")
    check("Key assets (logo, theme CSS, mirror scripts, video) load", not bad, "; ".join(bad))


def misc_checks(base, is_prod, host_features=True):
    r = get(base + "/sitemap.xml", allow_redirects=True)
    urls = re.findall(r"<loc>(.*?)</loc>", r.text) if r.status_code == 200 else []
    check("sitemap.xml lists the pages", r.status_code == 200 and len(urls) >= 50, f"{len(urls)} urls")
    r = get(base + "/robots.txt", allow_redirects=True)
    want = "Allow: /" if is_prod else "Disallow: /"
    check("robots.txt matches environment", r.status_code == 200 and want in r.text, r.text.strip().replace("\n", " | ")[:80])
    r = get(base + "/wp-admin/admin-ajax.php", allow_redirects=True)
    check("WordPress AJAX endpoint answers '0' (never a page)", r.status_code == 200 and r.text.strip() == "0", r.text[:40])
    if not host_features:
        print("SKIP redirect/404 checks (need the Cloudflare host)")
        return
    r = get(base + "/sitemap_index.xml")
    check("Old WordPress sitemap URL redirects to sitemap.xml", r.status_code in (301, 302, 308) and r.headers.get("Location", "").endswith("/sitemap.xml"),
          f"{r.status_code}")
    r = get(base + "/this-page-does-not-exist-xyz/", allow_redirects=True)
    check("Unknown URL returns 404 with the plain not-found page", r.status_code == 404 and "Page not found" in r.text and "nectar" not in r.text, str(r.status_code))
    r = get(base + "/living-between-the-city-and-the-sea-how-mangalore-is-redefining-sea-view-apartment-living/")
    check("Legacy redirect preserved", r.status_code in (301, 308) and "sea-view-apartments-in-mangalore" in r.headers.get("Location", ""), str(r.status_code))


def render_checks(base):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP render checks (pip install playwright && playwright install chromium to enable)")
        return
    errors, failed = [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1366, "height": 800})
        page.on("pageerror", lambda e: errors.append(str(e)[:120]))
        page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.url.startswith(base) and r.status >= 400 else None)
        for path in ["/", "/insights/", "/contact/", "/yamuna-sky-city/"]:
            page.goto(base + path, wait_until="load", timeout=60000)
            for _ in range(8):
                page.evaluate("window.scrollBy(0, 800)"); page.wait_for_timeout(250)
            page.wait_for_timeout(800)
        page.goto(base + "/insights/", wait_until="load"); page.wait_for_timeout(1500)
        for _ in range(12):
            page.evaluate("window.scrollBy(0, 700)"); page.wait_for_timeout(150)
        lm = page.evaluate("(()=>{const e=document.querySelector('.load-more-wrap');return e?getComputedStyle(e).display:'absent'})()")
        b.close()
    check("Rendered pages: no JavaScript errors", not errors, "; ".join(errors[:3]))
    check("Rendered pages: no failed requests to this host", not failed, "; ".join(failed[:3]))
    check("Insights: 'Load More' button not shown", lm in ("none", "absent"), lm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--staging", action="store_true", help="check the staging preview instead of production")
    ap.add_argument("--base", help="custom base URL (e.g. http://localhost:8080)")
    ap.add_argument("--no-dns", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--expect", choices=["prod", "preview"], help="which build to expect at a custom --base")
    a = ap.parse_args()
    base = (a.base or (STAGING if a.staging else PROD)).rstrip("/")
    custom = bool(a.base)
    is_prod = (a.expect == "prod") if custom else (base == PROD)
    print(f"== Site check: {base} (expecting {'production' if is_prod else 'preview'} build{', local/custom host' if custom else ''})")
    if not a.no_dns and not custom:
        dns_checks(base.split("//")[1])
    if not custom:
        http_checks(base, is_prod)
    page_checks(base, is_prod, PROD if (custom and is_prod) else base)
    asset_checks(base)
    misc_checks(base, is_prod, host_features=not custom)
    if not a.no_render:
        render_checks(base)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = [(n, d) for n, ok, d in results if not ok]
    print(f"\n== {passed}/{len(results)} checks passed")
    for n, d in failed:
        print(f"   FAILED: {n} {('[' + d + ']') if d else ''}")
    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
