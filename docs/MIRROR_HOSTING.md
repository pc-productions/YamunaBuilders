# Keeping yamunabuilders.com live: the static mirror

`scripts/build_mirror.py` turns the archive in `archive/yamunabuilders.com/` into a plain static
website (`dist/`, about 170 MB, ~1,100 files) that looks and behaves like the live WordPress site
but needs no server, no database and no paid hosting. It is the fastest way to keep the site up
if the agency takes the original down.

```sh
pip install beautifulsoup4 lxml
python3 scripts/build_mirror.py            # -> dist/
python3 -m http.server -d dist 8080        # preview at http://localhost:8080
```

Build settings (environment variables, all optional):

| Variable | Effect |
|---|---|
| `MIRROR_SITE_URL` | Absolute site URL for canonical tags and `sitemap.xml`, e.g. `https://yamunabuilders.com` |
| `MIRROR_CONTACT_EMAIL` | Address the forms hand enquiries to (default `yamunahomes16@gmail.com`) |
| `WEB3FORMS_KEY` | If set, forms are relayed silently by e-mail through web3forms.com (free tier) instead of opening the visitor's mail app |
| `MIRROR_MAX_FILE_MB` | Per-file size cap for the host (default 25, Cloudflare Pages' limit) |

## What is different from the live site

- **Forms.** The site had two Contact Form 7 forms, both with an e-mail OTP step and Cloudflare
  Turnstile, which need WordPress:
  - *Contact form* (`/contact/`, form ID 9): name, subject of inquiry, e-mail, OTP, contact number, message.
  - *Download Brochure* (form ID 1886, in the brochure pop-up on the Sky City pages): name, contact number, e-mail, OTP.
  On the mirror the OTP and Turnstile pieces are hidden. Submitting the contact form opens the
  visitor's e-mail app with a pre-filled message to `yamunahomes16@gmail.com`; the brochure form
  goes straight to the brochure page. Phone, WhatsApp and e-mail links work unchanged.
- **Comments** on blog posts are removed (they posted to WordPress). Existing comments are not shown.
- **Search** returns the homepage.
- **Videos.** Two background loops were 180 MB and 139 MB; the mirror uses muted 720p re-encodes
  (16 MB and 10 MB) produced by `.github/workflows/transcode-videos.yml`.
- **One PDF** (`YamunaSkyCity_Brochure.pdf`, 28 MB) is not copied. No page links to it; the brochure
  pages use image spreads. It remains in the archive and the Google Drive backup.
- **PWA / service worker** and WordPress REST, feed, pingback and oEmbed links are removed.
- **Fonts.** Headings and body text use Adobe Fonts (Typekit kit `nmv4gyz`: *Ofelia Display* and
  *The Seasons*). Adobe only serves a kit on domains its owner has approved. The mirror keeps the
  kit link and, if the fonts do not load on the new domain, swaps in Poppins and Cormorant Garamond
  from Google Fonts automatically. To keep the exact typefaces, whoever owns the Adobe Fonts
  account adds the new domain under Web Projects → kit `nmv4gyz` → Domains.
- Google Tag Manager, GA4 and Microsoft Clarity tags are unchanged and keep reporting.

## Hosting for free: Cloudflare Pages (recommended)

Free, unlimited bandwidth, commercial use allowed, free SSL and custom domains.

1. Sign up at dash.cloudflare.com (free plan).
2. Workers & Pages → **Create** → **Pages** → **Connect to Git** → authorise GitHub → choose
   `pc-productions/yamunabuilders`.
3. Build settings:
   - Production branch: `main`
   - Framework preset: *None*
   - Build command: `pip install beautifulsoup4 lxml && python3 scripts/build_mirror.py`
   - Build output directory: `dist`
   - Environment variables: `PYTHON_VERSION` = `3.11`, `MIRROR_SITE_URL` = the final URL
4. **Save and Deploy**. The first build takes 2–4 minutes and gives a `https://<project>.pages.dev` URL.
5. Custom domain: project → **Custom domains** → add `yamunabuilders.com` and `www.yamunabuilders.com`.
   Cloudflare shows the DNS records to create at the domain's registrar (a CNAME to the
   `pages.dev` host), or move the domain's nameservers to Cloudflare.

Every push to `main` redeploys automatically.

### Alternatives

- **Netlify** (free tier): same build command and output directory; set `PYTHON_VERSION=3.11`.
- **Vercel**: works as a static project, but the free Hobby plan forbids commercial sites; Pro is
  USD 20/month.
- **GitHub Pages**: technically works but its terms exclude business websites.

## What you need to control

- **The domain.** If `yamunabuilders.com` is registered under the agency's account, it cannot be
  pointed at the mirror without them. Find out where it is registered (a WHOIS lookup shows the
  registrar and expiry) and either get the registrar login or transfer the domain. Otherwise the
  mirror goes live on a new domain (about USD 10/year) or on the free `pages.dev` address.
- **E-mail.** If the domain moves, keep its MX records so `@yamunabuilders.com` mailboxes, if any,
  keep working.
