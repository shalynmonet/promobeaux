"""Promobeaux backend regression tests (demo auth, profile, watchlist, deals, savings, alerts, barcode)."""
import os
import time

import pytest
import requests


def _base():
    url = os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    if not url:
        for line in open("/app/frontend/.env"):
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                url = line.split("=", 1)[1].strip().strip('"')
    return url.rstrip("/")


BASE_URL = _base()


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=20)
    assert r.status_code == 200
    t = r.json().get("token")
    assert isinstance(t, str) and len(t) > 20
    return t


@pytest.fixture(scope="session")
def s(token):
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    return sess


# Auth guard
class TestAuth:
    @pytest.mark.parametrize("path", ["/api/me", "/api/watchlist", "/api/deals", "/api/savings", "/api/alerts"])
    def test_no_token_401(self, path):
        assert requests.get(f"{BASE_URL}{path}", timeout=15).status_code == 401

    def test_invalid_token_401(self):
        r = requests.get(f"{BASE_URL}/api/me", headers={"Authorization": "Bearer abc.def.ghi"}, timeout=15)
        assert r.status_code == 401

    def test_bogus_hs256_401(self):
        import jwt
        bad = jwt.encode({"sub": "demo_user", "demo": True}, "wrongsecret", algorithm="HS256")
        r = requests.get(f"{BASE_URL}/api/me", headers={"Authorization": f"Bearer {bad}"}, timeout=15)
        assert r.status_code == 401


# Profile + onboarding
class TestProfile:
    def test_me(self, s):
        r = s.get(f"{BASE_URL}/api/me", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["user_id"].startswith("demo_") and d["is_demo"] is True and d["onboarded"] is True
        assert len(d["zip"]) == 5 and 1 <= len(d["stores"]) <= 7
        assert "_id" not in d

    @pytest.mark.parametrize("body", [
        {"zip": "1234", "stores": ["Kroger", "Walmart"]},
        {"zip": "abcde", "stores": ["Kroger", "Walmart"]},
        {"zip": "75201", "stores": []},
        {"zip": "75201", "stores": ["Kroger", "Walmart", "Target", "Aldi", "H-E-B", "Tom Thumb", "Sprouts", "Kroger"]},
    ])
    def test_onboarding_validation_422(self, s, body):
        assert s.put(f"{BASE_URL}/api/me/onboarding", json=body, timeout=15).status_code == 422

    def test_onboarding_unknown_store_400(self, s):
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ["Kroger", "Costco"]}, timeout=15)
        assert r.status_code == 400

    def test_onboarding_update_and_restore(self, s):
        orig = s.get(f"{BASE_URL}/api/me", timeout=15).json()
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75202", "stores": ["Aldi", "H-E-B"]}, timeout=15)
        assert r.status_code == 200 and r.json()["stores"] == ["Aldi", "H-E-B"]
        assert s.get(f"{BASE_URL}/api/me", timeout=15).json()["zip"] == "75202"
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": orig["zip"], "stores": orig["stores"]}, timeout=15)
        assert r.status_code == 200 and r.json()["stores"] == orig["stores"]


# Watchlist CRUD
class TestWatchlist:
    def test_list(self, s):
        r = s.get(f"{BASE_URL}/api/watchlist", timeout=15)
        assert r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 1
        assert all("id" in i and "_id" not in i for i in r.json())

    @pytest.mark.parametrize("bad", [{"name": "TEST_x", "usual_price": 0}, {"name": "TEST_x", "usual_price": -1},
                                     {"name": "", "usual_price": 2}, {"name": "TEST_x"}])
    def test_create_validation(self, s, bad):
        assert s.post(f"{BASE_URL}/api/watchlist", json=bad, timeout=15).status_code == 422

    def test_crud_flow(self, s):
        r = s.post(f"{BASE_URL}/api/watchlist", json={"name": "TEST_Bananas", "brand": "Dole", "size": "1 lb", "usual_price": 0.69}, timeout=15)
        assert r.status_code == 200
        it = r.json()
        assert it["name"] == "TEST_Bananas" and it["usual_price"] == 0.69 and it["id"]
        ids = [i["id"] for i in s.get(f"{BASE_URL}/api/watchlist", timeout=15).json()]
        assert it["id"] in ids
        r = s.put(f"{BASE_URL}/api/watchlist/{it['id']}", json={"name": "TEST_Bananas2", "usual_price": 0.99}, timeout=15)
        assert r.status_code == 200 and r.json()["name"] == "TEST_Bananas2" and r.json()["usual_price"] == 0.99
        assert s.delete(f"{BASE_URL}/api/watchlist/{it['id']}", timeout=15).status_code == 200
        ids = [i["id"] for i in s.get(f"{BASE_URL}/api/watchlist", timeout=15).json()]
        assert it["id"] not in ids
        assert s.delete(f"{BASE_URL}/api/watchlist/{it['id']}", timeout=15).status_code == 404

    def test_bad_ids_404(self, s):
        assert s.delete(f"{BASE_URL}/api/watchlist/notanid", timeout=15).status_code == 404
        assert s.put(f"{BASE_URL}/api/watchlist/507f1f77bcf86cd799439011", json={"name": "x", "usual_price": 1}, timeout=15).status_code == 404


# Barcode lookup
class TestBarcode:
    def test_found(self, s):
        r = s.get(f"{BASE_URL}/api/barcode/3017620422003", timeout=25)
        assert r.status_code == 200
        d = r.json()
        assert d["found"] is True and "nutella" in d["name"].lower()

    def test_invalid_400(self, s):
        assert s.get(f"{BASE_URL}/api/barcode/abc123", timeout=15).status_code == 400

    def test_unknown(self, s):
        r = s.get(f"{BASE_URL}/api/barcode/00000000000000", timeout=25)
        assert r.status_code == 200 and r.json()["found"] is False


# Deals, savings, alerts
class TestDeals:
    def test_deals_and_savings_shape(self):
        # fresh demo session: onboarding test above removes stores (which now deletes their deals)
        s = requests.Session()
        s.headers.update({"Authorization": "Bearer " + requests.post(f"{BASE_URL}/api/auth/demo", timeout=20).json()["token"]})
        deals = s.get(f"{BASE_URL}/api/deals", timeout=15).json()
        assert any(d["is_sample"] for d in deals)
        for d in deals:
            assert d["promo_type"] in ("sale", "bogo", "coupon", "cashback")
            assert d["sale_price"] < d["usual_price"] and d["savings"] > 0
            assert d["pct_off"] >= 10 or d["promo_type"] != "sale"
        sv = s.get(f"{BASE_URL}/api/savings", timeout=15).json()
        assert sv["total"] > 0 and isinstance(sv["by_store"], list)
        assert abs(sum(x["savings"] for x in sv["by_store"]) - sv["total"]) < 0.02

    def test_check_live(self, s):
        t = time.time()
        r = s.post(f"{BASE_URL}/api/deals/check", timeout=120)
        print(f"check took {time.time()-t:.1f}s -> {r.status_code} {r.text[:200]}")
        assert r.status_code == 200
        d = r.json()
        assert set(d) == {"checked", "found", "new_alerts"} and d["checked"] >= 1

    def test_alerts_read_all(self, s):
        al = s.get(f"{BASE_URL}/api/alerts", timeout=15)
        assert al.status_code == 200 and isinstance(al.json(), list)
        assert s.post(f"{BASE_URL}/api/alerts/read-all", timeout=15).json() == {"ok": True}
        assert all(a["read"] for a in s.get(f"{BASE_URL}/api/alerts", timeout=15).json())
