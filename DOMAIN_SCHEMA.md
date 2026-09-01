# Domain Schema: Municipal Transit Incidents

## Entity Overview
A **Municipal Transit Incident** represents a single reported event that disrupts or affects
public transit service (bus, subway, light rail, streetcar, etc.) within a city's transit system.

---

## Fields

| Field Name         | Data Type | Required | Description                                                                 |
|---------------------|-----------|----------|-------------------------------------------------------------------------------|
| incident_id          | Integer / String | Yes | Unique identifier for the incident (e.g., `INC-00147`).                     |
| incident_type        | Category  | Yes      | The kind of incident. See **Incident Type** category values below.          |
| transit_mode         | Category  | Yes      | The mode of transit affected. See **Transit Mode** category values below.   |
| route_or_line        | String    | Yes      | Name/number of the affected route or line (e.g., "Route 22", "Blue Line").  |
| location             | String    | Yes      | Nearest stop, station, or intersection where the incident occurred.         |
| date_reported        | Date      | Yes      | Date the incident was reported (YYYY-MM-DD).                                |
| time_reported        | Time      | Yes      | Time the incident was reported (HH:MM, 24-hr format).                       |
| severity             | Category  | Yes      | Impact level of the incident. See **Severity** category values below.       |
| status               | Category  | Yes      | Current resolution status. See **Status** category values below.            |
| delay_minutes        | Integer   | No       | Estimated delay caused, in minutes (0 if no delay, blank if not applicable).|
| description          | String (long text) | No | Free-text summary of what happened.                                    |
| reported_by          | Category  | No       | Source of the report. See **Reported By** category values below.            |

---

## Category Values

### Incident Type
- Mechanical Breakdown
- Accident / Collision
- Delay
- Route Detour
- Signal / Track Problem
- Overcrowding
- Weather-Related
- Security Incident
- Power Outage
- Other

### Transit Mode
- Bus
- Subway
- Light Rail
- Streetcar
- Commuter Rail
- Ferry

### Severity
- Low
- Moderate
- High
- Critical

### Status
- Reported
- Under Investigation
- In Progress
- Resolved
- Cancelled

### Reported By
- Passenger
- Driver / Operator
- Transit Staff
- Automated Sensor
- Police / Emergency Services
