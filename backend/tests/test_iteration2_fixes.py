"""Iteration 2 retests: matcher precision, store-removal deal cleanup, per-session demo users, register-push skip."""
import re
import sys

import pytest
import requests

from test_promobeaux_api import BASE_URL

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from server import Item, score_result  # noqa: E402


def _item(name, brand, size, price):
    return Item(user_id="t", name=name, brand=brand, size=size, usual_price=price)


EGGS = _item("Large Eggs", "Eggland's Best", "12 ct", 4.79)
COFFEE = _item("Ground Coffee", "Folgers Classic Roast", "25.9 oz", 12.99)
CHICKEN = _item("Boneless Chicken Breast", "Tyson", "2.5 lb", 11.49)
TIDE = _item("Laundry Detergent Pacs", "Tide Pods", "42 ct", 13.99)
CHEERIOS = _item("Cheerios Cereal", "General Mills", "18 oz", 5.49)
NOBRAND_CHICKEN = _item("Boneless Chicken Breast", "", "", 11.49)
NOBRAND_COFFEE = _item("Ground Coffee", "", "", 12.99)


# --- matcher precision (unit) ---
class TestMatcher:
    @pytest.mark.parametrize("item,text", [
        (EGGS, "Kroger weekly ad: Goldfish Crackers Large Size $3.49 with Card"),
        (COFFEE, "Walmart Rollback: Ground Beef 80/20 $4.99 per lb"),
        (CHICKEN, "Target deal: Boneless Chuck Roast $7.99 lb"),
        (TIDE, "Kroger: Tide Stain Remover pen $2.99, save 30% off"),
        (NOBRAND_CHICKEN, "Boneless Chuck Roast only $7.99 at Kroger"),
        (NOBRAND_COFFEE, "Ground Beef family pack $5.99 at Walmart"),
        (EGGS, "Large Size Eggland's Best? Not here. Goldfish $2.99"),
    ])
    def test_false_positives_rejected(self, item, text):
        assert score_result(item, text) is None

    @pytest.mark.parametrize("item,text,ptype", [
        (EGGS, "Digital deal: Eggland's Best Large Eggs 12 ct $3.49 with Card", None),
        (COFFEE, "Folgers Classic Roast Ground Coffee 25.9 oz now $9.99 at Target", "sale"),
        (CHICKEN, "Tyson Boneless Skinless Chicken Breast 2.5 lb $8.99 this week", "sale"),
        (TIDE, "$2 cash back on Tide Pods 42 ct via digital rebate, now $11.99", "cashback"),
        (CHEERIOS, "Buy 1 Get 1 Free on Cheerios cereals at Walmart", "bogo"),
        (NOBRAND_CHICKEN, "Kroger: chicken breast boneless $7.99 lb", "sale"),
    ])
    def test_true_matches_accepted(self, item, text, ptype):
        r = score_result(item, text)
        assert r is not None, text
        assert r["sale_price"] < item.usual_price
        if ptype:
            assert r["promo_type"] == ptype

    def test_snippet_word_boundary(self):
        long = "Folgers Classic Roast Ground Coffee 25.9 oz $9.99 " + "extraordinarily " * 30
        r = score_result(COFFEE, long)
        assert r and len(r["snippet"]) <= 201
        assert server._clean_snippet("x" * 10 + " " + "word " * 60).endswith("…")
        s = server._clean_snippet("Folgers " + "abcdefghij " * 25)
        assert s.endswith("abcdefghij…")


@pytest.fixture
def new_sess():
    tok = requests.post(f"{BASE_URL}/api/auth/demo", timeout=20).json()["token"]
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return sess


# --- per-session demo users ---
class TestDemoIsolation:
    def test_separate_users_seeded_and_isolated(self, new_sess):
        tok2 = requests.post(f"{BASE_URL}/api/auth/demo", timeout=20).json()["token"]
        s2 = requests.Session()
        s2.headers.update({"Authorization": f"Bearer {tok2}"})
        u1 = new_sess.get(f"{BASE_URL}/api/me").json()["user_id"]
        u2 = s2.get(f"{BASE_URL}/api/me").json()["user_id"]
        assert u1 != u2 and re.fullmatch(r"demo_[0-9a-f]{12}", u1) and re.fullmatch(r"demo_[0-9a-f]{12}", u2)
        assert len(new_sess.get(f"{BASE_URL}/api/watchlist").json()) == 6
        assert len(new_sess.get(f"{BASE_URL}/api/deals").json()) == 4
        it = new_sess.post(f"{BASE_URL}/api/watchlist", json={"name": "TEST_Isolation", "usual_price": 3.0}).json()
        assert any(i["name"] == "TEST_Isolation" for i in new_sess.get(f"{BASE_URL}/api/watchlist").json())
        assert not any(i["name"] == "TEST_Isolation" for i in s2.get(f"{BASE_URL}/api/watchlist").json())
        assert s2.delete(f"{BASE_URL}/api/watchlist/{it['id']}").status_code == 404
        assert s2.put(f"{BASE_URL}/api/watchlist/{it['id']}", json={"name": "x", "usual_price": 1}).status_code == 404
        assert len(s2.get(f"{BASE_URL}/api/watchlist").json()) == 6


# --- store removal cleans deals ---
class TestStoreRemoval:
    def test_remove_store_deletes_deals(self, new_sess):
        before = new_sess.get(f"{BASE_URL}/api/deals").json()
        assert {d["store"] for d in before} >= {"Kroger", "Walmart", "Target"}
        r = new_sess.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ["Walmart", "Target"]})
        assert r.status_code == 200 and r.json()["stores"] == ["Walmart", "Target"]
        after = new_sess.get(f"{BASE_URL}/api/deals").json()
        assert all(d["store"] != "Kroger" for d in after) and len(after) == 2
        sv = new_sess.get(f"{BASE_URL}/api/savings").json()
        assert all(x["store"] != "Kroger" for x in sv["by_store"])
        assert all(x["store"] != "Kroger" for x in sv["top"])
        assert abs(sv["total"] - round(sum(d["savings"] for d in after), 2)) < 0.02


# --- push registration placeholder ---
class TestRegisterPush:
    def test_skipped_201(self, new_sess):
        r = new_sess.post(f"{BASE_URL}/api/register-push", json={"platform": "ios", "device_token": "TEST_tok"})
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "skipped"

    def test_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/register-push", json={"platform": "ios", "device_token": "x"})
        assert r.status_code == 401


# --- known precision gaps found in iteration 2 (expected to FAIL until matcher uses word boundaries) ---
class TestMatcherGaps:
    def test_name_terms_word_bounded(self):
        eggs = _item("Large Eggs", "", "", 4.79)
        assert score_result(eggs, "Eggshell paint $3.49 Walmart") is None


    def test_snippet_window_not_cut_mid_word(self):
        txt = "Folgers Classic Roast Ground Coffee 25.9 oz $9.99 with card Select Varieties, Limit 4 per household"
        r = score_result(COFFEE, txt)
        assert r and r["snippet"].split()[-1] in txt.split(), r["snippet"]
