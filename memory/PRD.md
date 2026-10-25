# Promobeaux — PRD

## Original problem statement
Mobile app for budget-conscious grocery shoppers that alerts them when the groceries they buy regularly go on sale at nearby stores. Flow: Clerk sign-in (email + Google) → onboarding (ZIP + 2–4 stores: Kroger, Walmart, Target, Aldi, H-E-B, Tom Thumb) → watchlist (barcode scan or typed; name/brand/size/usual price) → Exa-powered deal search → scoring (real deal = 10%+ off, or BOGO/coupon/cashback) → alerts → deals feed grouped by store with savings → Savings screen "You could save $X this week" → "Check deals now". Clean, friendly, light design with one bold accent color, built for one-handed use.

## User choices
Clerk keys provided · Exa key provided · push + in-app banners · daily check scheduled inside the backend · one-tap demo mode with no sign-in.

## Architecture
- Expo Router (SDK 58): sign-in, onboarding, (tabs) Deals / Watchlist / Savings / Profile, add-item modal, scan (expo-camera).
- Auth: @clerk/expo (legacy email/password + email code, Google via useSSO on native). The backend checks Clerk sign-ins using Clerk's public signing keys (derived from the publishable key), plus HS256 demo tokens.
- FastAPI + MongoDB (users, items, deals, alerts). Exa search with highlights → precise matcher (brand + product word, whole words, nearby price). Open Food Facts barcode lookup. APScheduler runs at 8am CT (also clears out 7-day-old demo users).
- Push: Emergent relay (`/api/register-push`, `send_push`); skipped while EMERGENT_PUSH_KEY=placeholder. In-app banners poll alerts.

## Implemented (2026-10-24)
- All screens and flows above; separate demo user per visitor with sample data; demo deal checks limited to one per minute.
- Tested in iterations 1 and 2 (48/48 backend tests pass; all frontend flows pass); later matcher, snippet and UI fixes were checked with pytest.

## Iteration 2 (2026-10-25)
- Added Sprouts (7 stores total; Tom Thumb already present).
- Weekly-ad scan: one Exa search per selected store each check, scored against every watchlist item; deals tagged "Weekly ad".
- Store attribution: page domain first, else earliest whole-word store mention; "Brussels sprouts" etc. ignored.
- Matcher stays within a single ad line (no crossing "..." separators). Sample deals are cleared after the first real scan; an item's earlier deals are kept if only its own search fails. Two-letter store badges (TT vs T).
- Tested in iteration 3 (66/66 backend tests pass after fixes).

## Iteration 3 (2026-10-25)
- Savings share card (/share-card): branded image via react-native-view-shot + expo-sharing on phones; text share fallback on web.
- Undo delete: deleted items + deals go to `trash` (cleared after 1 day); POST /api/watchlist/{id}/restore; 6s Undo banner.
- Weekly ad browser (/ads, from the Deals header): GET /api/ads/{store} uses Exa, caches 6h (24h for demo), never caches empty results, drops non-US/Spanish sources and headline lines; "Watch" pre-fills Add item.
- Best store trip (/trip, from Savings): GET /api/trip picks the store with the highest summed best-deal savings (current stores only), builds the shopping list with an estimated total; checkmarks saved on the device.
- Deal alert banners show only on the main tabs. Tested in iteration 4; fixes then checked with pytest (81 pass).

## Iteration 4 (2026-10-25)
- Deal expiry: `ends_at` read from ad text/URL ("Oct 21 - Oct 27", "valid thru 10/28", slug oct-21-oct-27); otherwise estimated from the store's weekly-ad cycle (Kroger/Aldi/H-E-B/Tom Thumb/Sprouts end Tue, Target Sat; Walmart none) with `ends_estimated`. Deals the ad says are already over are skipped; ended deals are hidden from deals, savings and trip.
- Reminders: POST /api/reminders toggles a reminder per item+store; one alert (and a phone notification on real builds) when a reminded deal ends today or tomorrow — checked on toggle, after every deal check, and at 9am and 6pm.
- Deal cards show an expiry pill (warning color when ≤1 day) and a bell toggle; new "Ending soon" chip (≤2 days).
- After iteration 5 testing: month names must be real words (no "Octopus"), sizes like "12 - 24 oz" are never read as dates, the current ad-week range is preferred over weekend promos, and the server sends days_left in Chicago time so pills and alerts agree. Reminders are removed with their item/store; the reminder job only checks users who set reminders. Bell moved to the card tile, pill is full width with dark text on amber. 97 backend tests pass.

## Iteration 5 (2026-10-25)
- Brand logo added: the houndstooth cart wordmark (transparent background) on the sign-in screen and the share card; the cart artwork is used for the app icon, Android icon and splash (background #F8F8F8). Source files are in assets/images/brand/.

## Backlog
- P1: Confirm before deleting an item (or offer undo); stricter brand+product matching (e.g. Tyson nuggets vs breast).
- P1: Price history per item; shopping list for the best store this week.
- P2: Push only works on a published native build; Android needs google-services.json.
- P2: Share savings card.
