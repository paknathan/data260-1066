import sys
import logging
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP

# Force all logging to stderr to prevent stdout JSON-RPC corruption
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("transit_domain_server")

mcp = FastMCP("TransitIncidentsServer")

# Domain Dataset: Municipal Transit Incidents
DATASET: List[Dict[str, Any]] = [
    {
        "id": "inc_101",
        "route_id": "Route 22",
        "mode": "Bus",
        "type": "Mechanical Delay",
        "severity": "Medium",
        "delay_minutes": 18,
        "status": "Resolved"
    },
    {
        "id": "inc_102",
        "route_id": "Blue Line",
        "mode": "Light Rail",
        "type": "Signal Failure",
        "severity": "High",
        "delay_minutes": 42,
        "status": "Active"
    },
    {
        "id": "inc_103",
        "route_id": "Route 22",
        "mode": "Bus",
        "type": "Traffic Congestion",
        "severity": "Low",
        "delay_minutes": 10,
        "status": "Resolved"
    },
    {
        "id": "inc_104",
        "route_id": "Express 500",
        "mode": "Express Bus",
        "type": "Medical Emergency",
        "severity": "High",
        "delay_minutes": 30,
        "status": "Resolved"
    },
    {
        "id": "inc_105",
        "route_id": "Green Line",
        "mode": "Light Rail",
        "type": "Track Maintenance",
        "severity": "Medium",
        "delay_minutes": 25,
        "status": "Active"
    }
]

def envelope(ok: bool, data: Optional[Any] = None, error: Optional[str] = None) -> Dict[str, Any]:
    """Standard response envelope required for all tools."""
    return {
        "ok": ok,
        "data": data,
        "error": error
    }

# -------------------------------------------------------------------
# Tool 1: Search Operation
# -------------------------------------------------------------------
@mcp.tool()
def search_incidents(query: str) -> Dict[str, Any]:
    """Search transit incidents by route ID, incident type, or transit mode."""
    logger.info(f"Searching transit incidents for query: '{query}'")
    
    # Strip whitespace and any leading/trailing literal quotation marks
    cleaned_query = query.strip().strip('"').strip("'")
    
    if not cleaned_query:
        return envelope(ok=False, data=None, error="Search query cannot be empty.")
        
    q = cleaned_query.lower()
    results = [
        inc for inc in DATASET 
        if q in inc["route_id"].lower() 
        or q in inc["type"].lower() 
        or q in inc["mode"].lower()
    ]
    
    return envelope(ok=True, data=results, error=None)
# -------------------------------------------------------------------
# Tool 2: Detail Lookup
# -------------------------------------------------------------------
@mcp.tool()
def get_incident_detail(incident_id: str) -> Dict[str, Any]:
    """Retrieve full incident report by its unique ID (e.g., 'inc_101')."""
    logger.info(f"Detail lookup requested for incident ID: '{incident_id}'")
    
    if not incident_id or not incident_id.strip():
        return envelope(ok=False, data=None, error="incident_id parameter is required.")
        
    incident = next((inc for inc in DATASET if inc["id"] == incident_id.strip()), None)
    if not incident:
        return envelope(ok=False, data=None, error=f"Incident with ID '{incident_id}' was not found.")
        
    return envelope(ok=True, data=item if (item := incident) else None, error=None)

# -------------------------------------------------------------------
# Tool 3: Aggregate Operation
# -------------------------------------------------------------------
@mcp.tool()
def aggregate_route_stats(route_id: str) -> Dict[str, Any]:
    """Calculate aggregate incident statistics for a given transit route."""
    logger.info(f"Aggregating incident statistics for route: '{route_id}'")
    
    if not route_id or not route_id.strip():
        return envelope(ok=False, data=None, error="route_id parameter is required.")
        
    route_incidents = [
        inc for inc in DATASET 
        if inc["route_id"].lower() == route_id.lower().strip()
    ]
    
    if not route_incidents:
        valid_routes = sorted(list({inc["route_id"] for inc in DATASET}))
        return envelope(
            ok=False, 
            data=None, 
            error=f"No incident logs found for route '{route_id}'. Valid routes: {valid_routes}"
        )
        
    total_incidents = len(route_incidents)
    total_delay = sum(inc["delay_minutes"] for inc in route_incidents)
    avg_delay = total_delay / total_incidents
    active_count = sum(1 for inc in route_incidents if inc["status"] == "Active")
    
    stats = {
        "route_id": route_incidents[0]["route_id"],
        "total_incidents": total_incidents,
        "active_incidents": active_count,
        "avg_delay_minutes": round(avg_delay, 1),
        "total_delay_minutes": total_delay
    }
    
    return envelope(ok=True, data=stats, error=None)

if __name__ == "__main__":
    mcp.run()