"""Speedtest module using speedtest-cli."""

import subprocess
import json
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class SpeedTest:
    """Run network speedtests."""
    
    @staticmethod
    def run_speedtest(timeout: int = 60) -> Optional[Dict[str, float]]:
        """
        Run speedtest and return results.
        
        Args:
            timeout: Speedtest timeout in seconds
            
        Returns:
            Dictionary with download_mbps, upload_mbps, ping_ms or None on failure
        """
        try:
            import sys
            print("DEBUG: SpeedTest.run_speedtest started", file=sys.stderr, flush=True)
            logger.info("Running speedtest via speedtest-cli...")
            
            # Run speedtest-cli with JSON output
            print("DEBUG: Executing speedtest-cli --json --secure --timeout 30", file=sys.stderr, flush=True)
            # Use smaller timeout for the command call to ensure we don't hang forever
            result = subprocess.run(
                ["speedtest-cli", "--json", "--secure", "--timeout", "30"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            print(f"DEBUG: speedtest-cli finished with code {result.returncode}", file=sys.stderr, flush=True)
            
            if result.returncode != 0:
                print(f"DEBUG: speedtest-cli error: {result.stderr}", file=sys.stderr, flush=True)
                return None
                
            # Parse JSON output
            print("DEBUG: Parsing speedtest JSON", file=sys.stderr, flush=True)
            data = json.loads(result.stdout)
            
            # Convert to Mbps
            download_mbps = round(data.get('download', 0) / 1_000_000, 2)
            upload_mbps = round(data.get('upload', 0) / 1_000_000, 2)
            ping_ms = round(data.get('ping', 0), 2)
            
            print(f"DEBUG: Speedtest complete: DL={download_mbps}, UL={upload_mbps}", file=sys.stderr, flush=True)
            
            return {
                'download_mbps': download_mbps,
                'upload_mbps': upload_mbps,
                'ping_ms': ping_ms
            }
            
        except subprocess.TimeoutExpired:
            print("DEBUG: Speedtest timed out", file=sys.stderr, flush=True)
            return None
        except json.JSONDecodeError as e:
            print(f"DEBUG: Failed to parse speedtest output: {e}", file=sys.stderr, flush=True)
            return None
        except Exception as e:
            print(f"DEBUG: Speedtest error: {e}", file=sys.stderr, flush=True)
            return None
