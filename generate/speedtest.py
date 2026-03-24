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
            logger.info("Running speedtest via speedtest-cli...")
            
            # Verify speedtest-cli is available
            import shutil
            if not shutil.which('speedtest-cli'):
                logger.error("speedtest-cli not found in PATH. Install with: pip install speedtest-cli")
                return None
            
            # Run speedtest-cli with JSON output
            # Use smaller timeout for the command call to ensure we don't hang forever
            result = subprocess.run(
                ["speedtest-cli", "--json", "--secure", "--timeout", "30"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode != 0:
                return None
                
            # Parse JSON output
            data = json.loads(result.stdout)
            
            # Convert to Mbps
            download_mbps = round(data.get('download', 0) / 1_000_000, 2)
            upload_mbps = round(data.get('upload', 0) / 1_000_000, 2)
            ping_ms = round(data.get('ping', 0), 2)
            
            return {
                'download_mbps': download_mbps,
                'upload_mbps': upload_mbps,
                'ping_ms': ping_ms
            }
            
        except subprocess.TimeoutExpired:
            return None
        except json.JSONDecodeError as e:
            return None
        except Exception as e:
            return None
