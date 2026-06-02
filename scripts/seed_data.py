"""
Run from the project root:
    python -m scripts.seed_data

Inserts: 12 stations, sample trains, all seats (708 seats), ticket prices, and one sample schedule.

Seat layout (matches real THSR):
  Car 6  — 商務車廂 (Business): 12 rows × A C D E  = 48 seats
  Cars 1–5, 7–12 — 標準車廂 (Standard): 12 rows × A B C D E = 660 seats
  Aisle is between C and D in all cars.
"""

from app.database import SessionLocal, engine
from app import models
from app.auth import get_password_hash

models.Base.metadata.create_all(bind=engine)

# ── Taiwan HSR Stations (south-bound order) ───────────────────────────────────
STATIONS = [
    {"station_name": "南港", "sequence_no": 1,  "latitude": 25.052893, "longitude": 121.607913},
    {"station_name": "台北", "sequence_no": 2,  "latitude": 25.049198, "longitude": 121.517198},
    {"station_name": "板橋", "sequence_no": 3,  "latitude": 25.014623, "longitude": 121.463500},
    {"station_name": "桃園", "sequence_no": 4,  "latitude": 24.954680, "longitude": 121.225716},
    {"station_name": "新竹", "sequence_no": 5,  "latitude": 24.803140, "longitude": 120.973830},
    {"station_name": "苗栗", "sequence_no": 6,  "latitude": 24.568790, "longitude": 120.821050},
    {"station_name": "台中", "sequence_no": 7,  "latitude": 24.267730, "longitude": 120.684280},
    {"station_name": "彰化", "sequence_no": 8,  "latitude": 24.051080, "longitude": 120.561540},
    {"station_name": "雲林", "sequence_no": 9,  "latitude": 23.711670, "longitude": 120.394440},
    {"station_name": "嘉義", "sequence_no": 10, "latitude": 23.388780, "longitude": 120.340500},
    {"station_name": "台南", "sequence_no": 11, "latitude": 22.997480, "longitude": 120.241650},
    {"station_name": "左營", "sequence_no": 12, "latitude": 22.684600, "longitude": 120.295690},
]

# ── Trains ─────────────────────────────────────────────────────────────────────
TRAINS = [
    {"train_no": "0101", "train_type": "express",  "total_carriages": 12},
    {"train_no": "0103", "train_type": "express",  "total_carriages": 12},
    {"train_no": "0111", "train_type": "standard", "total_carriages": 12},
    {"train_no": "0113", "train_type": "standard", "total_carriages": 12},
    {"train_no": "0201", "train_type": "express",  "total_carriages": 12},
    {"train_no": "0203", "train_type": "express",  "total_carriages": 12},
]

# ── Seat layout ────────────────────────────────────────────────────────────────
# Car 6 only  → 商務車廂 (Business): 12 rows × 4 seats (A C D E)  – no B seat
# Cars 1-5, 7-12 → 標準車廂 (Standard): 12 rows × 5 seats (A B C D E)
# Aisle is between C and D in both car types.

BUSINESS_LETTERS = ["A", "C", "D", "E"]   # 商務艙 – 2+2 layout, aisle between C and D
STANDARD_LETTERS = ["A", "B", "C", "D", "E"]  # 標準艙 – 3+2 layout, aisle between C and D


def _build_seats() -> list[dict]:
    seats = []
    for carriage in range(1, 13):
        is_biz = (carriage == 6)          # only car 6 is business class
        letters = BUSINESS_LETTERS if is_biz else STANDARD_LETTERS
        for row in range(1, 13):           # 12 rows per car
            for letter in letters:
                seats.append({
                    "carriage_no": carriage,
                    "row_no": row,
                    "seat_letter": letter,
                    "is_business_class": is_biz,
                })
    return seats


# ── Ticket prices (standard + business, all 12×11 directional pairs) ───────────
# Base prices approximated from real THSR fares (NTD).
# Indexed by (start_seq, end_seq) → standard price; business ≈ standard × 1.65

_STANDARD_PRICES = {
    (1, 2): 30,   (1, 3): 50,   (1, 4): 160,  (1, 5): 290,  (1, 6): 430,
    (1, 7): 530,  (1, 8): 600,  (1, 9): 700,  (1, 10): 790, (1, 11): 870, (1, 12): 990,
    (2, 3): 30,   (2, 4): 140,  (2, 5): 260,  (2, 6): 400,  (2, 7): 490,
    (2, 8): 560,  (2, 9): 660,  (2, 10): 750, (2, 11): 820, (2, 12): 940,
    (3, 4): 120,  (3, 5): 240,  (3, 6): 380,  (3, 7): 470,
    (3, 8): 540,  (3, 9): 640,  (3, 10): 730, (3, 11): 800, (3, 12): 920,
    (4, 5): 130,  (4, 6): 270,  (4, 7): 360,
    (4, 8): 430,  (4, 9): 530,  (4, 10): 620, (4, 11): 690, (4, 12): 810,
    (5, 6): 150,  (5, 7): 240,
    (5, 8): 310,  (5, 9): 410,  (5, 10): 500, (5, 11): 570, (5, 12): 690,
    (6, 7): 100,
    (6, 8): 170,  (6, 9): 270,  (6, 10): 360, (6, 11): 430, (6, 12): 550,
    (7, 8): 80,   (7, 9): 180,  (7, 10): 270, (7, 11): 340, (7, 12): 460,
    (8, 9): 110,  (8, 10): 200, (8, 11): 270, (8, 12): 390,
    (9, 10): 100, (9, 11): 170, (9, 12): 290,
    (10, 11): 80, (10, 12): 200,
    (11, 12): 130,
}


def _build_prices(station_id_by_seq: dict[int, int]) -> list[dict]:
    prices = []
    for (s_seq, e_seq), std_price in _STANDARD_PRICES.items():
        biz_price = int(std_price * 1.65)
        sid = station_id_by_seq[s_seq]
        eid = station_id_by_seq[e_seq]
        prices.append({"start_station_id": sid, "end_station_id": eid, "is_business": False, "base_price": std_price})
        prices.append({"start_station_id": sid, "end_station_id": eid, "is_business": True,  "base_price": biz_price})
        # Also add reverse direction
        prices.append({"start_station_id": eid, "end_station_id": sid, "is_business": False, "base_price": std_price})
        prices.append({"start_station_id": eid, "end_station_id": sid, "is_business": True,  "base_price": biz_price})
    return prices


# ── Sample schedule (0101, 2026-06-01, express from 南港 to 左營) ──────────────
from datetime import time, date

SAMPLE_SCHEDULE = {
    "train_no": "0101",
    "departure_date": date(2026, 6, 1),
    "non_reserved_start_carriage": 10,
    "stops": [
        {"station_name": "南港", "arrival_time": None,             "departure_time": time(6, 30)},
        {"station_name": "台北", "arrival_time": time(6, 36),      "departure_time": time(6, 40)},
        {"station_name": "板橋", "arrival_time": time(6, 47),      "departure_time": time(6, 49)},
        {"station_name": "新竹", "arrival_time": time(7, 20),      "departure_time": time(7, 22)},
        {"station_name": "台中", "arrival_time": time(7, 55),      "departure_time": time(7, 57)},
        {"station_name": "嘉義", "arrival_time": time(8, 33),      "departure_time": time(8, 35)},
        {"station_name": "台南", "arrival_time": time(8, 55),      "departure_time": time(8, 57)},
        {"station_name": "左營", "arrival_time": time(9, 10),      "departure_time": None},
    ],
    "early_bird": [
        {"discount_rate": 0.65, "initial_quota": 30, "available_quota": 30},
        {"discount_rate": 0.80, "initial_quota": 50, "available_quota": 50},
    ],
}


def seed():
    db = SessionLocal()
    try:
        # ── Admin user ──────────────────────────────────────────────────────
        if not db.query(models.User).filter(models.User.email == "admin@thsr.com").first():
            db.add(models.User(
                email="admin@thsr.com",
                password_hash=get_password_hash("admin1234"),
                name="System Admin",
                phone="0800000000",
                user_type="admin",
            ))
            db.add(models.User(
                email="user@thsr.com",
                password_hash=get_password_hash("user1234"),
                name="測試用戶",
                phone="0912345678",
                user_type="general",
            ))
            print("Created admin and demo user")

        # ── Stations ────────────────────────────────────────────────────────
        station_id_by_seq: dict[int, int] = {}
        for s in STATIONS:
            existing = db.query(models.Station).filter(models.Station.station_name == s["station_name"]).first()
            if not existing:
                obj = models.Station(**s)
                db.add(obj)
                db.flush()
                station_id_by_seq[s["sequence_no"]] = obj.station_id
            else:
                station_id_by_seq[existing.sequence_no] = existing.station_id
        db.commit()
        # reload all in case some were already present
        for st in db.query(models.Station).all():
            station_id_by_seq[st.sequence_no] = st.station_id
        print(f"Stations ready ({len(station_id_by_seq)} total)")

        # ── Trains ──────────────────────────────────────────────────────────
        for t in TRAINS:
            if not db.query(models.Train).filter(models.Train.train_no == t["train_no"]).first():
                db.add(models.Train(**t))
        db.commit()
        print("Trains ready")

        # ── Seats ───────────────────────────────────────────────────────────
        EXPECTED_SEATS = 708  # 11 std cars × 12 rows × 5 + 1 biz car × 12 rows × 4
        existing_count = db.query(models.Seat).count()
        if existing_count == 0:
            seats = _build_seats()
            db.bulk_insert_mappings(models.Seat, seats)
            db.commit()
            print(f"Seats inserted ({len(seats)} total)")
        elif existing_count != EXPECTED_SEATS:
            print(f"Seat layout mismatch: found {existing_count}, expected {EXPECTED_SEATS}.")
            print("To reset to the new layout run:")
            print("  DELETE FROM order_tickets; DELETE FROM waitlists;")
            print("  DELETE FROM seats;")
            print("Then re-run this script.")
        else:
            print("Seats already exist with correct layout, skipping")

        # ── Ticket Prices ───────────────────────────────────────────────────
        if db.query(models.TicketPrice).count() == 0:
            prices = _build_prices(station_id_by_seq)
            db.bulk_insert_mappings(models.TicketPrice, prices)
            db.commit()
            print(f"Ticket prices inserted ({len(prices)} entries)")
        else:
            print("Ticket prices already exist, skipping")

        # ── Sample Schedule ─────────────────────────────────────────────────
        sc = SAMPLE_SCHEDULE
        existing_sched = db.query(models.Schedule).filter(
            models.Schedule.train_no == sc["train_no"],
            models.Schedule.departure_date == sc["departure_date"],
        ).first()

        if not existing_sched:
            schedule = models.Schedule(
                train_no=sc["train_no"],
                departure_date=sc["departure_date"],
                non_reserved_start_carriage=sc["non_reserved_start_carriage"],
            )
            db.add(schedule)
            db.flush()

            station_by_name = {s.station_name: s for s in db.query(models.Station).all()}
            for stop in sc["stops"]:
                st = station_by_name[stop["station_name"]]
                db.add(models.StopTime(
                    schedule_id=schedule.schedule_id,
                    station_id=st.station_id,
                    arrival_time=stop["arrival_time"],
                    departure_time=stop["departure_time"],
                ))

            for eb in sc["early_bird"]:
                db.add(models.EarlyBirdPool(schedule_id=schedule.schedule_id, **eb))

            db.commit()
            print(f"Sample schedule created (schedule_id={schedule.schedule_id})")
        else:
            print(f"Sample schedule already exists (schedule_id={existing_sched.schedule_id})")

        print("\nSeed complete!")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
