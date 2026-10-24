"""Live check (Exa): live deals for an item replace that item's sample deals; savings uses best-deal-per-item."""
import time

import requests

from test_promobeaux_api import BASE_URL


def test_live_replaces_samples_and_best_per_item():
    s = requests.Session()
    s.headers.update({"Authorization": "Bearer " + requests.post(f"{BASE_URL}/api/auth/demo", timeout=20).json()["token"]})
    t = time.time()
    r = s.post(f"{BASE_URL}/api/deals/check", timeout=180)
    print(f"\ncheck {time.time()-t:.1f}s -> {r.json()}")
    assert r.status_code == 200
    deals = s.get(f"{BASE_URL}/api/deals").json()
    by_item = {}
    for d in deals:
        by_item.setdefault(d["item_id"], []).append(d)
        print(f"  [{'S' if d['is_sample'] else 'L'}] {d['item_name']} @{d['store']} ${d['sale_price']} ({d['promo_type']}, {d['pct_off']}%) :: {d['promo_text'][:160]} | {d.get('source_url')}")
    for iid, ds in by_item.items():
        live = [d for d in ds if not d["is_sample"]]
        if live:
            assert not any(d["is_sample"] for d in ds), f"sample not replaced for {ds[0]['item_name']}"
    sv = s.get(f"{BASE_URL}/api/savings").json()
    expected = round(sum(max(d["savings"] for d in ds) for ds in by_item.values()), 2)
    assert abs(sv["total"] - expected) < 0.02 and sv["deal_count"] == len(by_item)
    # second check is idempotent for alerts (no duplicate alert for same deal key)
    r2 = s.post(f"{BASE_URL}/api/deals/check", timeout=180).json()
    print(f"second check -> {r2}")
    keys = [a["deal_key"] for a in s.get(f"{BASE_URL}/api/alerts").json()]
    assert len(keys) == len(set(keys))
