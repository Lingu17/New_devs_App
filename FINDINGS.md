# Revenue dashboard - what I found

Short notes on the bugs behind the three complaints, and what I changed.

---

### 1. Ocean Rentals seeing someone else's revenue

Started with the seed data. `prop-001` exists twice - once for Sunset (Beach House
Alpha) and once for Ocean (Mountain Lodge Beta). The table allows it since the key
is `(id, tenant_id)`.

The cache in `services/cache.py` was keyed on `revenue:{property_id}` only. So
whichever client opened prop-001 first, the other one got that cached number for
the next 5 minutes. That's the "sometimes on refresh" part.

There was a second leak too: if the DB query failed, `calculate_total_revenue`
returned hard-coded numbers per property ID, again ignoring the tenant.

**Changed:** cache key is now `revenue:{tenant_id}:{property_id}`, and I took the
hard-coded fallback out so a DB failure shows up as an error instead of fake data.

---

### 2. Sunset's March numbers don't match

Booking `res-tz-1` checks in at `2024-02-29 23:30 UTC`. The property is in Paris,
so for the client that's 1 March, 00:30. Our monthly calc built the month range
with plain `datetime(year, month, 1)`, i.e. UTC, so this booking was counted in
February instead. The function also used `tenant_id` in the query without ever
receiving it.

**Changed:** `calculate_monthly_revenue` takes `tenant_id` now, joins
`properties` to get the timezone, and compares check-in in the property's local
time (`AT TIME ZONE p.timezone`).

---

### 3. Totals off by a few cents

`total_amount` is stored with 3 decimals (e.g. 333.333 + 333.333 + 333.334). The
API turned the total into a float, and the frontend rounded that float again.
Float maths isn't exact, so the cents could drift.

**Changed:** the backend rounds once to 2 decimals using `Decimal`
(`ROUND_HALF_UP`) before sending it.

---

### 4. The dashboard wasn't actually reading the database

Found this while looking at #1. `database_pool.py` was reading config values
(`supabase_db_*`) that don't exist, used `QueuePool` which doesn't work with the
async engine, and `get_session()` was `async`, so `async with` on it failed. Every
request ended up on the hard-coded numbers. It was also creating a new pool on
each request.

**Changed:** use `settings.database_url`, drop `QueuePool`, make `get_session()` a
normal method, only initialise once, and reuse the shared `db_pool`. Once it actually
hit the DB, it failed on a missing `greenlet` package, so `requirements.txt` now has
`sqlalchemy[asyncio]` instead of plain `sqlalchemy`.

---

### How to check

```
docker compose up --build
```

- Log in as Sunset, open Beach House Alpha -> should be **2250.00**
  (1250 + 333.333 + 333.333 + 333.334).
- Log in as Ocean, open the same property ID -> **0.00** (no bookings seeded for it).
- Refresh a few times on both - numbers shouldn't swap anymore.
- If old values are still cached: `docker compose exec redis redis-cli FLUSHALL`
