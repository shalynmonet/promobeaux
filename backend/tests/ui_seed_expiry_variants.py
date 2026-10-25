# Helper for UI tests: waits for the next demo user and rewrites its sample deals' end dates
# (estimated / unknown / expired / far) so the Deals screen labels can be verified.
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
since = ObjectId.from_datetime(datetime.now(timezone.utc))
t = datetime.now(ZoneInfo("America/Chicago")).date()
for _ in range(90):
    u = db.users.find_one({"is_demo": True, "_id": {"$gt": since}}, sort=[("_id", -1)])
    if u and db.deals.count_documents({"user_id": u["user_id"]}) >= 4:
        uid = u["user_id"]
        db.deals.update_one({"user_id": uid, "item_name": "Large Eggs"},
                            {"$set": {"ends_estimated": True, "ends_at": (t + timedelta(days=3)).isoformat()}})
        db.deals.update_one({"user_id": uid, "item_name": "Ground Coffee"}, {"$set": {"ends_at": None}})
        db.deals.update_one({"user_id": uid, "item_name": "Laundry Detergent Pacs"},
                            {"$set": {"ends_at": (t - timedelta(days=1)).isoformat()}})
        db.deals.update_one({"user_id": uid, "item_name": "Cheerios Cereal"},
                            {"$set": {"ends_at": (t + timedelta(days=10)).isoformat()}})
        print("patched", uid)
        break
    time.sleep(1)
