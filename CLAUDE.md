# YamunaBuilders repo guide

This repo keeps **yamunabuilders.com** (Yamuna Homes and Design, Mangalore) online independently of
the agency that ran the original WordPress site. Read `docs/CLAUDE_CODE_DEPLOY_TASK.md` for the
current task.

- `archive/yamunabuilders.com/` — frozen snapshot of the live site (do not edit by hand; refresh via
  the "Scrape" workflow). `SITE-CONTENT.md` there has every page's text; `manifest.json` indexes it.
- `scripts/build_mirror.py` — builds the deployable static site into `dist/` (git-ignored).
  Env: `MIRROR_SITE_URL`, `MIRROR_CONTACT_EMAIL`, `WEB3FORMS_KEY`, `MIRROR_MAX_FILE_MB`.
- `wrangler.jsonc` + `package.json` — Cloudflare Workers static-assets deployment (`npm run deploy`).
- `.github/workflows/deploy.yml` — deploys on push to `main` once the repo secrets
  `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` exist.
- `docs/MIRROR_HOSTING.md` — what differs from the live site and hosting notes.
- `docs/WORDPRESS_EXPORT_GUIDE.md` — the WordPress backup (full UpdraftPlus backup is in Google Drive).

Rules: never commit secrets or the database backup (the repo may become public); keep `archive/`
untouched; run `python3 scripts/build_mirror.py` and check `dist/` before deploying; commit messages
in plain imperative English.
