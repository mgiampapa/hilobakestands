# HiloBakeStands.com — Project Status Report

> Written by Claude, 2026-06-10; last updated 2026-06-14 (end of session).
> Purpose: context for resuming work in a future chat.
>
> SESSION CHECKPOINT 2026-06-14: v1.1 public-submissions build continuing.
> SLICE 3 DONE (commit 1748b43): completing a claim now also verifies the
> stand. stand_claim (stands/views.py) calls
> stand.mark_verified(via=Stand.VerifiedVia.CLAIM, save=False) folded into
> the existing single update_fields save, so owner assignment + verification
> land atomically (no second write). The mark_verified helper already
> existed from the admin "Mark verified" action — Slice 3 was just the
> wire-up. Added test_claim_verifies_stand (forces unverified, POSTs claim,
> asserts verification=verified + verified_via=claim). Full suite 153 tests,
> all green. Prior v1.1 slices already in git: Slice 1 (verified-only
> list/map + community toggle + unverified badge, f059c35), Slice 2a/2b/2c
> (public submit form + notify + CTA + URL safety + denylist/honeypot/rate
> limit/Turnstile + map pin + 25m dup warning). Remaining v1.1 checklist
> items: admin review-queue polish, badge/toggle QA, and the conditional/
> deferred bits (report-integrity hardening + auto-hide + semantic LLM
> moderator — all built only if abuse appears). Matthew testing the claim->
> verify flow live after deploy → VERIFIED working.
> ALSO 2026-06-14 (post-Slice-3): (a) shaka 🤙 emoji on the "Unverified"
> filter toggle pill. (b) Claim success flash reworded — owner tools are
> live now, so it points new owners to the "Edit details" button instead of
> "coming soon." (c) NEW "Claim your stand" info page (/claim-your-stand/,
> claim_your_stand view + template) + a "🤙 Is this your stand?" breadcrumb
> on every owner-less stand detail page (hidden once claimed). Realizes the
> v1.0 Open-Q3 owner-INITIATED claim path for owners who find their listing
> before getting a flyer: page explains the site, that it's free, the
> hide-but-community-can-resubmit caveat, and how to reach Matthew (email
> matt@hilobakestands.com, DM @hilobakestands from their business account as
> proof, or he leaves a claim slip at their cashbox on rounds). Copy
> APPROVED by Matthew. 3 tests added → 156 tests, all green. @hilobakestands
> IG account CREATED (verification channel only, not a content feed; bio
> routes general questions to email; Matthew signed in on phone for push
> notifications; hibiscus profile pic rendered to brand/instagram_profile_*.png
> 1080². DM management: no build for now — lean on Meta Business Suite
> notifications; Instagram Messaging API webhook → email is the homelab path
> if DM volume ever justifies it). (d) Found that single-account-owns-many-
> stands ALREADY WORKS (owner FK + /my/ lists all owned_stands) — logged as
> v1.2 backlog; see "v1.2 backlog" below. (e) FINAL QA SWEEP DONE → v1.1
> called DONE 2026-06-14. Full suite 157 (added end-to-end
> test_submitted_stand_claimable_via_minted_token_becomes_verified covering
> the Slice 2->3 handoff: submit mints token -> different user claims via it
> -> verified + visible), no pending migrations, manage.py check clean, data
> migration 0007 reversible. Only spec test item without automated coverage:
> "migration marks seeds verified" — skipped deliberately (already applied +
> verified live on prod; Matthew prefers fail-forward over retroactive
> coverage). Conditional items (report-integrity, auto-hide, semantic LLM
> moderator) remain deferred until abuse appears.
> FIELD/FEEDBACK TASKS CLOSED OUT 2026-06-18: Reddit /r/bigisland post done →
> gathered good feedback, reported issues already resolved. Map pins down to
> just 3 stands without pins/good location data (from 13); remaining ones
> resolve naturally via the claim flow, not a tracked field trip. The
> feedback-gathering phase that paused feature work is COMPLETE.
>
> SESSION CHECKPOINT 2026-06-13: (1) mobile list thumbnail VERIFIED across
> Firefox + iPhone/Safari + Chrome-on-Android → that workstream DONE.
> (2) Vision API key ROTATED via GCP key-detail "Rotate key" (keeps
> restrictions + grace period) + old key deleted; verified live by reading
> stands_photo.moderation_detail = "safesearch:" (NOT "homelab:") — recall
> moderation.py only logs on FAILURE, so read the verdict from the DB, not
> journalctl. (3) Public photo captions SHIPPED + deployed + verified
> (detail.html figure+figcaption.muted); were alt-text + owner-dashboard
> only before. Sanitization confirmed safe both layers (Django autoescape,
> no |safe; server-side strip()[:200]); 2 regression tests added → 115
> tests. (4) IG-sourced photo seeding marked WONTFIX (see item 9).
> (5) Weekly A1 attempt run (~117 Creates, all Out-of-capacity, session
> expired) — see item 1.
> SESSION CHECKPOINT 2026-06-13 (later): item 13 (privacy-first usage
> logging + Accept-Language signal) BUILT + deployed + LIVE — see item 13
> for full detail (server-side Django JSONL, opt-in, UTC-daily-salted
> visitor hash, usage_stats command with per-day uniques, 121 tests).
> Already capturing real hits (incl. a /wp-admin/install.php WP-scanner
> bot — expected noise). NEXT: Matthew is PAUSING feature work to go
> solicit real user feedback before building more; i18n now gated on BOTH
> the usage data AND that feedback. [UPDATE 2026-06-18: field tasks now CLOSED
> — Reddit done + good feedback + issues resolved; pins down to 3 of 13.]
> A1 retry continues weekly Saturday.

## Where things stand: LAUNCHED 🌺

https://hilobakestands.com is live and public with 25 real listings.

## What exists

**Site:** Django 5.2 + SQLite directory of Hilo bake stands / food trucks / farm
stands / pop-ups. Public list with filters (type, food, open-now), detail pages
with hours, payment badges, OSM embed + Google/Apple/Waze deep links, report-a-
problem form (honeypot-protected, lowers validation score, never auto-delists).
Admin has bulk Publish/Unpublish actions, inline hours/overrides/photos, and an
admin-only `internal_notes` field holding research provenance.

**Repo layout (this folder):**
- `SPEC.md` — finalized spec v1.0 (all decisions recorded)
- `config/`, `stands/` — Django project + app; `stands/management/commands/`
  has `seed`, `import_listings` (non-destructive), and `geocode`
- `listings.xlsx` — data collection sheet; blue text = scraped from Instagram
  2026-06-10. Idempotent import: `manage.py import_listings` (drafts by default)
- `deploy/` — bootstrap.sh (idempotent), systemd units, nightly backup script
  (03:15 HST, 14-day retention), cloudflared config template
- `DEPLOY.md` — full runbook; `README.md` — dev quickstart
- Tests: 23 passing (`manage.py test`; sandbox needs `DB_PATH=/tmp/...` because
  SQLite can't lock on the Cowork mount)

**Infrastructure (ALL FREE TIER — hard constraint, never suggest paid):**
- Oracle Cloud us-sanjose-1, tenancy `hawaii808vibes`, instance `hilobakestands`
  = VM.Standard.E2.1.Micro (1 OCPU / 1 GB, Always Free), Ubuntu 24.04,
  public IP 170.9.18.3, user `ubuntu`, Matthew's ed25519 key
- App at `/opt/hilobakestands/` (app/, venv/, data/db.sqlite3, .env), gunicorn
  via systemd service `hilobakestands` on 127.0.0.1:8000
- Cloudflare Tunnel `hilobakestands` fronts the site (no open inbound ports);
  DNS zone on Cloudflare (moved from Namecheap 2026-06-10)
- Matthew works by voice + clipboard paste; give him single-paste command blocks when convenient.
- A web SSH client (media.home.giampapa.com:2222/ssh) is available to be driven in chrome if needed. 

**Update flow:** edit locally → `rsync -az --exclude .venv --exclude db.sqlite3
~/Claude/Projects/HiloBakeStands.com/ ubuntu@170.9.18.3:~/HiloBakeStands.com/`
→ `sudo bash deploy/deploy.sh` on the box (DATA-SAFE: code/deps/migrate/
static/restart only; never seeds or imports). bootstrap.sh is provisioning
only. PROD DB IS THE SOURCE OF TRUTH for listings now — 12 geocoded
coordinate sets + future admin edits live only in prod + backups.

## Deploy hygiene (2026-06-11, Matthew's catch)

Both rsync hops now mirror with --delete (DEPLOY.md updated) — previously
the Mac→staging hop accumulated orphans forever. MEDIA_ROOT moved out of
the app dir to /opt/hilobakestands/media via .env (matches the systemd
ReadWritePaths grant, which would have blocked uploads at app/media, AND
keeps user uploads out of the --delete mirror; deploy.sh also excludes
'media' defensively). Nightly backup already copies that path. When
photos ship: confirm media lands there + extend the media.home off-box
pull to include media (currently DB snapshots only).

## Data notes

- 25 listings seeded from Matthew's knowledge + Instagram research (bios, post
  captions, hours posts). Only ~5 stands have true fixed hours; most announce
  openings day-of on IG — validates the open-now/override design.
- Multi-vendor pattern is real: 458 Bakestand, She Shed, Hale ʻAi Momona all
  host guest vendors. A "hosted at" relationship is a likely future model need
  (Mojo's Dough Co currently its own listing but operates from Hale ʻAi Momona).
- Flagged: "Le dessert stand" matched only to @le.dessert.haus (invite-only —
  verify before trusting); Tiny Barn address Ainaola vs Ainaloa unresolved;
  Violet W's + Sugar Wave have no IG found.
- "Sells out" close times in DB are ESTIMATES (open + 8h, capped 8pm), flagged
  in irregular_hours_note.

## Open work, roughly prioritized

1. **A1 migration (recurring):** A1.Flex ARM still out of capacity in
   us-sanjose-1 AD-1 (only AD). Attempts 2026-06-10: ~10:45pm PT (x2),
   ~midnight PT (x1), then an automated retry loop ~12:10–12:35am PT
   (~37 Create clicks at ~20–30s intervals) — ALL "Out of capacity".
   2026-06-11 ~12:25–12:45pm: second loop, ~14 more clicks — ALL OOC too
   (so daytime PT also no luck; ~55 total attempts logged). 
   Conclusion: late-night PT is not a magic hour; spamming doesn't help.
   Capacity for trial accounts likely frees in bursts; keep the weekly
   Saturday morning attempt. Retry loop recipe (works well): JS-click
   Create inside the wizard iframe, wait ~20s, check innerText for
   "Out of capacity" vs URL leaving /create (= success). Weekly Sat 7:00am HST calendar
   reminder exists ("Try moving HiloBakeStands to Oracle A1"). On success:
   rsync + bootstrap, move tunnel, reassign. 2026-06-10 attempt learnings:
   wizard fully stageable — hilobakestands-a1, Ubuntu 24.04, A1.Flex 2
   OCPU/12GB, existing VCN/subnet (vcn-20260610-1217 in root compartment;
   note Instances list shows the old VM under... it did NOT show in root
   list — investigate sometime), auto-public-IP toggle WORKS when selecting
   the existing subnet (old inline-VCN gotcha doesn't apply), SSH "Paste
   public key" rejects keys whose comment contains spaces (use a single-word
   comment), Matthew's ed25519 pubkey ends ...edxHkkZx. After error, wizard
   state survives — retry = click Create again. Console UI gotchas for
   automation: create form lives in an iframe (use contentDocument JS for
   scrolling/clicks; find/read_page don't see it).
   Old gotcha kept for reference: `cloudflared tunnel route dns
   --overwrite-dns` (zone has old records).
2. **Owner accounts: Google OAuth LIVE + VERIFIED end-to-end 2026-06-11**
   (Matthew signed in on prod; matt@giampapa.com Verified/Primary).
   SCOPE ['profile','email'] set explicitly — allauth's Google default
   omits email (QUERY_EMAIL=False) and the first sign-in created an
   email-less user (deleted). SOCIALACCOUNT_EMAIL_AUTHENTICATION +
   _AUTO_CONNECT = True so a future Apple sign-in with the same verified
   email joins the same account (Apple "Hide My Email" relay = separate
   account, merge by hand; fine at this scale).
   Header sign-in/out DONE + deployed + verified live 2026-06-11:
   base.html header is now flex; anonymous = "Sign in" button POSTing
   straight to {% provider_login_url 'google' %} (POST skips allauth's
   unstyled interstitial), signed-in = "Aloha, {first_name}" + Sign out
   POST form. 3 new tests (26/26). Profile page still wanted eventually
   (allauth default account pages remain unstyled bare-HTML — skin when
   building the owner dashboard). Allauth flash "signed in as matthew"
   (lowercase username) — RESOLVED (fixed + deployed + verified 2026-06-13 via
   ACCOUNT_USER_DISPLAY → first_name; admin username leaks also fixed via a
   global User.__str__ patch in stands/apps.py).
   Setup details: GCP
   project `hilobakestands` (org giampapa.com; the old "My First Project" =
   mystical-banner-274601 was left untouched). Auth Platform configured: app
   name "HiloBakeStands", support email matt@giampapa.com, External,
   PUBLISHED TO PRODUCTION (any Google account can sign in; only basic
   scopes so no verification needed). Client `hilobakestands-web`: JS origin
   https://hilobakestands.com, redirect URI
   https://hilobakestands.com/accounts/google/login/callback/. Client ID
   853762969460-t8c6vf3mt62nb3i7acc4bmej0kvh44up.apps.googleusercontent.com;
   TWO secrets exist (first one's plaintext was lost — new console shows
   secrets only once; the second, ending ISVL, is the live one in
   /opt/hilobakestands/.env — secret handled via clipboard, never in
   chat/repo). Gotcha: typing right after clicking "Add URI" can land in
   the console's top search bar — click the new field directly first.
   Sign in with Apple DROPPED 2026-06-11: requires $99/yr Apple Developer
   Program — Matthew ruled it excessive at this scale. Settings mapping was
   fixed anyway and kept (client_id=Services ID, secret=Key ID,
   key=APPLE_TEAM_ID, certificate_key from APPLE_PRIVATE_KEY_B64 since
   systemd EnvironmentFile can't hold multi-line PEM) — dormant until env
   vars exist; in repo, rides along with next deploy. Decision: Google-only
   for the seeding round. If bakers get stuck, add FACEBOOK login (free;
   email+public_profile are default-access, no app review; needs privacy
   policy URL + data-deletion page; audience is FB/IG-heavy so good fit).
   Instagram login for web no longer exists (Basic Display API dead).
   CLAIM FLOW LIVE + VERIFIED end-to-end on prod 2026-06-11 (claimed
   adoboliciouss as Matthew, token 404'd after burn, ownership then
   reverted so the real baker can claim). Design: per-stand random token
   (secrets.token_urlsafe(12), NOT slug-derived) in Stand.claim_token
   (null/unique/editable=False) + claimed_at; /claim/<token>/ →
   anonymous gets Google sign-in button with next= back to the claim URL,
   signed-in gets confirm button; POST sets owner, burns token (NULL),
   redirects to detail. Migration 0004. stands/templates/stands/claim.html.
   Admin: "Claim link" readonly field = click-to-select plain URL (Matthew
   wants straight URLs for SMS/email delivery, not just QR) + per-stand
   "Generate claim link"/"Regenerate" button (custom admin URL
   <pk>/generate-claim-token/) + bulk "Generate claim tokens" action
   (skips owned). SITE_BASE_URL setting builds absolute URLs. 33/33 tests.
   In-person handout IS the verification; deliberately not bulletproof
   (restore-from-backup is the fallback).
   Friendly errors (2026-06-11, verified live): invalid/used claim links
   render stands/claim_invalid.html in site chrome with 404 status
   ("used or can't be found", help email, browse button); plus site-wide
   branded templates/404.html (works in prod where DEBUG=False). 35/35
   tests. Adoboliciouss ownership reverted post-test (owner=None; its
   test token already burned — real baker gets a fresh one).
   STILL TO DO: QR flyer PDFs, ONE PDF PAGE PER STAND (flyer-style,
   leaveable) — generate from the same claim URLs, batch + single
   (single-stand QR/URL matters: Matthew delivers some by SMS/email).
   After seeding round: "claim this stand" button on unclaimed listings →
   contact form (reuse Turnstile helper) → Matthew follows up, possibly by
   generating a QR for them.
   Owner dashboard v1 scope (Matthew's picks): open/closed-today toggle,
   edit hours, edit basic info (description, phone, IG, payment), drag own
   map pin (coords_source=owner_pin already wins), photo upload + ONE
   special thumbnail image for the list view (~100x100, plus a smaller
   mobile variant — sizes need experimenting).
   DASHBOARD SLICE 1 LIVE + VERIFIED on prod 2026-06-12: /my/ (my_stands)
   + /my/<slug>/today/ (set_today). Anonymous → styled Google sign-in page
   (POST direct to provider, no allauth interstitial); owner sees cards w/
   live badge + today buttons: We're open today / Closed today / Sold out!
   (closed + note) / Back to regular schedule (deletes override, only shown
   when one exists). update_or_create on (stand, today) = idempotent; 404
   on non-owned slug; midnight auto-reset is inherent (override is per-date).
   Header "My stand" link only when user.owned_stands.exists. 53/53 tests.
   Verified live via test stand "Matt's Test Mochi Emporium" (Matthew's,
   marked unattended → badge says "Stocked now"): open → appears in
   /?open=now; Sold out → drops out + note shows; clear → schedule. Test
   stand still published — Matthew may want to unpublish/delete it.
   NEXT SLICES: edit basic info → edit hours → drag pin → photos+thumbnail.
   SLICE 2 LIVE + VERIFIED on prod 2026-06-12 (two deploys same day):
   /my/<slug>/edit/ (edit_stand) + stands/forms.py StandBasicInfoForm.
   Owner-editable: location_type, description, phone, instagram,
   payment_methods (checkboxes), STATUS (Matthew's call: "it's theirs") —
   framed as Visibility radios "Listed on the site" / "Hidden — taking a
   break or closed". Hiding a listed stand → server-side interstitial
   (.warnbox, needs_confirm + confirm_hide POST flag) spelling out it
   vanishes from list/map/open-now; re-listing needs no confirm; 'delisted'
   never an owner choice and admin-delisted stands get NO status field
   (can't self-relist). Name/slug stay locked: footer note links to the
   stand's feedback form (mailto fallback when hidden, since report view
   404s on unpublished). Hidden stands: yellow badge on dashboard, name
   not linked (detail 404s). "Sold out!" renamed "Pau!" (note: "Pau — sold
   out", shows publicly as "Today: Closed — Pau — sold out"). 65/65 tests.
   Verified live on Matt's Test Mochi Emporium: edit form, hide
   interstitial, vanish from public list + detail 404, re-list, no
   interstitial on relist. Test stand kept ON PURPOSE as Matthew's test
   bed (clearly named; it's "down the street" so it tops his near-me sort).
   Gotcha: Django 5 renders CheckboxSelectMultiple/RadioSelect as nested
   divs, not ul/li — CSS must target .field div label.
   SLICE 2b LIVE + VERIFIED 2026-06-12: edit form gained facebook, tiktok,
   website, email + INPUT SANITIZATION (stands/forms.py): _clean_handle()
   normalizes @name / bare / full pasted profile URLs (instagram.com,
   instagr.am, facebook.com, fb.com, m.facebook.com, tiktok.com) down to
   a whitelisted handle ([A-Za-z0-9._] IG/TikTok, +.- for FB) because
   detail.html interpolates them into hrefs; hostile values (javascript:,
   "><script>) → form error. Phone whitelisted [0-9+-(). ]{7,30} (tel:
   link). Description: control chars stripped, 2000 cap; Django's
   ProhibitNullCharactersValidator already rejects \x00 BEFORE clean_*
   (test documents this). website=URLField/email=EmailField built-ins.
   Output side already safe: autoescape everywhere, no |safe in templates.
   73/73 tests. Verified live: pasted messy IG/FB/TikTok URLs on test
   stand → stored clean, public links correct. NOTE: test stand now has
   fake socials (matts.mochi / Matts-Mochi / mochitok / example.com) —
   harmless, it's the test bed.
   SLICE 3 (EDIT HOURS) LIVE + VERIFIED 2026-06-12: /my/<slug>/hours/
   (edit_hours, no form class — hand-rolled 7-day grid, <input type=time>,
   "HH:MM" via time.fromisoformat). Blank day = closed; both-or-neither +
   close>open validation per day; errors re-render with ALL submitted
   values preserved; valid save = transaction.atomic wipe + bulk_create
   (one range/day) + irregular_hours_note (owner-editable here, [:300]) +
   updated_by. Multi-range days (admin-set split hours): grid shows first
   range + warnbox that saving replaces extras. Overnight hours
   (close<open) rejected — is_open_now can't represent them anyway.
   🕐 Edit hours button on dashboard cards. 84/84 tests. Verified live on
   test stand: error path (close-before-open, values preserved), save,
   public detail shows new hours, open-now badge driven by new schedule.
   Test stand now has Mon 9-11a + Fri 6a-11p + Sat 7a-1p + note.
   SLICE 4 (OWNER PIN) LIVE + VERIFIED 2026-06-12: /my/<slug>/pin/
   (edit_pin) — full-width Leaflet map (eager load like map.html, NOT the
   lazy split-view pattern), drag pin or tap map; Save disabled until pin
   moves; "📍 Use my current location" = getCurrentPosition w/
   enableHighAccuracy (the owner-crowdsourced pin flow for the 13
   unpinned stands — bakers tap it standing at their stand). POST
   validates floats + generous Big Island bbox (18.7–20.5, -156.4–-154.5,
   views.BIG_ISLAND_BOUNDS) → friendly "doesn't look like the Big
   Island" error; saves coords_source=owner_pin + updated_by.
   Regression test mirrors geocode command's exclude() queryset (command
   has no should_geocode method — it's a queryset filter in handle()).
   📌 Set/Move map pin button on dashboard. 92/92 tests. Verified live
   via Chrome remote: REAL mouse click on map moves pin + fills inputs +
   enables save; REAL left_click_drag of marker works too; saved coords
   round-trip. NOTE: Matthew's Google user is NOT Django staff — admin
   pages can't be checked through his browser session (admin checks need
   his separate superuser login). Test stand pin ended at 19.703678,
   -155.125269 (Haleloke St area, owner_pin source).
   NEXT SLICE: photos + ~100x100 list thumbnail (last dashboard slice;
   remember MEDIA_ROOT=/opt/hilobakestands/media, extend media.home
   off-box pull to include media when photos ship).
   MOBILE FEEDBACK ROUND (Matthew's testing) LIVE 2026-06-12, 96/96:
   (1) NEAR-ME AUTO-ENABLE FIX — mobile Firefox doesn't persist
   geolocation grants in a way permissions.query reports ('prompt' even
   with a remembered silent grant). New rule in _filters.html: pref
   'hbs-geosort'==='on' → locate() on EVERY load regardless of
   permission state (browser may re-prompt; Matthew's Firefox grants
   silently); unset pref → silent enable only when query says 'granted';
   'off' → never. Matthew's rationale: proximity is the site's primary
   use case, default to it whenever possible. (2) ✏️ Edit details button
   beside the stand name on detail pages (owner only, .titlerow flex) →
   /my/. (3) Dashboard: .manage-actions (edit info/hours/pin) split
   below a dashed divider from .today-actions (daily scheduling
   buttons); @media (pointer: coarse) bumps button padding for touch;
   .btn:disabled dimmed. Matthew confirmed all pin-placement methods
   work on mobile Firefox (his daily driver). Matthew CONFIRMED on his
   phone: the pref-based change fixed near-me auto-enable.
   DASHBOARD TODAY-BUTTON HIGHLIGHT FIX: DONE + VERIFIED on prod
   2026-06-12 (later session). Bug: the btn-primary highlight was
   HARDCODED on "We're open today" — clicking Closed/Pau changed the
   status (badge + override text updated) but the highlight never moved.
   Fix in my_stands.html: highlight is now conditional on today's
   override — open active when override.is_open; Closed when override &&
   !is_open && !note; Pau when override && !is_open && note (the Pau
   button is the only one that posts a note, so note-truthiness cleanly
   separates Pau from plain Closed without string-matching). Also:
   removed the redundant muted status <p> above the buttons (the green
   Django messages flash already says it — was showing twice), and the
   former conditional "Back to regular schedule" button is now a
   PERMANENT "Regular schedule" button that highlights when there's no
   override (so exactly one button is always selected, including the
   no-override state). 113/113 tests (new regression
   test_today_button_highlight_follows_override walks open→closed→pau→
   clear and asserts the active label each step). Deployed via standard
   deploy.sh; NOTE prod caches templates so the restart in deploy.sh is
   what makes template-only changes take effect.
3. **Email: FULLY DONE 2026-06-11.** hilobakestands.com is a USER ALIAS
   domain on the Workspace account (matt@hilobakestands.com =
   matt@giampapa.com); MX/SPF/DKIM/DMARC live at Cloudflare and verified; app
   password in /opt/hilobakestands/.env; test email delivered.
   Report-notification email (mail_admins, fail_silently) and admin low-score
   surfacing (badge, needs-review filter, open-reports column, lowest-first
   sort) DEPLOYED; 10/10 tests pass. Gmail "Send mail as" for
   matt@hilobakestands.com confirmed active (the 2026-06-10 attempt actually
   succeeded despite Google's 404 outage), so From: now stays correct.
   Nothing remaining.
4. **SSL hardening: DONE 2026-06-11.** At Cloudflare (SSL/TLS → Edge
   Certificates): Always Use HTTPS ON (edge 301s http→https), HSTS ON
   (max-age 6 months, includeSubdomains OFF deliberately, preload OFF,
   No-Sniff header ON), Minimum TLS Version raised 1.0→1.2. No Django
   changes needed (edge handles redirect; cookies already Secure).
   Note: Cloudflare dashboard sometimes hangs on its loading spinner —
   retry later or re-navigate from dash root; it loaded fine by day.
5. **Spam protection: DONE 2026-06-11.** Cloudflare Turnstile (managed mode)
   on the report form, honeypot kept as second layer. Widget
   "hilobakestands-report-form", sitekey 0x4AAAAAADi8eNvy8TVZxoJo (public;
   default unset in dev so tests/local skip verification). Secret in
   /opt/hilobakestands/.env as TURNSTILE_SECRET_KEY (handled via clipboard,
   never in chat/repo). Server-side siteverify via stdlib urllib in
   stands/views.py:turnstile_ok() — fails OPEN on network errors, CLOSED on
   invalid token. 14/14 tests pass. Helper is reusable for future owner-claim
   forms. Gotcha: `~` inside `sudo bash -c` is /root — use absolute paths in
   paste blocks.
6. **Deploy/data lifecycle refactor: DONE 2026-06-11 (code).** New
   `deploy/deploy.sh` = rsync/pip/migrate/collectstatic/restart only, refuses
   to run on an unprovisioned box. bootstrap.sh now seeds/imports ONLY on
   first boot (no db.sqlite3) or with `--with-data`. import_listings is
   non-destructive by default: existing stands (matched by slug) are left
   completely untouched — admin edits, status, hours, M2Ms preserved;
   `--overwrite` flag restores old sheet-wins behavior. 3 new regression
   tests; 17/17 pass. Routine update flow is now: rsync → `sudo bash
   deploy/deploy.sh`. DEPLOYED + verified on prod 2026-06-11 (25/25
   listings unchanged across deploy). BONUS FIND: nightly backups had
   NEVER run — /var/backups/hilobakestands was root-owned but the service
   runs as hilobake (silent permission failure since launch). Fixed via
   chown on the box + in bootstrap.sh; manual run produced a snapshot that
   restores cleanly (integrity_check ok, 25 rows). First real timer run
   should appear next 03:15; worth a glance that it did.
7. **Off-box backups: DONE 2026-06-11.** media.home pulls nightly via cron
   (4:30am HST, after the 3:15 on-box backup): script
   /srv/hilobakestand_backup/pull.sh (logs to last_run.log there), data to
   /media/the_vault/Backup/hilobakestand/ — both paths already covered by
   Matthew's Duplicati jobs (local + B2). Pull uses key ~/.ssh/id_ed25519
   (comment "mediapull") as mgiampapa@media → ubuntu@oracle.hilobakestands.com
   (DNS-only hostname). Script exits 1 if newest snapshot >~2 days old
   (staleness alarm). Old snapshots accumulate locally on purpose (deeper
   history; ~19KB each). Note: Duplicati can NOT pull remote sources over
   SSH (destination-only; open feature request since 2017) — hence the cron.
8. **Map view: LIVE 2026-06-11** (incl. two same-day follow-ups, both
   deployed: OSM tiles 403'd because Django's default Referrer-Policy:
   same-origin strips Referer cross-origin and OSM blocks referrer-less
   tile requests — fixed with Leaflet's referrerPolicy:'origin' option in
   map.html AND admin_map_pin.js; and list-follows-map: cards under the
   map re-filter to the visible bounds on moveend/zoomend, client-side
   only, stacking on top of the type/food/open-now filters).** /map page with full
   filter parity (shared _filtered_stands helper + _filters.html include,
   list↔map toggle preserves querystring). Leaflet 1.9.4 (cdnjs) + OSM
   tiles. All markers uniform (Matthew's choice; precision still stored).
   Data model: coords_source (owner_pin > admin > geocoded — geocoder NEVER
   overwrites human pins), geocode_precision, geocoded_at; migration 000X
   added. `manage.py geocode [--all] [--dry-run]`: Nominatim, 1.1s/req,
   Big Island viewbox (bounded). ROAD-LEVEL MATCHES REJECTED (Matthew's
   call mid-dry-run: street centroids on long rural roads are worse than
   no pin; he hand-places those with the admin widget). 23/23 tests. SURPRISE FINDING: all 25 listings had EMPTY lat/lng
   (sheet columns never filled) — detail-page OSM embeds were silently
   hidden all along. Admin got a drag-a-pin Leaflet widget
   (stands/static/stands/admin_map_pin.js) that fills lat/lng and sets
   coords_source=admin. import_listings marks sheet coords as admin-source.
   Workflow after deploy: geocode --dry-run on box → review →
   real run → Matthew drags pins for the fuzzy ones (street-only addresses
   like Hoaloha St, Popolo St, "Kaumauna"). Owner pin-setting UI comes with
   owner dashboard (model ready). Note: sandbox can't reach Nominatim
   (403) — geocode runs happen on the box.
8b. **QR claim flyers: DONE + verified by Matthew on prod 2026-06-11.**
   stands/flyers.py (reportlab + qrcode, both in requirements.txt): one
   US-letter page per stand — green header band with hibiscus + wordmark,
   stand name (auto-shrinks for long names), pitch text, 3.2" QR of the
   claim URL, plain URL underneath, sand footer. DejaVu fonts (on box +
   sandbox) for ʻokina; falls back to Helvetica. Hibiscus = Twemoji 1f33a
   (CC-BY 4.0): repo assets stands/static/stands/hibiscus.png (512px, for
   PDFs) + hibiscus.svg (2KB, used by site header + favicon — also
   replaced the emoji in base.html per Matthew). Admin: per-stand
   "Download flyer (PDF)" (auto-generates token if missing, NEVER rotates
   an existing one) + Regenerate (DOES rotate — kills handed-out links) +
   bulk flyer action and bulk "Generate claim links" action whose success
   message lists all URLs click-to-copy (Matthew's feedback: consistent
   "link" naming + give bulk URLs together). GOTCHA admin buttons must use
   reverse('admin:...') not relative hrefs (break on change pages).

8c. **Desktop split view: LIVE 2026-06-11.** List page (/) at ≥1100px =
   grid: cards column + sticky side map (#side-map), list-follows-map
   hides out-of-bounds cards, note shows "X/Y in view · N not on the map
   yet (no pin)". Mobile unchanged AND never downloads Leaflet
   (matchMedia-gated lazy inject of CSS+JS — wait for BOTH before init,
   else markers mis-render; ResizeObserver → invalidateSize for resizes).
   /map stays as the mobile map; at desktop width it location.replace()s
   back to / preserving querystring (Matthew's resize-strand repro).
   .toggle-view link hidden at desktop. Markers context now also fed to
   stand_list via shared _marker_data() helper. 41/41 tests.
   QA notes from Matthew's testing, all fixed same night: relative admin
   URLs, first-load marker race, /map resize strand. "Empty map" with
   filters = usually the matched stands just have no pins yet (e.g.
   Basic Bitch Bakery 808).

8d. **Near-me / distance sort: LIVE + VERIFIED on prod 2026-06-12**
   (43/43 tests; verified in Matthew's browser: auto-enable on granted
   permission, distance badges + closest-first order, green you-dot,
   toggle off→alpha restore→on again, no console errors). 100% client-side, zero view/model changes.
   _filters.html owns the logic: "📍 Near me" button (hidden if no
   geolocation API) + shared window.hbsDistMi (haversine, miles) /
   hbsFmtMi / hbsGeoPos. Auto-enable WITHOUT prompting via
   navigator.permissions.query({name:'geolocation'}) — free, never
   popups; enables only if state==='granted'. Preference in
   localStorage 'hbs-geosort' ('on'/'off'): 'off' = never auto;
   no Permissions API (old Safari <16) = auto only if 'on' (Matthew's
   cookie idea, minus the server). Button click prompts via
   getCurrentPosition (maximumAge 5min). Pages listen for the 'geosort'
   CustomEvent (detail = {lat,lng} or null) + check window.hbsGeoPos at
   boot (event can fire before lazy map init). List page: cards
   re-appended closest-first (stable sort keeps no-pin cards
   alphabetical at the end), blue "X mi" .badge.distance after h2,
   green-dot circleMarker "Your location", setView(user, 13) — BUT only
   if nearest stand ≤20mi, else keep stands fit (list-follows-map would
   hide every card for faraway visitors). Off = restore alpha + refit.
   /map page: same dot/center rules, in-view list sorted + distance
   badges. CSS in base.html (#near-me.active green, .badge.distance).

8e. **QR-flyer field trip — CLOSED OUT 2026-06-18.** First round done: it
   surfaced one stand that NO LONGER EXISTS (delisted/removed). Other parts of
   town still uncovered, but Matthew is closing this as an active task because
   socials are known for everyone else → those are easy to verify at
   REGISTRATION/claim time (no on-site visit needed). So remaining pins/visits
   resolve naturally through the claim flow, not a tracked field-trip task.
   (Original plan: hand-place the 13 missing pins on-site via the admin
   drag-pin widget during the flyer delivery round.)
   UPDATE 2026-06-18: down to just 3 stands without pins/good location data
   (from 13). Fully closed as a field task — the last 3 resolve via the claim
   flow.

8f. **PHOTOS SLICE LIVE + Vision moderation VERIFIED on prod 2026-06-12.**
   Owner photo gallery (/my/<slug>/photos/, max 6 + 1 list thumbnail),
   pipeline strips EXIF/GPS + resizes to 1600px JPEG, moderation chain =
   Google Vision SafeSearch → homelab fallback → fail-safe pending+email.
   112/112 tests. VERIFIED END-TO-END: test upload auto-approved live
   ("adult/violence/racy" clean → instant publish); pre-key uploads
   correctly queued pending. All test photos deleted after.
   FULL LIVE EXERCISE 2026-06-12 (later session, Matthew): uploads,
   setting + swapping the list thumbnail, and the 6-file max all work;
   every image Vision-approved instantly. Photos slice considered
   battle-tested on prod.
   GOOGLE SETUP (Matthew's call: Google + cap + homelab, after learning
   free tier needs a card): billing account "HiloBakeStands"
   (0148BC-B422EE-94C8E2) funded by Matthew's VIRTUAL CARD with its own
   spend limit (the true hard cap); $20/mo budget alert (50/90/100%);
   Vision API enabled on project hilobakestands; umbrella "Requests per
   minute" quota cut 1,800→5 (Vision has NO per-day quota — per-minute
   is the only cap; 5/min never binds one-at-a-time uploads); API key
   "hilobakestands-vision" restricted to Vision API ONLY + IP 170.9.18.3
   ONLY, installed as VISION_API_KEY in /opt/hilobakestands/.env.
   NOTE: key text leaked into a chat transcript (terminal paste) —
   acceptably safe given IP+API+quota restrictions, but rotating it
   someday is cheap insurance (Credentials → hilobakestands-vision →
   regenerate, then the .env one-liner).
   GOTCHAS LEARNED: (1) Vision 403s until the PROJECT is linked to the
   billing account — creating the account + card is NOT enough; the
   linkedaccount page has the missing "Link a billing account" step.
   (2) Budget ≠ cap (console says so itself). (3) `read -p` breaks in
   zsh (media.home's shell) — use `printf ... && read`. (4) Matthew's
   web SSH lands him on VARIOUS boxes — always confirm prompt user@host
   before giving box-specific paste blocks ("Password:" prompt at sudo =
   probably media.home; oracle ubuntu is NOPASSWD).
   HOMELAB FALLBACK — STATE AT SESSION CHECKPOINT 2026-06-12 (~midnight):
   DONE: service INSTALLED + healthz {"ok":true} on media.home
   (/srv/hilobakestand_moderation, venv, Falconsai ViT model downloaded,
   systemd hilobake-moderation, bound 127.0.0.1:8788, token in .env
   chmod 600). Debian 13 gotcha hit+fixed: python3-venv wasn't installed.
   REVERSE TUNNEL + FALLBACK ENV: DONE + VERIFIED 2026-06-12 (new chat).
   hilobake-tunnel.service on media.home is active + enabled (ssh -N -R
   127.0.0.1:8788:127.0.0.1:8788 ubuntu@oracle, Restart=always +
   keepalives). Verified oracle->tunnel healthz {"ok":true}; oracle
   /opt/hilobakestands/.env has the 2 fallback lines
   (MODERATION_FALLBACK_URL=http://127.0.0.1:8788/check +
   MODERATION_FALLBACK_TOKEN); app restarted + active.
   GOTCHA / ROOT CAUSE of the original "Permission denied (publickey)":
   the web SSH had landed Matthew in as ROOT on media, so the original
   block's `User=$USER` baked `User=root` into the unit AND the ExecStart
   ssh ran as root — root has NO key on oracle (the authorized "mediapull"
   key lives at /home/mgiampapa/.ssh/id_ed25519). FIX that stuck: pin the
   unit to `User=mgiampapa` AND add explicit
   `-i /home/mgiampapa/.ssh/id_ed25519` to ExecStart. (mgiampapa->oracle
   auth confirmed working, so the nightly backup pull is healthy too.)
   Reconfirmed gotcha 8f-4: ALWAYS check whoami@hostname before pasting
   box-specific blocks; root-vs-mgiampapa changed everything here.
   FALLBACK PATH PROVEN END-TO-END 2026-06-12: instead of the riskier
   comment-key-and-restart approach, ran the app's OWN moderate_image()
   in a one-off process on oracle with VISION_API_KEY forced empty (no
   .env edit, no prod restart) — benign test image returned
   outcome='ok', detail='homelab: nsfw=0.007', confirming oracle ->
   tunnel -> media ViT -> clean verdict via the exact code an upload
   uses. Recipe (run from media as root): scp a tiny script to oracle
   that does django.setup() + moderate_image(Image.new(...)), run it via
   `sudo env PYTHONPATH=<appdir> DJANGO_SETTINGS_MODULE=config.settings
   VISION_API_KEY="" MODERATION_FALLBACK_URL=.. MODERATION_FALLBACK_TOKEN=..
   /opt/hilobakestands/venv/bin/python`. NOTE: oracle loads .env via
   systemd EnvironmentFile (settings.py reads os.environ, NO dotenv) — a
   plain `manage.py shell` does NOT see those vars; inject them.
   (a) MEDIA OFF-BOX BACKUP: DONE + test-run VERIFIED 2026-06-12.
   /srv/hilobakestand_backup/pull_media.sh (owned mgiampapa, 0755) =
   rsync -az --delete --rsync-path="sudo rsync" -e "ssh -i
   /home/mgiampapa/.ssh/id_ed25519 ..." ubuntu@oracle:
   /opt/hilobakestands/media/ -> /media/the_vault/Backup/hilobakestand/
   media/ ; logs to /srv/hilobakestand_backup/media_last_run.log. In
   mgiampapa's crontab at '40 4 * * *' (4:40am HST, right after the 4:30
   DB pull.sh; box TZ confirmed -10:00). Test run: script exit OK,
   "OK: 0 files, 0 total" (correct — no photos live yet; populates on
   first baker upload). Duplicati (local + B2) versions the dest. No
   staleness alarm on this one (0 files is legitimate until uploads
   exist), unlike the DB pull which exits 1 on a >2-day-old snapshot.
   MOBILE LIST THUMBNAIL 2026-06-12 (later session, shipped "good
   enough"): on narrow view (≤480px) the list thumbnail went 64px →
   115px (+80%, now bigger than the 100px desktop on purpose) and the
   image is wrapped in an <a class="listthumb-link"> to the stand page
   so it's tappable like the name. CSS moved the float onto the link
   wrapper (.card .listthumb-link { float:right; margin:0 0 .5rem .8rem }
   with inner img float:none) so text still wraps. list.html + base.html;
   113/113 (extended test_list_thumb_shows_on_list_page to assert the
   thumb links to get_absolute_url). TODO: cross-browser check the
   mobile thumbnail on iPhone/Safari AND Chrome-on-Android (only tested
   on Matthew's mobile Firefox so far); may need size/layout tweaks.
   STILL OPTIONAL: (b) rotate the Vision key (it hit a chat transcript).

9. **Photos:** approval-gated model exists; no photos seeded yet. Could pull
   from stand IGs with owner permission as part of claim outreach.
   → SUPERSEDED by 8f: owner upload flow is LIVE.
   → WONTFIX 2026-06-13 (Matthew): manual IG seeding not worth it — once
   claimed, owners (who are very active on IG) keep their own photos
   current as menus change, so a one-time scrape goes stale. The ONLY
   version worth building is an automated periodic pull of each stand's
   last 6 IG photos so owners do nothing — revisit ONLY if owner-upload
   adoption is weak. Public captions now also live (detail.html).
10. **Reddit /r/bigisland post — DONE + CLOSED OUT 2026-06-18.** Posted; strong
   result: lots of POSITIVE feedback, several STAND OWNERS CLAIMED their stands,
   AND it surfaced the desktop map-toggle bug (since fixed 2026-06-18). Served
   its purpose (discovery + inbound links + real claims) — closing as a task.
11. i18n: strings wrapped, Japanese translation deferred — GATED on real
   demand signal from item 13 before investing in translation.
13. **Basic usage stats + native-language signal — SHIPPED + LIVE on prod
   2026-06-13.** Decision: server-side Django logging (chose it over GA4 —
   no third-party JS/cookies/consent banner, fits the 1GB box; self-hosted
   dashboards ruled out: Plausible needs ~2GB, Umami ~500MB+DB; GoatCounter
   the only box-viable upgrade IF a live dashboard is ever wanted).
   IMPL: stands/middleware.py UsageLogMiddleware appends one JSONL line per
   non-static request (ts UTC, hashed visitor, method, path, status,
   Accept-Language, UA, referer) to settings.USAGE_LOG_PATH. Opt-in: unset
   = DISABLED (so tests/dev don't write); prod has
   USAGE_LOG_PATH=/opt/hilobakestands/data/usage.jsonl in .env (data dir is
   writable, already in systemd ReadWritePaths). PRIVACY: IP never stored
   raw — only a UTC-daily-salted sha256(SECRET_KEY|utc-date|ip)[:16], so
   unique-visitor-DAYS countable within a day but NOT linkable across days
   (salt rotates). Read it with `manage.py usage_stats --file <path>`
   (run via venv python; no DB needed so systemd env not required): prints
   requests, unique visitors, PER-DAY table (date/requests/unique
   visitors), primary-Accept-Language breakdown (the i18n signal), top
   paths, status codes. GOTCHA: hash salt MUST use UTC date to match the
   UTC ts (first cut used local date.today() — fixed same day). 121 tests.
   NOISE: log catches bot/scanner hits (e.g. /wp-admin/install.php WP-worm
   probe) — filter scanners in off-box analysis; they usually send no real
   Accept-Language so they bucket as (none)/en and don't pollute the JA
   signal much. i18n (item 11) now gated on this data AND on real user
   feedback (Matthew pausing feature work 2026-06-13 to solicit actual
   user feedback before building more).
12. Conditional milestones: simplified admin UI (if a helper joins),
   containerize (if moving hosts / multi-service).

## v1.2 backlog (capture only — not building yet)

- **BUG — FIXED + VERIFIED ON PROD 2026-06-18 (user feedback 2026-06-14):** the
  map-view toggle "didn't work" in the wider desktop side-by-side (list + map)
  layout. ROOT CAUSE was CSS specificity, not JS: list.html tried to hide the
  toggle in split view with `.toggle-view { display: none }` (specificity
  0,1,0), but base.html line 104 `a.btn { ...; display: inline-block }` (0,1,1)
  is more specific and always won — so the toggle stayed VISIBLE at desktop
  width. Clicking "Map view" navigated to /map/, which (≥1100px) immediately
  `location.replace()`s back to /, landing on the same split page → looked like
  the toggle did nothing. FIX: bumped the hide rule to `a.btn.toggle-view {
  display: none }` (0,2,0, beats a.btn). Also (Matthew's request) moved the
  view-toggle out from under the Filter button and into the on/off pill group
  below the `<hr class="filter-sep">`, next to Near me / Unverified — it's a
  pill-style .btn so it belongs there; row now reads List/Map view · Near me ·
  Unverified. Template-only change, no migration. Verified on prod: toggle gone
  in desktop split view, appears in the pill row at narrow widths, toggling
  works on mobile. GOTCHA hit during deploy: local .venv was stale (predated
  whitenoise/gunicorn being added to requirements.txt) → `manage.py test` threw
  127 ModuleNotFoundError: whitenoise errors at middleware-load (all the tests
  that issue an HTTP request); fix was `pip install -r requirements.txt` to
  re-sync the venv. 157 tests pass.

- **Better photo management — DONE + VERIFIED ON PROD 2026-06-18.** Owners can
  now (a) edit a photo's caption/alt AFTER upload and (b) reorder photos. NO
  migration needed — Photo already had `sort_order` (PositiveSmallIntegerField,
  Meta.ordering=['sort_order','id'], used by both public detail + dashboard).
  Reorder UX = UP/DOWN BUTTONS, not drag (Matthew's call: better for
  accessibility + his hand injury / voice-clipboard workflow; no JS). IMPL: new
  endpoints edit_photo_caption (POST .../photos/<pk>/caption/) and move_photo
  (POST .../photos/<pk>/move/ with direction=up|down). move_photo swaps with the
  neighbour then RENUMBERS all the stand's photos sequentially (self-heals
  legacy rows sharing sort_order=0). MODERATION (Matthew's requirement): all
  caption text — both new uploads AND edits — now routes through new
  forms.PhotoCaptionForm whose clean_caption strips, caps [:200], and calls the
  SHARED `_reject_if_blocked` (same denylist/threat layer as stand
  name/description/address; field has NO max_length so the bypassable-HTML-
  maxlength server-cap test still holds). Closed a prior gap: the upload path
  previously stored captions UNMODERATED. Designed so future TextModerator
  layers auto-apply to captions. photos.html: per-photo inline prefilled caption
  edit form + up/down buttons omitted at the ends via forloop.first/last. 169
  tests (9 new: caption save/clear/truncate/blocked-on-edit+upload/non-owner
  404; reorder up/down/no-op-at-ends/renumber-heals-zeros/non-owner 404).
  Verified functional on prod by Matthew.

- **Reviews / ratings** — already slated for v1.2 (SPEC-1.1 §9); flows through
  the §5a `TextModerator` pono/kind/constructive pipeline when built.
- **Multi-stand / shared management (Matthew, 2026-06-14).** Two halves:
  - *One account owns many stands* — ALREADY WORKS today. `Stand.owner` is a FK
    and `/my/` lists `request.user.owned_stands` (plural). For test flows, mint a
    claim token per stand and claim them all with one account — no feature
    needed. Only friction: one token burned per claim.
  - *Shared / delegated management* — the actual v1.2 work. For multi-location
    operators AND "people who operate in others' spaces as well as their own"
    (a vendor running a listing inside a host's space — see the "hosted at"
    pattern already flagged in Data notes: 458 Bakestand, She Shed, Hale ʻAi
    Momona host guest vendors). The single `owner` FK can't model multiple
    managers per stand → needs a managers M2M or a through-model with roles
    (owner vs manager). Likely shares per-user identity plumbing with reviews.
- **PWA / installable app (Matthew, 2026-06-14).** Make the site installable
  ("Add to Home Screen") via web manifest + service worker + icons (reuse the
  hibiscus). ~Hours, $0, no app stores/dev accounts, iOS + Android, self-
  contained. Cheapest "have an app" win. Beyond it (only if asked): Android
  Play via TWA/Bubblewrap ($25 one-time); iOS App Store is hard (thin webview
  hits Apple Guideline 4.2 "repackaged website" rejection → needs Capacitor +
  native bits + $99/yr, which also covers Apple Sign-In). GOTCHA: Google blocks
  OAuth in embedded webviews → breaks Google login in a naive wrapper; PWA/TWA
  avoid it, Capacitor must route sign-in through the system browser.
- **Threads social + social-platform icons — DONE + DEPLOYED 2026-06-18
  (Matthew, 2026-06-14).** (a) Threads field: `Stand.threads` CharField(100)
  after tiktok (migration 0009, additive AddField); `clean_threads` in
  SanitizedStandFieldsMixin reuses `_clean_handle` with domains
  threads.com/threads.net + IG pattern [A-Za-z0-9._]{1,30} (Threads = the IG
  username). Added to BOTH StandSubmitForm + StandBasicInfoForm fields (auto-
  renders via each template's `{% for field in form %}` loop), labels, help.
  Admin auto-includes it (StandAdmin has no restricted `fields` list).
  detail.html renders a Threads pill: https://www.threads.com/@<handle> (.com
  is canonical now — verified via search; .net redirects). (b) Brand-colored
  icons: inline Simple Icons SVGs (CC0/public-domain, no CDN/icon-font) on each
  social pill — IG #FF0069, FB #0866FF, TikTok/Threads #000000 — fetched from
  the `simple-icons` npm package (web_fetch won't return raw SVG asset bodies;
  npm install in sandbox + node to read .path/.hex is the way). New `.sicon`
  CSS in base.html (1em, vertical-align). Website/phone left text-only (not
  social brands). 173 tests (4 new: threads normalize + hostile-reject + detail
  render + no-pill-when-unset). IMPORTER: NO Threads column in listings.xlsx
  yet → not wired; if a `Threads` column is ever added, route it through
  clean_threads (same lesson as the FB importer fix). REUSE pattern confirmed:
  a new IG-style social = field + _clean_handle(domains,pattern) + form fields +
  detail pill + Simple-Icons glyph.
- **SEO / discoverability / link-trust cluster — DONE + DEPLOYED + spot-checked
  on prod 2026-06-18 (Matthew, 2026-06-14).** All parts shipped. (a) /robots.txt
  + /.well-known/security.txt = plain function views in views.py
  (robots_txt/security_txt) wired in config/urls.py; robots allows crawl,
  Disallows /admin//accounts//my//claim/, Sitemap: line built from
  settings.SITE_BASE_URL; security.txt Contact mailto:matt@, Expires computed
  now+365d (never goes stale), Preferred-Languages en. NOTE: Matthew
  deliberately did NOT add AI-bot opt-out (Google-Extended/GPTBot/ClaudeBot/etc)
  — wants AI discoverability (Google-Extended is AI-only, doesn't touch search).
  (b) /sitemap.xml via django.contrib.sitemaps (added to INSTALLED_APPS):
  stands/sitemaps.py StandSitemap + StaticViewSitemap (protocol https,
  lastmod=updated_at). SCOPE CHANGE from original plan — Matthew's call: INCLUDE
  UNVERIFIED stands (filter = status=published + auto_hidden=False only, NOT
  verification=verified), since existing controls + low volume + email-notif
  review make it safe and it aids discovery. GOTCHA solved: sitemap framework
  builds URLs from the django.contrib.sites Site.domain which was still the
  default 'example.com' → migration 0010 sets it from SITE_BASE_URL host
  (idempotent update_or_create; also benefits allauth). Google Search Console +
  Bing Webmaster sitemap SUBMISSION is still a MANUAL post-deploy step (not
  done yet — offer to drive via Chrome). (c) Link trust: OG + Twitter Card +
  rel=canonical + meta description in base.html, driven by per-page context vars
  (meta_description reused for <meta desc> AND og:description = DRY; Twitter
  falls back to og: tags so only twitter:card declared). canonical/og:url =
  clean {scheme}://{host}{path} (no query). stand_detail view passes
  meta_description (stand.description truncated 158, else generated line),
  og_title, og_type=place, og_image=first approved photo abs URL. Branded
  1200x630 og-image.png generated via PIL (sand bg, hibiscus, green title +
  coral .com, tagline) at stands/static/stands/og-image.png = default og:image.
  Facebook Sharing Debugger RE-SCRAPE DONE 2026-06-18 (new square graphic live). (d) Bing
  items folded in: meta description (done above) + exactly ONE <h1> per page —
  sr-only h1 on list.html + map.html (don't disturb layout; new .sr-only CSS in
  base.html), h2→h1 on submit.html AND submit_signin.html (the crawler-facing
  anon variant — easy to miss) + claim_your_stand.html; detail already had one.
  178 tests (5 new SeoTests: robots/security content, sitemap includes-unverified
  + excludes draft/hidden, detail meta+canonical, one-h1-per-page). REMAINING
  Bing items: Cloudflare email-obfuscation toggle — DONE 2026-06-18: turned OFF
  via Security → Settings → Email Address Obfuscation (the old Scrape Shield
  toggle; /scrape-shield path now 404s, it moved under Security → Settings, tag
  "Client side abuse"). mailto:matt@ links now render clean for crawlers (kills
  the /cdn-cgi/l/email-protection rewrite Bing flagged). Done via Claude-in-
  Chrome on Matthew's logged-in dash. SITEMAP SUBMITTED + ACCEPTED 2026-06-18: Google
  Search Console fetch SUCCESS (showed "Couldn't fetch" at submit then flipped
  to success on its own re-crawl — GSC's normal transient behavior, sitemap was
  serving 200 application/xml the whole time); Bing Webmaster accepted it, found
  27 URLs. FB SHARING DEBUGGER — CLOSED OUT 2026-06-18: re-scrape tested, new
  OG graphic (1200x1200 square) now applied/showing in FB's preview card —
  nothing left pending here. OG HEAD BUG
  FOUND + FIXED + VERIFIED ON FB 2026-06-18: the SEO deploy's base.html had a
  MULTI-LINE `{# ... #}` comment in <head> — Django's `{# #}` is SINGLE-LINE
  ONLY, so the multi-line one rendered as LITERAL TEXT. Stray text in <head>
  makes the HTML parser close </head> early → all following og: tags landed in
  <body>, where Facebook IGNORES them. Symptom: visible comment text atop every
  page + FB card had no image and fell back to <title> for og:title. Tricky to
  spot because a browser DOM query still finds the (reparented) tags. Stand
  pages LOOKED fine only because FB inferred the big body <img> photo; the
  homepage has no large body image so it came up blank. FIX: use
  `{% comment %}...{% endcomment %}` (multi-line safe). Also added explicit
  og:image:width/height/type/secure_url/alt on the default image. Verified via
  Claude-in-Chrome on Matthew's browser: FB re-scrape now parses og:image +
  full og:title, og:image warning gone (only the optional fb:app_id notice
  remains — harmless). NO Cloudflare purge needed (was our code, not cache).
  REGRESSION TEST added (SeoTests.test_head_clean_and_og_inside_head: comment
  text absent + og: tags before </head>). 180 tests. LESSON: never use
  multi-line `{# #}`; use `{% comment %}`.
- **URL-triggered status override / scan-to-open — DONE + DEPLOYED + verified
  live 2026-06-18 (Matthew, 2026-06-14 brainstorm; built per the refined plan
  below).** Owner gets per-stand Open/Closed QR codes on /my/;
  scanning one lands on a GET page whose JS POSTs to set_today, then flashes
  the screen (green=open / red=closed) + plays audio (fanfare=open / "Taps"=
  closed) and shows confirmation. IMPL: new view scan_status(slug, action) +
  url my/<slug>/scan/<action>/ (name='scan_status'); SCAN_ACTIONS map supports
  open/closed/pau/regular (only open+closed get QR codes today, rest are
  future-proofing). GET only RENDERS — never mutates (the safety property);
  the page's fetch() POST to the existing set_today is the only mutation, so
  scanners/prefetchers/link-previewers that don't run JS can't flip status.
  Anonymous → Google sign-in w/ next= back (no 404, so slugs aren't leaked to
  logged-out scanners); non-owner → 403 + logger.warning (audit) + NO acting
  form; idempotent SET semantics so re-scans are harmless. QR codes are inline
  base64 PNG data: URIs via new flyers.qr_data_uri() (reuses the qrcode lib),
  built in my_stands with request.build_absolute_uri so prod host/scheme are
  right. Dashboard: <hr class=manage-sep> + QR section under Edit/Photos with
  the "scan from your phone… print copies… only work signed in" copy. Audio =
  Web Audio API oscillators (no asset files) — open is a rising fanfare, closed
  is the opening phrase of "Taps". CAVEAT: mobile browsers block autoplay until
  a gesture, so the sound may not fire until the owner's first tap — the page
  arms a one-shot pointerdown listener to replay it; the green/red flash always
  works. ALSO: /stand/<slug> now shows a tip to a signed-in owner with NO posted
  weekly hours — explains the 3 ways to set status (edit hours / manual toggle /
  QR codes) + links to /my/. 190 tests (10 new: ScanStatusTests GET-no-mutate,
  owner form present, mutation-via-set_today, anon-signin-no-mutate, non-owner-
  403-no-form, unknown-action-404, dashboard-shows-2-QRs; OwnerHoursTipTests
  shown/hidden-with-hours/hidden-from-non-owner). LIVE VERIFY 2026-06-18:
  green/red flash + the GET-safe POST all work; AUDIO DID NOT PLAY on Firefox
  mobile in any config Matthew tried (Firefox mobile is especially strict about
  Web Audio autoplay even with the arm-on-first-tap fallback) — accepted as-is,
  the color flash is the reliable signal. FOLLOW-UP TWEAK shipped same day:
  dashboard QR row now uses justify-content:space-between so the Open code sits
  at the LEFT edge and Closed at the RIGHT edge of the text column (more
  separation on screen + printout, harder to scan the wrong one; stacks cleanly
  when the column is too narrow). FEATURE CLOSED OUT.
  ADMIN OUTREACH MESSAGE — DONE + DEPLOYED + verified live 2026-06-18 (QoL for
  Matthew). On an UNCLAIMED stand's admin change page there's now an "Outreach
  message" readonly field: a textarea pre-filled with his verbatim invite copy
  (CLAIM_MESSAGE_TEMPLATE constant in admin.py, {link} substituted with the
  stand's claim URL) + a one-click "Copy message" button (navigator.clipboard;
  textarea is also click-to-select-all as a fallback). Shows "—" once claimed,
  prompts to generate a link first if none. claim_message() method on StandAdmin,
  added to readonly_fields after claim_link. 192 tests (2 new
  AdminClaimMessageTests: message+link+Copy present when unclaimed, absent once
  claimed). Edit the script in one place (the constant). ORIGINAL PLAN kept below
  for reference:
  Set today's status by hitting a URL instead of a dashboard
  pill — /my/<slug>/override/open|closed|pau (+ /regular to clear) → enables
  per-stand QR stickers (RFID later) in the cashbox for one-scan open/close.
  Builds on the existing set_today/DayOverride today-toggle; reuse flyers.py QR
  machinery. Auth: logged-in owner → act; logged-out → login (next= back) then
  act; logged-in non-owner → error AND LOG (fishy-behavior audit, vs set_today's
  plain 404). APPROACH (refined): the GET just RENDERS a thin landing page (no
  mutation on the GET); JS on the page fires the real change as a CSRF POST to
  set_today, then confirms. Sidesteps the GET-mutates anti-pattern — prefetch/
  preview-bots/URL-scanners fetch the GET but don't run JS, so nothing changes;
  only a real browser mutates (POST). Use idempotent SET semantics anyway
  (open/closed/pau absolute, not toggle). Logged-in non-owner → error + log,
  never renders the acting JS. Thin GET view + auto-submitting template +
  existing set_today POST; no new data model.
- **Admin "Geocode now" button — DONE + DEPLOYED 2026-06-18 (Matthew).** Speeds
  up his social-media-sourced adds: a per-stand admin button fills lat/long from
  the street address instead of him looking it up on Google Maps by hand. NEW
  stands/geocoding.py is now the SINGLE source of the Nominatim rules (Big-Island
  viewbox+bounded, countrycodes=us, road-level/highway matches REJECTED, query
  shaping) shared by BOTH the batch `geocode` command (refactored to call it +
  keep its 1.1s politeness + never-overwrite-owner/admin-pin filter) AND the
  button. geocode_address(addr) returns a status dict (ok/road_only/no_match/
  error) and never raises on network trouble. Admin: geocode_button readonly
  field (shows current pin/source + "📍 Geocode now (best guess)") + url
  <pk>/geocode/ (name stands_stand_geocode) → on a place-level hit sets
  coords_source=GEOCODED + precision + geocoded_at and flashes coords+precision
  to eyeball; road_only/no_match/error just message (no save). DECISION: button
  ONLY — Matthew nixed submission-time auto-geocode 2026-06-18 because concurrent
  public submissions could blow the 1 req/s limit and queueing/state-tracking is
  overkill for the value. Road-only still REFUSED (consistent w/ the batch
  command, his call) — a street centroid is worse than no pin. 196 tests (4 new
  AdminGeocodeButtonTests: place-fills, road-refused, no-address-noop, button
  renders; the 3 GeocodeCommandTests repointed their mock to
  stands.geocoding.nominatim). No migration.
- **Facebook social link validation/normalization — DONE + VERIFIED ON PROD
  2026-06-18 (Matthew, 2026-06-14).** FB was messier than IG/TikTok: old
  forms.py _clean_handle did `.split('/')[0].split('?')[0]` → kept only the
  first path segment, so profile.php?id=NNN stored "profile.php" and
  pages/Name/ID stored "pages" → dead links; importer's own clean_handle only
  stripped @ (didn't even drop the domain). DECISION (Matthew's call): store FB
  as a FULL CANONICAL URL (https://www.facebook.com/...), NOT a bare handle
  like the other socials. IMPL: new module-level `normalize_facebook(value)` in
  forms.py parses vanity / full-or-partial URL (±scheme/www/m./fb.com) /
  profile.php?id=NNN / pages/Name/NNN and REBUILDS the URL from validated
  regex groups (nothing raw reaches the rendered href — security-safe);
  clean_facebook now calls it (so owner-edit + public-submit both covered).
  Root-cause fix: import_listings.py uses a `fb_url()` wrapper around the SAME
  normalizer (bad sheet cells import blank, don't abort the run). detail.html
  renders `href="{{ stand.facebook }}"` directly (was facebook.com/{{value}}).
  Model: facebook CharField widened 100→255 (full URLs are longer). Migration
  0008 = AlterField + RunPython backfill converting existing bare handles →
  full URLs (idempotent: skips values already starting with http; leaves
  unparseable legacy values untouched for manual admin review). 160 tests
  (added normalize-shapes/idempotency/hostile-reject + updated 2 old
  bare-handle assertions). Verified on prod (Sugar Wave Bakery FB link intact
  through deploy). NOTE for Threads (v1.2 backlog): reuse this same
  build-from-validated-parts pattern. Other socials (IG/TikTok) unchanged —
  still bare handles.
- **Make the claim-to-edit path more obvious (Matthew, 2026-06-14).** Real
  signal: an owner found errors and RE-SUBMITTED their stand (dup) instead of
  claiming it, then reached out on IG; Matthew resolved by sending both claim
  links and asking which to keep. Happened DESPITE the new claim_your_stand
  page + breadcrumb + 25m dup-warning → those aren't discoverable/strong
  enough. Consider: (1) submit-time dup guard says "Is this your stand? Claim
  it to fix details" + match on NAME similarity too (not just 25m geo, which a
  re-typed address slips); (2) more prominent breadcrumb + a claim CTA tied to
  the "Something wrong with this listing?" report link; (3) claim_your_stand
  page lead with "claim to EDIT/fix your info." Manual fix until auto-dedup:
  send both claim links, keep one, delist the other.
- **Bing Webmaster Tools findings (Matthew, 2026-06-14)** — overlaps SEO
  cluster; verified vs templates. (a) Missing image alt — DONE + VERIFIED ON
  PROD 2026-06-18: detail.html + owner photos.html now render
  alt="{caption else 'Photo from {{ stand.name }}'}" (blocktrans-wrapped for
  i18n). Matthew's call on the fallback phrasing: "Photo from <stand>" (not
  "<stand> — photo") to acknowledge it's user-submitted content. Non-empty,
  honest, translatable. The list-thumb empty alt (has aria-label on its link)
  and header hibiscus alt="" (decorative) left as-is — already correct.
  (b) No meta description (same as SEO item).
  (c) No H1 in body (BingBot cares): home/list, /map, submit.html,
  claim_your_stand.html use h2 and lack an h1 (Bing crawled home); add exactly
  one h1/page. (d) /cdn-cgi/l/email-protection errored link = Cloudflare Email
  Address Obfuscation (Scrape Shield) rewriting the mailto:matt@ links — NOT a
  code bug; a Cloudflare dashboard toggle. TURNED OFF 2026-06-18 (Security →
  Settings → Email Address Obfuscation) → clean mailto, Bing flag resolved.

## Person/context notes

- Matthew is injured — voice + clipboard only. Use AskUserQuestion choices,
  single-paste command blocks, read his clipboard rather than asking him to
  type. He's technical (ex-Facebook/Instagram M&A) but new to Django.
- Hobby project, explicitly not-for-profit, also a vehicle for learning AI
  tools. Motto applied at spec time: "perfect is the enemy of the good enough."
- Hard constraint: STAY IN FREE TIER everywhere (small child, project may
  pause anytime; no billing risk allowed).
