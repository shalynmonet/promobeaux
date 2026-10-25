"""Iteration 4: watchlist undo-delete (trash/restore), best single-store trip, weekly ad browser."""
import os
import sys

import pytest
import requests

from test_promobeaux_api import BASE_URL

sys.path.insert(0, "/app/backend")
from server import _ad_lines  # noqa: E402


def _new_session():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=20)
    assert r.status_code == 200
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def s1():
    return _new_session()


@pytest.fixture(scope="module")
def s2():
    return _new_session()


# --- Undo delete ---
class TestUndoDelete:
    def test_delete_then_restore_keeps_id_and_deals(self):
        s = _new_session()
        deals = s.get(f"{BASE_URL}/api/deals").json()
        assert deals, "demo should have sample deals"
        item_id = deals[0]["item_id"]
        item_deals = sorted(d["id"] for d in deals if d["item_id"] == item_id)
        wl_before = s.get(f"{BASE_URL}/api/watchlist").json()
        item = next(i for i in wl_before if i["id"] == item_id)

        r = s.delete(f"{BASE_URL}/api/watchlist/{item_id}")
        assert r.status_code == 200 and r.json() == {"ok": True}
        assert item_id not in [i["id"] for i in s.get(f"{BASE_URL}/api/watchlist").json()]
        assert not [d for d in s.get(f"{BASE_URL}/api/deals").json() if d["item_id"] == item_id]

        r = s.post(f"{BASE_URL}/api/watchlist/{item_id}/restore")
        assert r.status_code == 200, r.text
        restored = r.json()
        assert restored["id"] == item_id
        assert restored["name"] == item["name"] and restored["usual_price"] == item["usual_price"]
        assert "_id" not in restored
        wl_after = s.get(f"{BASE_URL}/api/watchlist").json()
        assert item_id in [i["id"] for i in wl_after] and len(wl_after) == len(wl_before)
        assert sorted(d["id"] for d in s.get(f"{BASE_URL}/api/deals").json() if d["item_id"] == item_id) == item_deals

        # second restore -> 404
        assert s.post(f"{BASE_URL}/api/watchlist/{item_id}/restore").status_code == 404

    def test_restore_other_users_item_404(self, s1, s2):
        item_id = s1.get(f"{BASE_URL}/api/watchlist").json()[-1]["id"]
        assert s1.delete(f"{BASE_URL}/api/watchlist/{item_id}").status_code == 200
        assert s2.post(f"{BASE_URL}/api/watchlist/{item_id}/restore").status_code == 404
        # owner still can
        assert s1.post(f"{BASE_URL}/api/watchlist/{item_id}/restore").status_code == 200

    def test_restore_invalid_and_unauth(self, s1):
        assert s1.post(f"{BASE_URL}/api/watchlist/notanid/restore").status_code == 404
        assert s1.post(f"{BASE_URL}/api/watchlist/{'0' * 24}/restore").status_code == 404
        assert requests.post(f"{BASE_URL}/api/watchlist/{'0' * 24}/restore").status_code in (401, 403)

    def test_restore_after_readd_does_not_duplicate(self):
        s = _new_session()
        item_id = s.get(f"{BASE_URL}/api/watchlist").json()[0]["id"]
        s.delete(f"{BASE_URL}/api/watchlist/{item_id}")
        s.post(f"{BASE_URL}/api/watchlist/{item_id}/restore")
        ids = [i["id"] for i in s.get(f"{BASE_URL}/api/watchlist").json()]
        assert ids.count(item_id) == 1


# --- Best store trip ---
class TestTrip:
    def test_trip_shape_and_math(self, s2):
        t = s2.get(f"{BASE_URL}/api/trip")
        assert t.status_code == 200
        t = t.json()
        for k in ("store", "savings", "estimated_total", "items", "alternatives"):
            assert k in t
        wl = s2.get(f"{BASE_URL}/api/watchlist").json()
        deals = s2.get(f"{BASE_URL}/api/deals").json()
        # expected per-store totals of best deal per item
        best = {}
        for d in deals:
            k = (d["store"], d["item_id"])
            if k not in best or d["savings"] > best[k]["savings"]:
                best[k] = d
        totals = {}
        for (st, _), d in best.items():
            totals[st] = round(totals.get(st, 0) + d["savings"], 2)
        assert t["store"] is not None
        assert abs(t["savings"] - max(totals.values())) < 0.01
        assert abs(t["savings"] - totals[t["store"]]) < 0.01
        assert len(t["items"]) == len(wl)
        assert {r["item_id"] for r in t["items"]} == {i["id"] for i in wl}
        for r in t["items"]:
            for k in ("item_id", "name", "price", "usual_price", "savings", "on_deal", "promo_type"):
                assert k in r
            if not r["on_deal"]:
                assert r["price"] == r["usual_price"] and r["savings"] == 0
            else:
                assert (t["store"], r["item_id"]) in best
        assert abs(t["estimated_total"] - round(sum(r["price"] for r in t["items"]), 2)) < 0.01
        assert {a["store"] for a in t["alternatives"]} == set(totals) - {t["store"]}

    def test_trip_empty_deals_store_null(self):
        s = _new_session()
        for d in {d["item_id"] for d in s.get(f"{BASE_URL}/api/deals").json()}:
            s.delete(f"{BASE_URL}/api/watchlist/{d}")
        t = s.get(f"{BASE_URL}/api/trip").json()
        assert t["store"] is None and t["savings"] == 0 and t["items"] == [] and t["alternatives"] == []

    def test_trip_unauth(self):
        assert requests.get(f"{BASE_URL}/api/trip").status_code in (401, 403)


# --- Weekly ad browser ---
class TestAds:
    def test_unknown_store_404(self, s1):
        assert s1.get(f"{BASE_URL}/api/ads/NotAStore").status_code == 404

    def test_ads_shape_and_cache(self, s1, s2):
        r = s1.get(f"{BASE_URL}/api/ads/Kroger", timeout=90)
        assert r.status_code == 200, r.text
        a = r.json()
        for k in ("store", "zip", "retrieved_at", "lines", "sources"):
            assert k in a
        assert a["store"] == "Kroger" and a["zip"] == "75201" and "_id" not in a
        print(f"Kroger ad lines={len(a['lines'])} sources={len(a['sources'])}")
        for ln in a["lines"]:
            assert set(ln) >= {"text", "price", "promo_type", "source_url"}
            assert ln["source_url"].startswith("http")
        # demo user always gets cache (same retrieved_at), even with refresh
        b = s2.get(f"{BASE_URL}/api/ads/Kroger?refresh=true", timeout=90).json()
        assert b["retrieved_at"] == a["retrieved_at"]

    def test_ads_unauth(self):
        assert requests.get(f"{BASE_URL}/api/ads/Kroger").status_code in (401, 403)


# --- ad line parser unit ---
class TestAdLines:
    def test_parser(self):
        out = _ad_lines("Cheerios Cereal 18 oz $2.99 ... Tyson Chicken BOGO $9.99\n## short $1")
        assert any("Cheerios" in x for x in out)
        assert any("Tyson" in x for x in out)
        assert all(len(x) >= 12 for x in out)
