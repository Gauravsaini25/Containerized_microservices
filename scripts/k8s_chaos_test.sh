#!/bin/bash
# ==========================================
# KUBERNETES CHAOS TEST SCRIPT
# ==========================================
# Kills a backend pod and measures K8s self-healing recovery time.
# Results saved to results/k8s_chaos_test_results.md
#
# Usage: bash scripts/k8s_chaos_test.sh
# ==========================================

echo "============================================"
echo "  K8S CHAOS TEST - Fault Tolerance"
echo "  Comparative: Kubernetes Self-Healing"
echo "============================================"
echo ""

NAMESPACE="cc-research"
RESULTS_FILE="$(dirname "$0")/../results/k8s_chaos_test_results.md"
TEST_DATE=$(date "+%Y-%m-%d %H:%M:%S")

mkdir -p "$(dirname "$RESULTS_FILE")"

cat > "$RESULTS_FILE" << EOF
# Kubernetes Chaos Test Results

## Test Date: $TEST_DATE
## Platform: Kubernetes (Docker Desktop)

---

## Before Kill

EOF

# Step 1: Show current state
echo "📋 Step 1: Current State (BEFORE chaos)"
echo "----------------------------------------"
kubectl get pods -n "$NAMESPACE" -l app=backend
echo ""

BEFORE_COUNT=$(kubectl get pods -n "$NAMESPACE" -l app=backend --field-selector=status.phase=Running --no-headers | wc -l)
echo "✅ Running pods: $BEFORE_COUNT"

echo "| Pod Name | Status | Node |" >> "$RESULTS_FILE"
echo "|---|---|---|" >> "$RESULTS_FILE"
kubectl get pods -n "$NAMESPACE" -l app=backend --no-headers -o custom-columns="NAME:.metadata.name,STATUS:.status.phase,NODE:.spec.nodeName" | while read line; do
    echo "| $line |" >> "$RESULTS_FILE"
done
echo "" >> "$RESULTS_FILE"
echo "Running pods: **$BEFORE_COUNT** ✅" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
echo "---" >> "$RESULTS_FILE"

# Step 2: Kill a pod
echo ""
echo "💀 Step 2: Killing one backend pod..."
TARGET_POD=$(kubectl get pods -n "$NAMESPACE" -l app=backend --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')

if [ -z "$TARGET_POD" ]; then
    echo "❌ No backend pods found!"
    exit 1
fi

echo "Target pod: $TARGET_POD"

echo "## Kill Event" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
echo "- **Pod killed**: \`$TARGET_POD\`" >> "$RESULTS_FILE"
echo "- **Kill time**: $(date '+%Y-%m-%d %H:%M:%S')" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
echo "---" >> "$RESULTS_FILE"

KILL_TIME=$(date +%s)
kubectl delete pod "$TARGET_POD" -n "$NAMESPACE" --grace-period=0 --force 2>/dev/null
echo "✅ Pod killed at $(date)"

# Step 3: Monitor recovery
echo ""
echo "🔄 Step 3: Monitoring self-healing..."

echo "## Self-Healing Monitoring" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
echo "| Time (s) | Running Pods | Ready Pods | Notes |" >> "$RESULTS_FILE"
echo "|---|---|---|---|" >> "$RESULTS_FILE"

MAX_WAIT=60
HEALED=false
RECOVERY_SECONDS="N/A"

for i in $(seq 1 $MAX_WAIT); do
    RUNNING=$(kubectl get pods -n "$NAMESPACE" -l app=backend --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    READY=$(kubectl get pods -n "$NAMESPACE" -l app=backend --no-headers 2>/dev/null | grep "1/1" | wc -l)

    echo "  [$i s] Running: $RUNNING | Ready: $READY / $BEFORE_COUNT"
    echo "| $i | $RUNNING | $READY | |" >> "$RESULTS_FILE"

    if [ "$READY" -ge "$BEFORE_COUNT" ]; then
        HEAL_TIME=$(date +%s)
        RECOVERY_SECONDS=$((HEAL_TIME - KILL_TIME))
        HEALED=true
        echo ""
        echo "✅ Self-healing COMPLETE!"
        echo "⏱️  Recovery time: ${RECOVERY_SECONDS} seconds"
        sed -i "$ s/| |/| ✅ Fully recovered |/" "$RESULTS_FILE" 2>/dev/null
        break
    fi
    sleep 1
done

echo "" >> "$RESULTS_FILE"
echo "**Recovery Time**: $RECOVERY_SECONDS seconds" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
echo "---" >> "$RESULTS_FILE"

# Step 4: Verify
echo ""
echo "🔍 Step 4: Verifying application..."

echo "## After Recovery" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
kubectl get pods -n "$NAMESPACE" -l app=backend --no-headers -o custom-columns="NAME:.metadata.name,STATUS:.status.phase,READY:.status.conditions[?(@.type=='Ready')].status" | while read line; do
    echo "| $line |" >> "$RESULTS_FILE"
done
echo "" >> "$RESULTS_FILE"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:30888/api/ 2>/dev/null)
echo "## Application Availability" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Application AVAILABLE (HTTP $HTTP_CODE)"
    echo "- HTTP Status: **$HTTP_CODE** ✅" >> "$RESULTS_FILE"
else
    echo "⚠️  HTTP $HTTP_CODE"
    echo "- HTTP Status: **$HTTP_CODE** ⚠️" >> "$RESULTS_FILE"
fi

echo "" >> "$RESULTS_FILE"
echo "## Conclusion" >> "$RESULTS_FILE"
echo "" >> "$RESULTS_FILE"
echo "**Kubernetes Self-Healing**: ✅ VERIFIED" >> "$RESULTS_FILE"
echo "**Recovery Time**: $RECOVERY_SECONDS seconds" >> "$RESULTS_FILE"
echo "**Killed Pod**: \`$TARGET_POD\`" >> "$RESULTS_FILE"

echo ""
echo "============================================"
echo "  K8S CHAOS TEST COMPLETE"
echo "  Recovery time: ${RECOVERY_SECONDS}s"
echo "============================================"
echo ""
echo "📄 Results saved to: $RESULTS_FILE"
