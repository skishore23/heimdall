#!/usr/bin/env python3
"""Send configurable requests through the Heimdall gateway to collect latency stats."""

import argparse
import asyncio
import logging
import statistics
import time
from collections import Counter

import httpx

logger = logging.getLogger(__name__)


def _get_percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, int(len(sorted_values) * percentile / 100) - 1)
    index = min(len(sorted_values) - 1, index)
    return sorted_values[index]


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure request latencies through the Heimdall gateway.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000/v1/chat/completions",
        help="Gateway endpoint to hit",
    )
    parser.add_argument(
        "--policy-id",
        default="enterprise_default_v1",
        help="Policy header value to send",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="LLM model to request",
    )
    parser.add_argument(
        "--requests",
        "-n",
        type=int,
        default=20,
        help="Total number of requests to run",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        type=int,
        default=4,
        help="Concurrent outstanding requests",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds",
    )
    parser.add_argument(
        "--api-key",
        default="sk-test-key",
        help="Authorization header sent to the gateway",
    )
    parser.add_argument(
        "--prompt",
        default="Heimdall latency test",
        help="Prompt to include in every request",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Do not send an Authorization header",
    )
    return parser.parse_args()


async def _bounded_request(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    url: str,
    headers: dict[str, str],
    payload: dict[str, object],
) -> dict[str, object]:
    async with sem:
        start = time.perf_counter()
        try:
            response = await client.post(url, json=payload, headers=headers)
            latency_ms = (time.perf_counter() - start) * 1000.0
            return {
                "latency": latency_ms,
                "status": response.status_code,
                "error": None,
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000.0
            logger.warning("Request failed: %s", exc)
            return {
                "latency": latency_ms,
                "status": None,
                "error": str(exc),
            }


async def run(args: argparse.Namespace) -> None:
    if args.requests <= 0:
        raise ValueError("--requests must be greater than 0")

    headers = {"Content-Type": "application/json", "x-policy-id": args.policy_id}
    if not args.no_auth:
        headers["Authorization"] = f"Bearer {args.api_key}"

    payload = {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
    }

    timeout = httpx.Timeout(args.timeout, connect=args.timeout)

    logger.info(
        "Measuring %d requests (concurrency=%d) to %s",
        args.requests,
        args.concurrency,
        args.url,
    )

    sem = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [
            asyncio.create_task(_bounded_request(client, sem, args.url, headers, payload))
            for _ in range(args.requests)
        ]
        results = await asyncio.gather(*tasks)

    latencies = [result["latency"] for result in results if result["latency"] is not None]
    statuses = Counter(
        "error" if result["status"] is None else str(result["status"])
        for result in results
    )
    failures = sum(1 for result in results if not (result["status"] and 200 <= result["status"] < 400))

    if latencies:
        sorted_latencies = sorted(latencies)
        stats = {
            "mean": statistics.fmean(latencies),
            "median": statistics.median(latencies),
            "p95": _get_percentile(sorted_latencies, 95),
            "p99": _get_percentile(sorted_latencies, 99),
        }
    else:
        stats = {"mean": 0.0, "median": 0.0, "p95": 0.0, "p99": 0.0}

    logger.info(
        "Requests completed: %d success, %d failure(s). Status distribution: %s",
        args.requests - failures,
        failures,
        dict(statuses),
    )
    logger.info(
        "Latency (ms) — mean: %.2f, median: %.2f, p95: %.2f, p99: %.2f",
        stats["mean"],
        stats["median"],
        stats["p95"],
        stats["p99"],
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
