"""VPN connection manager using OpenVPN."""

import sys
import os
import subprocess
import time
import logging
import signal
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class VPNManager:
    """Manage OpenVPN connections."""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.connected = False
        
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
