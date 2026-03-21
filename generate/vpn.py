"""VPN connection manager using OpenVPN."""

import sys
import os
import re
import subprocess
import time
import logging
import signal
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

ROUTING_TABLE_ID = "100"
ROUTING_RULE_PRIORITY = "100"


class VPNManager:
    """Manage OpenVPN connections."""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.connected = False
        self._original_gw: Optional[str] = None
        self._original_dev: Optional[str] = None
        self._eth0_ip: Optional[str] = None
        
    def connect(self, ovpn_file: str, username: str, password: str, timeout: int = 30) -> bool:
        """
        Connect to VPN using OpenVPN config file.
        
        Args:
            ovpn_file: Path to .ovpn configuration file
            username: VPN username
            password: VPN password
            timeout: Connection timeout in seconds
            
        Returns:
            True if connection successful, False otherwise
        """
        print(f"DEBUG: VPNManager.connect started for {ovpn_file}", file=sys.stderr, flush=True)
        if self.connected:
            logger.warning("VPN already connected, disconnecting first")
            self.disconnect()
            
        if not os.path.exists(ovpn_file):
            logger.error(f"OpenVPN config file not found: {ovpn_file}")
            return False
            
        try:
            # Create unique auth file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', prefix='vpn_auth_', delete=False) as f:
                auth_file = f.name
                f.write(f"{username}\n{password}\n")
            os.chmod(auth_file, 0o600)
            
            # Start OpenVPN process without --daemon to manage it directly
            self._save_original_route()
            cmd = [
                "openvpn",
                "--config", ovpn_file,
                "--auth-user-pass", auth_file,
                "--dev", "tun", # Explicitly request tun
                "--writepid", "/tmp/openvpn.pid" # Track PID
            ]
            
            print(f"DEBUG: Starting OpenVPN with Popen: {' '.join(cmd)}", file=sys.stderr, flush=True)
            # Use subprocess.Popen so it doesn't block
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setsid # Create process group for easy cleanup
            )
            
            # Wait for connection to establish
            print(f"DEBUG: Waiting up to {timeout}s for tun0 interface", file=sys.stderr, flush=True)
            for i in range(timeout):
                if self.process.poll() is not None:
                    print(f"DEBUG: OpenVPN process exited prematurely with code {self.process.returncode}", file=sys.stderr, flush=True)
                    return False
                
                time.sleep(1)
                if i % 5 == 0:
                    print(f"DEBUG: Wait heartbeat {i}/{timeout}...", file=sys.stderr, flush=True)
                
                if self._verify_connection():
                    self.connected = True
                    print("DEBUG: VPN connection detected on tun0!", file=sys.stderr, flush=True)
                    logger.info("VPN connection established on tun0")
                    self._preserve_web_access()
                    return True
                    
            print("DEBUG: VPN connection timed out waiting for tun0", file=sys.stderr, flush=True)
            self.disconnect()
            return False
            
        except subprocess.TimeoutExpired:
            logger.error("OpenVPN command timed out")
            return False
        except Exception as e:
            logger.error(f"VPN connection error: {e}")
            return False
        finally:
            # Clean up auth file
            if os.path.exists(auth_file):
                os.remove(auth_file)
                
    def disconnect(self) -> None:
        """Disconnect from VPN."""
        print("DEBUG: Disconnecting VPN...", file=sys.stderr, flush=True)
        self._restore_routing()
        try:
            if self.process:
                # Kill the process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=5)
                self.process = None
            
            # Fallback cleanup
            subprocess.run(["killall", "openvpn"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1)
            self.connected = False
            print("DEBUG: VPN disconnected", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"DEBUG: Error during disconnect: {e}", file=sys.stderr, flush=True)
            # Last resort
            subprocess.run(["killall", "-9", "openvpn"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.connected = False
            
    def _save_original_route(self) -> None:
        """Save the original default gateway and eth0 IP before VPN connects."""
        try:
            # Get default gateway: "default via 172.18.0.1 dev eth0"
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True
            )
            match = re.search(r'default via (\S+) dev (\S+)', result.stdout)
            if match:
                self._original_gw = match.group(1)
                self._original_dev = match.group(2)

            # Get eth0 IP: "inet 172.18.0.2/16"
            result = subprocess.run(
                ["ip", "-4", "addr", "show", self._original_dev or "eth0"],
                capture_output=True, text=True
            )
            match = re.search(r'inet (\S+?)/', result.stdout)
            if match:
                self._eth0_ip = match.group(1)

            print(f"DEBUG: Saved route: gw={self._original_gw} dev={self._original_dev} ip={self._eth0_ip}",
                  file=sys.stderr, flush=True)
        except Exception as e:
            logger.warning(f"Failed to save original route: {e}")

    def _preserve_web_access(self) -> None:
        """Add policy routing so web server responses bypass the VPN tunnel."""
        if not all([self._original_gw, self._original_dev, self._eth0_ip]):
            logger.warning("Missing routing info, cannot preserve web access")
            return
        try:
            # Add default route to custom table via original gateway
            subprocess.run(
                ["ip", "route", "add", "default", "via", self._original_gw,
                 "dev", self._original_dev, "table", ROUTING_TABLE_ID],
                capture_output=True
            )
            # Traffic FROM our container IP uses the custom table
            subprocess.run(
                ["ip", "rule", "add", "from", self._eth0_ip,
                 "table", ROUTING_TABLE_ID, "priority", ROUTING_RULE_PRIORITY],
                capture_output=True
            )
            print(f"DEBUG: Policy route added: from {self._eth0_ip} -> table {ROUTING_TABLE_ID} via {self._original_gw}",
                  file=sys.stderr, flush=True)
        except Exception as e:
            logger.warning(f"Failed to add policy route: {e}")

    def _restore_routing(self) -> None:
        """Remove policy routing rules added by _preserve_web_access."""
        try:
            subprocess.run(
                ["ip", "rule", "del", "table", ROUTING_TABLE_ID],
                capture_output=True
            )
            subprocess.run(
                ["ip", "route", "flush", "table", ROUTING_TABLE_ID],
                capture_output=True
            )
            print("DEBUG: Policy route removed", file=sys.stderr, flush=True)
        except Exception as e:
            logger.warning(f"Failed to remove policy route: {e}")

    def _verify_connection(self) -> bool:
        """Verify VPN connection by checking for tun interface."""
        try:
            result = subprocess.run(
                ["ip", "addr", "show", "tun0"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False
            
    def get_current_ip(self) -> Optional[str]:
        """Get current public IP address."""
        try:
            result = subprocess.run(
                ["curl", "-s", "https://api.ipify.org"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to get current IP: {e}")
        return None
        
    def __del__(self):
        """Cleanup on destruction."""
        if self.connected:
            self.disconnect()
