#!/usr/bin/env python3
"""
Gateway latency benchmark

Send a burst of chat completions through Bifröst, record latencies,
and surface guard metadata to validate the tiered execution path.
"""

import argparse
import asyncio
import statistics
import time
from typing import Any, Dict

import httpx


DEFAULT_URL = "http://localhost:8000/v1/chat/completions"


async def _send_request(
    client: httpx.AsyncClient,
    payload: Dict[str, Any],
    policy_id: str,
    results: list[float],
    guard_rows: list[Dict[str, Any]]
):
    start = time.perf_counter()
    response = await client.post(payload["url"], json=payload["body"])
    latency_ms = (time.perf_counter() - start) * 1000
    results.append(latency_ms)

    if response.status_code != 200:
        raise RuntimeError(f"Gateway error {response.status_code}: {response.text}")

    body = response.json()
    guardrails = body.get("guardrails") or {}
    guard_rows.append(
        {
            "policy": policy_id,
            "input_guards": len(guardrails.get("input_guards", [])),
            "output_guards": len(guardrails.get("output_guards", [])),
            "tier_stats": guardrails.get("tier_stats", {}),
            "latency_ms": latency_ms,
        }
    )


async def run_benchmark(
    url: str,
    policy_id: str,
    model: str,
    requests: int,
    concurrency: int,
    messages: list[Dict[str, str]]
):
    payload = {
        "url": url,
        "body": {
            "model": model,
            "messages": messages,
            "stream": False,
        },
    }

    headers = {
        "Content-Type": "application/json",
        "X-Policy-ID": policy_id,
    }

    results: list[float] = []
    guard_rows: list[Dict[str, Any]] = []
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        async def worker(_i: int):
            async with sem:
                await _send_request(client, payload, policy_id, results, guard_rows)

        await asyncio.gather(*(worker(i) for i in range(requests)))

    return results, guard_rows


def summarize(latencies: list[float]) -> None:
    latencies_sorted = sorted(latencies)
    print("Latency (ms):")
    print(f"  Total requests: {len(latencies)}")
    print(f"  Mean: {statistics.mean(latencies):.2f}")
    print(f"  Median: {statistics.median(latencies):.2f}")
    for pct in (50, 75, 90, 95, 99):
        idx = int(len(latencies_sorted) * pct / 100) - 1
        idx = max(0, min(idx, len(latencies_sorted) - 1))
        print(f"  p{pct}: {latencies_sorted[idx]:.2f}")


def print_guard_summary(rows: list[Dict[str, Any]]) -> None:
    if not rows:
        return
    guards_seen = sum(row["input_guards"] + row["output_guards"] for row in rows)
    print(f"\nGuard metadata sampled ({len(rows)} requests):")
    print(f"  Total guards executed: {guards_seen}")
    tier_freq: Dict[str, int] = {}
    for row in rows:
        for tier in row["tier_stats"].keys():
            tier_freq[tier] = tier_freq.get(tier, 0) + 1
    for tier, count in tier_freq.items():
        print(f"  {tier}: {count} executions")


def main():
    parser = argparse.ArgumentParser(description="Benchmark the Heimdall gateway.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Gateway chat endpoint")
    parser.add_argument("--requests", type=int, default=200, help="Number of requests")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent requests")
    parser.add_argument("--model", default="gpt-4o-mini", help="Model to call upstream")
    parser.add_argument("--policy", default="enterprise_default_v1", help="Policy ID to apply")
    args = parser.parse_args()

    sample_messages = [
        {"role": "user", "content": "Hello! Count to three with safe words."}
    ]

    results, guard_rows = asyncio.run(
        run_benchmark(
            url=args.url,
            policy_id=args.policy,
            model=args.model,
            requests=args.requests,
            concurrency=args.concurrency,
            messages=sample_messages,
        )
    )

    summarize(results)
    print_guard_summary(guard_rows)


if __name__ == "__main__":
    main()
