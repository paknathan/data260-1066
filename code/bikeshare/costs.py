"""HW7 Part 4 - deterministic cost engine (no model): used to cross-check the agent and build the weekly table.

It applies the prices the agent extracted (and cited) from the pricing page to every trip in the uploaded CSV.
"""

import sqlite3
from typing import Any

PRICING_FIELDS = {
    "membership_monthly_fee": "monthly membership price ($/month)",
    "member_included_minutes": "classic-bike minutes included per member ride",
    "member_overage_per_min": "member $/min beyond the included classic minutes",
    "member_ebike_per_min": "member $/min on an ebike",
    "single_ride_price": "pay-per-use classic single ride price ($)",
    "single_ride_included_minutes": "minutes included in a single ride",
    "nonmember_extra_per_min": "pay-per-use $/min beyond the included minutes",
    "nonmember_ebike_unlock": "pay-per-use ebike base/unlock price ($)",
    "nonmember_ebike_per_min": "pay-per-use ebike $/min",
}


def missing_pricing(pricing: dict[str, Any]) -> list[str]:
    """Fields the engine needs that are absent or not numeric."""
    bad = []
    for f in PRICING_FIELDS:
        try:
            float(pricing.get(f))
        except (TypeError, ValueError):
            bad.append(f)
    return bad


def ride_costs(p: dict[str, float], billed_min: int, is_ebike: int) -> tuple[float, float]:
    """(pay-per-use cost, member residual cost) for one ride."""
    if is_ebike:
        ppu = p["nonmember_ebike_unlock"] + p["nonmember_ebike_per_min"] * billed_min
        member = p["member_ebike_per_min"] * billed_min
    else:
        ppu = p["single_ride_price"] + max(0, billed_min - p["single_ride_included_minutes"]) * p["nonmember_extra_per_min"]
        member = max(0, billed_min - p["member_included_minutes"]) * p["member_overage_per_min"]
    return ppu, member


def compute(con: sqlite3.Connection, pricing: dict[str, Any]) -> dict[str, Any]:
    """Totals, break-even and a weekly table for the trips table under both plans."""
    missing = missing_pricing(pricing)
    if missing:
        return {"ok": False, "missing_pricing": missing}
    p = {k: float(pricing[k]) for k in PRICING_FIELDS}
    rows = con.execute("SELECT billed_min, is_ebike, duration_min, week_start, month FROM trips").fetchall()
    if not rows:
        return {"ok": False, "error": "no usable trips"}
    weeks: dict[str, dict[str, float]] = {}
    ppu_total = member_resid = 0.0
    months = set()
    for billed, ebike, dur, week, month in rows:
        ppu, mem = ride_costs(p, int(billed), int(ebike))
        ppu_total += ppu
        member_resid += mem
        months.add(month)
        w = weeks.setdefault(week, {"rides": 0, "minutes": 0.0, "ppu_spend": 0.0, "member_residual": 0.0})
        w["rides"] += 1
        w["minutes"] += dur
        w["ppu_spend"] += ppu
        w["member_residual"] += mem
    n, m = len(rows), len(months)
    fees = p["membership_monthly_fee"] * m
    per_ride_saving = (ppu_total - member_resid) / n
    weekly = [{"week_start": k, "rides": int(v["rides"]), "avg_duration_min": round(v["minutes"] / v["rides"], 1),
               "pay_per_use_spend": round(v["ppu_spend"], 2), "member_residual": round(v["member_residual"], 2)}
              for k, v in sorted(weeks.items())]
    ebike_rides = sum(1 for r in rows if r[1])
    return {
        "ok": True,
        "rides": n, "months": m, "ebike_rides": ebike_rides, "classic_rides": n - ebike_rides,
        "pay_per_use_total": round(ppu_total, 2),
        "membership_fees": round(fees, 2),
        "membership_residual": round(member_resid, 2),
        "membership_total": round(fees + member_resid, 2),
        "rides_per_month": round(n / m, 1),
        "break_even_rides_per_month": round(p["membership_monthly_fee"] / per_ride_saving, 1) if per_ride_saving > 0 else None,
        "avg_duration_min": round(sum(r[2] for r in rows) / n, 1),
        "cheaper": "Buy Monthly Membership" if fees + member_resid < ppu_total else "Pay Per Ride/Minute",
        "weekly": weekly,
    }
