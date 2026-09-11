# Task for Claude Code (local terminal): put the yamunabuilders.com mirror live on Cloudflare

You are working in a local clone of `pc-productions/YamunaBuilders`. A remote session already built
and tested the static mirror (`scripts/build_mirror.py` → `dist/`, 83 pages, ~170 MB, zero broken
assets). Your job is the part that needs a browser login and Cloudflare's API: deploy it, wire up
auto-deploys, and stage the domain. Do the steps in order; stop and ask the user only where marked.

## 0. Context you need

- Goal: an exact, lightweight copy of https://yamunabuilders.com/ hosted under the client's control,
  free, on Cloudflare. The agency may take the original down any day.
- The domain `yamunabuilders.com` is registered at **GoDaddy** (client-controlled). It must keep
  pointing at the agency's server until the client says otherwise.
- Contact details on the site stay as they are: yamunahomes16@gmail.com, +91 88844 39155.
- Forms on the mirror open the visitor's mail app (no backend). Do not "fix" this.
- Never commit secrets. Never edit `archive/`.

## 1. Cloudflare tooling for this agent (Cloudflare's official setup)

Run exactly these (from https://developers.cloudflare.com/agent-setup/prompt.md):

```
claude plugin marketplace add cloudflare/skills
claude plugin install cloudflare@cloudflare
```

Then ask the user to run `/reload-plugins` in Claude Code. On first use of a Cloudflare MCP tool a
browser OAuth window opens; the user signs in to their Cloudflare account (free plan is fine).

## 2. Local prerequisites

```
python3 --version            # 3.10+
pip install -r requirements.txt
node --version               # 18+ ; install Node LTS if missing
npm install                  # installs wrangler locally
npx wrangler login           # opens the browser; user signs in to Cloudflare
npx wrangler whoami          # prints the account name and Account ID — note the Account ID
```

## 3. Build and preview

```
npm run build                # python3 scripts/build_mirror.py -> dist/
npm run preview              # http://localhost:8080 — open /, /contact/, /yamuna-sky-city/
```

Expect "pages written: 83" and "referenced but unavailable: 0". If the build fails, fix the cause
(usually a missing Python package) rather than editing the archive.

## 4. First deployment (Workers static assets)

```
npx wrangler deploy
```

This creates a Worker named `yamunabuilders` that serves `dist/` and prints a URL like
`https://yamunabuilders.<account>.workers.dev`. Then verify:

```
for p in / /contact/ /yamuna-sky-city/ /projects/ /insights/ /gallery/ /wp-content/uploads/2024/12/YAMUNA_LOGO-png.webp; do
  curl -s -o /dev/null -w "%{http_code} $p\n" "https://yamunabuilders.<account>.workers.dev$p"; done
```

All must be 200. Open the homepage in a browser: header, hero image, WhatsApp button and fonts
(Nunito Sans / Cormorant Garamond) should render; the contact page's form should show no OTP field.

If `wrangler deploy` is refused because assets-only Workers are not available on the account, use
Pages instead: `npx wrangler pages project create yamunabuilders --production-branch main` then
`npm run deploy:pages`; the URL becomes `https://yamunabuilders.pages.dev`.

## 5. Auto-deploy from GitHub

1. Create an API token: Cloudflare dashboard → My Profile → API Tokens → Create Token → template
   **Edit Cloudflare Workers** → Create. (Ask the user to do this in the browser and paste the token
   into the GitHub secret themselves; do not print it.)
2. In GitHub → `pc-productions/YamunaBuilders` → Settings → Secrets and variables → Actions:
   - secret `CLOUDFLARE_API_TOKEN` = the token
   - secret `CLOUDFLARE_ACCOUNT_ID` = the Account ID from `wrangler whoami`
   - variable `MIRROR_SITE_URL` = the deployed URL for now (later `https://yamunabuilders.com`)
3. Run the workflow once: Actions → "Deploy mirror to Cloudflare" → Run workflow. It must go green.
   From then on every push to `main` redeploys.

## 6. Stage the domain (no cut-over yet)

1. Cloudflare dashboard → Add a site → `yamunabuilders.com` → Free plan. Cloudflare scans and imports
   the existing DNS records (the A record pointing at the agency's Hostinger server, any MX/TXT for
   e-mail). **Ask the user to confirm the imported list matches GoDaddy's DNS page**, especially MX.
2. Cloudflare shows two nameservers. **Stop and ask the user** before they change nameservers at
   GoDaddy (GoDaddy → My Products → domain → DNS → Nameservers → Change). After the change the site
   still resolves to the agency's server because the records were imported unchanged.
3. Do **not** attach the custom domain to the Worker yet.

## 7. Cut-over (only when the user says the agency's site is down or they want to switch)

1. Workers & Pages → `yamunabuilders` → Settings → Domains & Routes → Add → Custom domain →
   `yamunabuilders.com`, then again for `www.yamunabuilders.com`. Cloudflare replaces the A record.
2. Set the GitHub variable `MIRROR_SITE_URL` to `https://yamunabuilders.com` and re-run the deploy
   workflow so canonical tags and the sitemap carry the real domain.
3. Verify `https://yamunabuilders.com/`, `/contact/`, `/yamuna-sky-city/` return 200 over HTTPS and
   that `www` redirects or serves the same site.
4. Optional, free: Cloudflare → Email Routing to forward addresses like info@yamunabuilders.com to
   the client's Gmail.

## 8. Report

Tell the user: the live URL(s), whether the GitHub deploy is green, the nameservers to set at GoDaddy
(if not done), and anything that did not match this plan.
