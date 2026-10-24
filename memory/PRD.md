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

## Backlog
- P1: Confirm before deleting an item (or offer undo); stricter brand+product matching (e.g. Tyson nuggets vs breast).
- P1: Price history per item; shopping list for the best store this week.
- P2: Push only works on a published native build; Android needs google-services.json.
- P2: Share savings card.
