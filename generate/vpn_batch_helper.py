"""VPN speedtest helper - batch processing logic."""

def _perform_vpn_speedtests_batch(endpoints_dict, ovpn_dir, username, password, progress, batch_size=20, interactive=True, selected_domains=None, formatting=None):
    """Perform VPN speedtests on endpoints that have matching .ovpn files with batch processing."""
    import os
    import logging
    from pathlib import Path
    from generate.vpn import VPNManager
    from generate.speedtest import SpeedTest
    
    import sys
    logger = logging.getLogger(__name__)
    print("DEBUG: _perform_vpn_speedtests_batch started", file=sys.stderr, flush=True)
    
    # Find matching .ovpn files
    ovpn_path = Path(ovpn_dir)
    if not ovpn_path.exists():
        logger.warning(f"VPN config directory not found: {ovpn_dir}")
        return
        
    # Map domains to .ovpn files
    ovpn_files = {}
    for ovpn_file in ovpn_path.glob("*.ovpn"):
        # Extract domain from filename (e.g., "ad1.nordvpn.com.udp.ovpn" -> "ad1.nordvpn.com")
        filename = ovpn_file.stem  # Remove .ovpn
        if filename.endswith('.udp') or filename.endswith('.tcp'):
            domain = filename.rsplit('.', 1)[0]
        else:
            domain = filename
        ovpn_files[domain] = str(ovpn_file)
    print(f"DEBUG: Found {len(ovpn_files)} total OVPN files", file=sys.stderr, flush=True)
    
    # Filter endpoints based on selection
    if selected_domains:
        # Web UI: Use only selected domains
        matched_endpoints = {domain: data for domain, data in endpoints_dict.items() 
                           if domain in ovpn_files and domain in selected_domains}
    else:
        # CLI: Use all matched endpoints
        matched_endpoints = {domain: data for domain, data in endpoints_dict.items() if domain in ovpn_files}
    
    if not matched_endpoints:
        logger.info("No VPN config files found for any scanned endpoints")
        return
    
    # Sort by latency (best performers first)
    # Sort by latency (best performers first)
    # Handle both old list format [latency, ip, country, city] and new dict format
    def get_latency(entry):
        if isinstance(entry, dict):
            return entry.get('latency_ms', 9999)
        elif isinstance(entry, (list, tuple)) and len(entry) > 0:
            return entry[0]
        return 9999

    sorted_endpoints = sorted(matched_endpoints.items(), key=lambda x: get_latency(x[1]))
    print(f"DEBUG: {len(sorted_endpoints)} matched endpoints after filtering", file=sys.stderr, flush=True)
    
    print(f"DEBUG: Found {len(sorted_endpoints)} endpoints with VPN configs", file=sys.stderr, flush=True)
    if formatting:
        print("DEBUG: Disabling formatting for background process", file=sys.stderr, flush=True)
        formatting.enabled = False
    print(f"Performing VPN speedtests on {len(sorted_endpoints)} endpoints...", file=sys.stderr, flush=True)
    
    print("DEBUG: Initializing vpn_manager and speedtest", file=sys.stderr, flush=True)
    vpn_manager = VPNManager()
    speedtest = SpeedTest()
    print("DEBUG: Managers initialized", file=sys.stderr, flush=True)
    
    # Process in batches
    total_count = len(sorted_endpoints)
    for batch_start in range(0, total_count, batch_size):
        batch_end = min(batch_start + batch_size, total_count)
        batch = sorted_endpoints[batch_start:batch_end]
        
        print(f"=== Batch {batch_start//batch_size + 1}: Testing endpoints {batch_start + 1}-{batch_end} of {total_count} ===", file=sys.stderr, flush=True)
        
        for idx, (domain, data) in enumerate(batch, start=batch_start + 1):
            try:
                # Safely get latency for display
                latency = data.get('latency_ms', 0) if isinstance(data, dict) else (data[0] if isinstance(data, list) and len(data) > 0 else 0)
                
                print(f"[{idx}/{total_count}] Testing {domain} (latency: {latency:.2f}ms)...", file=sys.stderr, flush=True)
                
                # Connect to VPN
                ovpn_file = ovpn_files[domain]
                if vpn_manager.connect(ovpn_file, username, password):
                    # Run speedtest
                    print(f"DEBUG: VPN connected. Calling speedtest.run_speedtest()", file=sys.stderr, flush=True)
                    result = speedtest.run_speedtest()
                    print(f"DEBUG: speedtest.run_speedtest() returned {result}", file=sys.stderr, flush=True)
                    if result:
                        if isinstance(endpoints_dict[domain], dict):
                            endpoints_dict[domain]['rx_speed_mbps'] = result['download_mbps']
                            endpoints_dict[domain]['tx_speed_mbps'] = result['upload_mbps']
                        
                        print(f"✓ {domain}: DL={result['download_mbps']} Mbps, UL={result['upload_mbps']} Mbps", file=sys.stderr, flush=True)
                    else:
                        print(f"DEBUG: Speedtest failed for {domain}", file=sys.stderr, flush=True)
                else:
                    print(f"DEBUG: VPN connection failed for {domain}", file=sys.stderr, flush=True)
                    
                # Disconnect VPN
                vpn_manager.disconnect()
                
            except Exception as e:
                print(f"DEBUG: Error testing {domain}: {e}", file=sys.stderr, flush=True)
                vpn_manager.disconnect()
        
        # Ask user if they want to continue (only in interactive mode)
        if interactive and batch_end < total_count:
            if formatting:
                formatting.output('bold', 'yellow')
            print(f"\nCompleted batch {batch_start//batch_size + 1}. {total_count - batch_end} endpoints remaining.")
            if formatting:
                formatting.output('reset')
            
            try:
                response = input("Continue with next batch? (y/n): ").strip().lower()
                if response not in ['y', 'yes']:
                    if formatting:
                        formatting.output('yellow')
                    print("VPN speedtest stopped by user.")
                    if formatting:
                        formatting.output('reset')
                    break
            except (EOFError, KeyboardInterrupt):
                if formatting:
                    formatting.output('yellow')
                print("\nVPN speedtest interrupted by user.")
                if formatting:
                    formatting.output('reset')
                break
