# HiloBakeStands.com — Spec v1.1: Public Stand Submissions

> **Status:** Draft — v1.1 (design agreed 2026-06-13; not yet built)
> **Builds on:** v1.0 (see `SPEC.md`). Realizes the v1.0 "User submission of
> locations → Later: logged-in users stub out an entry to be verified or
> claimed" item.
> **Last updated:** 2026-06-13

## 1. Why

Today every listing is seeded by Matthew, so all data is implicitly trusted.
v1.1 opens the door to community-sourced listings: point anyone on r/bigisland,
Facebook groups, or Instagram at a "Submit a stand" form and let them add stands,
trucks, and pop-ups themselves. Submissions are clearly marked **Unverified**
until Matthew approves them or the real operator claims them, so the curated
core stays trustworthy while the long tail fills in from the community.

This also unlocks **remote owner onboarding**: because the claim flow is already
URL-token based (not tied to an in-person QR handout), an operator who DMs
Matthew from their business Instagram can be sent a claim URL and verify
themselves without Matthew ever visiting in person.

## 2. Decisions (agreed 2026-06-13)

| Decision | Choice |
| --- | --- |
| Moderation model | A submission publishes immediately badged *Unverified*. **Launch = manual review** (low scores flag for Matthew, nothing auto-acts — the v1.0 stance). The **hybrid auto-hide** (auto-hide on report, pending review) is designed but **conditional** — built only if abuse appears (see §5b right-sizing). |
| Extra abuse defense | **Text denylist filter** on submitted text, *in addition to* the report button. |
| Default public view | **Verified only.** Unverified stands are hidden by default behind a toggle. |
| What flips Unverified → Verified | **Either** Matthew approves it **or** an owner claims it via the existing claim flow. |
| Who can submit | **Logged-in users only** (Google sign-in already in place) — gives accountability and per-user rate limiting. |
| Submitter vs owner | The submitter is **recorded but not made owner.** A fan submitting their favorite truck shouldn't "own" it; the operator still claims it separately. |
| Notifications | Each new submission **emails Matthew** (email infra already live). |

## 3. Data Model Changes (`Stand`)

New fields. None remove or repurpose existing ones; the existing `status`
(draft/published/delisted), `owner`, `claim_token`, `claimed_at`, and
`validation_score` all keep their current meaning.

| Field | Type | Purpose |
| --- | --- | --- |
| `verification` | CharField choices `unverified` / `verified`, default `unverified` | The new trust flag. Independent of `status` (visibility) and `owner` (control). |
| `created_by` | FK → User, null, `on_delete=SET_NULL` | Who submitted/created the stand. Distinct from `owner`. |
| `created_via` | CharField choices `admin_seed` / `public_submit` (extensible) | Provenance of the record. |
| `submitted_at` | DateTimeField, null | When a public submission came in. |
| `verified_at` | DateTimeField, null | When it flipped to verified. |
| `verified_via` | CharField choices `admin` / `claim`, blank | How it got verified (audit trail). |
| `auto_hidden` | BooleanField, default False | Set True by the report hook (the "hybrid" auto-hide). Excludes the stand from public views regardless of `status` and surfaces it in the admin review queue. Cleared by Matthew. |

**Three independent facts, by design:** *who submitted it* (`created_by`),
*whether anyone owns it* (`owner`), and *whether it's verified* (`verification`).

**Claim tokens for submissions.** Today tokens are minted for seeded stands.
The submit path must also **mint a `claim_token`** so Matthew can hand out the
claim URL to anyone, anytime (e.g. via Instagram DM).

## 4. Submission Flow

1. A logged-in user opens **"Submit a stand"** (new header/footer CTA; login-gated — anonymous visitors are sent to sign in first).
2. Form collects the v1.0 stand fields (name, type, description, address, contact, categories, payment, attendance). Reuses the existing `forms.py` sanitization (handle whitelisting from pasted URLs, strip, length caps).
3. Submission is gated by, in order: **login**, **Cloudflare Turnstile** (already used on the report form), a **per-user rate limit**, a **honeypot**, the **text denylist filter** (§5), and — when configured — the **optional off-box semantic/LLM gate** (§5a, runs on the homelab). **Loading indicator:** any step that can take more than a second or two — the off-box moderation round-trip and address geocoding in particular — must show a visible working state (throbber/spinner) and disable the submit button while in flight, so the user knows it's still processing and doesn't double-submit. (General principle for any async operation in these flows, not just submit.)
4. On success the stand is created as `status=published`, `verification=unverified`, `created_by=<user>`, `created_via=public_submit`, `submitted_at=now`, with a fresh `claim_token` minted.
5. Matthew gets a **notification email**. The stand appears publicly **badged "Unverified,"** but only to users who have toggled unverified stands on (default view hides them).
6. **Location & pin.** The street address is geocoded to an approximate point as a fallback, but the submitter can **drag a pin to the exact location**, and a placed pin **overrides the geocoded address**. This reuses the v1.0 `CoordsSource` precedence (a human-placed pin outranks `geocoded` and is never overwritten by the geocoder), so the exact pin always wins over the rough address match. The same **drag-to-place pin** behavior applies in **both** flows — the public submission form here *and* the post-claim owner edit flow (`/my/<slug>/pin/`, already built). A submitter's pin **reuses the `owner_pin` coords source** (resolved §10.4), so it outranks and is never overwritten by the geocoder, and is **constrained to the Big Island** via the existing bbox check. **Duplicate guard:** at submit time, if an existing stand is within **25 m** of the entered address/pin, show a non-blocking **proximity warning** so the submitter can confirm it isn't already listed (resolved §10.2).

## 5. Moderation & Anti-Abuse

Pointing "anyone on Reddit" at a form is a spam/abuse magnet, so the submit path
layers cheap defenses rather than relying on any one:

- **Login required** — Google sign-in gives a stable identity to rate-limit and ban.
- **Cloudflare Turnstile** — deters basic/script bots (already integrated for the report form). **Realistic caveat:** in the AI-tooling era, CAPTCHA-style gates are increasingly solvable, so Turnstile is treated as *one* layer, not the linchpin. The stronger bot gate for **submissions** is the **login requirement** (a bot needs a real Google account, which is far costlier to farm than solving a CAPTCHA); for **anonymous reports** the backstop is low impact (manual review, no auto-action in v1.1) plus the per-IP rate-limit lever held in reserve.
- **Per-user rate limit** — **5 submissions per user per day** (§10.1), tuned from logs.
- **Honeypot field** — silent bot trap.
- **Text denylist filter** — the cheap, always-on first layer: a server-side screen of `name` + `description` for slurs, spam terms, and URL-spam (excessive links / all-caps / repeated chars). On match: reject with a generic message (or silently flag for review). Lives in a small module (e.g. `stands/textmod.py`) with a maintainable term/regex list. This is the "text filters in addition to reporting." It is the first backend of the pluggable moderator described in §5a.
- **Semantic check (optional, stubbed for v1.1)** — an optional second layer that sends the text to a service (an LLM) to judge whether it is **pono** (proper / in good faith), **kind**, and **constructive** — catching hostile, trolling, or low-effort content that a keyword list misses. See §5a.
- **Hybrid auto-hide (CONDITIONAL — deferred unless abuse appears; see §5b right-sizing)** — when built, an unverified stand auto-hides (`auto_hidden=True`, reversible, pending review — **not** delisted) only after **N distinct authenticated users** report it (N ≥ 2, exact value TBD). **A single report never hides a stand.** Verified stands are **exempt**: per the v1.0 rule, reports on them only trigger admin review, never auto-hide. This depends on the report-integrity fixes in §5b — auto-hide must not ship on top of today's unprotected report flow.
- **Report button** — the existing reporting path still applies to all stands.

Sanitization note: all submitted text is escaped on output (Django autoescape,
no `|safe`), and social handles are whitelisted/normalized server-side, matching
the existing owner-edit hardening.

### 5a. Pluggable content moderation (denylist now, semantic/LLM later)

Text moderation is built behind **one small interface** rather than hard-wired,
mirroring the proven photo-moderation design (Vision SafeSearch primary +
homelab fallback). A `TextModerator` takes `(text, context)` and returns a
verdict: `allow` / `flag` / `reject`, plus a reason and optional scores.

Two backends, layered:

1. **Denylist (active in v1.1)** — synchronous, free, always runs. Hard-`reject`s
   clear violations (slurs, obvious spam).
2. **Semantic / LLM (architecture decided 2026-06-13; wired post-v1.1)** — scores
   the text on **pono / kind / constructive** and returns a verdict. The decided
   chain mirrors the image pipeline (Vision primary + homelab fallback):
   **denylist (wordlist) → Cloudflare Worker (primary) → local self-hosted model
   (fallback on `media.home`)**. Cloudflare Workers AI is primary — free daily
   allocation, serverless, no 24/7 hardware, stays in-stack; the homelab small
   GGUF (Llama 3.2 1B / small Qwen via llama.cpp/Ollama, CPU-only) is the
   fallback, reusing the existing `MODERATION_FALLBACK_URL`/`TOKEN` config and
   reverse tunnel already built for image moderation. Env-gated like
   `VISION_API_KEY`; **v1.1 ships with this layer dark** (denylist only) — the
   Worker + fallback are wired in a later pass. Final model + thresholds: §10.8.

Design intent: the LLM is a **softer** instrument than the denylist. Fuzzy tone
judgments should usually `flag` (route to the review queue via `auto_hidden`),
**not** hard-`reject`, so an imperfect model doesn't silently eat legitimate
submissions. The denylist stays the only thing allowed to auto-reject outright.

**Failure mode: fail-CLOSED + notify (decided 2026-06-13, reverses earlier
fail-open).** If the chain can't produce a verdict — Cloudflare Worker *and*
local fallback both unreachable — the submission is **held: saved but withheld
from public, not auto-published**, and Matthew is **emailed** to review/release
it by hand. Rationale: submissions are review-gated and low-volume anyway, so
hold-and-notify beats silently publishing unmoderated content. The submitter
sees a clear *"pending review"* state, not an error, and the held item is
actionable in admin. This is distinct from a `flag` verdict — a *working*
moderator that flags routes to the normal review queue; fail-closed is
specifically the both-backends-down case.

**Reuse for reviews (forward-looking).** User reviews/ratings are deferred to
**v1.2** (originally a v1.0 "Later" item). When they land, review text is the
same kind of short user-generated content, so it flows through this **same
`TextModerator` pipeline** — building the interface now (even with only the
denylist wired) means the v1.2 review system inherits pono/kind/constructive
screening for free. This is the main reason to define the interface in v1.1
rather than inline the denylist.

### 5b. Report integrity (hardens an existing v1.0 flaw)

**The flaw (found during v1.1 review).** Today's `stand_report` view is
**anonymous**, Turnstile-gated, and drops `validation_score` by 10 per
submission with **no per-user dedup** and **no record of who reported**. One
person can submit the form repeatedly and crater a stand's score to 0. Right now
that can't delist anything (v1.0 makes low scores trigger admin review, never
auto-delist — the deliberate protection), but it spams the admin queue + email.
The instant v1.1 adds auto-hide, this unprotected flow becomes a
**single-actor takedown vector**.

**Right-sizing (scope decision).** This is a low-profile local directory unlikely
to attract coordinated abuse, so the elaborate fix below is **conditional, not
launch-blocking.** v1.1 ships submissions on the cheap, proven defenses — login +
Turnstile + denylist + **manual review** — exactly the v1.0 stance where low
scores flag for human review and nothing auto-acts. The report-integrity work and
the hybrid auto-hide are **built only if abuse actually materializes.** If it
does, the escalation levers, cheapest first, are: (a) per-IP rate-limit reports;
(b) reuse the §5a `TextModerator`/LLM to **classify each report as spam vs.
worth-human-attention**, routing only genuine ones to the admin (the same tool,
pointed at reports instead of submissions); (c) an email-spam-filter style pass;
and only then (d) the full reporter-identity + threshold-auto-hide machinery.

If/when that machinery is built, the design is:

- **Record the reporter.** Add `reporter` (FK User, nullable) + a salted-daily
  IP hash to the `Report` model so reports are attributable.
- **One report per user per stand.** Dedup so a user's repeated reports on the
  same stand count **once** toward score and the auto-hide threshold. Kills
  single-actor serial reporting.
- **Authenticated reports carry the weight.** Only logged-in, deduped reports
  move the score and count toward auto-hide.
- **Anonymous reports still notify, but don't score.** An anonymous report is
  still **recorded and surfaced to the admin** (so a legitimate "this stand is
  gone" from a not-logged-in user isn't lost) but does **not** move the score or
  count toward auto-hide. Preserves a low-friction path without letting it be
  weaponized into a takedown.
- **Protect the notification channel (later lever).** Notifications are
  themselves a spam surface (a troll who can't move the score could still
  mail-bomb the admin). **Decision (§10.6): not addressed in v1.1** — anonymous
  reports stay **real-time per-event email** and Matthew accepts the flood risk
  while the site is low-volume; the real rate will be learned from actual use.
  Per-IP rate-limiting or a throttled digest remains a documented escalation
  lever for if/when volume demands it.
- **Sockpuppet caveat.** Login raises the bar but coordinated multi-account
  reporting is still possible; weighting by account age / prior standing is a
  later lever. The backstop is that auto-hide is **reversible + review-gated**, so
  the worst case is a brief hide pending review — never a permanent kill.

This same reporter-identity + dedup model is also what a future review system
(v1.2) needs, so it is not throwaway work.

## 6. Verification Model

A stand flips `unverified → verified` via either path:

- **Admin approval** — a Django-admin bulk action "Mark verified" (sets `verification=verified`, `verified_at=now`, `verified_via=admin`).
- **Owner claim** — completing the existing claim flow sets `owner`, `claimed_at`, **and** `verification=verified`, `verified_via=claim`. So when an operator claims their stand it becomes verified automatically.

Verified stands lose the "Unverified" badge and appear in the default public view.

## 7. Filtering & UI

- **Default queryset** for the public list and map filters to `verification=verified` and `auto_hidden=False`.
- **Toggle** — "Show community submissions" (or "Include unverified") reveals unverified stands. Persisted client-side, mirroring the existing near-me `localStorage` preference pattern.
- **Badge** — unverified stands show a subtle "Unverified" / "Community-submitted" badge on list cards and the detail page.
- Unverified stands, when toggled on, appear on **both** the list and the map (consistent behavior).

## 8. Migration Plan

- Add the new fields (§3) in one migration.
- **Data migration:** set all existing stands to `verification=verified`,
  `created_via=admin_seed`, `verified_via=admin`, `verified_at=now`,
  `created_by=null` (or Matthew's superuser). They were curated by Matthew, so
  they are verified by definition — the public view is unchanged on deploy.
- Seeded stands already have claim tokens; only the submit path needs to mint new ones.
- Template-and-code + one schema migration. No data loss; safe under the
  standard `deploy.sh` (migrate + restart).

## 9. Non-Goals for v1.1

- No *active* automated/ML content moderation in v1.1 — the denylist + Turnstile + report + manual review carry launch. The semantic/LLM layer (§5a) is **interface-only / stubbed**: defined and wireable, but off until its endpoint is configured.
- **No user reviews/ratings in v1.1 — deferred to v1.2.** The `TextModerator` interface (§5a) is built now so v1.2 reviews inherit pono/kind/constructive screening without rework.
- No anonymous submissions (login required).
- **Report-integrity hardening + hybrid auto-hide are deferred/conditional** — not built for v1.1 launch (manual review handles the realistic case). Designed in §5b, triggered only if abuse materializes; escalation path documented there.
- No edit-by-anyone — only the owner (post-claim) or admin can edit a listing.
- No automated duplicate *merge* in v1.1 — but the submit form shows a within-25m **proximity warning** (§10.2) so submitters can self-catch dupes; Matthew merges by hand in admin. Automated batch dup-detection is deferred unless dupes become a real problem.

## 10. Open Questions

1. ~~Rate-limit threshold~~ **RESOLVED (2026-06-13): 5 submissions per user per day**, tune from logs.
2. ~~Duplicate submissions~~ **RESOLVED (2026-06-13):** warn the submitter at submit time if an existing stand is **within 25 meters** (proximity warning, non-blocking). If duplicates become a real problem, add a **batch process** to identify them later — no automated merge in v1.1.
3. ~~Denylist source & upkeep~~ **RESOLVED (2026-06-13):** seed `textmod.py` from a public profanity wordlist (e.g. the LDNOOBW "naughty words" list), **supplemented with local Hawaiian Pidgin** profanity/slurs. Keep the list **narrow** (clear slurs/spam only) and lean on the §5a LLM layer for nuance — Hawaiian/Pidgin is legitimate local content, so the denylist must not flag local language generally (avoid Scunthorpe-style false positives). Maintenance: Matthew curates additions.
4. ~~Submitter pin provenance~~ **RESOLVED (2026-06-13):** trust the **submitter's pin over the geocoder** ("a random person's best guess beats the geocoder"). **Reuse the existing `owner_pin` coords source** (no new source type) — so a submitter pin gets the same top precedence and is never overwritten by the geocoder. (Provenance that it came from a public submission is still captured by `created_via=public_submit`, so reusing `owner_pin` doesn't lose that history.) **Constrain the pin to the island** by reusing the Big Island bbox check already built for the owner pin page (`/my/<slug>/pin/`) — no dragging the pin to LA.
5. ~~Auto-hide threshold (N)~~ **RESOLVED (2026-06-13): N = 2** distinct authenticated reporters — small island, small population; raise N as the userbase grows. (Applies only if the conditional auto-hide machinery is ever built, §5b.)
6. ~~Reports: login required, or anonymous-as-weak-signal?~~ **RESOLVED (2026-06-13):** keep the **anonymous path** — no login required to report. The **signal-strength model** is endorsed for when the conditional §5b machinery is built (authenticated/deduped reports move the score + count toward auto-hide; anonymous reports are a weak, notify-only signal). **Notifications: real-time per-event email for now** — no rate-limit or digest; Matthew accepts the flood risk and will revisit once the site is in real use and initial data is being crowdsourced. Rate-limit/digest stays a documented later lever.
7. ~~Notification format~~ **RESOLVED (2026-06-13):** same as §10.6 — **real-time per-event email** per submission for now; Matthew accepts the volume while the site is low-traffic and will revisit once real usage shows the rate. A daily digest stays a documented later lever.
8. ~~Semantic moderator backend~~ **ARCHITECTURE RESOLVED (2026-06-13); only final model + thresholds remain (post-v1.1).** Chain: **denylist → Cloudflare Worker (primary) → local self-hosted fallback**, **fail-CLOSED + notify** (§5a). The task is tiny (classify a short blurb), so a **1–3B model is plenty and runs CPU-only** — no GPU needed. The resolved primary + fallback shape mirrors the photo pipeline:
   - **Primary: Cloudflare Workers AI** — free tier 10,000 Neurons/day (resets daily, includes hosted open-source models); a low-traffic directory won't approach that ceiling, so effectively free, serverless, no 24/7 hardware, and stays in the existing Cloudflare stack. Call a small Llama/Qwen from a Worker.
   - **Fallback: small self-hosted GGUF on media.home** — e.g. Llama 3.2 1B or a small Qwen at Q4_K_M via llama.cpp/Ollama; usable CPU speed for short classification (3B possible but slower). Reuses the existing homelab moderation service + reverse tunnel already built for image moderation — a text-classify endpoint slots in beside it.
   - **High-volume / paid path = the same Worker.** If free-tier Neurons are ever exceeded, Workers AI scales by simply **attaching billing — same integration, no new code or vendor.** So the Worker is *both* the free path and the cheap-paid-API path; a separate third-party LLM API (Gemini Flash / GPT-4o-mini / Groq) is therefore largely **redundant** and worth considering only if Cloudflare's model menu falls short. (Aside: OpenAI's *moderation* endpoint is free but scores fixed safety categories only — can't do `pono`/`kind`/`constructive` — so a small instruct model + custom prompt is better regardless of host.)
   - Still to settle when wired: exact model, the JSON verdict shape (allow/flag/reject + scores), and `flag`-vs-`reject` thresholds (per §5a, default to **flag** for fuzzy tone, only denylist auto-rejects).

## 11. Implementation Checklist (when built)

1. Model: add fields (§3) + migration + data migration (seeds → verified).
2. Admin: list filters on `verification` / `created_via` / `auto_hidden`; "Mark verified" bulk action; review queue for `auto_hidden`.
3. Submit form + login-gated view; reuse `forms.py` sanitization; Turnstile; honeypot; per-user rate limit; `textmod.py` denylist behind a `TextModerator` interface (§5a) with the semantic/LLM backend stubbed + env-gated.
4. On submit: create published + unverified + provenance fields + mint `claim_token`; send notification email.
5. Claim flow: on successful claim, also set `verification=verified`, `verified_via=claim`, `verified_at`.
6. *(Conditional — only if abuse appears, §5b)* Report integrity: add `reporter` FK + salted-daily IP hash to `Report`; one-report-per-user-per-stand dedup; only authenticated deduped reports move the score; rate-limit reports.
7. *(Conditional — only if abuse appears, §5b)* Report hook: trip `auto_hidden=True` only at N distinct authenticated reporters; verified stands exempt. (Earlier escalation levers — per-IP rate limit, LLM spam-vs-genuine classification — come first.)
8. List/map querysets: default verified + not-hidden; toggle param + UI; persist preference.
9. Badge UI on cards + detail.
10. Header/footer "Submit a stand" CTA (login-gated).
11. Tests: submit happy path; login required; denylist rejects; rate limit; unverified hidden by default; toggle reveals; claim verifies; report auto-hides (only at N distinct reporters, not one); serial-report dedup counts once; migration marks seeds verified.
