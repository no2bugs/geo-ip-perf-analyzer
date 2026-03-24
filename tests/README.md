# End-to-End Tests

140 tests covering every API endpoint, HTML page, input validation, and security boundary.

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
| `test_results.py` | 27 | `/api/results`, `/api/countries`, `/api/results/geo`, `/api/top-servers`, `/api/statistics`, `/api/prune-stale`, `/api/v1/top/*` |
| `test_servers.py` | 6 | `/api/servers` GET/POST, dedup, normalization |
| `test_config.py` | 16 | `/api/config`, `/api/credentials`, `/api/config/test-notification`, `/api/schedule/*` |
| `test_scan.py` | 14 | `/api/scan/start`, `/api/scan/status`, `/api/scan/stop`, `/api/vpn-speedtest`, `/api/queue/*` |
| `test_theme.py` | 17 | `/api/theme`, `/api/wallpaper/*`, `/api/origin` |
| `test_ovpn.py` | 12 | `/api/ovpn/*`, `/api/geolite/*` |
| `test_logs.py` | 11 | `/api/logs`, `/api/logs/clear`, `/api/logs/files`, `/api/logs/file/<name>` |
| `test_security.py` | 14 | Parameter clamping, credential leaks, path traversal, ZIP bombs, file extension validation |

## How It Works

- **Fully isolated** — every test runs against a temp directory; no production files are touched
- **External calls mocked** — GeoIP reader, HTTP requests, and background threads are patched
- **No credentials needed** — all test data uses `example.com` domains and RFC 5737 IPs
- **Fast** — full suite runs in ~3 seconds
