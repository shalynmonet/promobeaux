import asyncio
import base64
import logging
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, List, Optional
from zoneinfo import ZoneInfo

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
    image_url: Optional[str] = None  # product photo from Open Food Facts, when one matches
    image_checked: bool = False
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
    ends_at: Optional[str] = None  # YYYY-MM-DD, last day the deal is valid (store-local)
    ends_estimated: bool = False  # True when inferred from the store's usual weekly-ad cycle
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
    stores: List[str] = Field(min_length=1, max_length=len(STORES))


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
    # name: (store, sale price, promo, text, days until the deal ends)
    "Large Eggs": ("Kroger", 3.49, "sale", "Digital deal: Eggland's Best Large Eggs 12 ct $3.49 with Card", 3),
    "Ground Coffee": ("Target", 9.99, "coupon", "Save $3 with Target Circle on Folgers 25.9 oz canisters", 5),
    "Cheerios Cereal": ("Walmart", 2.75, "bogo", "Buy 1 Get 1 Free on select General Mills cereals", 1),
    "Laundry Detergent Pacs": ("Kroger", 11.99, "cashback", "$2 cash back on Tide Pods 42 ct via digital rebate", 6),
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
            store, sale, ptype, text, days_left = DEMO_DEALS[name]
            savings = round(price - sale, 2)
            await db.deals.insert_one(Deal(
                user_id=uid, item_id=str(res.inserted_id), item_name=name, brand=brand, size=size,
                store=store, usual_price=price, sale_price=sale, savings=savings,
                pct_off=round(savings / price * 100, 1), promo_type=ptype, promo_text=text, is_sample=True,
                ends_at=(local_today() + timedelta(days=days_left)).isoformat(),
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
    body.stores = list(dict.fromkeys(body.stores))  # drop duplicates, keep order
    bad = [s for s in body.stores if s not in STORES]
    if bad:
        raise HTTPException(400, f"Unknown stores: {bad}")
    await db.users.update_one({"user_id": user.user_id},
                              {"$set": {"zip": body.zip, "stores": body.stores, "onboarded": True}})
    await db.deals.delete_many({"user_id": user.user_id, "store": {"$nin": body.stores}})
    await db.reminders.delete_many({"user_id": user.user_id, "store": {"$nin": body.stores}})
    doc = await db.users.find_one({"user_id": user.user_id})
    return User.from_mongo(doc).model_dump()


# ---------------------------------------------------------------- watchlist
@api.get("/watchlist")
async def get_watchlist(user: User = Depends(current_user)):
    docs = await db.items.find({"user_id": user.user_id}).sort("created_at", -1).to_list(200)
    if any(not d.get("image_checked") for d in docs):
        schedule_image_fill(user.user_id)
    return [Item.from_mongo(d).model_dump() for d in docs]


@api.post("/watchlist")
async def add_item(body: ItemIn, user: User = Depends(current_user)):
    item = Item(user_id=user.user_id, **body.model_dump())
    res = await db.items.insert_one(item.to_mongo())
    item.id = str(res.inserted_id)
    schedule_image_fill(user.user_id)
    return item.model_dump()


def _oid(item_id: str) -> ObjectId:
    if not ObjectId.is_valid(item_id):
        raise HTTPException(404, "Item not found")
    return ObjectId(item_id)


@api.put("/watchlist/{item_id}")
async def update_item(item_id: str, body: ItemIn, user: User = Depends(current_user)):
    res = await db.items.update_one({"_id": _oid(item_id), "user_id": user.user_id},
                                    {"$set": {**body.model_dump(), "image_url": None, "image_checked": False, "image_attempts": 0}})
    if not res.matched_count:
        raise HTTPException(404, "Item not found")
    schedule_image_fill(user.user_id)
    return Item.from_mongo(await db.items.find_one({"_id": _oid(item_id)})).model_dump()


@api.delete("/watchlist/{item_id}")
async def delete_item(item_id: str, user: User = Depends(current_user)):
    item = await db.items.find_one({"_id": _oid(item_id), "user_id": user.user_id})
    if not item:
        raise HTTPException(404, "Item not found")
    deals = await db.deals.find({"user_id": user.user_id, "item_id": item_id}).to_list(100)
    # Keep a restorable copy so the app can offer "Undo".
    await db.trash.replace_one({"_id": item["_id"]},
                               {"_id": item["_id"], "user_id": user.user_id, "item": item, "deals": deals,
                                "deleted_at": now_iso()}, upsert=True)
    await db.items.delete_one({"_id": item["_id"]})
    await db.deals.delete_many({"user_id": user.user_id, "item_id": item_id})
    await db.reminders.delete_many({"user_id": user.user_id, "item_id": item_id})
    return {"ok": True}


@api.post("/watchlist/{item_id}/restore")
async def restore_item(item_id: str, user: User = Depends(current_user)):
    doc = await db.trash.find_one({"_id": _oid(item_id), "user_id": user.user_id})
    if not doc:
        raise HTTPException(404, "Nothing to restore")
    await db.items.replace_one({"_id": doc["item"]["_id"]}, doc["item"], upsert=True)
    # Don't resurrect sample deals after a real scan, or deals from stores the user has since removed.
    keep = [d for d in doc["deals"]
            if d.get("store") in user.stores and not (d.get("is_sample") and user.last_checked_at)]
    if keep:
        await db.deals.insert_many(keep)
    await db.trash.delete_one({"_id": doc["_id"]})
    return Item.from_mongo(doc["item"]).model_dump()


# ---------------------------------------------------------------- product photos (Open Food Facts, no key)
_image_jobs: set = set()


class PhotoServiceBusy(Exception):
    """Open Food Facts is rate limiting / down — try again later instead of saving 'no photo'."""


def _photo_key(item: Item) -> str:
    return item.barcode or re.sub(r"\s+", " ", f"{item.brand} {item.name}".lower()).strip()


async def _off_get(c: httpx.AsyncClient, url: str, params: dict) -> dict:
    r = await c.get(url, params=params)
    if r.status_code == 429 or r.status_code >= 500:
        raise PhotoServiceBusy(f"HTTP {r.status_code}")
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json() or {}


async def lookup_product_image(item: Item) -> Optional[str]:
    async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "Promobeaux/1.0"}) as c:
        if item.barcode:
            data = await _off_get(c, f"https://world.openfoodfacts.org/api/v2/product/{item.barcode}.json",
                                  {"fields": "image_front_small_url"})
            url = (data.get("product") or {}).get("image_front_small_url")
            if url:
                return url
        data = await _off_get(c, "https://world.openfoodfacts.org/cgi/search.pl", {
            "search_terms": f"{item.brand} {item.name}".strip(), "search_simple": 1, "action": "process",
            "json": 1, "page_size": 8, "fields": "product_name,brands,image_front_small_url"})
        r_products = data.get("products", [])
        terms = _terms(item.name, 3) + _terms(item.brand, 3)[:1]
        for p in r_products:
            url, text = p.get("image_front_small_url"), f"{p.get('product_name', '')} {p.get('brands', '')}".lower()
            # Only accept a photo whose name shares a distinctive word with the item (avoids random products).
            if url and terms and any(re.search(r"\b" + re.escape(t), text) for t in terms):
                return url
    return None


async def fill_images(user_id: str) -> None:
    try:
        docs = await db.items.find({"user_id": user_id, "image_checked": {"$ne": True}}).to_list(15)
        for i, d in enumerate(docs):
            item = Item.from_mongo(d)
            key = _photo_key(item)
            cached = await db.photo_cache.find_one({"_id": key})  # shared across users
            if cached and not cached.get("url") and cached.get("at", "") < (datetime.now(timezone.utc) - timedelta(days=7)).isoformat():
                cached = None  # "no photo" answers expire after a week so new database entries get picked up
            if cached:
                url = cached.get("url")
            else:
                if i:
                    await asyncio.sleep(1.5)  # be gentle with the free photo service
                try:
                    url = await lookup_product_image(item)
                    await db.photo_cache.update_one({"_id": key}, {"$set": {"url": url, "at": now_iso()}}, upsert=True)
                except (PhotoServiceBusy, httpx.TimeoutException, httpx.TransportError) as e:
                    attempts = d.get("image_attempts", 0) + 1
                    logger.info(f"Photo service busy for {item.name} ({e}), attempt {attempts}")
                    if attempts < 4:  # leave unchecked so a later visit retries
                        await db.items.update_one({"_id": d["_id"]}, {"$set": {"image_attempts": attempts}})
                        await asyncio.sleep(5 * attempts)
                        continue
                    url = None
                except Exception as e:
                    logger.info(f"Image lookup failed for {item.name}: {e}")
                    url = None  # treat as "no photo" so the app stops waiting; editing the item retries
            await db.items.update_one({"_id": d["_id"]}, {"$set": {"image_url": url, "image_checked": True}})
    finally:
        _image_jobs.discard(user_id)


def schedule_image_fill(user_id: str) -> None:
    """Look up missing product photos in the background (one job per user at a time)."""
    if user_id not in _image_jobs:
        _image_jobs.add(user_id)
        asyncio.create_task(fill_images(user_id))


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


# ---------------------------------------------------------------- deal expiry
LOCAL_TZ = ZoneInfo("America/Chicago")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MON = (r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
       r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?(?![a-z])")
RANGE_WORDS = r"(?:-|–|—|to|thru|through|until)"
NOT_SIZE = r"(?!\s*(?:oz|fl|ct|lb|lbs|pk|pack|count|g\b|kg|ml|l\b|jars?|cans?|bottles?|rolls?|pcs?|pieces?|qt|gal))"
R_RANGE_TEXT = re.compile(rf"{MON}\s*(\d{{1,2}})(?:st|nd|rd|th)?,?\s*{RANGE_WORDS}\s*(?:{MON}\s*)?(\d{{1,2}})\b{NOT_SIZE}", re.I)
R_END_TEXT = re.compile(rf"\b(?:valid|good|ends?|expires?|thru|through|until|till)\s*(?:on\s*|thru\s*|through\s*)?{MON}\s*(\d{{1,2}})\b{NOT_SIZE}", re.I)
R_RANGE_NUM = re.compile(rf"(?<![\d.$/])(\d{{1,2}})/(\d{{1,2}})(?:/\d{{2,4}})?\s*(?:-|–|to|thru|through)\s*(\d{{1,2}})/(\d{{1,2}})(?![\d.]){NOT_SIZE}")
R_END_NUM = re.compile(rf"\b(?:valid|good|ends?|expires?|exp\.?|thru|through|until|till)\s*(?:on\s*)?(\d{{1,2}})/(\d{{1,2}})(?![\d.]){NOT_SIZE}", re.I)
R_SLUG = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*-(\d{1,2})-(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*-)?(\d{1,2})(?!\d)", re.I)
# Day (Mon=0) each store's weekly ad usually ends. Walmart has no fixed ad week, so no estimate there.
STORE_AD_END_WEEKDAY = {"Kroger": 1, "Aldi": 1, "H-E-B": 1, "Tom Thumb": 1, "Sprouts": 1, "Target": 5}


def local_today() -> date:
    return datetime.now(LOCAL_TZ).date()


def _resolve(month: str, day: str, today: date) -> Optional[date]:
    try:
        d = date(today.year, MONTHS[month.lower()[:3]], int(day))
    except (ValueError, KeyError):
        return None
    if (d - today).days < -180:
        d = d.replace(year=d.year + 1)
    elif (d - today).days > 180:
        d = d.replace(year=d.year - 1)
    return d


def _resolve_num(month: str, day: str, today: date) -> Optional[date]:
    m = int(month)
    return _resolve(list(MONTHS)[m - 1], day, today) if 1 <= m <= 12 else None


def parse_end_date(text: str, url: str, today: date) -> Optional[date]:
    """Last valid day of a deal if the ad text or its URL says so (e.g. 'Oct 21 - Oct 27', 'valid thru 10/28')."""
    ranges: List[Optional[date]] = []
    singles: List[Optional[date]] = []
    for m in R_RANGE_TEXT.finditer(text):
        m1, _, m2, d2 = m.groups()
        ranges.append(_resolve(m2 or m1, d2, today))
    for m in R_RANGE_NUM.finditer(text):
        ranges.append(_resolve_num(m.group(3), m.group(4), today))
    for m in R_SLUG.finditer(url.lower()):
        m1, _, m2, d2 = m.groups()
        ranges.append(_resolve(m2 or m1, d2, today))
    for m in R_END_TEXT.finditer(text):
        singles.append(_resolve(m.group(1), m.group(2), today))
    for m in R_END_NUM.finditer(text):
        singles.append(_resolve_num(m.group(1), m.group(2), today))

    def ok(c):  # ended within the last month (stale ads count as expired) or ending within ~6 weeks
        return c and -30 <= (c - today).days <= 45

    ranges, singles = [c for c in ranges if ok(c)], [c for c in singles if ok(c)]
    # Prefer the ad-week range that's still running (latest end within a week), e.g. the Oct 21-27 ad week
    # over a weekend-only promo on the same page; else an explicit "valid thru"; else whatever we found.
    current = [c for c in ranges if 0 <= (c - today).days <= 7]
    if current:
        return max(current)
    if singles:
        return singles[0]
    return ranges[0] if ranges else None


def deal_end(store: str, url: str, text: str) -> tuple:
    """(ends_at ISO or None, estimated?, already expired?)"""
    today = local_today()
    end = parse_end_date(text, url, today)
    if end:
        return end.isoformat(), False, end < today
    wd = STORE_AD_END_WEEKDAY.get(store)
    if wd is None:
        return None, False, False
    return (today + timedelta(days=(wd - today.weekday()) % 7)).isoformat(), True, False


def active_q(user_id: str) -> dict:
    """Mongo filter for a user's deals that haven't ended yet."""
    return {"user_id": user_id, "$or": [{"ends_at": None}, {"ends_at": {"$gte": local_today().isoformat()}}]}


def _collect(item: Item, results, stores: List[str], best: dict, source_kind: str) -> None:
    """Score every highlight in a set of Exa results for one item; keep the best deal per store."""
    for r in results or []:
        url = getattr(r, "url", "") or ""
        if not url.startswith("http") or _foreign(url):
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
                ends_at, estimated, expired = deal_end(store, url, f"{title} {hl}")
                if expired:
                    continue  # the ad says this deal is already over
                snippet = scored.pop("snippet")
                best[store] = {**scored, "store": store, "promo_text": snippet, "source_kind": source_kind,
                               "source_url": url, "source_title": title[:140],
                               "ends_at": ends_at, "ends_estimated": estimated}


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
    expiring = await run_expiry_reminders(user)
    return {"checked": len(items), "found": found, "new_alerts": len(new_alerts) + expiring}


class ReminderIn(BaseModel):
    item_id: str
    store: str


async def run_expiry_reminders(user: User) -> int:
    """Alert once when a deal the shopper asked to be reminded about ends today or tomorrow."""
    today = local_today()
    sent: List[Alert] = []
    async for r in db.reminders.find({"user_id": user.user_id}):
        doc = await db.deals.find_one({**active_q(user.user_id), "item_id": r["item_id"], "store": r["store"]},
                                      sort=[("savings", -1)])
        if not doc or not doc.get("ends_at"):
            continue
        deal = Deal.from_mongo(doc)
        left = (date.fromisoformat(deal.ends_at) - today).days
        if left > 1:
            continue
        key = f"expiry:{deal.item_id}:{deal.store}:{deal.ends_at}"
        if await db.alerts.find_one({"user_id": user.user_id, "deal_key": key}):
            continue
        when = "today" if left <= 0 else "tomorrow"
        alert = Alert(
            user_id=user.user_id, deal_key=key,
            title=f"{deal.item_name} deal {'likely ' if deal.ends_estimated else ''}ends {when} at {deal.store}",
            message=f"${deal.sale_price:.2f} (usually ${deal.usual_price:.2f}) — grab it before it's gone",
        )
        await db.alerts.insert_one(alert.to_mongo())
        sent.append(alert)
    if sent:
        try:
            title = sent[0].title if len(sent) == 1 else f"{len(sent)} of your deals end soon"
            await send_push([user.user_id], {"title": title, "message": sent[0].message, "action_url": "/"})
        except Exception as e:
            logger.warning(f"Push failed (non-blocking): {e}")
    return len(sent)


@api.post("/reminders")
async def toggle_reminder(body: ReminderIn, user: User = Depends(current_user)):
    if not await db.items.find_one({"_id": _oid(body.item_id), "user_id": user.user_id}):
        raise HTTPException(404, "Item not found")
    if body.store not in STORES:
        raise HTTPException(400, "Unknown store")
    q = {"user_id": user.user_id, "item_id": body.item_id, "store": body.store}
    if await db.reminders.find_one(q):
        await db.reminders.delete_one(q)
        return {"remind": False, "sent": 0}
    await db.reminders.insert_one({**q, "created_at": now_iso()})
    return {"remind": True, "sent": await run_expiry_reminders(user)}


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
    docs = await db.deals.find(active_q(user.user_id)).sort("pct_off", -1).to_list(300)
    reminders = {(r["item_id"], r["store"]) async for r in db.reminders.find({"user_id": user.user_id})}
    items = {str(i["_id"]): i async for i in db.items.find({"user_id": user.user_id}, {"image_url": 1, "image_checked": 1})}
    if any(not i.get("image_checked") for i in items.values()):
        schedule_image_fill(user.user_id)
    today = local_today()
    out = []
    for d in docs:
        deal = Deal.from_mongo(d)
        # days_left is computed in store-local time so the app and alerts always agree on "today"/"tomorrow".
        left = (date.fromisoformat(deal.ends_at) - today).days if deal.ends_at else None
        item_doc = items.get(deal.item_id) or {}
        out.append({**deal.model_dump(), "remind": (deal.item_id, deal.store) in reminders, "days_left": left,
                    "image_url": item_doc.get("image_url"),
                    "image_pending": bool(item_doc) and not item_doc.get("image_checked")})
    return out


@api.get("/savings")
async def savings(user: User = Depends(current_user)):
    deals = [Deal.from_mongo(d) for d in await db.deals.find(active_q(user.user_id)).to_list(300)]
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


# ---------------------------------------------------------------- best store trip
@api.get("/trip")
async def best_store_trip(user: User = Depends(current_user)):
    """Pick the one store that saves the most on the watchlist this week and build its shopping list."""
    items = [Item.from_mongo(d) for d in await db.items.find({"user_id": user.user_id}).to_list(200)]
    deals = [Deal.from_mongo(d) for d in await db.deals.find(
        {**active_q(user.user_id), "store": {"$in": user.stores}}).to_list(500)]
    best_at: dict = {}  # (store, item_id) -> best deal
    for d in deals:
        k = (d.store, d.item_id)
        if k not in best_at or d.savings > best_at[k].savings:
            best_at[k] = d
    totals: dict = {}
    for (store, _), d in best_at.items():
        totals[store] = round(totals.get(store, 0) + d.savings, 2)
    if not totals:
        return {"store": None, "savings": 0, "estimated_total": round(sum(i.usual_price for i in items), 2),
                "items": [], "alternatives": []}
    store = max(totals, key=lambda s: (totals[s], -user.stores.index(s) if s in user.stores else 0))
    rows = []
    for i in items:
        d = best_at.get((store, i.id))
        rows.append({
            "item_id": i.id, "name": i.name, "brand": i.brand, "size": i.size, "usual_price": i.usual_price,
            "price": d.sale_price if d else i.usual_price, "savings": d.savings if d else 0,
            "promo_type": d.promo_type if d else None, "on_deal": bool(d),
        })
    rows.sort(key=lambda r: (not r["on_deal"], -r["savings"], r["name"]))
    return {
        "store": store, "savings": totals[store],
        "estimated_total": round(sum(r["price"] for r in rows), 2),
        "items": rows,
        "alternatives": sorted(({"store": s, "savings": v} for s, v in totals.items() if s != store),
                               key=lambda x: -x["savings"]),
    }


# ---------------------------------------------------------------- weekly ad browser
AD_LINE_SPLIT = re.compile(r"\.\.\.|…|\n|\s\|\s|•|\s-\s(?=[A-Z])")
FOREIGN_HOST = re.compile(r"\.(mx|ca|uk|au|es|ar|cl|br|in|de|fr|it|nz|ie|pe|ve|gt|cr|pr)$")
SPANISH_HINT = re.compile(r"\b(la pieza|el kilo|por kilo|kilogramo|pesos|precio|ofertas?|oferta de|frutas|verduras)\b", re.I)
HEADLINE_HINT = re.compile(
    r"^(save|get|earn|shop|deals?|this week|weekly|top|best|hot|new)\b|and more|\bwyb\b|participating|prices listed|"
    r"valid (thru|through|from)|while supplies|limit \d|see store|terms apply", re.I)


def _foreign(url: str) -> bool:
    """True for non-US sources (e.g. walmart.com.mx coverage on .mx news sites)."""
    host = re.sub(r"^https?://", "", url.lower()).split("/")[0].split(":")[0]
    return bool(FOREIGN_HOST.search(host)) or "/es-mx/" in url.lower() or "/es/" in url.lower()


def _ad_lines(text: str) -> List[str]:
    out = []
    for raw in AD_LINE_SPLIT.split(text):
        line = re.sub(r"[#*_\[\]>]+", " ", raw)
        line = re.sub(r"\s+", " ", line).strip(" -–:;,.")
        if not (12 <= len(line) <= 160 and PRICE_RE.search(line) and re.search(r"[A-Za-z]{3,}", line)):
            continue
        if SPANISH_HINT.search(line) or HEADLINE_HINT.search(line):
            continue
        out.append(line)
    return out


def _exa_ad_browse(store: str, zip_code: str):
    since = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%dT00:00:00.000Z")
    return exa.search(
        f"{store} weekly ad this week grocery sale prices near {zip_code}",
        type="auto", num_results=6, start_published_date=since,
        contents={"highlights": {"query": f"{store} weekly ad grocery items with sale prices, BOGO and digital coupons",
                                 "max_characters": 4000}},
    )


@api.get("/ads/{store}")
async def weekly_ad(store: str, refresh: bool = False, user: User = Depends(current_user)):
    if store not in STORES:
        raise HTTPException(404, "Unknown store")
    zip_code = user.zip or "75201"
    key = f"{store}|{zip_code}"
    cached = await db.ad_cache.find_one({"_id": key})
    fresh_cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    demo_cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    # Demo shoppers reuse a cached ad for 24h (keeps paid searches down); others refresh after 6h or on pull-to-refresh.
    use_cache = cached and (
        (user.is_demo and cached["retrieved_at"] > demo_cutoff)
        or (not refresh and cached["retrieved_at"] > fresh_cutoff)
    )
    if use_cache:
        return {k: v for k, v in cached.items() if k != "_id"}
    try:
        resp = await asyncio.to_thread(_exa_ad_browse, store, zip_code)
    except Exception as e:
        logger.warning(f"Ad browse failed for {store}: {e}")
        if cached:
            return {k: v for k, v in cached.items() if k != "_id"}
        raise HTTPException(502, "Couldn't load this store's weekly ad right now")
    seen, lines, sources = set(), [], []
    for r in getattr(resp, "results", []) or []:
        url, title = getattr(r, "url", "") or "", getattr(r, "title", "") or ""
        if not url.startswith("http") or _foreign(url):
            continue
        blob = f" {url} {title} ".lower()
        if _match_store(blob + " " + " ".join(getattr(r, "highlights", None) or []).lower(), [store], url) != store:
            continue
        added = 0
        for hl in getattr(r, "highlights", None) or []:
            for line in _ad_lines(hl):
                norm = re.sub(r"[^a-z0-9$.]", "", line.lower())
                if norm in seen:
                    continue
                seen.add(norm)
                price = PRICE_RE.search(line)
                promo = "bogo" if re.search(r"\bbogo\b|\bb1g1\b|buy\s?(one|1)\s?,?\s?get", line.lower()) else (
                    "coupon" if "coupon" in line.lower() else None)
                lines.append({"text": line, "price": float(price.group(1)) if price else None,
                              "promo_type": promo, "source_url": url})
                added += 1
        if added:
            sources.append({"title": title[:120], "url": url})
    doc = {"store": store, "zip": zip_code, "retrieved_at": now_iso(), "lines": lines[:80], "sources": sources}
    if lines:  # never cache an empty ad, so the next visit tries again
        await db.ad_cache.replace_one({"_id": key}, {"_id": key, **doc}, upsert=True)
    else:
        await db.ad_cache.delete_one({"_id": key})
    return doc


# ---------------------------------------------------------------- scheduler
scheduler = AsyncIOScheduler(timezone="America/Chicago")


async def daily_check():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    await db.trash.delete_many({"deleted_at": {"$lt": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()}})
    async for doc in db.users.find({"is_demo": True, "created_at": {"$lt": cutoff}}):
        for coll in (db.items, db.deals, db.alerts, db.reminders, db.users):
            await coll.delete_many({"user_id": doc["user_id"]})
    async for doc in db.users.find({"onboarded": True, "is_demo": {"$ne": True}}):
        user = User.from_mongo(doc)
        try:
            res = await run_check(user)
            logger.info(f"Daily check {user.user_id}: {res}")
        except Exception as e:
            logger.warning(f"Daily check failed for {user.user_id}: {e}")


async def expiry_reminders_job():
    # Only shoppers who actually set a reminder need checking.
    for uid in await db.reminders.distinct("user_id"):
        doc = await db.users.find_one({"user_id": uid, "onboarded": True})
        if not doc:
            continue
        try:
            await run_expiry_reminders(User.from_mongo(doc))
        except Exception as e:
            logger.warning(f"Expiry reminders failed for {uid}: {e}")


@app.on_event("startup")
async def startup():
    await db.users.create_index("user_id", unique=True)
    await db.items.create_index("user_id")
    await db.deals.create_index([("user_id", 1), ("item_id", 1)])
    await db.alerts.create_index([("user_id", 1), ("deal_key", 1)])
    await db.reminders.create_index([("user_id", 1), ("item_id", 1), ("store", 1)], unique=True)
    scheduler.add_job(daily_check, "cron", hour=8, minute=0, id="daily_check", replace_existing=True)
    # Runs after the morning scan, and again in the evening for deals ending tomorrow.
    scheduler.add_job(expiry_reminders_job, "cron", hour="9,18", minute=0, id="expiry_reminders", replace_existing=True)
    scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)
    client.close()


app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=False, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
