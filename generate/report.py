"""Report rendering for latency scan results with VPN speedtest support."""

from format.colors import Format
from json import loads
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import logging
import sys
import re

logger = logging.getLogger(__name__)


class Analyze:
    """Read results and generate filtered reports and stats."""
    formatting = Format()

    def __init__(self, res_fl: str):
        self.res_fl = res_fl

    @staticmethod
    def read_json_file(json_file: str) -> Dict[str, Any]:
        logger.info("Reading file: %s", json_file)
        with Path(json_file).open('r', encoding='utf-8') as infile:
            data = infile.read()
            json_data = loads(data)

        return json_data

    @staticmethod
    def _normalize_result(server_data: Any) -> Dict:
        """Normalize results to dict format (handles both old list and new dict formats)."""
        if isinstance(server_data, dict):
            # New format
            return {
                'latency_ms': server_data.get('latency_ms', 0),
                'ip': server_data.get('ip', 'N/A'),
                'country': server_data.get('country', 'Unknown'),
                'city': server_data.get('city', 'Unknown'),
                'rx_speed_mbps': server_data.get('rx_speed_mbps'),
                'tx_speed_mbps': server_data.get('tx_speed_mbps')
            }
        elif isinstance(server_data, list) and len(server_data) >= 4:
            # Old format: [latency, ip, country, city]
            return {
                'latency_ms': server_data[0],
                'ip': server_data[1],
                'country': server_data[2],
                'city': server_data[3],
                'rx_speed_mbps': None,
                'tx_speed_mbps': None
            }
        else:
            return {
                'latency_ms': 0,
                'ip': 'N/A',
                'country': 'Unknown',
                'city': 'Unknown',
                'rx_speed_mbps': None,
                'tx_speed_mbps': None
            }

    def get_top_performers(self, limit: Optional[int] = None, country: Optional[str] = None,
                           city: Optional[str] = None, sort_by: int = 1,
                           min_latency_limit: float = 0, max_latency_limit: float = float("inf")) -> List:
        if not limit:
            limit = 'all'

        top_servers = []

        results_json = self.read_json_file(self.res_fl)

        for domain, data in results_json.items():
            norm_data = self._normalize_result(data)
            latency = norm_data['latency_ms']
            
            if latency < min_latency_limit or latency > max_latency_limit:
                continue
                
            if country and not re.search(str(country), norm_data['country'], re.IGNORECASE):
                continue
            if city and not re.search(str(city), norm_data['city'], re.IGNORECASE):
                continue
                
            top_servers.append((
                domain,
                latency,
                norm_data['ip'],
                norm_data['country'],
                norm_data['city'],
                norm_data['rx_speed_mbps'],
                norm_data['tx_speed_mbps']
            ))

        if not top_servers:
            self.formatting.output('yellow')
            logger.info("No matching results found")
            self.formatting.output('reset')
        else:
            fields = {0: 'ENDPOINT', 1: 'LATENCY', 2: 'IP', 3: 'COUNTRY', 4: 'CITY', 5: 'DL(Mbps)', 6: 'UL(Mbps)'}

            self.formatting.output('bold', 'green')
            logger.info("Sorted by: %s", fields[min(sort_by, 4)])  # Limit to existing sort fields
            self.formatting.output('reset')

            if sort_by == 2:  # IP
                def _ipv4_key(value):
                    parts = str(value[2]).split('.')
                    if len(parts) != 4 or not all(p.isdigit() for p in parts):
                        return (999, 999, 999, 999)
                    return tuple(int(p) for p in parts)
                top_servers.sort(key=_ipv4_key)
            elif sort_by <= 4:
                top_servers.sort(key=lambda x: x[sort_by])

            if limit == 'all':
                limit = len(top_servers)
                
            # Check if any speedtest data exists
            has_speedtest = any(s[5] is not None or s[6] is not None for s in top_servers[:limit])
            
            max_endpoint_len = max(len(l[0]) for l in top_servers[0:limit])
            max_latency_len = max(len(str(l[1])) for l in top_servers[0:limit])
            max_country_len = max(len(l[3]) for l in top_servers[0:limit])
            max_city_len = max(len(l[4]) for l in top_servers[0:limit])
            
            self.formatting.output('bold', 'reverse')
            if has_speedtest:
                logger.info('{0:^5} {1:^{max_endpoint}} {2:^{max_latency}} {3:^16} {4:^{max_country}} {5:^{max_city}} {6:^10} {7:^10}'.format(
                    '#', 'ENDPOINT', 'LATENCY', 'IP', 'COUNTRY', 'CITY', 'DL(Mbps)', 'UL(Mbps)',
                    max_latency=max_latency_len + 2,
                    max_endpoint=max_endpoint_len + 2,
                    max_city=max_city_len + 2,
                    max_country=max_country_len + 2))
            else:
                logger.info('{0:^5} {1:^{max_endpoint}} {2:^{max_latency}} {3:^16} {4:^{max_country}} {5:^{max_city}}'.format(
                    '#', 'ENDPOINT', 'LATENCY', 'IP', 'COUNTRY', 'CITY',
                    max_latency=max_latency_len + 2,
                    max_endpoint=max_endpoint_len + 2,
                    max_city=max_city_len + 2,
                    max_country=max_country_len + 2))
            self.formatting.output('reset')

            for i, item in enumerate(top_servers[0:limit], 1):
                self.formatting.output('bold')
                dl_speed = f"{item[5]:.2f}" if item[5] is not None else "N/A"
                ul_speed = f"{item[6]:.2f}" if item[6] is not None else "N/A"
                
                if has_speedtest:
                    logger.info('{0:<5} {1:<{max_endpoint}} {2:<{max_latency}} {3:<16} {4:<{max_country}} {5:<{max_city}} {6:<10} {7:<10}'.format(
                        i, item[0], round(item[1], 2), item[2], item[3], item[4], dl_speed, ul_speed,
                        max_latency=max_latency_len + 2,
                        max_endpoint=max_endpoint_len + 2,
                        max_city=max_city_len + 2,
                        max_country=max_country_len + 2))
                else:
                    logger.info('{0:<5} {1:<{max_endpoint}} {2:<{max_latency}} {3:<16} {4:<{max_country}} {5:<{max_city}}'.format(
                        i, item[0], round(item[1], 2), item[2], item[3], item[4],
                        max_latency=max_latency_len + 2,
                        max_endpoint=max_endpoint_len + 2,
                        max_city=max_city_len + 2,
                        max_country=max_country_len + 2))
                self.formatting.output('reset')

            self.formatting.output('green')
            logger.info("Found: %s results", min(limit, len(top_servers)))
            self.formatting.output('reset')

        return top_servers

    def country_stats(self, sort_by: int = 2, min_latency_limit: float = 0,
                      max_latency_limit: float = float("inf")) -> None:
        country_servers = {}
        country_latency = defaultdict(list)
        country_metrics = []

        results_json = self.read_json_file(self.res_fl)

        for domain, data in results_json.items():
            norm_data = self._normalize_result(data)
            server_latency = float(norm_data['latency_ms'])
            
            if server_latency < min_latency_limit or server_latency > max_latency_limit:
                continue

            country = norm_data['country']
            country_latency[country].append(server_latency)

            if country in country_servers:
                country_servers[country] += 1
            else:
                country_servers[country] = 1

        if not country_servers:
            self.formatting.output('bold', 'yellow')
            logger.info("No results found")
            self.formatting.output('reset')
            sys.exit(0)

        for country, servers in country_servers.items():
            min_latency = round(min(country_latency[country]), 2)
            country_metrics.append((country, servers, min_latency))

        fields = {0: 'COUNTRY', 1: 'SERVERS', 2: 'LATENCY'}
        rev_sort = True if fields[sort_by] == 'SERVERS' else False
        country_metrics.sort(key=lambda x: x[sort_by], reverse=rev_sort)

        self.formatting.output('bold', 'green')
        logger.info("Sorted by: %s", fields[sort_by])
        self.formatting.output('reset')

        max_country_len = max(len(str(l[0])) for l in country_metrics)
        max_latency_len = max(len(str(l[2])) for l in country_metrics)
        self.formatting.output('bold', 'reverse')
        logger.info('{0:^5} {1:^{max_country}} {2:^8} {3:^{max_latency}}'.format(
            '#', fields[0], fields[1], fields[2],
            max_country=max_country_len + 2,
            max_latency=max_latency_len + 2))
        self.formatting.output('reset')

        for i, each in enumerate(country_metrics, 1):
            self.formatting.output('bold')
            logger.info('{0:<5} {1:<{max_country}} {2:<8} {3:<{max_latency}}'.format(
                i, each[0], each[1], round(each[2], 2),
                max_country=max_country_len + 2,
                max_latency=max_latency_len + 2))
            self.formatting.output('reset')

        self.formatting.output('bold', 'green')
        logger.info("Total Countries: %s", len(country_metrics))
        self.formatting.output('reset')

    def city_stats(self, sort_by: int = 2, min_latency_limit: float = 0,
                   max_latency_limit: float = float("inf")) -> None:
        city_servers = {}
        city_latency = defaultdict(list)
        city_metrics = []

        results_json = self.read_json_file(self.res_fl)

        for domain, data in results_json.items():
            norm_data = self._normalize_result(data)
            server_latency = float(norm_data['latency_ms'])
            
            if server_latency < min_latency_limit or server_latency > max_latency_limit:
                continue

            city = norm_data['city']
            city_latency[city].append(server_latency)

            if city in city_servers:
                city_servers[city] += 1
            else:
                city_servers[city] = 1

        for city, servers in city_servers.items():
            min_latency = round(min(city_latency[city]), 2)
            city_metrics.append((city, servers, min_latency))

        fields = {0: 'CITY', 1: 'SERVERS', 2: 'LATENCY'}
        rev_sort = True if fields[sort_by] == 'SERVERS' else False
        city_metrics.sort(key=lambda x: x[sort_by], reverse=rev_sort)

        self.formatting.output('bold', 'green')
        logger.info("Sorted by: %s", fields[sort_by])
        self.formatting.output('reset')

        max_city_len = max(len(str(l[0])) for l in city_metrics)
        max_latency_len = max(len(str(l[2])) for l in city_metrics)
        self.formatting.output('bold', 'reverse')
        logger.info('{0:^5} {1:^{max_city}} {2:^8} {3:^{max_latency}}'.format(
            '#', fields[0], fields[1], fields[2],
            max_city=max_city_len + 2,
            max_latency=max_latency_len + 2))
        self.formatting.output('reset')

        for i, each in enumerate(city_metrics, 1):
            self.formatting.output('bold')
            logger.info('{0:<5} {1:<{max_city}} {2:<8} {3:<{max_latency}}'.format(
                i, each[0], each[1], round(each[2], 2),
                max_city=max_city_len + 2,
                max_latency=max_latency_len + 2))
            self.formatting.output('reset')

        self.formatting.output('bold', 'green')
        logger.info("Total Cities: %s", len(city_metrics))
        self.formatting.output('reset')
