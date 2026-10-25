"""Iteration 6: store picker allows 1..7 stores; watchlist image_url/image_checked + background photo lookup."""
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
ALL = ["Kroger", "Walmart", "Target", "Aldi", "H-E-B", "Tom Thumb", "Sprouts"]


def _new_session():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=20)
    assert r.status_code == 200
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="module")
def s():
    return _new_session()


# Onboarding: store count 1..7
class TestOnboardingStoreCount:
    def test_stores_endpoint_lists_7(self, s):
        r = s.get(f"{BASE_URL}/api/stores", timeout=15)
        assert r.status_code == 200 and r.json()["stores"] == ALL

    def test_all_7_stores_saved(self, s):
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ALL}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["stores"] == ALL
        me = s.get(f"{BASE_URL}/api/me", timeout=15).json()
        assert me["stores"] == ALL and me["onboarded"] is True and "_id" not in me

    @pytest.mark.parametrize("stores", [["Aldi"], ["H-E-B"], ["Tom Thumb"], ["Aldi", "H-E-B", "Tom Thumb", "Sprouts", "Kroger"]])
    def test_1_to_5_stores_saved(self, s, stores):
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": stores}, timeout=15)
        assert r.status_code == 200, r.text
        assert s.get(f"{BASE_URL}/api/me", timeout=15).json()["stores"] == stores

    def test_zero_stores_422(self, s):
        assert s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": []}, timeout=15).status_code == 422

    def test_8_stores_422(self, s):
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ALL + ["Kroger"]}, timeout=15)
        assert r.status_code == 422

    def test_unknown_store_400(self, s):
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ["Aldi", "Costco"]}, timeout=15)
        assert r.status_code == 400 and "Costco" in r.text

    def test_duplicate_stores_not_persisted_twice(self, s):
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ["Aldi", "Aldi"]}, timeout=15)
        # Either rejected or de-duplicated is acceptable; duplicates stored is a bug.
        if r.status_code == 200:
            assert r.json()["stores"] == ["Aldi"], f"duplicates persisted: {r.json()['stores']}"
        else:
            assert r.status_code in (400, 422)

    def test_deals_for_removed_stores_dropped(self):
        s2 = _new_session()
        s2.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ["Aldi"]}, timeout=15)
        deals = s2.get(f"{BASE_URL}/api/deals", timeout=15).json()
        assert all(d["store"] == "Aldi" for d in deals)


# Watchlist photos
class TestWatchlistPhotos:
    def test_fields_present(self, s):
        r = s.get(f"{BASE_URL}/api/watchlist", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        for it in items:
            assert "image_url" in it and "image_checked" in it and "_id" not in it
            assert isinstance(it["image_checked"], bool)

    def test_background_lookup_marks_checked(self, s):
        deadline = time.time() + 90
        items = []
        while time.time() < deadline:
            items = s.get(f"{BASE_URL}/api/watchlist", timeout=15).json()
            if all(i["image_checked"] for i in items):
                break
            time.sleep(4)
        assert all(i["image_checked"] for i in items), [(i["name"], i["image_checked"]) for i in items]
        with_photo = [i for i in items if i["image_url"]]
        print(f"photos: {len(with_photo)}/{len(items)}", [(i["name"], bool(i["image_url"])) for i in items])
        for i in with_photo:
            assert i["image_url"].startswith("http")

    def test_add_item_unchecked_then_edit_resets(self, s):
        r = s.post(f"{BASE_URL}/api/watchlist", json={"name": "TEST_Nutella Hazelnut Spread", "brand": "Nutella",
                                                       "size": "13 oz", "usual_price": 5.49}, timeout=15)
        assert r.status_code == 200
        it = r.json()
        assert it["image_checked"] is False and it["image_url"] is None
        iid = it["id"]
        try:
            deadline = time.time() + 60
            got = None
            while time.time() < deadline:
                got = next(i for i in s.get(f"{BASE_URL}/api/watchlist", timeout=15).json() if i["id"] == iid)
                if got["image_checked"]:
                    break
                time.sleep(3)
            assert got["image_checked"] is True
            print("Nutella image:", got["image_url"])
            u = s.put(f"{BASE_URL}/api/watchlist/{iid}", json={"name": "TEST_Nutella Hazelnut Spread", "brand": "Nutella",
                                                              "size": "26 oz", "usual_price": 8.99}, timeout=15)
            assert u.status_code == 200 and u.json()["image_checked"] is False and u.json()["size"] == "26 oz"
        finally:
            s.delete(f"{BASE_URL}/api/watchlist/{iid}", timeout=15)

    def test_delete_restore_keeps_image_fields(self, s):
        items = s.get(f"{BASE_URL}/api/watchlist", timeout=15).json()
        it = items[0]
        assert s.delete(f"{BASE_URL}/api/watchlist/{it['id']}", timeout=15).status_code == 200
        assert it["id"] not in [i["id"] for i in s.get(f"{BASE_URL}/api/watchlist", timeout=15).json()]
        r = s.post(f"{BASE_URL}/api/watchlist/{it['id']}/restore", timeout=15)
        assert r.status_code == 200 and r.json()["image_url"] == it["image_url"]
        assert it["id"] in [i["id"] for i in s.get(f"{BASE_URL}/api/watchlist", timeout=15).json()]
