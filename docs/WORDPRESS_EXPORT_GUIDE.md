# yamunabuilders.com — what to export from WordPress for an exact rebuild

The live site is: WordPress 7.1 · **Salient** theme 18.1.1 (ThemeForest) · **WPBakery Page Builder**
(the Salient bundle) · Salient Core · Nectar Slider · Contact Form 7 + "Email Verification for
Contact Form 7" (OTP) + "Redirection for Contact Form 7" · Click to Chat (WhatsApp) · Popup Maker ·
Ultimate Image Gallery · SuperPWA · Rank Math SEO · Akismet · Mousewheel Smooth Scroll · webp-uploads ·
Adobe Fonts (Typekit kit `nmv4gyz`) · Google Tag Manager `GTM-NXVV44J6` / GA4 `G-YWB3RH6HGV` ·
hosted on **Hostinger** (LiteSpeed). The steps below assume **wp-admin access only** (no hosting panel).

The public scrape in `archive/yamunabuilders.com/` already has every page's HTML, copy and media.
What it cannot contain is the *editable* source: page-builder shortcodes, theme options, form
settings, menus/widgets and plugin configuration. Those live in the WordPress database and the
theme/plugin files. The exports below capture all of it.

> **This repository is public.** Never commit the database export, the full site backup, or any
> file containing keys/passwords here. Upload those to a private Google Drive folder instead
> (`yamunabuilders-export`); Claude can read that folder through the Google Drive connector.

## Tier 1 — the exact clone (do these first, they are the insurance copy)

You need an **Administrator** account in wp-admin (the left menu shows *Plugins* and *Settings*).
No hosting-panel (hPanel) access is required for any of this.

### Route A (recommended): UpdraftPlus straight into Google Drive

1. wp-admin → Plugins → Add New → search **UpdraftPlus** → Install → Activate.
2. Settings → UpdraftPlus Backups → **Settings** tab → *Choose your remote storage*: **Google Drive**
   → Save Changes → follow the "authenticate with Google" link (sign in to the Google account
   whose Drive is connected to Claude) → Complete setup.
3. Still in Settings: tick all of *Plugins, Themes, Uploads, Any other directories found inside
   wp-content*. Leave "split archives every" at 400 MB. Save.
4. **Backup / Restore** tab → **Backup Now** → tick *Include your database* and *Include your files*
   and *Send this backup to remote storage* → Backup Now. Wait until the log says finished.
5. In Google Drive a folder **`UpdraftPlus`** now holds: `backup_…-db.gz` (the database),
   `…-themes.zip`, `…-plugins.zip`, `…-uploads.zip` (possibly `uploads2.zip`…), `…-others.zip`.
   Move or copy them into the `yamunabuilders-export` folder.
6. Optional but helpful for Claude: open the `-db.gz` on your computer (7-Zip / macOS double-click)
   and upload the plain `.sql` file as well.

### Route B (alternative): Duplicator — one standard zip you download

1. Plugins → Add New → **Duplicator** → Install → Activate.
2. Duplicator → Backups → **Create New** → Next → (it scans; warnings about size are fine) →
   **Create Backup**. Download both files: `…_archive.zip` and `installer.php`.
   The zip is a normal zip: it contains `wp-content/…` and `dup-installer/…/database.sql`.
3. Upload both to the `yamunabuilders-export` folder in Drive.
   If the build fails on a timeout, re-run with *Archive → Filters* excluding `uploads` and use
   the scraped uploads already in this repo, then create a second package with only uploads.

### Either route, also:

| # | What | Where | Output |
|---|------|-------|--------|
| 3 | **Site Health report** (WP/PHP versions, theme & plugins with versions, server) | Tools → **Site Health** → *Info* → **Copy site info to clipboard** → paste into a text file | `site-health.txt` |
| 3b | `wp-config.php` is inside the backup ("others"/root); it holds DB name and salts only, no need to open it |  |  |

If *Plugins → Add New* is missing, plugin installation has been locked by the hosting owner
(`DISALLOW_FILE_MODS`). Then Tier 1 is impossible from wp-admin; skip to Tier 2, which still works,
and ask whoever holds the Hostinger account for a one-off backup download.

## Tier 2 — editable source, as plain text (fast to hand over, safe to keep in Drive)

| # | What | Where | Output |
|---|------|-------|--------|
| 4 | **Content export (WXR)** — pages, posts, media metadata, menus, galleries, popups, CF7 forms as posts | wp-admin → Tools → **Export** → *All content* → Download Export File | `yamunabuilders.WordPress.xml` |
| 5 | **Salient theme options** (colours, typography, header/footer layout, logos, page-transition & smooth-scroll settings) | wp-admin → **Salient** (left menu) → Theme Options → **Import / Export** → *Export* → Copy data / Download | `salient-options.json` |
| 6 | **Custom CSS / JS** | (a) Salient → Theme Options → General Settings → *CSS/Script related* → Custom CSS + Custom JS; (b) WPBakery → General Settings → *Custom CSS*; (c) Appearance → Customize → *Additional CSS* | `custom-css-js.txt` (paste all three, labelled) |
| 7 | **Rank Math settings** (titles, schema, redirections, sitemap config) | wp-admin → Rank Math → **Status & Tools** → *Import & Export* → Export settings (tick everything) | `rank-math-settings.json` |
| 8 | **Contact Form 7** — every form's *Form*, *Mail*, *Messages*, *Additional settings* tabs; the *Redirect* tab (thank-you URL); Email Verification (OTP) settings; the Turnstile/Integration keys | wp-admin → Contact → **Contact Forms** → open each (there are at least the homepage/contact "wpcf7" forms); Contact → Integration | one text file per form + screenshots |
| 9 | **Plugin & theme list with versions** (cross-check of #3) | wp-admin → Plugins → screenshot the whole list (active and inactive); Appearance → Themes → screenshot | screenshots |
| 10 | **Menus & widgets** (menu structure is in #4; footer widget content is in #2) | Appearance → Menus (screenshot each menu) · Appearance → Widgets (screenshot footer columns) | screenshots |
| 11 | **Popup Maker**, **Click to Chat**, **SuperPWA**, **Ultimate Image Gallery** settings | each plugin's Settings page → screenshot; all also live in #2 | screenshots |

## Tier 3 — things outside WordPress that the site depends on

| # | What | Why | Where |
|---|------|-----|-------|
| 12 | **Adobe Fonts (Typekit) kit `nmv4gyz`** — which font families/weights it serves, and who owns the Adobe account | The headings/body typography come from this kit. The kit only works on domains its owner allows. | fonts.adobe.com → Web Projects → kit `nmv4gyz` → note the families; or Salient → Theme Options → Typography (family names are shown there) |
| 13 | **Salient purchase code / Envato account** | Needed for future theme updates and support; the theme zip itself is in #1 | Salient → Theme Registration |
| 14 | **Google Tag Manager `GTM-NXVV44J6` and GA4 `G-YWB3RH6HGV`** access | To keep analytics/conversion tags identical | tagmanager.google.com (container export: Admin → Export Container) |
| 15 | **DNS zone + email (MX) records** | Moving hosts must not break email | Whoever holds the Hostinger/domain account: hPanel → Domains → DNS. Without that access, run `nslookup -type=any yamunabuilders.com` or use dnschecker.org and save the A/CNAME/MX/TXT records; also note the domain expiry date from a WHOIS lookup. |
| 16 | **Cloudflare Turnstile** site key + secret, **Akismet** key, any SMTP plugin credentials | Forms and spam protection | in #2 and the plugin screens; keep private |
| 17 | **YouTube video `cAXe3qlK0hs`** (Sky City walkthrough) and the Instagram post | Embedded from outside the site | keep access to those accounts; download the master video if you have it |

## Optional but very helpful for a pixel-accurate code rebuild

- Full-page screenshots of the homepage, Yamuna Sky City, Kamaldeep Twin Tower, Projects, About,
  Contact, Insights and one blog post — desktop (1440 px wide) and mobile (390 px). Chrome:
  DevTools → `Ctrl/Cmd+Shift+P` → *Capture full size screenshot*.
- A short screen recording of the homepage scrolling (shows the intro animation, parallax, header
  behaviour and the popup timing that no export captures).

## Handing it over

1. Create a Google Drive folder named **`yamunabuilders-export`** and upload everything above
   (keep the file names from the tables).
2. Tell Claude the folder is ready. Text files (SQL, XML, JSON, TXT, CSV) are read directly through
   the Drive connector; the large zips stay in Drive as the insurance copy.
3. Nothing from Tier 1 or item 16 goes into this Git repository.
