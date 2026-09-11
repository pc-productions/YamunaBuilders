# Site checkup for yamunabuilders.com (task for Claude Code in the terminal)

Run this whenever you want to confirm the live site and the staging preview are healthy, or after any
"Push to Prod". It takes about two minutes and needs nothing but Python and internet access.

## What to do

1. From the repo root (`git pull` first so the script is current):

   ```
   pip install -r requirements.txt
   pip install playwright && python -m playwright install chromium      # once; enables the render checks
   python3 scripts/site_check.py                                        # production: https://yamunabuilders.com
   python3 scripts/site_check.py --staging                              # preview Worker
   ```

2. Read the report. Every line is `PASS` or `FAIL`; the last lines summarise. Exit code 0 = all good.

3. If anything FAILs, do **not** change the live site. Diagnose from the check name and detail:

   | Failing check | Usual meaning | What to do |
   |---|---|---|
   | DNS resolves / points at Cloudflare / old server | domain or nameserver problem | Look at GoDaddy nameservers (must be `lamar` / `maleah.ns.cloudflare.com`) and Cloudflare DNS; report to the owner, don't edit DNS unasked |
   | http→https or www redirect | Cloudflare rule missing | Cloudflare → yamunabuilders.com → Rules → Redirect Rules ("Redirect from WWW to root") and SSL/TLS → Edge Certificates → Always Use HTTPS |
   | Served by Cloudflare | site not going through Cloudflare | check the Worker's custom domains: Workers & Pages → yamunabuilders → Domains |
   | key pages / assets 200 | broken deploy | GitHub → Actions → "Deploy mirror to Cloudflare": open the latest run; rebuild locally with `python3 scripts/build_mirror.py` and `python3 scripts/site_check.py --base http://localhost:8080 --expect prod` |
   | Insights grid 35 posts / Load More | post-grid pre-render regressed | `scripts/build_mirror.py`, `complete_post_grids()` |
   | Canonical / indexing flag / robots | env mix-up between staging and prod | `.github/workflows/deploy.yml` env values: `MIRROR_SITE_URL`, `MIRROR_NOINDEX` |
   | Contact form / OTP hidden / hand-off script | forms shim regressed | `scripts/build_mirror.py`, `FORMS_JS` and `MIRROR_CSS` |
   | Rendered pages: JS errors / failed requests | something on a page calls the old WordPress backend | run `python3 scripts/site_check.py` with render enabled, then reproduce in a browser dev-tools console on the failing page |

4. Report back to the owner in plain words: what passed, what failed, the likely cause, and the fix you
   propose. Make fixes on the `staging` branch only; they go live only when the owner says "Push to Prod".

## What the script covers

DNS (Cloudflare, not the old Hostinger IP) · http→https and www→root redirects · served via Cloudflare ·
14 key pages return the mirror · logo, theme CSS, mirror scripts and a video load · sitemap.xml,
old WordPress sitemap redirect, robots.txt per environment · plain 404 page · WordPress AJAX endpoint
answers `0` · legacy redirect · canonical and noindex per environment · analytics tags present · contact
form present with OTP hidden and the e-mail hand-off script · Insights grid shows all 35 posts · rendered
homepage, Insights, Contact and Sky City pages have no JavaScript errors or failed requests.

## Not covered (check by hand occasionally)

- Google Search Console: coverage errors and the sitemap status.
- Cloudflare dashboard: Workers errors should stay at 0; total requests should not drop to zero.
- Domain renewal date at GoDaddy.
