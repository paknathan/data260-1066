"""Validation for the primary domain entity: Municipal Transit Incident (see DOMAIN_SCHEMA.md)."""

import re
from datetime import datetime
from typing import Any

INCIDENT_TYPES = ["Mechanical Breakdown", "Accident / Collision", "Delay", "Route Detour", "Signal / Track Problem",
                  "Overcrowding", "Weather-Related", "Security Incident", "Power Outage", "Other"]
TRANSIT_MODES = ["Bus", "Subway", "Light Rail", "Streetcar", "Commuter Rail", "Ferry"]
SEVERITIES = ["Low", "Moderate", "High", "Critical"]
STATUSES = ["Reported", "Under Investigation", "In Progress", "Resolved", "Cancelled"]
REPORTED_BY = ["Passenger", "Driver / Operator", "Transit Staff", "Automated Sensor", "Police / Emergency Services"]

REQUIRED = {
    "incident_type": INCIDENT_TYPES,
    "transit_mode": TRANSIT_MODES,
    "route_or_line": str,
    "location": str,
    "date_reported": "date",
    "time_reported": "time",
    "severity": SEVERITIES,
    "status": STATUSES,
}
OPTIONAL = {"delay_minutes": int, "description": str, "reported_by": REPORTED_BY}


def validate_incident(data: Any) -> tuple[dict | None, str | None]:
    """Return (clean_incident, None) or (None, error message). Rejects missing, empty, invalid or unknown fields."""
    if not isinstance(data, dict):
        return None, "data must be a JSON object"
    unknown = sorted(set(data) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        return None, f"Unknown field(s): {unknown}"
    missing = [f for f in REQUIRED if f not in data or data[f] is None or str(data[f]).strip() == ""]
    if missing:
        return None, f"Missing or empty required field(s): {missing}"
    clean: dict = {}
    for field, rule in {**REQUIRED, **OPTIONAL}.items():
        if field not in data or data[field] is None:
            continue
        value = data[field]
        if isinstance(rule, list):
            if value not in rule:
                return None, f"Invalid {field} '{value}'; allowed: {rule}"
        elif rule == "date":
            try:
                datetime.strptime(str(value), "%Y-%m-%d")
            except ValueError:
                return None, f"Invalid date_reported '{value}'; expected YYYY-MM-DD"
        elif rule == "time":
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(value)):
                return None, f"Invalid time_reported '{value}'; expected HH:MM (24-hour)"
        elif rule is int:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return None, f"Invalid {field} '{value}'; expected a whole number >= 0"
        elif rule is str:
            if not isinstance(value, str) or not value.strip():
                return None, f"Invalid {field}; expected non-empty text"
            if len(value) > 2000:
                return None, f"{field} too long (max 2000 characters)"
            value = value.strip()
        clean[field] = value
    return clean, None
