"""Iteration 4 extra (testing agent): double restore 404, double delete 404, ads quality for each user store."""
import requests
import pytest

from test_promobeaux_api import BASE_URL


def _sess():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=20)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


# Undo: second restore and second delete -> 404; restored deals keep item linkage
def test_second_restore_404_and_deals_restored():
    s = _sess()
    deals = s.get(f"{BASE_URL}/api/deals").json()
    iid = deals[0]["item_id"]
    n = len([d for d in deals if d["item_id"] == iid])
    assert s.delete(f"{BASE_URL}/api/watchlist/{iid}").status_code == 200
    assert s.delete(f"{BASE_URL}/api/watchlist/{iid}").status_code == 404
    assert not [d for d in s.get(f"{BASE_URL}/api/deals").json() if d["item_id"] == iid]
    r = s.post(f"{BASE_URL}/api/watchlist/{iid}/restore")
    assert r.status_code == 200 and r.json()["id"] == iid
    assert len([d for d in s.get(f"{BASE_URL}/api/deals").json() if d["item_id"] == iid]) == n
    assert s.post(f"{BASE_URL}/api/watchlist/{iid}/restore").status_code == 404


# Trip with demo seed: on_deal rows first
def test_trip_on_deal_rows_first():
    s = _sess()
    t = s.get(f"{BASE_URL}/api/trip").json()
    flags = [r["on_deal"] for r in t["items"]]
    assert flags == sorted(flags, reverse=True)


@pytest.mark.parametrize("store", ["Walmart", "Target"])
def test_ads_other_stores(store):
    s = _sess()
    r = s.get(f"{BASE_URL}/api/ads/{store}", timeout=90)
    assert r.status_code == 200, r.text
    a = r.json()
    print(f"\n{store}: lines={len(a['lines'])} sources={[x['url'] for x in a['sources']]}")
    for ln in a["lines"][:8]:
        print("   ", ln["price"], ln["promo_type"], ln["text"][:100])
    assert a["store"] == store
