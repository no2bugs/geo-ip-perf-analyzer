from format.colors import Format
from json import loads
from collections import defaultdict
import sys
import re


class Analyze:
    formatting = Format()

    def __init__(self, res_fl):
        self.res_fl = res_fl

    @staticmethod
    def read_json_file(json_file):
        print("Reading file:", json_file, '\n')
        with open(json_file, 'r') as infile:
            data = infile.read()
            json_data = loads(data)

        return json_data

    def get_top_performers(self, limit=None, country=None, city=None, sort_by=1, min_latency_limit=0, max_latency_limit=float("inf")):
        if not limit:
            limit = 'all'

        top_servers = []

        results_json = self.read_json_file(self.res_fl)

        if country and city:
            print('Searching for', limit, 'servers matching', city.capitalize() + ',', country.capitalize(), '\n')
            for server in results_json.items():
                if re.search(str(country), server[1][2], re.IGNORECASE) \
                        and re.match(str(city), server[1][3], re.IGNORECASE) \
                        and min_latency_limit <= server[1][0] <= max_latency_limit:
                    top_servers.append((server[0], server[1][0], server[1][1], server[1][2], server[1][3]))
        elif country:
            print('Searching for', limit, 'servers matching country', country.capitalize(), '\n')
            for server in results_json.items():
                if re.search(str(country), server[1][2], re.IGNORECASE) \
                        and min_latency_limit <= server[1][0] <= max_latency_limit:
                    top_servers.append((server[0], server[1][0], server[1][1], server[1][2], server[1][3]))
        elif city:
            print('Searching for', limit, 'servers matching city', city.capitalize(), '\n')
            for server in results_json.items():
                if re.search(str(city), server[1][3], re.IGNORECASE) \
                        and min_latency_limit <= server[1][0] <= max_latency_limit:
                    top_servers.append((server[0], server[1][0], server[1][1], server[1][2], server[1][3]))
        else:
            print('Searching for', limit, 'servers\n')
            top_servers = [(server[0], server[1][0], server[1][1], server[1][2], server[1][3]) for server in
                           results_json.items() if min_latency_limit <= server[1][0] <= max_latency_limit]

        if not top_servers:
            self.formatting.output('yellow')
            if country and city:
                print('No results found for', city + ',', country)
                print('Run with --country-stats to see list of all available countries')
                print('Run with --city-stats to see list of all available cities')
            elif country:
                print('No results found for', country)
                print('Run with --country-stats to see list of all available countries')
            elif city:
                print('No results found for', city)
                print('Run with --city-stats to see list of all available cities')
            else:
                print('No matching results found')
            self.formatting.output('reset')
        else:
            fields = {0: 'ENDPOINT',
                      1: 'LATENCY',
                      2: 'IP',
                      3: 'COUNTRY',
                      4: 'CITY'}

            self.formatting.output('bold', 'green')
            print('Sorted by:', fields[sort_by])
            self.formatting.output('reset')

            if fields[sort_by] == 'IP':
                top_servers.sort(key=lambda x: (int(str(x[sort_by]).split('.')[0]),
                                                int(str(x[sort_by]).split('.')[1]),
                                                int(str(x[sort_by]).split('.')[2]),
                                                int(str(x[sort_by]).split('.')[3])))
            else:
                top_servers.sort(key=lambda x: x[sort_by])

            if limit == 'all':
                limit = len(top_servers)
            max_endpoint_len = max(len(l[0]) for l in top_servers[0:limit])
            max_latency_len = max(len(str(l[1])) for l in top_servers[0:limit])
            max_country_len = max(len(l[3]) for l in top_servers[0:limit])
            max_city_len = max(len(l[4]) for l in top_servers[0:limit])
            self.formatting.output('bold', 'reverse')
            print('{0:^5} {1:^{max_endpoint}} {2:^{max_latency}} {3:^16} {4:^{max_country}} {5:^{max_city}}'.format(
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
            print('{0:^5} {1:^{max_endpoint}} {2:^{max_latency}} {3:^16} {4:^{max_country}} {5:^{max_city}}'.format(
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
                    print('{0:<5} {1:<{max_endpoint}} {2:<{max_latency}} {3:<16} {4:<{max_country}} {5:<{max_city}}'.format(
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
                    print('Caught BrokenPipeError')
                self.formatting.output('reset')
                sys.stderr.close()

            self.formatting.output('green')
            if limit <= len(top_servers):
                print('\nFound: {0} results'.format(limit))
            else:
                print('\nFound: {0} results'.format(len(top_servers)))
            self.formatting.output('reset')

        return top_servers

    def country_stats(self, sort_by=2, min_latency_limit=0, max_latency_limit=float("inf")):
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
            print('No results found')
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
        print('Sorted by:', fields[sort_by])
        self.formatting.output('reset')

        max_country_len = max(len(str(l[0])) for l in country_metrics)
        max_latency_len = max(len(str(l[2])) for l in country_metrics)
        self.formatting.output('bold', 'reverse')
        print('{0:^5} {1:^{max_country}} {2:^8} {3:^{max_latency}}'.format('#',
                                                                           fields[0],
                                                                           fields[1],
                                                                           fields[2],
                                                                           max_country=max_country_len + 2,
                                                                           max_latency=max_latency_len + 2))
        self.formatting.output('reset')
        print('{0:^5} {1:^{max_country}} {2:^8} {3:^{max_latency}}'.format('-' * 5,
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
            print('{0:<5} {1:<{max_country}} {2:<8} {3:<{max_latency}}'.format(i,
                                                                               country,
                                                                               servers,
                                                                               latency,
                                                                               max_country=max_country_len + 2,
                                                                               max_latency=max_latency_len + 2))
            self.formatting.output('reset')

        self.formatting.output('bold', 'green')
        print("\nTotal Countries:", len(country_metrics))
        self.formatting.output('reset')

    def city_stats(self, sort_by=2, min_latency_limit=0, max_latency_limit=float("inf")):
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
        print('Sorted by:', fields[sort_by])
        self.formatting.output('reset')

        max_city_len = max(len(str(l[0])) for l in city_metrics)
        max_latency_len = max(len(str(l[2])) for l in city_metrics)
        self.formatting.output('bold', 'reverse')
        print('{0:^5} {1:^{max_city}} {2:^8} {3:^{max_latency}}'.format('#',
                                                                        fields[0],
                                                                        fields[1],
                                                                        fields[2],
                                                                        max_city=max_city_len + 2,
                                                                        max_latency=max_latency_len + 2))
        self.formatting.output('reset')
        print('{0:^5} {1:^{max_city}} {2:^8} {3:^{max_latency}}'.format('-' * 5,
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
            print('{0:<5} {1:<{max_city}} {2:<8} {3:<{max_latency}}'.format(i,
                                                                            city,
                                                                            servers,
                                                                            latency,
                                                                            max_city=max_city_len + 2,
                                                                            max_latency=max_latency_len + 2))
            self.formatting.output('reset')

        self.formatting.output('bold', 'green')
        print("\nTotal Cities:", len(city_metrics))
        self.formatting.output('reset')
