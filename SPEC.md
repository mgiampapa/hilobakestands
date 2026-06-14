# HiloBakeStands.com — Project Specification

> **Status:** Final — v1.0 (perfect is the enemy of the good enough)
> **Last updated:** 2026-06-10

## 1. Overview

A local directory of food stands, bakeries, food trucks, farm stands, and pop up eateries in the Hilo area. Helps people find tasty things to eat, see when places are open, and get directions.

- **One-line pitch:** Hilo's Local Ono Grindz
- **Primary audience:** Primary audience is local foodies and tourists
- Secondary audience: Small business owners running popular bake stands, food trucks and other food oriented pop-ups.
- **What success looks like:** success is just being live, it's a project I want to do and is an excuse to learn how to use AI tools and get exposure to things outside my domain of expertise. Also, I want to be able to find my favorites without tracking a bunch of socials across platforms like tiktok that I am too old to understand generationally. I'm Facebook old, and while I use Instagram (and in fact worked on the M&A of Instagram by Facebook) I'm rapidly approaching yelling at clouds.

## 2. Core Features

For each, mark: **MVP** / **Later** / **No**

| Feature                                           | Priority | Notes                                                                                                                                                                                                                                                                    |
| ------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Browsable listing of stands                       | MVP      | The core of the site is effectively a database of things in the world. Having a text listing of what is currently shown on the map view and filtered to seems like table stakes.                                                                                         |
| Open-now / hours display                          | MVP      | Owners log in, claim ownership, set regular weekly hours, with an easy open/closed-today override. Feedback mechanism for regular users to report issues, handled ad-hoc at first. (Auth in MVP is the single biggest build cost — see Open Question 5 for the fallback cut.) |
| Map view + directions link                        | MVP      | I would like to use Open Street Map but provide direction links that open in dedicated navigation software like google maps, apple maps, waze etc...                                                                                                                     |
| Search / filter (by food type, area, open now)    | MVP      | Open now, open at time, food type, location type (Bake Stand, Food Truck, Pop-up, Farm Stand), distance.                                                                                                                                                                 |
| Photos per listing and Menus / Specials           | MVP      | Owner supplied photos, will require some kind of claiming / ownership per entry. Not that many in Hilo so it could be a manual process to approve or verify. Can seed a few locations from socials.                                                                      |
| Owner-submitted updates ("we're open today!")     | MVP      | Ownership is owner-initiated: a "claim this listing" path tells them to reach out, then Matthew validates in person at the business (see Open Q3). Owners update their photos and set the order. They can use this however they like, but expect they will just point people to their socials to own the customer contact. |
| Reviews / ratings                                 | Later    | We should allow account creation based on common 3rd party identity providers, Google / Apple login and tie review back to those identities. If there is a node on other graphs with reviews like google maps, facebook etc... we can try to find it and provide a link. |
| Mobile-friendly                                   | MVP      | Assume most users are on phones                                                                                                                                                                                                                                          |
| User submission of locations.                     | Later    | MVP: email/simple form with details. Later: logged-in users stub out an entry to be verified or claimed.                                                                                                                                                                 |
| Links to their socials / websites / email / phone | MVP      | Seeded by Matthew from public socials; owners can edit once they claim the entry.                                                                                                                                                                                        |

## 3. Listing Data Model

What we track per stand. Confirm / edit:

- Name
- Description / what they sell
- Street Address
- Geo Map coordinates, let them pin a map
- Hours — v1 model: weekly schedule + owner "open/closed today" override toggle + free-text note for irregular patterns (with a warning that free-text hours won't drive the open-now filter). Calendar-style recurrence rules (RRULE) deferred to a later phase if the simple model proves too rigid.
- Contact (phone, Instagram, Facebook, TikTok, Website, email)
- Photos
- Categories/tags (baked goods, plate lunch, shave ice...)
- Payment options (Cash, PayPal, Venmo, CashApp, Credit card — owner chooses which to display on their page. Cards mostly apply to staffed businesses like food trucks; unattended honor stands are cash/app-based.)
- Stand attendance type (attended vs. unattended honor stand — for unattended stands, "open" effectively means "stocked," so display hours with that framing)
- User Validation Score. (Starts high; user reports lower it. Low score triggers **Matthew's review**, not automatic delisting — protects against one grumpy person spam-reporting, and avoids permanently stranding unclaimed stands. Admin can restore/delist manually.)
- Last update timestamp / who did it
- Creation timestamp / who did it

## 4. Content & Data

- **Initial listings:** I think there are at least 20 or so, I'll populate the ones I know and post to reddit /r/bigisland saying I am making a list and asking if anyone wants to let me know about others.
- **Keeping data fresh:** Ideally the owners of the stands will claim them, I can try to reach out. Otherwise the user validation score can eventually weed out old ones.
- **Adding new stands:** will need an interface to add manually at first, email or form submission will also get off the ground. Eventually would like to make it self service

## 5. Tech Approach

**Decided: custom app.** Owner accounts, claiming, validation scores, and open-now filtering in the MVP require a database and auth — static/hosted options are off the table.

- **Framework: Django + SQLite** (decided 2026-06-10). Traffic is low; SQLite is trivially backed up by copying one file. Django's built-in admin covers manual listing entry, the validation-score review queue, and claim approvals with no extra code.
- **Admin UX note:** Django admin is fine for Matthew as sole operator. If less-technical helpers ever join, a simplified custom admin/moderation UI becomes a priority — the bar for "someone else can run this" is higher than stock Django admin. (Tracked in milestones as a conditional item.)
- **Auth:** third-party identity (Google / Apple sign-in) via django-allauth — no passwords to store.
- **i18n:** build UI strings i18n-ready from day one (English ships first; Japanese is the likely second language given the tourist market).

- **Hosting / domain:** HiloBakeStands.com registered with namecheap.com, can host on Oracle free tier to start. Could also host on home internet (200Mbps fiber) but would need to limit blast radius with some network segmentation.
- **Decision criteria:** Cost is a factor. I already have equipment running 24/7 and I don't expect this to be a lot of traffic. Will probably want to have Cloudflare or some other platform in front of it because the internet is full of terrors.

### 5a. Operational concerns (added during review)

- **Photo storage & moderation:** owner-uploaded images need disk space limits, resizing on upload, and a manual approval step (it's user-generated content — liability lives here).
- **Spam protection:** submission and feedback forms need at minimum a honeypot/rate limit; Cloudflare Turnstile is a free fit since Cloudflare is already planned.
- **Backups:** once owners enter their own data, losing it burns goodwill. Nightly SQLite snapshot to a second location (home box ↔ Oracle, whichever isn't primary).
- **Email sending:** piggyback on existing Google Apps Legacy account, adding HiloBakeStands.com as an additional domain. Not for high volume, but nothing here is high volume. (App sends via Gmail SMTP/API with an app-specific credential; set up SPF/DKIM at Namecheap so mail authenticates.)

## 6. Design

- **Look & feel:** I like simple tropical vibes, think lilo and stich.
- **Logo / branding:** Functional would be the key, can always revisit. The idea is to get them somewhere else
- **Languages:** English, modern browsers can auto translate effectively. Internationalization could be useful for Japanese tourists which are a traditional mainstay of the tourist market.

## 7. Non-Goals (explicitly out of scope)

- This isn't trying to be a profit generation business, its not intending to follow any yelp like model.

## 8. Open Questions

1. ~~How do stands with irregular hours get represented honestly?~~ **Resolved:** v1 uses weekly schedule + open/closed-today override + free-text note; calendar recurrence (RRULE) deferred. (Original instinct was the calendar approach — kept as the upgrade path.)
2. It's solving a problem I have personally had. Since Merry Monarch 2026 there has been a proliferation of people opening bake stands as side hustles. As a result, there is all kinds of great local food to try, and I only find out so much via the coconut wireless. If I am having this problem, others are too.
3. ~~Owner verification flow~~ **Resolved:** owner-initiated. The site has a "claim this listing" path that tells the owner to reach out; Matthew then validates in person by visiting the business when they're open. Flips the onus — owners contact Matthew instead of Matthew chasing them. Scales fine at this size, and in-person validation is about as fraud-proof as it gets.
4. ~~Naming~~ **Resolved — intentional.** "Bake stands" capitalizes on the post-Merry-Monarch trend of honor stands popping up all over town, itself an extension of Hawaii's long farm-stand tradition. Hawaii's cottage food laws make home baked-goods sales easy, which fuels the trend. It's the umbrella brand; scope deliberately includes trucks, pop-ups, and farm stands.
5. With auth in the MVP, what's the true minimum launchable cut if the build drags? (Pre-agreed fallback: launch read-only directory with Matthew-maintained data, flip on owner login when ready.)

## 9. Milestones

1. ~~Spec finalized~~ — **done 2026-06-10**
2. ~~Tech approach chosen~~ — **done 2026-06-10** (Django + SQLite, OAuth sign-in via django-allauth, Cloudflare in front)
3. Data collected for first batch of listings (~20 known; reddit /r/bigisland call for more)
4. First version live (fallback cut: read-only directory if auth drags)
5. Owner claiming live; reach out to stand owners
6. Gather feedback and iterate
7. (Conditional) Simplified admin UI — triggered if/when a less-technical helper joins
8. (Conditional) Containerize deployment — deferred 2026-06-10; trigger: moving hosts (e.g. Oracle → home server) or running multiple services on one box. systemd + bootstrap.sh is the deploy path until then.
