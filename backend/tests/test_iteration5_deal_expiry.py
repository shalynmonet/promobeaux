# Iteration 5: Deal expiry (ends_at, reminders, expiry alerts, parse_end_date)
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import jwt
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
load_dotenv(Path(__file__).resolve().parents[2] / "frontend" / ".env")

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")).rstrip("/")
mdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def today_ct() -> date:
    return datetime.now(ZoneInfo("America/Chicago")).date()


def new_demo():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=30)
    assert r.status_code == 200
    tok = r.json()["token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    uid = jwt.decode(tok, options={"verify_signature": False})["sub"]
    return s, uid


@pytest.fixture
def demo():
    s, uid = new_demo()
    yield s, uid
    for c in ("items", "deals", "alerts", "reminders", "users"):
        mdb[c].delete_many({"user_id": uid})


def by_name(deals, name):
    return next(d for d in deals if d["item_name"] == name)


# ---- GET /api/deals expiry fields + seed
class TestDealsExpiryFields:
    def test_fields_and_seed_offsets(self, demo):
        s, _ = demo
        deals = s.get(f"{BASE_URL}/api/deals").json()
        assert len(deals) == 4
        for d in deals:
            assert "ends_at" in d and "ends_estimated" in d and "remind" in d
            assert d["remind"] is False and d["ends_estimated"] is False
        t = today_ct()
        exp = {"Cheerios Cereal": ("Walmart", 1), "Large Eggs": ("Kroger", 3),
               "Ground Coffee": ("Target", 5), "Laundry Detergent Pacs": ("Kroger", 6)}
        for name, (store, off) in exp.items():
            d = by_name(deals, name)
            assert d["store"] == store
            assert d["ends_at"] == (t + timedelta(days=off)).isoformat(), (name, d["ends_at"])

    def test_expired_deal_hidden_everywhere(self, demo):
        s, uid = demo
        eggs = by_name(s.get(f"{BASE_URL}/api/deals").json(), "Large Eggs")
        before_sav = s.get(f"{BASE_URL}/api/savings").json()
        before_trip = s.get(f"{BASE_URL}/api/trip").json()
        yesterday = (today_ct() - timedelta(days=1)).isoformat()
        mdb.deals.update_one({"user_id": uid, "item_name": "Large Eggs"}, {"$set": {"ends_at": yesterday}})
        deals = s.get(f"{BASE_URL}/api/deals").json()
        assert all(d["id"] != eggs["id"] for d in deals)
        assert len(deals) == 3
        sav = s.get(f"{BASE_URL}/api/savings").json()
        trip = s.get(f"{BASE_URL}/api/trip").json()
        print("savings before/after", before_sav, sav)
        print("trip before/after", before_trip.get("savings"), trip.get("savings"))
        assert str(sav) != str(before_sav)
        eggs_row = next((r for r in trip["items"] if r["name"] == "Large Eggs"), None)
        assert eggs_row is None or eggs_row["on_deal"] is False

    def test_ends_today_still_visible(self, demo):
        s, uid = demo
        mdb.deals.update_one({"user_id": uid, "item_name": "Large Eggs"}, {"$set": {"ends_at": today_ct().isoformat()}})
        names = [d["item_name"] for d in s.get(f"{BASE_URL}/api/deals").json()]
        assert "Large Eggs" in names


# ---- POST /api/reminders toggle + expiry alerts
class TestReminders:
    def test_toggle_cheerios_creates_one_alert(self, demo):
        s, _ = demo
        ch = by_name(s.get(f"{BASE_URL}/api/deals").json(), "Cheerios Cereal")
        body = {"item_id": ch["item_id"], "store": "Walmart"}
        r = s.post(f"{BASE_URL}/api/reminders", json=body)
        assert r.status_code == 200 and r.json() == {"remind": True, "sent": 1}
        assert by_name(s.get(f"{BASE_URL}/api/deals").json(), "Cheerios Cereal")["remind"] is True
        alerts = s.get(f"{BASE_URL}/api/alerts").json()
        alerts = alerts if isinstance(alerts, list) else alerts.get("alerts", alerts)
        exp = [a for a in alerts if "ends tomorrow" in a["title"]]
        assert len(exp) == 1 and exp[0]["title"] == "Cheerios Cereal deal ends tomorrow at Walmart"
        assert s.post(f"{BASE_URL}/api/reminders", json=body).json() == {"remind": False, "sent": 0}
        assert by_name(s.get(f"{BASE_URL}/api/deals").json(), "Cheerios Cereal")["remind"] is False
        assert s.post(f"{BASE_URL}/api/reminders", json=body).json() == {"remind": True, "sent": 0}
        alerts = s.get(f"{BASE_URL}/api/alerts").json()
        alerts = alerts if isinstance(alerts, list) else alerts.get("alerts", alerts)
        assert len([a for a in alerts if "ends tomorrow" in a["title"]]) == 1

    def test_far_deal_sends_zero(self, demo):
        s, _ = demo
        cof = by_name(s.get(f"{BASE_URL}/api/deals").json(), "Ground Coffee")
        r = s.post(f"{BASE_URL}/api/reminders", json={"item_id": cof["item_id"], "store": "Target"})
        assert r.json() == {"remind": True, "sent": 0}

    def test_ends_today_message(self, demo):
        s, uid = demo
        mdb.deals.update_one({"user_id": uid, "item_name": "Large Eggs"}, {"$set": {"ends_at": today_ct().isoformat()}})
        eggs = by_name(s.get(f"{BASE_URL}/api/deals").json(), "Large Eggs")
        r = s.post(f"{BASE_URL}/api/reminders", json={"item_id": eggs["item_id"], "store": "Kroger"})
        assert r.json()["sent"] == 1
        titles = [a["title"] for a in s.get(f"{BASE_URL}/api/alerts").json()]
        assert "Large Eggs deal ends today at Kroger" in titles

    def test_reminder_errors(self, demo):
        s, _ = demo
        ch = by_name(s.get(f"{BASE_URL}/api/deals").json(), "Cheerios Cereal")
        assert s.post(f"{BASE_URL}/api/reminders", json={"item_id": "64b000000000000000000000", "store": "Walmart"}).status_code == 404
        assert s.post(f"{BASE_URL}/api/reminders", json={"item_id": "not-an-id", "store": "Walmart"}).status_code == 404
        assert s.post(f"{BASE_URL}/api/reminders", json={"item_id": ch["item_id"], "store": "FakeMart"}).status_code == 400
        assert s.post(f"{BASE_URL}/api/reminders", json={"store": "Walmart"}).status_code == 422
        other, ouid = new_demo()
        try:
            assert other.post(f"{BASE_URL}/api/reminders", json={"item_id": ch["item_id"], "store": "Walmart"}).status_code == 404
        finally:
            for c in ("items", "deals", "alerts", "reminders", "users"):
                mdb[c].delete_many({"user_id": ouid})
        assert requests.post(f"{BASE_URL}/api/reminders", json={"item_id": ch["item_id"], "store": "Walmart"}).status_code == 401

    def test_reminder_without_deal(self, demo):
        s, _ = demo
        milk = next(i for i in s.get(f"{BASE_URL}/api/watchlist").json() if i["name"] == "Whole Milk")
        r = s.post(f"{BASE_URL}/api/reminders", json={"item_id": milk["id"], "store": "Kroger"})
        assert r.status_code == 200 and r.json() == {"remind": True, "sent": 0}


# ---- parse_end_date / deal_end unit tests
class TestParseEndDate:
    T = date(2025, 10, 22)

    def p(self, text, url=""):
        import server
        return server.parse_end_date(text, url, self.T)

    def test_text_range(self):
        assert self.p("Weekly ad Oct 21 - Oct 27 eggs $2.99") == date(2025, 10, 27)

    def test_valid_thru_num(self):
        assert self.p("Eggs $2.99 valid thru 10/28") == date(2025, 10, 28)

    def test_num_range(self):
        assert self.p("Sale 10/22-10/28 eggs") == date(2025, 10, 28)

    def test_slug(self):
        assert self.p("eggs $2.99", "https://kroger.com/weekly-ad-oct-21-oct-27") == date(2025, 10, 27)

    def test_price_ignored(self):
        assert self.p("Yogurt $0.60/2 cups") is None

    def test_month_word_false_positive(self):
        # Words starting with a month abbreviation ('Decaf', 'Market', 'Mayo') should not be read as dates
        res = {t: self.p(t) for t in ["Folgers Decaf 12 - 24 oz $8.99", "Hellmann's Mayo 30 - 32 oz $4.99",
                                      "Marinara 2 to 3 jars $5"]}
        print("false-positive check:", res)
        assert all(v is None for v in res.values()), res

    def test_deal_end_estimates(self):
        import server
        e, est, expd = server.deal_end("Walmart", "", "Cheerios $2.75")
        assert (e, est, expd) == (None, False, False)
        e, est, _ = server.deal_end("Kroger", "", "Eggs $2.99")
        d = date.fromisoformat(e)
        assert est is True and d.weekday() == 1 and 0 <= (d - server.local_today()).days <= 6
        e, est, _ = server.deal_end("Target", "", "Coffee $9")
        assert date.fromisoformat(e).weekday() == 5 and est is True
        t = server.local_today() - timedelta(days=3)
        _, _, expd = server.deal_end("Kroger", "", f"valid thru {t.month}/{t.day}")
        assert expd is True
