# yamunabuilders.com

Everything needed to keep **yamunabuilders.com** (Yamuna Homes and Design, Mangalore) online and to
rebuild it later, independent of the agency that ran the original WordPress site.

| Path | What it is |
|---|---|
| `archive/yamunabuilders.com/` | Full snapshot of the live site (Sept 2026): every page's HTML, all copy in `SITE-CONTENT.md`, the media library, theme/plugin assets, WordPress API dumps, `manifest.json`. |
| `scripts/build_mirror.py` | Builds a deployable static copy of the site into `dist/` (see `docs/MIRROR_HOSTING.md`). |
| `scripts/scrape_yamunabuilders.py` | The crawler that produced the archive; re-run via the Actions workflow to refresh. |
| `scripts/site_check.py` + `docs/SITE_CHECKUP.md` | Health check of production and staging (`python3 scripts/site_check.py [--staging]`). |
| `docs/MIRROR_HOSTING.md` | How to host the mirror for free (Cloudflare Pages), what differs from the live site, domain notes. |
| `docs/WORDPRESS_EXPORT_GUIDE.md` | What was exported from wp-admin and where the full UpdraftPlus backup lives (Google Drive). |
| `.github/workflows/` | `deploy.yml` (build + deploy to Cloudflare on every push to `main`), `scrape-yamunabuilders.yml` (refresh the archive: **only meaningful while the agency's WordPress site is still what yamunabuilders.com serves**; after the domain points at this mirror the crawler would only copy the mirror), `transcode-videos.yml` (web-sized videos), `fetch-url.yml` (helper). |

## Editing workflow: staging first, production on request

| Branch | Deploys to | When |
|---|---|---|
| `staging` | https://yamunabuilders-staging.yamunabuilders-mirror.workers.dev (noindex, "PREVIEW BUILD" badge) | automatically on every push |
| `main` | https://yamunabuilders.com | only when `staging` is merged into `main` ("Push to Prod") |

All edits are made on `staging` and checked on the preview address. Nothing reaches the live site
until the merge into `main`, which is the explicit "Push to Prod" step.

## Quick start

```sh
pip install -r requirements.txt
python3 scripts/build_mirror.py          # -> dist/
python3 -m http.server -d dist 8080      # preview at http://localhost:8080
```

## Site facts (from the archive)

- Stack of the original: WordPress 7.1, Salient 18.1.1 + WPBakery, Contact Form 7 (+ OTP, Turnstile),
  Rank Math, Popup Maker, Ultimate Image Gallery, hosted on Hostinger.
- Contact: yamunahomes16@gmail.com · +91 88844 39155 · WhatsApp wa.me/918884439155 ·
  1st Floor, Nalapad Building, Mallikatta, Kadri, Mangalore 575003.
- Fonts: the original used Adobe Fonts kit `nmv4gyz` (Ofelia Display, The Seasons); the mirror uses
  Nunito Sans and Cormorant Garamond from Google Fonts instead (no Adobe account needed).
- Analytics: GTM `GTM-NXVV44J6`, GA4 `G-YWB3RH6HGV`, Microsoft Clarity.

## What the backup covers

- Every public page, post, image, PDF, video, stylesheet and script the site served (this archive),
  plus the WordPress REST data behind the blog grid (posts, media, users, categories).
- Server-side behaviour that a static copy cannot run is reproduced in the mirror build: the blog
  grid's "Load More"/filters (pre-rendered), forms (e-mail hand-off), redirects and sitemap.
- Everything else (form settings, popups configuration, theme options, plugin settings, the full
  database) is in the UpdraftPlus backup below and can be restored on any WordPress host.

## Full backup

A complete UpdraftPlus backup (database + themes + plugins + 6.3 GB of uploads) taken on
2026-09-11 is in the Google Drive folder `UpdraftPlus` of the PC Productions account. Restoring it
on any WordPress host recreates the original site byte for byte.
