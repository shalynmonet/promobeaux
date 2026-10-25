# Iteration 5: POST /api/deals/check with expiry reminders (live Exa) — new_alerts must equal alerts created
from datetime import date

from test_iteration5_deal_expiry import BASE_URL, mdb, new_demo, today_ct


def test_check_counts_expiry_alerts():
    s, uid = new_demo()
    try:
        items = {i["name"]: i["id"] for i in s.get(f"{BASE_URL}/api/watchlist").json()}
        # remind on every item/store pair without triggering via API (so check() is the one sending)
        for iid in items.values():
            for st in ("Kroger", "Walmart", "Target"):
                mdb.reminders.insert_one({"user_id": uid, "item_id": iid, "store": st, "created_at": "x"})
        before = len(s.get(f"{BASE_URL}/api/alerts").json())
        r = s.post(f"{BASE_URL}/api/deals/check", timeout=150)
        assert r.status_code == 200, r.text
        body = r.json()
        after = s.get(f"{BASE_URL}/api/alerts").json()
        print("check:", body, "alerts before/after", before, len(after))
        print("expiry alerts:", [a["title"] for a in after if a.get("title", "").find(" ends ") > 0])
        assert body["new_alerts"] == len(after) - before
        deals = s.get(f"{BASE_URL}/api/deals").json()
        t = today_ct()
        for d in deals:
            print(d["store"], d["item_name"], d["ends_at"], d["ends_estimated"], d["remind"], d.get("is_sample"), d["source_url"][:80])
            assert d["remind"] is True
            if d["ends_at"]:
                assert date.fromisoformat(d["ends_at"]) >= t
            if d["store"] == "Walmart" and not d.get("is_sample"):
                assert d["ends_estimated"] is False
        r2 = s.post(f"{BASE_URL}/api/deals/check", timeout=30)
        assert r2.status_code == 429
    finally:
        for c in ("items", "deals", "alerts", "reminders", "users"):
            mdb[c].delete_many({"user_id": uid})
