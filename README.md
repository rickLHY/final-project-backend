# 台灣高鐵訂票系統 — Database Final Project

FastAPI + PostgreSQL backend for a Taiwan High-Speed Rail ticket booking system.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create the PostgreSQL database

```sql
CREATE DATABASE thsr_db;
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials and a strong SECRET_KEY
```

### 4. Run seed data (creates tables + inserts stations, trains, seats, prices)

```bash
python -m scripts.seed_data
```

### 5. Start the server

```bash
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

---

## Default seed accounts

| Role  | Email            | Password   |
|-------|------------------|------------|
| Admin | admin@thsr.com   | admin1234  |
| User  | user@thsr.com    | user1234   |

---

## API Overview

| Method | Path                                          | Description                          |
|--------|-----------------------------------------------|--------------------------------------|
| POST   | /auth/register                                | Register new user                    |
| POST   | /auth/login                                   | Login (returns JWT)                  |
| GET    | /users/me                                     | Get own profile                      |
| GET    | /stations/                                    | List all stations                    |
| GET    | /trains/                                      | List all trains                      |
| GET    | /seats/                                       | List seats (filter by carriage/type) |
| GET    | /ticket-prices/                               | Query ticket prices                  |
| GET    | /schedules/?departure_date=&start_station_id=&end_station_id= | Search schedules |
| GET    | /schedules/{id}                               | Schedule details with stop times     |
| GET    | /schedules/{id}/available-seats               | Available seats for a segment        |
| GET    | /schedules/{id}/early-bird                    | Early-bird pools                     |
| GET    | /schedules/non-reserved-availability?departure_date=&station_id= | Non-reserved seat congestion level per train |
| GET    | /schedules/peak-sales?start_date=&end_date=   | Occupancy & sales stats for a date range |
| POST   | /orders/                                      | Book tickets (1–6 per order)         |
| GET    | /orders/{id}                                  | Order details                        |
| GET    | /orders/booking/{code}                        | Look up by booking code              |
| PUT    | /orders/{id}/pay                              | Pay for order                        |
| PUT    | /orders/{id}/cancel                           | Cancel order                         |
| PUT    | /orders/{id}/tickets/{tid}/refund             | Refund a single ticket               |
| POST   | /waitlists/                                   | Join waitlist                        |
| GET    | /waitlists/my                                 | My waitlist entries                  |
| DELETE | /waitlists/{id}                               | Cancel waitlist entry                |

---

## Key Business Logic

- **Seat availability** — checked via overlapping station-range query using `sequence_no`
- **Ticket pricing** — 全票 100 % · 大學生/敬老 80 % · 愛心/愛陪/兒童 50 % · 早鳥 from `early_bird_pools.discount_rate`
- **Non-reserved carriages** — controlled by `schedules.non_reserved_start_carriage`; cannot be booked via API
- **Companion ticket (愛陪)** — self-referential FK to its paired 愛心 ticket; refunding the 愛心 ticket auto-refunds the companion
- **Waitlist** — triggered automatically when a ticket is refunded; matches on schedule + station-range coverage + seat type preference
