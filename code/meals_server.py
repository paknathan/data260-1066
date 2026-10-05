import logging
import sys
from typing import Any, Dict, List, Union
import httpx
from mcp.server.fastmcp import FastMCP

# ------------------------------------------------------------------------------
# Logging Setup (MUST log to stderr for STDIO transport)
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("meals_server")

# ------------------------------------------------------------------------------
# Server & API Configuration
# ------------------------------------------------------------------------------
BASE_URL = "https://www.themealdb.com/api/json/v1/1"
mcp = FastMCP("meals")


def parse_ingredients(meal_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extracts and pairs non-empty ingredients and measurements from meal object."""
    ingredients = []
    for i in range(1, 21):
        ingredient = meal_data.get(f"strIngredient{i}")
        measure = meal_data.get(f"strMeasure{i}")
        if ingredient and ingredient.strip():
            ingredients.append({
                "name": ingredient.strip(),
                "measure": measure.strip() if measure else ""
            })
    return ingredients


def format_full_meal(meal: Dict[str, Any]) -> Dict[str, Any]:
    """Formats a raw meal record into the detailed recipe schema."""
    return {
        "id": meal.get("idMeal", ""),
        "name": meal.get("strMeal", ""),
        "category": meal.get("strCategory", ""),
        "area": meal.get("strArea", ""),
        "instructions": meal.get("strInstructions", ""),
        "image": meal.get("strMealThumb", ""),
        "source": meal.get("strSource") or "",
        "youtube": meal.get("strYoutube") or "",
        "ingredients": parse_ingredients(meal),
    }


# ------------------------------------------------------------------------------
# MCP Tools Definition
# ------------------------------------------------------------------------------
@mcp.tool()
async def search_meals_by_name(query: str, limit: int = 5) -> Union[List[Dict[str, Any]], Dict[str, str]]:
    """Search for meals by name. Returns up to 'limit' matching meals."""
    limit = max(1, min(limit, 25))
    url = f"{BASE_URL}/search.php?s={query}"
    logger.info("Calling search_meals_by_name with query='%s', limit=%d", query, limit)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        meals = data.get("meals")
        if not meals:
            return {"message": f"no matches found for '{query}'"}

        results = []
        for meal in meals[:limit]:
            results.append({
                "id": meal.get("idMeal", ""),
                "name": meal.get("strMeal", ""),
                "area": meal.get("strArea", ""),
                "category": meal.get("strCategory", ""),
                "thumb": meal.get("strMealThumb", ""),
            })
        return results

    except httpx.HTTPError as err:
        logger.error("HTTP error occurred in search_meals_by_name: %s", err)
        raise RuntimeError(f"Network error accessing TheMealDB: {err}")


@mcp.tool()
async def meals_by_ingredient(ingredient: str, limit: int = 12) -> Union[List[Dict[str, Any]], Dict[str, str]]:
    """Filter meals by main ingredient. Returns small cards (id, name, thumbnail)."""
    limit = max(1, limit)
    url = f"{BASE_URL}/filter.php?i={ingredient}"
    logger.info("Calling meals_by_ingredient with ingredient='%s', limit=%d", ingredient, limit)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        meals = data.get("meals")
        if not meals:
            return {"message": f"no matches found for ingredient '{ingredient}'"}

        results = []
        for meal in meals[:limit]:
            results.append({
                "id": meal.get("idMeal", ""),
                "name": meal.get("strMeal", ""),
                "thumb": meal.get("strMealThumb", ""),
            })
        return results

    except httpx.HTTPError as err:
        logger.error("HTTP error occurred in meals_by_ingredient: %s", err)
        raise RuntimeError(f"Network error accessing TheMealDB: {err}")


@mcp.tool()
async def random_meal() -> Union[Dict[str, Any], Dict[str, str]]:
    """Fetch a single random meal with full recipe details."""
    url = f"{BASE_URL}/random.php"
    logger.info("Calling random_meal")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        meals = data.get("meals")
        if not meals:
            return {"message": "no random meal found"}

        return format_full_meal(meals[0])

    except httpx.HTTPError as err:
        logger.error("HTTP error occurred in random_meal: %s", err)
        raise RuntimeError(f"Network error accessing TheMealDB: {err}")


@mcp.tool()
async def meal_details(id: Union[str, int]) -> Union[Dict[str, Any], Dict[str, str]]:
    """Lookup a single meal by ID and return its full recipe details."""
    meal_id = str(id).strip()
    url = f"{BASE_URL}/lookup.php?i={meal_id}"
    logger.info("Calling meal_details with id='%s'", meal_id)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        meals = data.get("meals")
        if not meals:
            return {"message": f"no meal found with ID '{meal_id}'"}

        return format_full_meal(meals[0])

    except httpx.HTTPError as err:
        logger.error("HTTP error occurred in meal_details: %s", err)
        raise RuntimeError(f"Network error accessing TheMealDB: {err}")


# ------------------------------------------------------------------------------
# Server Execution
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")