import os
import json
import time
import asyncio
import concurrent.futures
from typing import Any, Dict
from urllib import request, error

# Load from .env manually or hardcode for diagnostic
API_KEY = "sk-SXIXZAnw5Qj6NikY3NgOJ9XsiTyXJxDSY8BRcuN7PLz5cK0q"
BASE_URL = "https://api.moonshot.ai/v1"
MODEL = "kimi-k2.5"

def call_moonshot(system: str, user: str, timeout: float = 30.0) -> Dict[str, Any]:
    url = f"{BASE_URL}/chat/completions"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.3,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    
    start_time = time.time()
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            res_data = response.read()
            duration = time.time() - start_time
            return {
                "success": True,
                "duration": duration,
                "status": response.status,
                "data": json.loads(res_data.decode("utf-8"))
            }
    except error.HTTPError as e:
        duration = time.time() - start_time
        return {
            "success": False,
            "duration": duration,
            "status": e.code,
            "error": e.read().decode("utf-8")
        }
    except Exception as e:
        duration = time.time() - start_time
        return {
            "success": False,
            "duration": duration,
            "error": str(e)
        }

def run_diagnostic():
    print(f"--- Moonshot Diagnostic: {MODEL} ---")
    
    # Test 1: Simple Sequential Call
    print("\nTest 1: Sequential Call...")
    res = call_moonshot("You are a helpful assistant.", "Say hello.")
    if res["success"]:
        print(f"SUCCESS in {res['duration']:.2f}s: {res['data']['choices'][0]['message']['content']}")
    else:
        print(f"FAILED: {res.get('status')} - {res.get('error')}")

    # Test 2: Concurrency Stress Test (Simulate the parallel simulation environment)
    print("\nTest 2: Concurrency Stress Test (10 parallel calls)...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(call_moonshot, "Diagnose concurrency.", f"Task {i}") for i in range(10)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    success_count = sum(1 for r in results if r["success"])
    print(f"Done. Success: {success_count}/10")
    for i, r in enumerate(results):
        if not r["success"]:
            print(f"  Call {i} FAILED: {r.get('status')} - {r.get('error')[:100]}...")

    # Test 3: Large Context Test
    print("\nTest 3: Large Context Test...")
    large_user = "Repeat this word 500 times: hello " * 20
    res = call_moonshot("You are a helpful assistant.", large_user, timeout=60.0)
    if res["success"]:
        print(f"SUCCESS in {res['duration']:.2f}s")
    else:
        print(f"FAILED: {res.get('status')} - {res.get('error')}")

if __name__ == "__main__":
    run_diagnostic()
