import sys
import time
import logging
from typing import Any, Dict, Callable, Optional

# Standard logging to stderr per requirements
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("retry_demo")


def envelope(ok: bool, data: Optional[Any] = None, error: Optional[str] = None) -> Dict[str, Any]:
    return {"ok": ok, "data": data, "error": error}


def execute_with_retry(
    func: Callable[..., Dict[str, Any]],
    *args,
    max_retries: int = 3,
    initial_delay: float = 0.1,
    backoff_factor: float = 2.0,
    **kwargs
) -> Dict[str, Any]:
    """Wraps operation with bounded exponential backoff."""
    delay = initial_delay

    for attempt in range(1, max_retries + 1):
        logger.info(f"-> Attempt {attempt}/{max_retries} executing...")
        try:
            result = func(*args, **kwargs)
            if result.get("ok"):
                logger.info(f"   Success on attempt {attempt}.")
                return result
            else:
                logger.warning(f"   Attempt {attempt} failed: {result.get('error')}")
        except Exception as e:
            logger.warning(f"   Attempt {attempt} raised exception: {str(e)}")

        if attempt < max_retries:
            logger.info(f"   Backing off for {delay:.2f}s...")
            time.sleep(delay)
            delay *= backoff_factor

    return envelope(
        ok=False,
        data=None,
        error=f"Operation failed after {max_retries} allowed retries."
    )


# Simulated API tool call
call_counter = 0
mode = "success_first"

def mock_domain_api():
    global call_counter, mode
    call_counter += 1
    
    if mode == "success_first":
        return envelope(ok=True, data={"incident_id": "inc_101", "status": "Active"}, error=None)
    
    elif mode == "success_after_retry":
        if call_counter == 1:
            return envelope(ok=False, data=None, error="503 Service Unavailable (Transient)")
        return envelope(ok=True, data={"incident_id": "inc_101", "status": "Active"}, error=None)
        
    elif mode == "fail_all_retries":
        return envelope(ok=False, data=None, error="500 Internal Server Error (Persistent)")


if __name__ == "__main__":
    print("==================================================")
    print("1. DEMO: Success on the first attempt")
    print("==================================================")
    mode = "success_first"
    call_counter = 0
    res1 = execute_with_retry(mock_domain_api, max_retries=3, initial_delay=0.1)
    print(f"Result: {res1}\n")

    print("==================================================")
    print("2. DEMO: Failure on first attempt followed by success after retry")
    print("==================================================")
    mode = "success_after_retry"
    call_counter = 0
    res2 = execute_with_retry(mock_domain_api, max_retries=3, initial_delay=0.1)
    print(f"Result: {res2}\n")

    print("==================================================")
    print("3. DEMO: Failure after all allowed retries")
    print("==================================================")
    mode = "fail_all_retries"
    call_counter = 0
    res3 = execute_with_retry(mock_domain_api, max_retries=3, initial_delay=0.1)
    print(f"Result: {res3}\n")