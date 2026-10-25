"""Iteration 7: photo lookup retry + cross-user photo_cache; onboarding store de-duplication."""
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
FOOD = {"Large Eggs", "Whole Milk", "Ground Coffee", "Cheerios Cereal", "Boneless Chicken Breast"}


def _new_session():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=20)
    assert r.status_code == 200
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {r.json()['token']}"})
    return s


def _wait_checked(s, timeout=90):
    end = time.time() + timeout
    items = []
    while time.time() < end:
        items = s.get(f"{BASE_URL}/api/watchlist", timeout=15).json()
        if items and all(i["image_checked"] for i in items):
            return items, time.time()
        time.sleep(3)
    return items, None


# Onboarding: duplicate stores are de-duplicated
class TestOnboardingDedupe:
    def test_duplicate_aldi_saved_once(self):
        s = _new_session()
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ["Aldi", "Aldi"]}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["stores"] == ["Aldi"]
        assert s.get(f"{BASE_URL}/api/me", timeout=15).json()["stores"] == ["Aldi"]

    def test_dedupe_keeps_order(self):
        s = _new_session()
        r = s.put(f"{BASE_URL}/api/me/onboarding",
                  json={"zip": "75201", "stores": ["Tom Thumb", "Aldi", "Tom Thumb", "H-E-B", "Aldi"]}, timeout=15)
        assert r.status_code == 200 and r.json()["stores"] == ["Tom Thumb", "Aldi", "H-E-B"]

    def test_all_7_still_saved(self):
        s = _new_session()
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ALL}, timeout=15)
        assert r.status_code == 200 and r.json()["stores"] == ALL

    def test_8_entries_with_dupes_422(self):
        s = _new_session()
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ["Kroger"] * 8}, timeout=15)
        assert r.status_code == 422

    def test_unknown_store_still_400(self):
        s = _new_session()
        r = s.put(f"{BASE_URL}/api/me/onboarding", json={"zip": "75201", "stores": ["Aldi", "Costco"]}, timeout=15)
        assert r.status_code == 400


# Photos: fresh demo users get photos for food items; cache reused for 2nd user
class TestPhotoCache:
    def test_first_demo_user_gets_food_photos(self):
        s = _new_session()
        items, done = _wait_checked(s)
        assert done, f"not all checked: {[(i['name'], i['image_checked']) for i in items]}"
        with_photo = {i["name"] for i in items if i["image_url"]}
        print("photos:", sorted(with_photo))
        assert len(with_photo & FOOD) >= 4, with_photo

    def test_second_demo_user_reuses_cache_fast(self):
        s = _new_session()
        t0 = time.time()
        items, done = _wait_checked(s, timeout=40)
        assert done
        print(f"2nd user all checked in {done - t0:.1f}s")
        assert done - t0 < 20  # cache hits skip the 1.5s spacing / OFF calls
        assert len({i["name"] for i in items if i["image_url"]} & FOOD) >= 4

    def test_same_photo_urls_across_users(self):
        a, b = _new_session(), _new_session()
        ia, _ = _wait_checked(a)
        ib, _ = _wait_checked(b)
        ma = {i["name"]: i["image_url"] for i in ia}
        mb = {i["name"]: i["image_url"] for i in ib}
        assert ma == mb

    def test_new_item_lookup_and_put_resets(self):
        s = _new_session()
        r = s.post(f"{BASE_URL}/api/watchlist",
                   json={"name": "TEST_Nutella Hazelnut Spread", "brand": "Nutella", "usual_price": 4.99}, timeout=15)
        assert r.status_code == 200 and r.json()["image_checked"] is False
        iid = r.json()["id"]
        try:
            items, done = _wait_checked(s, timeout=110)
            it = next(i for i in items if i["id"] == iid)
            print("nutella:", it["image_checked"], it["image_url"])
            # Either finished (photo or none) or still retrying — but must not be stuck forever unchecked with no job
            r2 = s.put(f"{BASE_URL}/api/watchlist/{iid}",
                       json={"name": "TEST_Nutella Hazelnut Spread", "brand": "Nutella", "usual_price": 5.49}, timeout=15)
            assert r2.status_code == 200 and r2.json()["image_checked"] is False and r2.json()["image_url"] is None
        finally:
            s.delete(f"{BASE_URL}/api/watchlist/{iid}", timeout=15)
