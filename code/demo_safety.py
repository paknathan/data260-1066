import json
from agent_part5 import execute_tool

def run_safety_demo():
    print("=========================================================")
    print("      PART 5: DOMAIN SAFETY RULE DEMONSTRATION          ")
    print("=========================================================\n")

    # 1. Allowed Call
    print("1. DEMO: Allowed Call (Standard Query)")
    print("---------------------------------------------------------")
    allowed_inputs = {"query": "Route 22"}
    print(f"Inputs: {json.dumps(allowed_inputs)}")
    
    allowed_output = execute_tool("search_incidents", allowed_inputs)
    print(f"Returned Envelope JSON:\n{allowed_output}\n")

    # 2. Blocked Call
    print("2. DEMO: Blocked Call (Safety Violation)")
    print("---------------------------------------------------------")
    blocked_inputs = {"query": "secure_line_data"}
    print(f"Inputs: {json.dumps(blocked_inputs)}")
    
    blocked_output = execute_tool("search_incidents", blocked_inputs)
    print(f"Returned Envelope JSON:\n{blocked_output}\n")

if __name__ == "__main__":
    run_safety_demo()