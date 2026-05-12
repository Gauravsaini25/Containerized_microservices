# Comparative Analysis: Docker Swarm vs Kubernetes

**Date**: 2026-05-11 20:03:40
**Requests per platform**: 200

---

## Executive Summary

| Metric | Docker Swarm | Kubernetes | Winner |
|--------|-------------|------------|--------|
| Throughput (req/s) | 85.3 | 97.2 | K8s ✅ |
| Avg Latency | 11.6ms | 10.19ms | K8s ✅ |
| P50 Latency | 6.5ms | 6.2ms | K8s ✅ |
| P95 Latency | 29.59ms | 26.7ms | K8s ✅ |
| P99 Latency | 33.58ms | 29.23ms | K8s ✅ |
| Error Rate | 0.0% | 0.0% | Tie |
| Distribution Balance | 0.0% dev | 5.0% dev | Swarm ✅ |
| Containers Used | 1 | 4 | — |

---

## Detailed Latency Comparison

| Percentile | Docker Swarm | Kubernetes |
|------------|-------------|------------|
| Min | 5.03ms | 4.8ms |
| Avg | 11.6ms | 10.19ms |
| P50 | 6.5ms | 6.2ms |
| P95 | 29.59ms | 26.7ms |
| P99 | 33.58ms | 29.23ms |
| Max | 33.9ms | 29.34ms |

---

## Load Balancing Distribution

### Docker Swarm (Algorithm 2: Memory-Based)

| Container | Requests | % |
|-----------|----------|---|
| `54acaf5874ee` | 200 | 100.0% |

### Kubernetes (Default Round-Robin)

| Pod | Requests | % |
|-----|----------|---|
| `backend-69bb` | 56 | 28.0% |
| `backend-69bb` | 58 | 29.0% |
| `backend-69bb` | 40 | 20.0% |
| `backend-69bb` | 46 | 23.0% |

---

## Analysis

### Load Balancing
- **Swarm** uses Algorithm 2 (memory-aware routing) with 0.0% max deviation from ideal
- **K8s** uses default kube-proxy round-robin with 5.0% max deviation from ideal

### Auto-Scaling
- **Swarm**: Custom Algorithm 1 — monitors memory via Docker Stats API, scales at >70% avg memory
- **K8s**: Native HPA — monitors CPU via Metrics Server, scales at >70% avg CPU utilization

### Service Discovery
- **Swarm**: Overlay network DNS (service names resolve via embedded DNS)
- **K8s**: CoreDNS (service names resolve via `svc.cluster.local` domain)
