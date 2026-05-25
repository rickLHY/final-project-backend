# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **database schema design project** for a Taiwan High-Speed Rail (THSR) ticket booking system. The schema is written in [DbDiagram.io](https://dbdiagram.io) syntax and lives in [database-schema.md](database-schema.md).

## Schema Architecture

The schema is organized into four modules:

### 1. Static Master Data
- `Users` — accounts with `user_type` (`general`, `corporate`, `admin`) and `tgo_balance` (loyalty points)
- `Stations` — stations with `sequence_no` ordering (南港=1, 台北=2, …) and GPS coordinates
- `Trains` — train definitions (`standard` / `express`)
- `Seats` — physical seat hardware (carriage + row + letter, `is_business_class` flag)
- `Ticket_Prices` — base price matrix keyed by `(start_station_id, end_station_id, is_business)`

### 2. Dynamic Operations
- `Schedules` — one row per (train, departure_date); carriages ≥ `non_reserved_start_carriage` are non-reserved
- `Stop_Times` — station stop times per schedule (many-to-many bridge)
- `Early_Bird_Pools` — early-bird discount quota per schedule (`discount_rate`, `initial_quota`, `available_quota`)

### 3. Core Business / Transactions
- `Orders` — parent order with `booking_code`, `total_amount`, and `payment_status` (`unpaid`/`paid`/`cancelled`)
- `Order_Tickets` — individual tickets; at most 6 per order. `ticket_type` values: `全票`, `早鳥`, `大學生`, `敬老`, `愛心`, `愛陪`, `兒童`

### 4. Innovation
- `Waitlists` — smart auto-rebooking queue triggered on cancellation

## Key Design Decisions

- **Companion ticket self-join:** `Order_Tickets.companion_ticket_id` → `Order_Tickets.ticket_id` (one-to-one) binds a 愛陪 (companion care) ticket to its paired 愛心 (care) ticket within the same order.
- **Cascade deletes:** `Stop_Times` and `Early_Bird_Pools` cascade-delete when their `schedule_id` is removed; `Order_Tickets` cascade-deletes when the parent `Orders` row is removed.
- **Price capture:** `Order_Tickets.actual_price` stores the price paid at booking time, independent of any future changes to `Ticket_Prices`.
- **Non-reserved seats:** Determined by `Schedules.non_reserved_start_carriage` — carriages at or above that number are non-reserved.

## DbDiagram.io Syntax Reference

- `[pk, increment]` — primary key with auto-increment
- `[unique, not null]` — constraints
- `[default: 'value']` or `[default: \`now()\`]` — defaults
- `[note: '...']` — inline comment
- `Note: '...'` inside a table block — table-level note
- `Ref: A.col > B.col` — many-to-one (A references B)
- `Ref: A.col - B.col` — one-to-one
- `[delete: cascade]` — cascading delete on the FK
