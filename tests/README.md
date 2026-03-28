# End-to-End Tests

177 tests covering every API endpoint, HTML page, input validation, and security boundary.

## Quick Start

```bash
./run_tests.sh
```

The script automatically creates a virtualenv and installs dependencies on first run.

## Common Options

```bash
./run_tests.sh -k scan          # only scan-related tests
./run_tests.sh -k theme         # only theme/wallpaper tests
./run_tests.sh -x               # stop on first failure
./run_tests.sh -s               # show print/log output
./run_tests.sh --co             # list all tests without running
./run_tests.sh tests/test_security.py  # run a single file
```

## Test Files

| File | Tests | What it covers |
|------|------:|----------------|
| `test_pages.py` | 7 | HTML page rendering + 404 |
| `test_results.py` | 40 | `/api/results`, `/api/countries`, `/api/results/geo`, `/api/top-servers`, `/api/statistics`, `/api/statistics/domains`, `/api/prune-stale`, `/api/v1/top/*`, `/api/server/<domain>/history`, status classification edge cases |
| `test_servers.py` | 6 | `/api/servers` GET/POST, dedup, normalization |
| `test_config.py` | 18 | `/api/config`, `/api/credentials`, `/api/config/test-notification`, `/api/schedule/*`, config robustness (missing keys, corrupt YAML) |
| `test_scan.py` | 18 | `/api/scan/start`, `/api/scan/status`, `/api/scan/stop`, `/api/vpn-speedtest`, `/api/queue/*` (FIFO, add-while-active, clear-safety) |
| `test_theme.py` | 17 | `/api/theme`, `/api/wallpaper/*`, `/api/origin` |
| `test_ovpn.py` | 12 | `/api/ovpn/*`, `/api/geolite/*` |
| `test_logs.py` | 11 | `/api/logs`, `/api/logs/clear`, `/api/logs/files`, `/api/logs/file/<name>` |
| `test_security.py` | 32 | Parameter clamping, credential leaks, path traversal, ZIP bombs, file extension validation, smoke tests for every endpoint |

## How It Works

- **Fully isolated** — every test runs against a temp directory; no production files are touched
- **External calls mocked** — GeoIP reader, HTTP requests, and background threads are patched
- **No credentials needed** — all test data uses `example.com` domains and RFC 5737 IPs
- **Fast** — full suite runs in ~3 seconds

---

## Smoke Test (Live Deployment)

The E2E suite tests the **code**. The smoke test validates a **running deployment** — container up, ports open, DB files mounted, APIs responding.

```bash
# Against local Docker
./smoke_test.sh http://localhost:5000

# Against production
./smoke_test.sh http://192.168.1.12:5000
```

It performs **read-only** GET requests against 25+ endpoints, checking HTTP status codes and response shapes. Nothing is modified — safe to run against production.

| What it checks | Details |
|----------------|---------|
| All 6 HTML pages | Return 200 with `<html` |
| Core APIs | `/api/scan/status`, `/api/results`, `/api/countries`, `/api/servers` |
| Statistics | `/api/statistics`, `/api/top-servers`, `/api/v1/top/*` |
| Config (read-only) | `/api/config`, `/api/credentials`, `/api/theme` |
| Infrastructure | `/api/ovpn/status`, `/api/geolite/status`, `/api/origin` |
| Logs | `/api/logs`, `/api/logs/files` |
| Security | Rejects invalid domain, 404 on unknown route |
