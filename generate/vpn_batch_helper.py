"""VPN speedtest helper - batch processing logic."""

def _perform_vpn_speedtests_batch(endpoints_dict, ovpn_dir, username, password, progress, batch_size=20, interactive=True, selected_domains=None, formatting=None, stop_event=None, results_file=None, source='user'):
    """Perform VPN speedtests on endpoints that have matching .ovpn files with batch processing."""
    import os
    import json
    
    batch_size = max(1, min(9999, int(batch_size)))
    import logging
    from datetime import datetime, timezone
    from pathlib import Path
    from generate.vpn import VPNManager
    from generate.speedtest import SpeedTest
    
    import sys
    logger = logging.getLogger(__name__)
    
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
    # Handle both old list format [latency, ip, country, city] and new dict format
    def get_latency(entry):
        if isinstance(entry, dict):
            return entry.get('latency_ms', 9999)
        elif isinstance(entry, (list, tuple)) and len(entry) > 0:
            return entry[0]
        return 9999

    sorted_endpoints = sorted(matched_endpoints.items(), key=lambda x: get_latency(x[1]))
    
    if formatting:
        formatting.enabled = False
    print(f"Performing VPN speedtests on {len(sorted_endpoints)} endpoints...", file=sys.stderr, flush=True)
    logger.info(f"Performing VPN speedtests on {len(sorted_endpoints)} endpoints...")
    
    vpn_manager = VPNManager()
    speedtest = SpeedTest()
    
    # Process in batches
    total_count = len(sorted_endpoints)
    progress['total'] = total_count
    progress['done'] = 0
    succeeded = 0
    vpn_failed = 0
    speedtest_failed = 0
    errors = 0
    
    for batch_start in range(0, total_count, batch_size):
        if stop_event and stop_event.is_set():
            logger.info("VPN speedtest stopped by user signal")
            break
            
        batch_end = min(batch_start + batch_size, total_count)
        batch = sorted_endpoints[batch_start:batch_end]
        
        print(f"=== Batch {batch_start//batch_size + 1}: Testing endpoints {batch_start + 1}-{batch_end} of {total_count} ===", file=sys.stderr, flush=True)
        logger.info(f"=== Batch {batch_start//batch_size + 1}: Testing endpoints {batch_start + 1}-{batch_end} of {total_count} ===")
        
        for idx, (domain, data) in enumerate(batch, start=batch_start + 1):
            if stop_event and stop_event.is_set():
                break
            progress['done'] = idx
            try:
                # Safely get latency for display
                latency = data.get('latency_ms', 0) if isinstance(data, dict) else (data[0] if isinstance(data, list) and len(data) > 0 else 0)
                
                print(f"[{idx}/{total_count}] Testing {domain} (latency: {latency:.2f}ms)...", file=sys.stderr, flush=True)
                logger.info(f"[{idx}/{total_count}] Testing {domain} (latency: {latency:.2f}ms)...")
                
                # Connect to VPN
                ovpn_file = ovpn_files[domain]
                now_iso = datetime.now(timezone.utc).isoformat()
                if vpn_manager.connect(ovpn_file, username, password):
                    # Run speedtest
                    result = speedtest.run_speedtest()
                    if result:
                        if isinstance(endpoints_dict[domain], dict):
                            endpoints_dict[domain]['rx_speed_mbps'] = result['download_mbps']
                            endpoints_dict[domain]['tx_speed_mbps'] = result['upload_mbps']
                            endpoints_dict[domain]['speedtest_timestamp'] = now_iso
                            endpoints_dict[domain].pop('speedtest_failed_timestamp', None)
                            endpoints_dict[domain].pop('speedtest_failed_reason', None)
                            history = endpoints_dict[domain].setdefault('history', [])
                            history.append({'timestamp': now_iso, 'event': 'success', 'source': source,
                                            'download_mbps': result['download_mbps'], 'upload_mbps': result['upload_mbps']})
                        
                        print(f"\u2713 {domain}: DL={result['download_mbps']} Mbps, UL={result['upload_mbps']} Mbps", file=sys.stderr, flush=True)
                        logger.info(f"\u2713 {domain}: DL={result['download_mbps']} Mbps, UL={result['upload_mbps']} Mbps")
                        succeeded += 1
                    else:
                        if isinstance(endpoints_dict[domain], dict):
                            endpoints_dict[domain]['speedtest_failed_timestamp'] = now_iso
                            endpoints_dict[domain]['speedtest_failed_reason'] = 'speedtest_failed'
                            history = endpoints_dict[domain].setdefault('history', [])
                            history.append({'timestamp': now_iso, 'event': 'speedtest_failed', 'source': source})
                        logger.info(f"\u2717 {domain}: Speedtest failed (no result)")
                        speedtest_failed += 1
                else:
                    if isinstance(endpoints_dict[domain], dict):
                        endpoints_dict[domain]['speedtest_failed_timestamp'] = now_iso
                        endpoints_dict[domain]['speedtest_failed_reason'] = 'vpn_failed'
                        history = endpoints_dict[domain].setdefault('history', [])
                        history.append({'timestamp': now_iso, 'event': 'vpn_failed', 'source': source})
                    logger.info(f"\u2717 {domain}: VPN connection failed")
                    vpn_failed += 1
                    
                # Disconnect VPN
                vpn_manager.disconnect()

                # Incremental save after each server
                if results_file:
                    try:
                        with open(results_file, 'w', encoding='utf-8') as rf:
                            json.dump(endpoints_dict, rf, indent=2)
                    except Exception:
                        pass
                
            except Exception as e:
                errors += 1
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

    # Summary report
    tested = succeeded + vpn_failed + speedtest_failed + errors
    summary = f"VPN Speedtest Report: {tested}/{total_count} tested — {succeeded} succeeded, {vpn_failed} VPN connection failed, {speedtest_failed} speedtest failed, {errors} errors"
    logger.info(summary)
    return {'total': total_count, 'tested': tested, 'succeeded': succeeded, 'vpn_failed': vpn_failed, 'speedtest_failed': speedtest_failed, 'errors': errors}
