"""Report rendering for latency scan results."""

from format.colors import Format
from json import loads
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
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
    def read_json_file(json_file: str) -> Dict[str, List]:
        logger.info("Reading file: %s", json_file)
        with Path(json_file).open('r', encoding='utf-8') as infile:
            data = infile.read()
            json_data = loads(data)

        return json_data

    def get_top_performers(self, limit: Optional[int] = None, country: Optional[str] = None,
                           city: Optional[str] = None, sort_by: int = 1,
                           min_latency_limit: float = 0, max_latency_limit: float = float("inf")) -> List[Tuple[str, float, str, str, str]]:
        if not limit:
            limit = 'all'

        top_servers = []

        results_json = self.read_json_file(self.res_fl)

        if country and city:
            logger.info("Searching for %s servers matching %s, %s", limit, city.capitalize(), country.capitalize())
            for server in results_json.items():
                if re.search(str(country), server[1][2], re.IGNORECASE) \
                        and re.match(str(city), server[1][3], re.IGNORECASE) \
                        and min_latency_limit <= server[1][0] <= max_latency_limit:
                    top_servers.append((server[0], server[1][0], server[1][1], server[1][2], server[1][3]))
        elif country:
            logger.info("Searching for %s servers matching country %s", limit, country.capitalize())
            for server in results_json.items():
                if re.search(str(country), server[1][2], re.IGNORECASE) \
                        and min_latency_limit <= server[1][0] <= max_latency_limit:
                    top_servers.append((server[0], server[1][0], server[1][1], server[1][2], server[1][3]))
        elif city:
            logger.info("Searching for %s servers matching city %s", limit, city.capitalize())
            for server in results_json.items():
                if re.search(str(city), server[1][3], re.IGNORECASE) \
                        and min_latency_limit <= server[1][0] <= max_latency_limit:
                    top_servers.append((server[0], server[1][0], server[1][1], server[1][2], server[1][3]))
        else:
            logger.info("Searching for %s servers", limit)
            top_servers = [(server[0], server[1][0], server[1][1], server[1][2], server[1][3]) for server in
                           results_json.items() if min_latency_limit <= server[1][0] <= max_latency_limit]

        if not top_servers:
            self.formatting.output('yellow')
            if country and city:
                logger.info("No results found for %s, %s", city, country)
                logger.info("Run with --country-stats to see list of all available countries")
                logger.info("Run with --city-stats to see list of all available cities")
            elif country:
                logger.info("No results found for %s", country)
                logger.info("Run with --country-stats to see list of all available countries")
            elif city:
                logger.info("No results found for %s", city)
                logger.info("Run with --city-stats to see list of all available cities")
            else:
                logger.info("No matching results found")
            self.formatting.output('reset')
        else:
            fields = {0: 'ENDPOINT',
                      1: 'LATENCY',
                      2: 'IP',
                      3: 'COUNTRY',
                      4: 'CITY'}

            self.formatting.output('bold', 'green')
            logger.info("Sorted by: %s", fields[sort_by])
            self.formatting.output('reset')

            if fields[sort_by] == 'IP':
                def _ipv4_key(value):
                    parts = str(value).split('.')
                    if len(parts) != 4 or not all(p.isdigit() for p in parts):
                        return (999, 999, 999, 999)
                    return tuple(int(p) for p in parts)

                top_servers.sort(key=lambda x: _ipv4_key(x[sort_by]))
            else:
                top_servers.sort(key=lambda x: x[sort_by])

            if limit == 'all':
                limit = len(top_servers)
            max_endpoint_len = max(len(l[0]) for l in top_servers[0:limit])
            max_latency_len = max(len(str(l[1])) for l in top_servers[0:limit])
            max_country_len = max(len(l[3]) for l in top_servers[0:limit])
            max_city_len = max(len(l[4]) for l in top_servers[0:limit])
            self.formatting.output('bold', 'reverse')
            logger.info('{0:^5} {1:^{max_endpoint}} {2:^{max_latency}} {3:^16} {4:^{max_country}} {5:^{max_city}}'.format(
                '#',
                fields[0],
                fields[1],
                fields[2],
                fields[3],
                fields[4],
                max_latency=max_latency_len + 2,
                max_endpoint=max_endpoint_len + 2,
                max_city=max_city_len + 2,
                max_country=max_country_len + 2))
            self.formatting.output('reset')
            logger.info('{0:^5} {1:^{max_endpoint}} {2:^{max_latency}} {3:^16} {4:^{max_country}} {5:^{max_city}}'.format(
                '-' * 5,
                '-' * (max_endpoint_len + 2),
                '-' * 8,
                '-' * 16,
                '-' * (max_country_len + 2),
                '-' * (max_city_len + 2),
                max_latency=max_latency_len + 2,
                max_endpoint=max_endpoint_len + 2,
                max_city=max_city_len + 2,
                max_country=max_country_len + 2))

            for i, item in enumerate(top_servers[0:limit], 1):
                endpoint = item[0]
                latency = round(item[1], 2)
                ip = item[2]
                country = item[3]
                city = item[4]
                self.formatting.output('bold')
                try:
                    logger.info('{0:<5} {1:<{max_endpoint}} {2:<{max_latency}} {3:<16} {4:<{max_country}} {5:<{max_city}}'.format(
                        i,
                        endpoint,
                        latency,
                        ip,
                        country,
                        city,
                        max_latency=max_latency_len + 2,
                        max_endpoint=max_endpoint_len + 2,
                        max_city=max_city_len + 2,
                        max_country=max_country_len + 2))
                except (BrokenPipeError, IOError):
                    logger.error("Caught BrokenPipeError")
                self.formatting.output('reset')

            self.formatting.output('green')
            if limit <= len(top_servers):
                logger.info("Found: %s results", limit)
            else:
                logger.info("Found: %s results", len(top_servers))
            self.formatting.output('reset')

        return top_servers

    def country_stats(self, sort_by: int = 2, min_latency_limit: float = 0,
                      max_latency_limit: float = float("inf")) -> None:
        country_servers = {}
        country_latency = defaultdict(list)
        country_metrics = []

        results_json = self.read_json_file(self.res_fl)

        for item in results_json.items():
            server_latency = float(item[1][0])
            if server_latency < min_latency_limit or server_latency > max_latency_limit:
                continue

            country = item[1][2]

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

        fields = {0: 'COUNTRY',
                  1: 'SERVERS',
                  2: 'LATENCY'}

        rev_sort = True if fields[sort_by] == 'SERVERS' else False

        country_metrics.sort(key=lambda x: x[sort_by], reverse=rev_sort)

        self.formatting.output('bold', 'green')
        logger.info("Sorted by: %s", fields[sort_by])
        self.formatting.output('reset')

        max_country_len = max(len(str(l[0])) for l in country_metrics)
        max_latency_len = max(len(str(l[2])) for l in country_metrics)
        self.formatting.output('bold', 'reverse')
        logger.info('{0:^5} {1:^{max_country}} {2:^8} {3:^{max_latency}}'.format('#',
                                                                           fields[0],
                                                                           fields[1],
                                                                           fields[2],
                                                                           max_country=max_country_len + 2,
                                                                           max_latency=max_latency_len + 2))
        self.formatting.output('reset')
        logger.info('{0:^5} {1:^{max_country}} {2:^8} {3:^{max_latency}}'.format('-' * 5,
                                                                           '-' * (max_country_len + 2),
                                                                           '-' * 8,
                                                                           '-' * (max_latency_len + 2),
                                                                           max_country=max_country_len + 2,
                                                                           max_latency=max_latency_len + 2))

        for i, each in enumerate(country_metrics, 1):
            country = each[0]
            servers = each[1]
            latency = round(each[2], 2)

            self.formatting.output('bold')
            logger.info('{0:<5} {1:<{max_country}} {2:<8} {3:<{max_latency}}'.format(i,
                                                                               country,
                                                                               servers,
                                                                               latency,
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

        for item in results_json.items():
            server_latency = float(item[1][0])
            if server_latency < min_latency_limit or server_latency > max_latency_limit:
                continue

            city = item[1][3]

            city_latency[city].append(server_latency)

            if city in city_servers:
                city_servers[city] += 1
            else:
                city_servers[city] = 1

        for city, servers in city_servers.items():
            min_latency = round(min(city_latency[city]), 2)
            city_metrics.append((city, servers, min_latency))

        city_metrics.sort(key=lambda x: x[sort_by])

        fields = {0: 'CITY',
                 1: 'SERVERS',
                 2: 'LATENCY'}

        rev_sort = True if fields[sort_by] == 'SERVERS' else False

        city_metrics.sort(key=lambda x: x[sort_by], reverse=rev_sort)

        self.formatting.output('bold', 'green')
        logger.info("Sorted by: %s", fields[sort_by])
        self.formatting.output('reset')

        max_city_len = max(len(str(l[0])) for l in city_metrics)
        max_latency_len = max(len(str(l[2])) for l in city_metrics)
        self.formatting.output('bold', 'reverse')
        logger.info('{0:^5} {1:^{max_city}} {2:^8} {3:^{max_latency}}'.format('#',
                                                                        fields[0],
                                                                        fields[1],
                                                                        fields[2],
                                                                        max_city=max_city_len + 2,
                                                                        max_latency=max_latency_len + 2))
        self.formatting.output('reset')
        logger.info('{0:^5} {1:^{max_city}} {2:^8} {3:^{max_latency}}'.format('-' * 5,
                                                                        '-' * (max_city_len + 2),
                                                                        '-' * 8,
                                                                        '-' * (max_latency_len + 2),
                                                                        max_city=max_city_len + 2,
                                                                        max_latency=max_latency_len + 2))

        for i, each in enumerate(city_metrics, 1):
            city = each[0]
            servers = each[1]
            latency = round(each[2], 2)
            self.formatting.output('bold')
            logger.info('{0:<5} {1:<{max_city}} {2:<8} {3:<{max_latency}}'.format(i,
                                                                            city,
                                                                            servers,
                                                                            latency,
                                                                            max_city=max_city_len + 2,
                                                                            max_latency=max_latency_len + 2))
            self.formatting.output('reset')

        self.formatting.output('bold', 'green')
        logger.info("Total Cities: %s", len(city_metrics))
        self.formatting.output('reset')
