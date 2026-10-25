"""Debug helper: inspect live Exa weekly-ad results per store (not a pytest test)."""
import asyncio
import sys
import time

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from server import Item, User, search_weekly_ad, _collect  # noqa: E402

ITEMS = [Item(user_id="t", name=n, brand=b, size=s, usual_price=p) for n, b, s, p in [
    ("Large Eggs", "Eggland's Best", "12 ct", 4.79), ("Ground Coffee", "Folgers Classic Roast", "25.9 oz", 12.99),
    ("Boneless Chicken Breast", "Tyson", "2.5 lb", 11.49), ("Laundry Detergent Pacs", "Tide Pods", "42 ct", 13.99),
    ("Cheerios Cereal", "General Mills", "18 oz", 5.49), ("Whole Milk", "Horizon Organic", "half gallon", 5.99)]]


async def main():
    user = User(user_id="t", zip="75201", stores=["Sprouts", "Tom Thumb"], onboarded=True)
    for store in user.stores:
        t = time.time()
        res = await search_weekly_ad(store, user, ITEMS)
        print(f"== {store}: {len(res)} results in {time.time()-t:.1f}s")
        for r in res:
            hl = " || ".join(r.highlights or [])[:160].replace("\n", " ")
            print(f"   {r.url[:80]}\n      {hl}")
        for it in ITEMS:
            best = {}
            _collect(it, res, [store], best, "weekly_ad")
            for d in best.values():
                print(f"   MATCH {it.name}: ${d['sale_price']} {d['promo_type']} | {d['promo_text'][:100]}")

asyncio.run(main())
