"""Latency scanning and GeoIP enrichment for target endpoints."""

import os
from validate.file import exists as file_exists
from format.colors import Format
from datetime import timedelta
from collections import OrderedDict
from subprocess import run, PIPE
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
import threading
from json import dump
from pathlib import Path
import logging
import geoip2.database
import platform
import re
import socket
import sys
import time

logger = logging.getLogger(__name__)


class Scanner:
    """Scan a list of targets, ping them, and write GeoIP-enriched results."""
    formatting = Format()

    def __init__(self, targets_file, city_db, country_db, results_json, excl_countries_fle, include_countries=None):
        self.targets_file = targets_file
        self.city_db = city_db
        self.country_db = country_db
        self.results_json = results_json
        self.exclude_countries_fle = excl_countries_fle
        self.include_countries = include_countries

    @staticmethod
    def write_json_file(json_file: str, data: Dict[str, List]) -> None:
        print("Creating json file:", json_file)
        with Path(json_file).open('w', encoding='utf-8') as outfile:
            dump(data, outfile, indent=2)
        print("DONE")

    def get_servers_list(self) -> Optional[List[str]]:
        if not file_exists(self.targets_file):
            return None

        logger.info("Reading targets from: %s", self.targets_file)
        with Path(self.targets_file).open('r', encoding='utf-8') as f:
            lines = f.readlines()
            servers = [line.strip().rstrip('\n') for line in lines if len(line) > 1]

        if len(servers) < 1:
            self.formatting.output('bold', 'red')
            logger.error("Error: %s does not have any targets", self.targets_file)
            self.formatting.output('reset')
            raise ValueError(f"Error: {self.targets_file} does not have any targets")

        servers.sort(key=str.lower)

        logger.info("Found total of %s targets", len(servers))

        return servers

    def exclude_countries(self) -> Optional[List[str]]:
        try:
            with Path(self.exclude_countries_fle).open('r', encoding='utf-8') as f:
                lines = f.readlines()
                excludes = [line.rstrip('\n') for line in lines if len(line) > 1]
        except FileNotFoundError:
            excludes = None
            self.formatting.output('yellow')
            logger.info("INFO: No countries were excluded from scan")
            logger.info('To exclude countries, create file "%s" with country name per line', self.exclude_countries_fle)
            self.formatting.output('reset')

        return excludes

    def scan(self, pings_num: int = 1, timeout_ms: int = 1000, workers: int = 20, all_a_records: bool = False, progress_container: Dict = None, vpn_speedtest: bool = False, vpn_ovpn_dir: str = 'ovpn', vpn_username: str = '', vpn_password: str = '', vpn_batch_size: int = 20, vpn_batch_interactive: bool = True, vpn_selected_domains: List[str] = None, stop_event: threading.Event = None) -> Dict[str, List]:
        domains = self.get_servers_list()
        excl_countries = None
        include_countries = self.include_countries

        endpoints_list: List[Tuple[str, float, str, str, str, Optional[float], Optional[float]]] = []
        endpoints_dict: "OrderedDict[str, List]" = OrderedDict()
        
        # Load existing results for merging
        existing_results = {}
        if self.results_json and os.path.exists(self.results_json):
            try:
                import json
                with open(self.results_json, 'r', encoding='utf-8') as f:
                    existing_results = json.load(f)
                    # Handle old list format conversion
                    if isinstance(existing_results, list):
                        temp_results = {}
                        for entry in existing_results:
                            if isinstance(entry, dict) and 'domain' in entry:
                                domain = entry.pop('domain')
                                temp_results[domain] = entry
                        existing_results = temp_results
            except Exception as e:
                logger.warning(f"Could not load existing results for merging: {e}")

        skipped_total = 0
        errors_total = 0

        city_reader = geoip2.database.Reader(self.city_db)
        country_reader = geoip2.database.Reader(self.country_db)
        lock = threading.Lock()

        if self.exclude_countries():
            excl_countries = sorted(self.exclude_countries())
            logger.info("Excluding results from: %s", excl_countries)
        excl_countries_norm = {c.strip().casefold() for c in excl_countries} if excl_countries else None
        include_countries_norm = {c.strip().casefold() for c in include_countries} if include_countries else None

        self.formatting.output('bold')
        logger.info("Measuring latency to %s servers", len(domains))
        logger.info("Pings: %s", pings_num)
        logger.info("Workers: %s", workers)
        logger.info("Timeout: %sms", timeout_ms)
        logger.info("All A records: %s", all_a_records)
        logger.info("Started: %s", time.strftime("%d/%m/%Y %H:%M:%S"))
        self.formatting.output('reset')

        start_scan = time.time()
        start_time = time.strftime("%d/%m/%Y %H:%M:%S")

        progress = progress_container if progress_container is not None else {"done": 0, "total": 0}
        targets = []
        for domain in domains:
            if stop_event and stop_event.is_set():
                break
            try:
                resolv = socket.gethostbyname_ex(domain)
                ips = resolv[2]
                if not ips:
                    raise ValueError('No IPs returned')
            except (socket.gaierror, socket.herror):
                self.formatting.output('red')
                print('Unable to resolve', domain, 'Skipping...')
                errors_total += 1
                self.formatting.output('reset')
                continue
            except Exception as error:
                self.formatting.output('red')
                print('Error with endpoint:', domain, 'Skipping...')
                print(error)
                errors_total += 1
                self.formatting.output('reset')
                continue

            if not all_a_records:
                ips = [ips[0]]

            for ip in ips:
                targets.append((domain, ip))

        total_targets = len(targets)
        progress["total"] = total_targets

        tasks = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for domain, ip in targets:
                if stop_event and stop_event.is_set():
                    break
                tasks.append(executor.submit(
                    self._scan_one,
                    domain,
                    ip,
                    pings_num,
                    timeout_ms,
                    excl_countries_norm,
                    include_countries_norm,
                    city_reader,
                    country_reader,
                    lock,
                    progress
                ))

            for future in as_completed(tasks):
                result = future.result()
                if result is None:
                    continue
                status, payload = result
                if status == 'ok':
                    endpoints_list.append(payload)
                elif status == 'skipped':
                    skipped_total += 1
                elif status == 'error':
                    errors_total += 1

        endpoints_list.sort(key=lambda x: x[1])

        retrieved_total = int(total_targets) - (skipped_total + errors_total)

        finish_time = time.strftime("%d/%m/%Y %H:%M:%S")
        finish_scan = time.time()
        t_diff = float(finish_scan) - float(start_scan)
        t_finish = timedelta(seconds=int(t_diff))

        self.formatting.output('bold', 'blue')
        logger.info("Started scan:    %s", start_time)
        logger.info("Finished scan:   %s", finish_time)
        logger.info("Scan duration:   %s", t_finish)

        if excl_countries:
            logger.info("Excluded countries: %s", excl_countries)
        logger.info("Excluded:        %s / %s", skipped_total, total_targets)
        logger.info("Errors:          %s / %s", errors_total, total_targets)
        logger.info("Total Retrieved:  %s / %s", retrieved_total, len(domains))

        for item in endpoints_list:
            domain = item[0]
            # Merge with existing speedtest results if available
            rx_speed = item[5]
            tx_speed = item[6]
            
            if domain in existing_results:
                old_data = existing_results[domain]
                if isinstance(old_data, dict):
                    if rx_speed is None: rx_speed = old_data.get('rx_speed_mbps')
                    if tx_speed is None: tx_speed = old_data.get('tx_speed_mbps')
            
            endpoints_dict[domain] = {
                'latency_ms': item[1],
                'ip': item[2],
                'country': item[3],
                'city': item[4],
                'rx_speed_mbps': rx_speed,
                'tx_speed_mbps': tx_speed
            }

        if endpoints_list:
            self.write_json_file(json_file=self.results_json, data=endpoints_dict)
            self.formatting.output('reset')
        else:
            self.formatting.output('red')
            print("Failed to ping any targets from the list")
            self.formatting.output('reset')

        # Perform VPN speedtests if requested
        if vpn_speedtest and vpn_ovpn_dir and vpn_username and vpn_password:
            self._perform_vpn_speedtests(
                endpoints_dict, 
                vpn_ovpn_dir, 
                vpn_username, 
                vpn_password,
                progress,
                batch_size=vpn_batch_size,
                interactive=vpn_batch_interactive,
                selected_domains=vpn_selected_domains
            )
            # Save results after speedtests
            if endpoints_dict:
                self.write_json_file(json_file=self.results_json, data=endpoints_dict)

        return endpoints_dict

    @staticmethod
    def _ping_avg_latency(ip: str, pings_num: int, timeout_ms: int) -> Optional[float]:
        # Use timeout per ping
        system = platform.system().lower()
        if system == 'windows':
            cmd = ["ping", "-n", str(pings_num), "-w", str(timeout_ms), ip]
        else:
            timeout_s = max(1, int(round(timeout_ms / 1000)))
            cmd = ["ping", "-c", str(pings_num), "-W", str(timeout_s), ip]

        result = run(cmd, stdout=PIPE).stdout.decode('UTF-8', errors='ignore')

        if system == 'windows':
            # Example: "Average = 23ms"
            match = re.search(r'Average\s*=\s*(\d+)\s*ms', result, re.IGNORECASE)
            if match:
                return float(match.group(1))
            return None

        # Example: "rtt min/avg/max/mdev = 12.3/23.4/..."
        match = re.search(r'=\s*([\d\.]+)/([\d\.]+)/', result)
        if match:
            return float(match.group(2))
        return None

    def _scan_one(self, domain: str, ip: str, pings_num: int, timeout_ms: int,
                  excl_countries: Optional[set], include_countries: Optional[set], city_reader, country_reader,
                  lock: threading.Lock, progress: Dict[str, int]) -> Optional[Tuple[str, Optional[Tuple[str, float, str, str, str, Optional[float], Optional[float]]]]]:
        try:
            try:
                country_result = country_reader.country(ip)
                country = country_result.country.name
                if not country:
                    raise ValueError()
            except Exception:
                with lock:
                    self.formatting.output('yellow')
                    print('Unable to determine country for', ip, 'setting country to Unknown')
                    self.formatting.output('reset')
                country = 'Unknown'

            try:
                city_result = city_reader.city(ip)
                city = city_result.city.name
                if not city:
                    raise ValueError()
            except Exception:
                with lock:
                    self.formatting.output('yellow')
                    print('Unable to determine city for', ip, 'setting city to Unknown')
                    self.formatting.output('reset')
                city = 'Unknown'
        except Exception as error:
            with lock:
                self.formatting.output('red')
                progress["done"] += 1
                total = progress.get("total", 0)
                prefix = f'({progress["done"]}/{total}) ' if total else ''
                print(prefix + 'Error with endpoint:', domain, 'Skipping...')
                print(error)
                self.formatting.output('reset')
            return ('error', None)

        if excl_countries and country and country.casefold() in excl_countries:
            with lock:
                self.formatting.output('yellow')
                progress["done"] += 1
                total = progress.get("total", 0)
                prefix = f'({progress["done"]}/{total}) ' if total else ''
                print(prefix + 'Excluding', domain, 'in', country)
                self.formatting.output('reset')
            return ('skipped', None)
        if include_countries is not None and (not country or country.casefold() not in include_countries):
            with lock:
                self.formatting.output('yellow')
                progress["done"] += 1
                total = progress.get("total", 0)
                prefix = f'({progress["done"]}/{total}) ' if total else ''
                print(prefix + 'Skipping', domain, 'in', country, '(not in include_countries)')
                self.formatting.output('reset')
            return ('skipped', None)

        avg_latency = self._ping_avg_latency(ip, pings_num, timeout_ms)
        if avg_latency is None:
            with lock:
                self.formatting.output('red')
                progress["done"] += 1
                total = progress.get("total", 0)
                prefix = f'({progress["done"]}/{total}) ' if total else ''
                print(prefix + 'Error: No response time received from', domain, 'Skipping...')
                self.formatting.output('reset')
            return ('error', None)

        with lock:
            self.formatting.output('green')
            progress["done"] += 1
            total = progress.get("total", 0)
            prefix = f'({progress["done"]}/{total}) ' if total else ''
            # Output to both console and log buffer
            msg = f"{prefix}{domain} {avg_latency} {ip} {country} {city}"
            print(msg)
            logger.info(msg)
            self.formatting.output('reset')

        return ('ok', (domain, avg_latency, ip, country, city, None, None))

    def _perform_vpn_speedtests(self, endpoints_dict: Dict, ovpn_dir: str, username: str, password: str, progress: Dict, batch_size: int = 20, interactive: bool = True, selected_domains: List[str] = None, stop_event: threading.Event = None) -> None:
        """Perform VPN speedtests on endpoints that have matching .ovpn files."""
        from generate.vpn_batch_helper import _perform_vpn_speedtests_batch
        _perform_vpn_speedtests_batch(
            endpoints_dict, ovpn_dir, username, password, progress,
            batch_size, interactive, selected_domains, self.formatting,
            stop_event=stop_event
        )

