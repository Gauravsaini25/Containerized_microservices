#!/usr/bin/env python3
"""
Platform Comparison Benchmark: Docker Swarm vs Kubernetes
==========================================================
Runs identical load tests against both platforms and generates
a comparative Markdown report.

Usage:
  python scripts/compare_platforms.py
  python scripts/compare_platforms.py --requests 500 --concurrency 30

Prerequisites:
  - Docker Swarm stack deployed (port 8888)
  - Kubernetes stack deployed (port 30888)
  - pip install aiohttp (or requests)
"""

import argparse
import asyncio
import time
import json
import sys
import os
from datetime import datetime
from collections import defaultdict

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class PlatformBenchmark:
    def __init__(self, name, base_url, total_requests, concurrency):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.total_requests = total_requests
        self.concurrency = concurrency
        self.results = []
        self.errors = 0
        self.success = 0
        self.container_hits = defaultdict(int)
        self.start_time = None
        self.end_time = None
        self.deploy_time = None

    async def _send_async(self, session, rid):
        url = f"{self.base_url}/api/"
        start = time.perf_counter()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                elapsed = (time.perf_counter() - start) * 1000
                body = await resp.text()
                cid = "unknown"
                try:
                    cid = json.loads(body).get("container_id", "unknown")
                except Exception:
                    pass
                self.results.append({"id": rid, "status": resp.status, "latency_ms": round(elapsed, 2), "container": cid})
                if 200 <= resp.status < 400:
                    self.success += 1
                    self.container_hits[cid] += 1
                else:
                    self.errors += 1
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            self.results.append({"id": rid, "status": 0, "latency_ms": round(elapsed, 2), "container": "error"})
            self.errors += 1

    async def run_async(self):
        connector = aiohttp.TCPConnector(limit=self.concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            sem = asyncio.Semaphore(self.concurrency)
            async def limited(i):
                async with sem:
                    return await self._send_async(session, i)
            tasks = [limited(i) for i in range(self.total_requests)]
            done = 0
            for coro in asyncio.as_completed(tasks):
                await coro
                done += 1
                if done % 50 == 0 or done == self.total_requests:
                    print(f"    [{self.name}] {done}/{self.total_requests}", end="\r")
            print()

    def _send_sync(self, rid):
        url = f"{self.base_url}/api/"
        start = time.perf_counter()
        try:
            resp = requests.get(url, timeout=30)
            elapsed = (time.perf_counter() - start) * 1000
            cid = "unknown"
            try:
                cid = resp.json().get("container_id", "unknown")
            except Exception:
                pass
            self.results.append({"id": rid, "status": resp.status_code, "latency_ms": round(elapsed, 2), "container": cid})
            if 200 <= resp.status_code < 400:
                self.success += 1
                self.container_hits[cid] += 1
            else:
                self.errors += 1
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            self.results.append({"id": rid, "status": 0, "latency_ms": round(elapsed, 2), "container": "error"})
            self.errors += 1

    def run(self):
        print(f"\n  Running benchmark: {self.name} ({self.total_requests} requests, concurrency={self.concurrency})")
        print(f"  Target: {self.base_url}/api/")
        self.start_time = time.time()
        if HAS_AIOHTTP:
            asyncio.run(self.run_async())
        else:
            for i in range(self.total_requests):
                self._send_sync(i)
                if (i+1) % 50 == 0:
                    print(f"    [{self.name}] {i+1}/{self.total_requests}", end="\r")
            print()
        self.end_time = time.time()

    def get_metrics(self):
        total_time = self.end_time - self.start_time
        latencies = sorted([r["latency_ms"] for r in self.results])
        total = len(self.results)
        if not latencies:
            return {}
        p50 = latencies[int(total * 0.50)]
        p95 = latencies[int(total * 0.95)] if total > 1 else latencies[0]
        p99 = latencies[int(total * 0.99)] if total > 1 else latencies[0]
        dist = dict(self.container_hits)
        total_hits = sum(dist.values())
        dist_pct = {k: round(v / max(total_hits, 1) * 100, 1) for k, v in dist.items()}
        ideal = 100 / max(len(dist), 1)
        max_dev = max(abs(v - ideal) for v in dist_pct.values()) if dist_pct else 0

        return {
            "platform": self.name,
            "total_requests": total,
            "successful": self.success,
            "failed": self.errors,
            "error_rate": round(self.errors / max(total, 1) * 100, 2),
            "total_time_s": round(total_time, 2),
            "rps": round(total / max(total_time, 0.001), 1),
            "latency_min": round(latencies[0], 2),
            "latency_avg": round(sum(latencies) / total, 2),
            "latency_p50": round(p50, 2),
            "latency_p95": round(p95, 2),
            "latency_p99": round(p99, 2),
            "latency_max": round(latencies[-1], 2),
            "containers_used": len(dist),
            "distribution": dist,
            "distribution_pct": dist_pct,
            "max_deviation": round(max_dev, 1),
        }


def check_platform(url, name):
    """Check if a platform is reachable."""
    try:
        if HAS_REQUESTS:
            r = requests.get(f"{url}/api/", timeout=5)
            return r.status_code == 200
        elif HAS_AIOHTTP:
            async def check():
                async with aiohttp.ClientSession() as s:
                    async with s.get(f"{url}/api/", timeout=aiohttp.ClientTimeout(total=5)) as r:
                        return r.status == 200
            return asyncio.run(check())
    except Exception:
        return False


def generate_report(swarm_metrics, k8s_metrics, output_dir):
    """Generate comparative Markdown report."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(output_dir, f"comparison_report_{ts}.md")

    s = swarm_metrics
    k = k8s_metrics

    def winner(s_val, k_val, lower_better=True):
        if lower_better:
            return "Swarm ✅" if s_val < k_val else "K8s ✅" if k_val < s_val else "Tie"
        else:
            return "Swarm ✅" if s_val > k_val else "K8s ✅" if k_val > s_val else "Tie"

    lines = [
        "# Comparative Analysis: Docker Swarm vs Kubernetes",
        "",
        f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Requests per platform**: {s['total_requests']}",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        "| Metric | Docker Swarm | Kubernetes | Winner |",
        "|--------|-------------|------------|--------|",
        f"| Throughput (req/s) | {s['rps']} | {k['rps']} | {winner(s['rps'], k['rps'], False)} |",
        f"| Avg Latency | {s['latency_avg']}ms | {k['latency_avg']}ms | {winner(s['latency_avg'], k['latency_avg'])} |",
        f"| P50 Latency | {s['latency_p50']}ms | {k['latency_p50']}ms | {winner(s['latency_p50'], k['latency_p50'])} |",
        f"| P95 Latency | {s['latency_p95']}ms | {k['latency_p95']}ms | {winner(s['latency_p95'], k['latency_p95'])} |",
        f"| P99 Latency | {s['latency_p99']}ms | {k['latency_p99']}ms | {winner(s['latency_p99'], k['latency_p99'])} |",
        f"| Error Rate | {s['error_rate']}% | {k['error_rate']}% | {winner(s['error_rate'], k['error_rate'])} |",
        f"| Distribution Balance | {s['max_deviation']}% dev | {k['max_deviation']}% dev | {winner(s['max_deviation'], k['max_deviation'])} |",
        f"| Containers Used | {s['containers_used']} | {k['containers_used']} | — |",
        "",
        "---",
        "",
        "## Detailed Latency Comparison",
        "",
        "| Percentile | Docker Swarm | Kubernetes |",
        "|------------|-------------|------------|",
        f"| Min | {s['latency_min']}ms | {k['latency_min']}ms |",
        f"| Avg | {s['latency_avg']}ms | {k['latency_avg']}ms |",
        f"| P50 | {s['latency_p50']}ms | {k['latency_p50']}ms |",
        f"| P95 | {s['latency_p95']}ms | {k['latency_p95']}ms |",
        f"| P99 | {s['latency_p99']}ms | {k['latency_p99']}ms |",
        f"| Max | {s['latency_max']}ms | {k['latency_max']}ms |",
        "",
        "---",
        "",
        "## Load Balancing Distribution",
        "",
        "### Docker Swarm (Algorithm 2: Memory-Based)",
        "",
        "| Container | Requests | % |",
        "|-----------|----------|---|",
    ]
    for cid, count in sorted(s["distribution"].items()):
        pct = s["distribution_pct"].get(cid, 0)
        lines.append(f"| `{cid[:12]}` | {count} | {pct}% |")

    lines += [
        "",
        "### Kubernetes (Default Round-Robin)",
        "",
        "| Pod | Requests | % |",
        "|-----|----------|---|",
    ]
    for cid, count in sorted(k["distribution"].items()):
        pct = k["distribution_pct"].get(cid, 0)
        lines.append(f"| `{cid[:12]}` | {count} | {pct}% |")

    lines += [
        "",
        "---",
        "",
        "## Analysis",
        "",
        "### Load Balancing",
        f"- **Swarm** uses Algorithm 2 (memory-aware routing) with {s['max_deviation']}% max deviation from ideal",
        f"- **K8s** uses default kube-proxy round-robin with {k['max_deviation']}% max deviation from ideal",
        "",
        "### Auto-Scaling",
        "- **Swarm**: Custom Algorithm 1 — monitors memory via Docker Stats API, scales at >70% avg memory",
        "- **K8s**: Native HPA — monitors CPU via Metrics Server, scales at >70% avg CPU utilization",
        "",
        "### Service Discovery",
        "- **Swarm**: Overlay network DNS (service names resolve via embedded DNS)",
        "- **K8s**: CoreDNS (service names resolve via `svc.cluster.local` domain)",
        "",
    ]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n  📄 Report saved to: {filepath}")
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Compare Docker Swarm vs Kubernetes")
    parser.add_argument("--swarm-url", default="http://localhost:8888", help="Swarm base URL")
    parser.add_argument("--k8s-url", default="http://localhost:30888", help="K8s base URL")
    parser.add_argument("--requests", type=int, default=200, help="Requests per platform")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent requests")
    parser.add_argument("--output", default=None, help="Output directory")
    args = parser.parse_args()

    if not HAS_AIOHTTP and not HAS_REQUESTS:
        print("ERROR: Install aiohttp or requests: pip install aiohttp")
        sys.exit(1)

    output_dir = args.output or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")

    print("=" * 60)
    print("  PLATFORM COMPARISON: Docker Swarm vs Kubernetes")
    print("=" * 60)

    # Check platforms
    swarm_ok = check_platform(args.swarm_url, "Swarm")
    k8s_ok = check_platform(args.k8s_url, "Kubernetes")

    print(f"\n  Docker Swarm ({args.swarm_url}): {'✅ ONLINE' if swarm_ok else '❌ OFFLINE'}")
    print(f"  Kubernetes  ({args.k8s_url}): {'✅ ONLINE' if k8s_ok else '❌ OFFLINE'}")

    if not swarm_ok and not k8s_ok:
        print("\n  ❌ Neither platform is reachable. Deploy first.")
        sys.exit(1)

    results = {}

    if swarm_ok:
        swarm = PlatformBenchmark("Docker Swarm", args.swarm_url, args.requests, args.concurrency)
        swarm.run()
        results["swarm"] = swarm.get_metrics()
        print(f"  ✅ Swarm: {results['swarm']['rps']} req/s, P50={results['swarm']['latency_p50']}ms")

    if k8s_ok:
        k8s = PlatformBenchmark("Kubernetes", args.k8s_url, args.requests, args.concurrency)
        k8s.run()
        results["k8s"] = k8s.get_metrics()
        print(f"  ✅ K8s:   {results['k8s']['rps']} req/s, P50={results['k8s']['latency_p50']}ms")

    if "swarm" in results and "k8s" in results:
        generate_report(results["swarm"], results["k8s"], output_dir)
    else:
        # Save individual results
        os.makedirs(output_dir, exist_ok=True)
        for name, metrics in results.items():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fp = os.path.join(output_dir, f"{name}_benchmark_{ts}.json")
            with open(fp, "w") as f:
                json.dump(metrics, f, indent=2)
            print(f"  📄 {name} results saved to: {fp}")
        print("\n  ⚠️  Only one platform was online. Deploy both for comparison report.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
