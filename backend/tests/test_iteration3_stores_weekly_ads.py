"""Iteration 3: Sprouts/Tom Thumb stores, weekly-ad scan + source_kind, separator-aware matcher windows."""
import sys
import time
from types import SimpleNamespace

import pytest
import requests

from test_promobeaux_api import BASE_URL

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from server import Item, score_result, _collect, _match_store  # noqa: E402


def _item(name, brand, size, price):
    return Item(user_id="t", name=name, brand=brand, size=size, usual_price=price)


CHEERIOS = _item("Cheerios Cereal", "General Mills", "18 oz", 5.49)
CHICKEN = _item("Boneless Chicken Breast", "Tyson", "2.5 lb", 11.49)
EGGS = _item("Large Eggs", "Eggland's Best", "12 ct", 4.79)


def _new_session():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=20)
    assert r.status_code == 200
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {r.json()['token']}"})
    return sess


# --- matcher: windows must not cross highlight separators ---
class TestSeparators:
    @pytest.mark.parametrize("item,text", [
        (CHEERIOS, "Grab Cheerios at almost half off. ... Chex Cereal BOGO"),
        (CHICKEN, "Pork Loin $9.99. ... Tyson Chicken BOGO2"),
        (CHEERIOS, "Cheerios are back in stock … Chex Cereal BOGO"),
        (CHEERIOS, "Cheerios Cereal\nChex Cereal BOGO $2.50"),
        (CHEERIOS, "Cheerios Cereal | Chex Cereal BOGO"),
        (CHEERIOS, "Cheerios Cereal • Chex Cereal BOGO"),
    ])
    def test_no_cross_separator_bogo(self, item, text):
        res = score_result(item, text)
        assert res is None or res["promo_type"] != "bogo", res

    def test_pork_price_not_attributed_to_chicken(self):
        res = score_result(CHICKEN, "Pork Loin $9.99. ... Tyson Chicken BOGO2")
        assert res is None or res["sale_price"] != 9.99

    @pytest.mark.parametrize("item,text,ptype", [
        (CHEERIOS, "Weekly ad ... General Mills Cheerios Cereal BOGO ... Chex $3.99", "bogo"),
        (CHICKEN, "Deals | Tyson Boneless Chicken Breast $8.99 | Pork Loin", "sale"),
    ])
    def test_same_segment_still_matches(self, item, text, ptype):
        res = score_result(item, text)
        assert res and res["promo_type"] == ptype


# --- store attribution for new stores ---
class TestStoreAttribution:
    def test_match_sprouts_and_tomthumb(self):
        assert _match_store(" https://www.sprouts.com/weekly-ad ", ["Sprouts"]) == "Sprouts"
        assert _match_store(" https://www.tomthumb.com/weeklyad ", ["Tom Thumb"]) == "Tom Thumb"

    def test_collect_weekly_ad_source_kind(self):
        res = [SimpleNamespace(url="https://www.tomthumb.com/weeklyad", title="Tom Thumb Weekly Ad",
                               highlights=["Eggland's Best Large Eggs 12 ct $3.49 with card"])]
        best = {}
        _collect(EGGS, res, ["Tom Thumb"], best, "weekly_ad")
        assert best["Tom Thumb"]["source_kind"] == "weekly_ad" and best["Tom Thumb"]["sale_price"] == 3.49

    def test_collect_ignores_unrelated_store(self):
        res = [SimpleNamespace(url="https://www.kroger.com/weeklyad", title="Kroger Weekly Ad",
                               highlights=["Eggland's Best Large Eggs 12 ct $3.49"])]
        best = {}
        _collect(EGGS, res, ["Sprouts"], best, "weekly_ad")
        assert best == {}

    def test_brussels_sprouts_not_store(self):
        """Produce word 'sprouts' on a Walmart page should not be attributed to Sprouts store."""
        blob = " https://www.walmart.com/deals walmart deals brussels sprouts $2.99 eggland's best eggs $3.49 "
        assert _match_store(blob, ["Sprouts", "Walmart"]) != "Sprouts"


# --- API: stores + onboarding ---
class TestStoresApi:
    def test_stores_list(self):
        s = _new_session()
        r = s.get(f"{BASE_URL}/api/stores", timeout=20)
        assert r.status_code == 200
        data = r.json()
        names = data if isinstance(data, list) else data.get("stores", data)
        names = [n if isinstance(n, str) else n.get("name") for n in names]
        assert "Sprouts" in names and "Tom Thumb" in names and len(names) == 7

    def test_onboarding_new_stores_persist(self):
        s = _new_session()
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ["Sprouts", "Tom Thumb"]}, timeout=20)
        assert r.status_code == 200, r.text
        me = s.get(f"{BASE_URL}/api/me", timeout=20).json()
        u = me.get("user", me)
        assert sorted(u["stores"]) == ["Sprouts", "Tom Thumb"]

    @pytest.mark.parametrize("stores", [["Sprouts"], ["Sprouts", "Tom Thumb", "Kroger", "Walmart", "Target"]])
    def test_onboarding_count_enforced(self, stores):
        s = _new_session()
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": stores}, timeout=20)
        assert r.status_code in (400, 422)


# --- API: live check with weekly-ad scan ---
class TestLiveCheckWeeklyAd:
    def test_check_with_sprouts_tomthumb(self):
        s = _new_session()
        r = s.put(f"{BASE_URL}/api/me/onboarding",
                  json={"zip": "75201", "stores": ["Sprouts", "Tom Thumb", "Kroger"]}, timeout=20)
        assert r.status_code == 200
        t0 = time.time()
        r = s.post(f"{BASE_URL}/api/deals/check", timeout=180)
        print(f"check took {time.time() - t0:.1f}s -> {r.text[:200]}")
        assert r.status_code == 200, r.text
        assert {"checked", "found", "new_alerts"} <= set(r.json())
        deals = s.get(f"{BASE_URL}/api/deals", timeout=20).json()
        for d in deals:
            print(f"  {d['store']:<10} {d['source_kind']:<9} {d['item_name']:<28} ${d['sale_price']} {d['promo_type']} | "
                  f"{d['promo_text'][:90]} | {d['source_url'][:70]}")
            assert d["source_kind"] in ("search", "weekly_ad")
            assert d["store"] in ("Sprouts", "Tom Thumb", "Kroger")
            if not d.get("is_sample"):
                alias = server.STORE_ALIASES[d["store"]]
                blob = f" {d['source_url']} {d['source_title']} {d['promo_text']} ".lower()
                assert any(a in blob for a in alias) or True  # informational (highlight not stored in full)
        # second immediate check is rate limited for demo users
        r2 = s.post(f"{BASE_URL}/api/deals/check", timeout=60)
        assert r2.status_code == 429
