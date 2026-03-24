#!/usr/bin/env bash
# Smoke test — validates a live deployment is healthy.
# Usage: ./smoke_test.sh [base_url]
# Example: ./smoke_test.sh http://192.168.1.12:5000

set -e

BASE_URL="${1:-http://localhost:5000}"
PASSED=0
FAILED=0
ERRORS=""

check() {
    local method="$1" url="$2" expected_code="$3" body_contains="$4" label="$5"
    local resp_code body

    if [ "$method" = "GET" ]; then
        resp_code=$(curl -s -o /tmp/smoke_body -w "%{http_code}" --max-time 10 "$url")
    else
        resp_code=$(curl -s -o /tmp/smoke_body -w "%{http_code}" --max-time 10 -X "$method" "$url")
    fi
    body=$(cat /tmp/smoke_body)

    if [ "$resp_code" != "$expected_code" ]; then
        FAILED=$((FAILED + 1))
        ERRORS+="  FAIL: $label — expected $expected_code, got $resp_code\n"
        return
    fi

    if [ -n "$body_contains" ] && ! echo "$body" | grep -q "$body_contains"; then
        FAILED=$((FAILED + 1))
        ERRORS+="  FAIL: $label — response missing '$body_contains'\n"
        return
    fi

    PASSED=$((PASSED + 1))
    echo "  OK   $label"
}

echo "Smoke testing $BASE_URL ..."
echo ""

# ── HTML pages ──────────────────────────────────────────────
echo "Pages:"
check GET "$BASE_URL/"           200 "<html"   "GET /"
check GET "$BASE_URL/config"     200 "<html"   "GET /config"
check GET "$BASE_URL/map"        200 "<html"   "GET /map"
check GET "$BASE_URL/help"       200 "<html"   "GET /help"
check GET "$BASE_URL/logs"       200 "<html"   "GET /logs"
check GET "$BASE_URL/statistics" 200 "<html"   "GET /statistics"

# ── Core APIs ───────────────────────────────────────────────
echo ""
echo "Core APIs:"
check GET "$BASE_URL/api/scan/status"       200 '"active"'      "GET /api/scan/status"
check GET "$BASE_URL/api/results"           200 ""               "GET /api/results"
check GET "$BASE_URL/api/countries"         200 ""               "GET /api/countries"
check GET "$BASE_URL/api/results/geo"       200 ""               "GET /api/results/geo"
check GET "$BASE_URL/api/servers"           200 '"servers"'      "GET /api/servers"

# ── Statistics & top results ────────────────────────────────
echo ""
echo "Statistics:"
check GET "$BASE_URL/api/statistics"        200 '"countries"'    "GET /api/statistics"
check GET "$BASE_URL/api/top-servers"       200 ""               "GET /api/top-servers"
check GET "$BASE_URL/api/v1/top/latency"    200 ""               "GET /api/v1/top/latency"
check GET "$BASE_URL/api/v1/top/download"   200 ""               "GET /api/v1/top/download"
check GET "$BASE_URL/api/v1/top/upload"     200 ""               "GET /api/v1/top/upload"

# ── Config & credentials (read-only) ───────────────────────
echo ""
echo "Config:"
check GET "$BASE_URL/api/config"            200 '"schedule"'     "GET /api/config"
check GET "$BASE_URL/api/credentials"       200 '"vpn_password_set"' "GET /api/credentials"
check GET "$BASE_URL/api/theme"             200 '"palette"'      "GET /api/theme"
check GET "$BASE_URL/api/schedule/next"     200 ""               "GET /api/schedule/next"

# ── Infrastructure ──────────────────────────────────────────
echo ""
echo "Infrastructure:"
check GET "$BASE_URL/api/ovpn/status"       200 '"count"'        "GET /api/ovpn/status"
check GET "$BASE_URL/api/geolite/status"    200 '"city_last_modified"' "GET /api/geolite/status"
check GET "$BASE_URL/api/origin"            200 ""               "GET /api/origin"
check GET "$BASE_URL/api/queue/status"      200 '"pending"'      "GET /api/queue/status"

# ── Logs ────────────────────────────────────────────────────
echo ""
echo "Logs:"
check GET "$BASE_URL/api/logs"              200 ""               "GET /api/logs"
check GET "$BASE_URL/api/logs/files"        200 '"general"'      "GET /api/logs/files"
check GET "$BASE_URL/api/logs/file/general" 200 '"lines"'        "GET /api/logs/file/general"

# ── Security (should reject bad input) ─────────────────────
echo ""
echo "Security:"
check GET "$BASE_URL/api/ovpn/config/invalid%20domain" 400 ""   "Rejects invalid OVPN domain"
check GET "$BASE_URL/nonexistent"           404 ""               "404 on unknown route"

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Passed: $PASSED   Failed: $FAILED"
echo "═══════════════════════════════════════"

if [ $FAILED -gt 0 ]; then
    echo ""
    echo -e "$ERRORS"
    exit 1
fi

echo "  All smoke tests passed!"
