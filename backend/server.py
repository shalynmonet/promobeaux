import asyncio
import base64
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, List, Optional

import httpx
import jwt
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson import ObjectId
from dotenv import load_dotenv
from exa_py import Exa
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("promobeaux")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

EXA_API_KEY = os.environ["EXA_API_KEY"]
DEMO_JWT_SECRET = os.environ["DEMO_JWT_SECRET"]
CLERK_PUBLISHABLE_KEY = os.environ["CLERK_PUBLISHABLE_KEY"]
PUSH_KEY = os.environ.get("EMERGENT_PUSH_KEY", "placeholder")
PUSH_BASE_URL = "https://integrations.emergentagent.com"

exa = Exa(api_key=EXA_API_KEY)


def _clerk_frontend_api(pk: str) -> str:
    enc = pk.split("_", 2)[2]
    enc += "=" * (-len(enc) % 4)
    return base64.b64decode(enc).decode().rstrip("$")


CLERK_ISSUER = f"https://{_clerk_frontend_api(CLERK_PUBLISHABLE_KEY)}"
jwks_client = jwt.PyJWKClient(f"{CLERK_ISSUER}/.well-known/jwks.json", cache_keys=True)
push_client = httpx.AsyncClient(base_url=PUSH_BASE_URL, headers={"X-Push-Key": PUSH_KEY}, timeout=10.0)

STORES = ["Kroger", "Walmart", "Target", "Aldi", "H-E-B", "Tom Thumb", "Sprouts"]
STORE_ALIASES = {
    "Kroger": ["kroger"],
    "Walmart": ["walmart"],
    "Target": ["target.com", "target "],
    "Aldi": ["aldi"],
    "H-E-B": ["h-e-b", "heb.com", " heb "],
    "Tom Thumb": ["tom thumb", "tomthumb"],
    "Sprouts": ["sprouts"],
}

app = FastAPI()


@app.get("/health", include_in_schema=False)
@app.head("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


api = APIRouter(prefix="/api")


# ---------------------------------------------------------------- models
PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        return cls.model_validate(doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude={"id"})
        if self.id:
            data["_id"] = ObjectId(self.id)
        return data


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class User(BaseDocument):
    user_id: str
    is_demo: bool = False
    zip: str = ""
    stores: List[str] = []
    onboarded: bool = False
    created_at: str = Field(default_factory=now_iso)
    last_checked_at: Optional[str] = None


class Item(BaseDocument):
    user_id: str
    name: str
    brand: str = ""
    size: str = ""
    usual_price: float
    barcode: str = ""
    created_at: str = Field(default_factory=now_iso)


class Deal(BaseDocument):
    user_id: str
    item_id: str
    item_name: str
    brand: str = ""
    size: str = ""
    store: str
    usual_price: float
    sale_price: float
    savings: float
    pct_off: float
    promo_type: str  # sale | bogo | coupon | cashback
    promo_text: str = ""
    source_kind: str = "search"  # search | weekly_ad
    source_url: str = ""
    source_title: str = ""
    is_sample: bool = False
    found_at: str = Field(default_factory=now_iso)


class Alert(BaseDocument):
    user_id: str
    title: str
    message: str
    deal_key: str
    read: bool = False
    created_at: str = Field(default_factory=now_iso)


class OnboardingIn(BaseModel):
    zip: str = Field(pattern=r"^\d{5}$")
    stores: List[str] = Field(min_length=2, max_length=4)


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand: str = Field(default="", max_length=80)
    size: str = Field(default="", max_length=40)
    usual_price: float = Field(gt=0, lt=1000)
    barcode: str = Field(default="", max_length=40)


class RegisterPushBody(BaseModel):
    user_id: Optional[str] = None
    platform: str
    device_token: str


# ---------------------------------------------------------------- auth
def _verify_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
    if header.get("alg") == "HS256":
        try:
            return jwt.decode(token, DEMO_JWT_SECRET, algorithms=["HS256"])
        except jwt.PyJWTError:
            raise HTTPException(401, "Invalid demo session")
    try:
        key = jwks_client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], leeway=60, options={"verify_aud": False})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired session")
    if claims.get("iss") != CLERK_ISSUER:
        raise HTTPException(401, "Invalid issuer")
    return claims


async def current_user(authorization: str = Header(default="")) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    claims = await asyncio.to_thread(_verify_token, authorization[7:])
    uid = claims["sub"]
    doc = await db.users.find_one({"user_id": uid})
    if not doc:
        user = User(user_id=uid, is_demo=bool(claims.get("demo")))
        await db.users.insert_one(user.to_mongo())
        doc = await db.users.find_one({"user_id": uid})
    return User.from_mongo(doc)


# ---------------------------------------------------------------- demo seed
DEMO_ITEMS = [
    ("Large Eggs", "Eggland's Best", "12 ct", 4.79),
    ("Whole Milk", "Horizon Organic", "64 oz", 6.29),
    ("Ground Coffee", "Folgers Classic Roast", "25.9 oz", 12.99),
    ("Cheerios Cereal", "General Mills", "18 oz", 5.49),
    ("Boneless Chicken Breast", "Tyson", "2.5 lb", 11.49),
    ("Laundry Detergent Pacs", "Tide Pods", "42 ct", 13.99),
]
DEMO_DEALS = {
    "Large Eggs": ("Kroger", 3.49, "sale", "Digital deal: Eggland's Best Large Eggs 12 ct $3.49 with Card"),
    "Ground Coffee": ("Target", 9.99, "coupon", "Save $3 with Target Circle on Folgers 25.9 oz canisters"),
    "Cheerios Cereal": ("Walmart", 2.75, "bogo", "Buy 1 Get 1 Free on select General Mills cereals"),
    "Laundry Detergent Pacs": ("Kroger", 11.99, "cashback", "$2 cash back on Tide Pods 42 ct via digital rebate"),
}


async def seed_demo(uid: str):
    await db.users.update_one(
        {"user_id": uid},
        {"$setOnInsert": User(user_id=uid, is_demo=True, zip="75201",
                              stores=["Kroger", "Walmart", "Target"], onboarded=True).to_mongo()},
        upsert=True,
    )
    if await db.items.count_documents({"user_id": uid}):
        return
    for name, brand, size, price in DEMO_ITEMS:
        item = Item(user_id=uid, name=name, brand=brand, size=size, usual_price=price)
        res = await db.items.insert_one(item.to_mongo())
        if name in DEMO_DEALS:
            store, sale, ptype, text = DEMO_DEALS[name]
            savings = round(price - sale, 2)
            await db.deals.insert_one(Deal(
                user_id=uid, item_id=str(res.inserted_id), item_name=name, brand=brand, size=size,
                store=store, usual_price=price, sale_price=sale, savings=savings,
                pct_off=round(savings / price * 100, 1), promo_type=ptype, promo_text=text, is_sample=True,
            ).to_mongo())
    await db.alerts.insert_one(Alert(
        user_id=uid, title="Cheerios is BOGO at Walmart",
        message="Buy 1 Get 1 Free — save $2.74 this week", deal_key="seed-cheerios").to_mongo())


@api.post("/auth/demo")
async def demo_login():
    uid = f"demo_{uuid.uuid4().hex[:12]}"
    await seed_demo(uid)
    token = jwt.encode(
        {"sub": uid, "demo": True, "exp": datetime.now(timezone.utc) + timedelta(days=7)},
        DEMO_JWT_SECRET, algorithm="HS256",
    )
    return {"token": token}


# ---------------------------------------------------------------- profile
@api.get("/stores")
async def list_stores():
    return {"stores": STORES}


@api.get("/me")
async def me(user: User = Depends(current_user)):
    return user.model_dump()


@api.put("/me/onboarding")
async def onboarding(body: OnboardingIn, user: User = Depends(current_user)):
    bad = [s for s in body.stores if s not in STORES]
    if bad:
        raise HTTPException(400, f"Unknown stores: {bad}")
    await db.users.update_one({"user_id": user.user_id},
                              {"$set": {"zip": body.zip, "stores": body.stores, "onboarded": True}})
    await db.deals.delete_many({"user_id": user.user_id, "store": {"$nin": body.stores}})
    doc = await db.users.find_one({"user_id": user.user_id})
    return User.from_mongo(doc).model_dump()


# ---------------------------------------------------------------- watchlist
@api.get("/watchlist")
async def get_watchlist(user: User = Depends(current_user)):
    docs = await db.items.find({"user_id": user.user_id}).sort("created_at", -1).to_list(200)
    return [Item.from_mongo(d).model_dump() for d in docs]


@api.post("/watchlist")
async def add_item(body: ItemIn, user: User = Depends(current_user)):
    item = Item(user_id=user.user_id, **body.model_dump())
    res = await db.items.insert_one(item.to_mongo())
    item.id = str(res.inserted_id)
    return item.model_dump()


def _oid(item_id: str) -> ObjectId:
    if not ObjectId.is_valid(item_id):
        raise HTTPException(404, "Item not found")
    return ObjectId(item_id)


@api.put("/watchlist/{item_id}")
async def update_item(item_id: str, body: ItemIn, user: User = Depends(current_user)):
    res = await db.items.update_one({"_id": _oid(item_id), "user_id": user.user_id}, {"$set": body.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Item not found")
    return Item.from_mongo(await db.items.find_one({"_id": _oid(item_id)})).model_dump()


@api.delete("/watchlist/{item_id}")
async def delete_item(item_id: str, user: User = Depends(current_user)):
    res = await db.items.delete_one({"_id": _oid(item_id), "user_id": user.user_id})
    if not res.deleted_count:
        raise HTTPException(404, "Item not found")
    await db.deals.delete_many({"user_id": user.user_id, "item_id": item_id})
    return {"ok": True}


@api.get("/barcode/{code}")
async def barcode_lookup(code: str, user: User = Depends(current_user)):
    if not re.fullmatch(r"\d{6,14}", code):
        raise HTTPException(400, "Invalid barcode")
    try:
        async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "Promobeaux/1.0"}) as c:
            r = await c.get(f"https://world.openfoodfacts.org/api/v2/product/{code}.json",
                            params={"fields": "product_name,brands,quantity"})
        data = r.json()
    except Exception:
        return {"found": False, "barcode": code}
    p = data.get("product") or {}
    if data.get("status") != 1 or not p.get("product_name"):
        return {"found": False, "barcode": code}
    return {"found": True, "barcode": code, "name": p.get("product_name", ""),
            "brand": (p.get("brands") or "").split(",")[0].strip(), "size": p.get("quantity", "")}


# ---------------------------------------------------------------- deal engine
PRICE_RE = re.compile(r"\$\s?(\d{1,3}(?:\.\d{1,2})?)")
PCT_RE = re.compile(r"(\d{1,2})\s?%\s?off", re.I)


STORE_DOMAINS = {
    "Kroger": "kroger.com", "Walmart": "walmart.com", "Target": "target.com", "Aldi": "aldi.us",
    "H-E-B": "heb.com", "Tom Thumb": "tomthumb.com", "Sprouts": "sprouts.com",
}
PRODUCE_FALSE_STORES = re.compile(r"\b(brussels?|bean|alfalfa|broccoli|pea|radish|mung)\s+sprouts\b")


def _match_store(blob: str, stores: List[str], url: str = "") -> Optional[str]:
    """Attribute a result to a store: the page's own domain wins, else the store named earliest in the text."""
    host = re.sub(r"^https?://(www\.)?", "", url.lower()).split("/")[0]
    for s in stores:
        if host == STORE_DOMAINS[s] or host.endswith("." + STORE_DOMAINS[s]):
            return s
    text = PRODUCE_FALSE_STORES.sub(" ", blob)
    hits = []
    for s in stores:
        for a in STORE_ALIASES[s]:
            m = re.search(r"(?<![a-z])" + re.escape(a.strip()) + r"(?![a-z])", text)
            if m:
                hits.append((m.start(), s))
    return min(hits)[1] if hits else None


def _relevant(item: Item, blob: str) -> bool:
    words = [w for w in re.findall(r"[a-z]{3,}", f"{item.name} {item.brand}".lower())]
    return any(w in blob for w in words)


GENERIC_WORDS = {
    "large", "small", "medium", "jumbo", "whole", "ground", "boneless", "skinless", "fresh", "frozen", "organic",
    "classic", "original", "select", "family", "size", "pack", "value", "great", "general", "mills", "brand",
    "cereal", "laundry", "detergent", "roast", "count", "the", "and", "with", "free", "best", "natural",
}


def _terms(s: str, min_len: int) -> List[str]:
    return [w for w in re.findall(r"[a-z]+", s.lower().replace("'", "")) if len(w) >= min_len and w not in GENERIC_WORDS]


def _windows(item: Item, text: str) -> List[str]:
    """Short text windows where this exact product is named (all distinctive name words, or the brand)."""
    low = text.lower().replace("'", "")
    flat = text.replace("'", "")
    name_terms = _terms(item.name, 3)
    brand_terms = _terms(item.brand, 3)
    out = []
    # With a brand: window must name the brand AND the product (or a second brand word, e.g. "Tide Pods").
    # Without one: window must contain every distinctive word of the product name.
    anchor = brand_terms[0] if brand_terms else (name_terms[0] if name_terms else None)
    if not anchor:
        return out
    def has(t: str, s: str) -> bool:  # whole word, optional plural
        return re.search(r"\b" + re.escape(t) + r"s?\b", s) is not None

    # Highlights glue separate ad lines with "..." / newlines; never let a window cross into a neighbour line.
    seps = [s.end() for s in re.finditer(r"\.\.\.|…|\n|\s\|\s|•", low)]
    seps_start = [s.start() for s in re.finditer(r"\.\.\.|…|\n|\s\|\s|•", low)]

    for m in re.finditer(r"\b" + re.escape(anchor) + r"s?\b", low):
        seg_lo = max([e for e in seps if e <= m.start()], default=0)
        seg_hi = min([s for s in seps_start if s >= m.end()], default=len(low))
        start, end = max(seg_lo, m.start() - 25), min(seg_hi, m.end() + 80)
        # snap to word boundaries so snippets never start or end mid-word
        while start > seg_lo and not low[start - 1].isspace():
            start -= 1
        while end < seg_hi and not low[end].isspace():
            end += 1
        win_low = low[start:end]
        if brand_terms:
            ok = any(has(t, win_low) for t in name_terms + brand_terms[1:])
        else:
            ok = all(has(t, win_low) for t in name_terms)
        if ok:
            out.append(flat[start:end])
    return out


def _clean_snippet(s: str) -> str:
    s = re.sub(r"[#*_\[\]|>]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[^A-Za-z$]+", "", s)  # drop leading list numbers / punctuation
    m = re.search(r"[A-Z$]", s[:30])
    if s and s[0].islower() and m:
        s = s[m.start():]  # start at the first real phrase, not a dangling unit
    if len(s) > 200:
        s = s[:200].rsplit(" ", 1)[0] + "…"
    return s


def score_result(item: Item, text: str) -> Optional[dict]:
    """Return a deal dict if text describes a real deal (10%+ off, BOGO, coupon or cashback)."""
    windows = _windows(item, text)
    if not windows:
        return None
    usual = item.usual_price
    best = None
    for win in windows:
        wl = win.lower()
        promo = "sale"
        if re.search(r"\bbogo\b|\bb1g1\b|buy\s?(one|1)\s?,?\s?get\s?(one|1)", wl):
            promo = "bogo"
        elif "cash back" in wl or "cashback" in wl or "rebate" in wl or "ibotta" in wl:
            promo = "cashback"
        elif "coupon" in wl or "circle" in wl or "digital deal" in wl:
            promo = "coupon"
        prices = [float(p) for p in PRICE_RE.findall(win)]
        plausible = [p for p in prices if usual * 0.4 <= p <= usual * 0.95]
        sale = min(plausible) if plausible else None
        if sale is None:
            m = PCT_RE.search(win)
            if m and 10 <= int(m.group(1)) <= 60:
                sale = round(usual * (1 - int(m.group(1)) / 100), 2)
        if sale is None and promo == "bogo":
            sale = round(usual / 2, 2)
        if sale is None:
            continue
        pct = (usual - sale) / usual * 100
        if pct < 10 and promo == "sale":
            continue
        cand = {"sale_price": round(sale, 2), "savings": round(usual - sale, 2), "pct_off": round(pct, 1),
                "promo_type": promo, "snippet": _clean_snippet(win)}
        if not best or cand["savings"] > best["savings"]:
            best = cand
    return best


def _exa_search(query: str):
    since = (datetime.now(timezone.utc) - timedelta(days=21)).strftime("%Y-%m-%dT00:00:00.000Z")
    return exa.search(
        query, type="auto", num_results=8, start_published_date=since,
        contents={"highlights": {"query": "sale price, weekly ad price, BOGO, digital coupon, cash back, valid dates",
                                 "max_characters": 1500}},
    )


def _collect(item: Item, results, stores: List[str], best: dict, source_kind: str) -> None:
    """Score every highlight in a set of Exa results for one item; keep the best deal per store."""
    for r in results or []:
        url = getattr(r, "url", "") or ""
        if not url.startswith("http"):
            continue
        title = getattr(r, "title", "") or ""
        highlights = getattr(r, "highlights", None) or []
        for hl in highlights or [title]:
            blob = f" {url} {title} {hl} ".lower()
            store = _match_store(blob, stores, url)
            if not store or not _relevant(item, blob):
                continue
            scored = score_result(item, f"{title} {hl}")
            if not scored:
                continue
            if store not in best or scored["savings"] > best[store]["savings"]:
                snippet = scored.pop("snippet")
                best[store] = {**scored, "store": store, "promo_text": snippet, "source_kind": source_kind,
                               "source_url": url, "source_title": title[:140]}


async def search_item(item: Item, user: User) -> list:
    query = (f"{item.brand} {item.name} {item.size} sale price this week weekly ad digital coupon "
             f"at {', '.join(user.stores)} near {user.zip}").strip()
    resp = await asyncio.to_thread(_exa_search, query)
    return getattr(resp, "results", []) or []


def _exa_weekly_ad(store: str, zip_code: str, item_names: List[str]):
    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT00:00:00.000Z")
    return exa.search(
        f"{store} weekly ad this week sale prices and digital coupons near {zip_code}",
        type="auto", num_results=6, start_published_date=since,
        contents={"highlights": {"query": f"{store} weekly ad sale prices for: {', '.join(item_names)}",
                                 "max_characters": 3000}},
    )


async def search_weekly_ad(store: str, user: User, items: List[Item]) -> list:
    names = [f"{i.brand} {i.name}".strip() for i in items][:15]
    resp = await asyncio.to_thread(_exa_weekly_ad, store, user.zip, names)
    return getattr(resp, "results", []) or []


async def send_push(recipients: List[str], data: dict) -> None:
    if not recipients or PUSH_KEY == "placeholder":
        return
    resp = await push_client.post("/api/v1/push/trigger", json={"recipients": recipients, "data": data})
    if resp.status_code >= 400:
        logger.warning(f"Push not delivered ({resp.status_code}): {resp.text[:200]}")


async def run_check(user: User) -> dict:
    items = [Item.from_mongo(d) for d in await db.items.find({"user_id": user.user_id}).to_list(25)]
    if not user.stores or not items:
        return {"checked": 0, "found": 0, "new_alerts": 0}
    sem = asyncio.Semaphore(4)

    async def guarded(label: str, coro):
        async with sem:
            try:
                return await coro
            except Exception as e:
                logger.warning(f"Exa search failed for {label}: {e}")
                return None

    # One weekly-ad scan per store (scored against every item) + one targeted search per item.
    ad_results, item_results = await asyncio.gather(
        asyncio.gather(*(guarded(f"{s} weekly ad", search_weekly_ad(s, user, items)) for s in user.stores)),
        asyncio.gather(*(guarded(i.name, search_item(i, user)) for i in items)),
    )
    weekly_ok = [r for r in ad_results if r is not None]
    results = []
    for item, own in zip(items, item_results):
        if own is None and not weekly_ok:
            results.append((item, None, True))
            continue
        best: dict = {}
        for ads, store in zip(ad_results, user.stores):
            if ads:
                _collect(item, ads, [store], best, "weekly_ad")
        _collect(item, own or [], user.stores, best, "search")
        results.append((item, list(best.values()), own is None))

    # Sample deals are only a placeholder until the first real scan succeeds.
    if weekly_ok or any(own is not None for own in item_results):
        await db.deals.delete_many({"user_id": user.user_id, "is_sample": True})

    found, new_alerts = 0, []
    for item, deals, own_failed in results:
        if deals is None:
            continue  # keep previous deals when every search failed
        # If only this item's own search failed, keep its earlier search deals and refresh weekly-ad ones.
        scope = {"source_kind": "weekly_ad"} if own_failed else {}
        await db.deals.delete_many({"user_id": user.user_id, "item_id": item.id, "is_sample": False, **scope})
        for d in deals:
            deal = Deal(user_id=user.user_id, item_id=item.id, item_name=item.name, brand=item.brand,
                        size=item.size, usual_price=item.usual_price, **d)
            await db.deals.insert_one(deal.to_mongo())
            found += 1
            key = f"{item.id}:{d['store']}:{d['sale_price']}"
            if not await db.alerts.find_one({"user_id": user.user_id, "deal_key": key}):
                label = {"bogo": "is BOGO", "coupon": "has a coupon", "cashback": "has cash back"}.get(
                    d["promo_type"], f"is {round(d['pct_off'])}% off")
                alert = Alert(user_id=user.user_id, title=f"{item.name} {label} at {d['store']}",
                              message=f"${d['sale_price']:.2f} (usually ${item.usual_price:.2f}) — save ${d['savings']:.2f}",
                              deal_key=key)
                await db.alerts.insert_one(alert.to_mongo())
                new_alerts.append(alert)
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"last_checked_at": now_iso()}})
    if new_alerts:
        try:
            first = new_alerts[0]
            msg = first.message if len(new_alerts) == 1 else f"{len(new_alerts)} of your items are on sale this week"
            await send_push([user.user_id], {"title": first.title if len(new_alerts) == 1 else "New deals found",
                                             "message": msg, "action_url": "/"})
        except Exception as e:
            logger.warning(f"Push failed (non-blocking): {e}")
    return {"checked": len(items), "found": found, "new_alerts": len(new_alerts)}


@api.post("/deals/check")
async def check_deals(user: User = Depends(current_user)):
    if not user.onboarded:
        raise HTTPException(400, "Finish onboarding first")
    if user.is_demo and user.last_checked_at:
        if datetime.now(timezone.utc) - datetime.fromisoformat(user.last_checked_at) < timedelta(seconds=60):
            raise HTTPException(429, "Demo checks are limited to one per minute")
    return await run_check(user)


@api.get("/deals")
async def get_deals(user: User = Depends(current_user)):
    docs = await db.deals.find({"user_id": user.user_id}).sort("pct_off", -1).to_list(300)
    return [Deal.from_mongo(d).model_dump() for d in docs]


@api.get("/savings")
async def savings(user: User = Depends(current_user)):
    deals = [Deal.from_mongo(d) for d in await db.deals.find({"user_id": user.user_id}).to_list(300)]
    best: dict = {}
    for d in deals:
        if d.item_id not in best or d.savings > best[d.item_id].savings:
            best[d.item_id] = d
    by_store: dict = {}
    for d in best.values():
        s = by_store.setdefault(d.store, {"store": d.store, "savings": 0.0, "count": 0})
        s["savings"] = round(s["savings"] + d.savings, 2)
        s["count"] += 1
    item_count = await db.items.count_documents({"user_id": user.user_id})
    return {
        "total": round(sum(d.savings for d in best.values()), 2),
        "deal_count": len(best),
        "item_count": item_count,
        "by_store": sorted(by_store.values(), key=lambda x: -x["savings"]),
        "top": [d.model_dump() for d in sorted(best.values(), key=lambda x: -x.savings)[:5]],
        "last_checked_at": user.last_checked_at,
    }


@api.get("/alerts")
async def get_alerts(user: User = Depends(current_user)):
    docs = await db.alerts.find({"user_id": user.user_id}).sort("created_at", -1).to_list(50)
    return [Alert.from_mongo(d).model_dump() for d in docs]


@api.post("/alerts/read-all")
async def read_alerts(user: User = Depends(current_user)):
    await db.alerts.update_many({"user_id": user.user_id, "read": False}, {"$set": {"read": True}})
    return {"ok": True}


@api.post("/register-push", status_code=201)
async def register_push(body: RegisterPushBody, user: User = Depends(current_user)):
    if PUSH_KEY == "placeholder":
        return {"status": "skipped", "reason": "Push is enabled after the app is published"}
    payload = {"user_id": user.user_id, "platform": body.platform, "device_token": body.device_token}
    resp = await push_client.post("/api/v1/push/users/register", json=payload)
    if resp.status_code == 401:
        raise HTTPException(500, "EMERGENT_PUSH_KEY missing or invalid")
    if resp.status_code >= 500:
        raise HTTPException(502, "Push provider unavailable")
    return {"status": "registered"}


# ---------------------------------------------------------------- scheduler
scheduler = AsyncIOScheduler(timezone="America/Chicago")


async def daily_check():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    async for doc in db.users.find({"is_demo": True, "created_at": {"$lt": cutoff}}):
        for coll in (db.items, db.deals, db.alerts, db.users):
            await coll.delete_many({"user_id": doc["user_id"]})
    async for doc in db.users.find({"onboarded": True, "is_demo": {"$ne": True}}):
        user = User.from_mongo(doc)
        try:
            res = await run_check(user)
            logger.info(f"Daily check {user.user_id}: {res}")
        except Exception as e:
            logger.warning(f"Daily check failed for {user.user_id}: {e}")


@app.on_event("startup")
async def startup():
    await db.users.create_index("user_id", unique=True)
    await db.items.create_index("user_id")
    await db.deals.create_index([("user_id", 1), ("item_id", 1)])
    await db.alerts.create_index([("user_id", 1), ("deal_key", 1)])
    scheduler.add_job(daily_check, "cron", hour=8, minute=0, id="daily_check", replace_existing=True)
    scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)
    client.close()


app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=False, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
