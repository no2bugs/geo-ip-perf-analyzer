from format.colors import output as format_output
from json import loads
import re


class Analyze:
    def __init__(self, res_fl):
        self.res_fl = res_fl

    def get_top_performers(self, limit, country=None, city=None):
        if not limit:
            limit = 'all'

        top_servers = []

        print("\nReading file", self.res_fl)
        with open(self.res_fl, 'r') as f:
            results = f.read()
            results_json = loads(results)

        if country and city:
            print('\nSearching for', limit, 'servers matching', city + ',', country, '\n')
            for server in results_json.items():
                if re.search(str(country), server[1][2], re.IGNORECASE) and re.match(str(city), server[1][3], re.IGNORECASE):
                    top_servers.append((server[0], server[1][0], server[1][1], server[1][2], server[1][3]))
        elif country:
            print('\nSearching for', limit, 'servers matching country', country, '\n')
            for server in results_json.items():
                if re.search(str(country), server[1][2], re.IGNORECASE):
                    top_servers.append((server[0], server[1][0], server[1][1], server[1][2], server[1][3]))
        elif city:
            print('\nSearching for', limit, 'servers matching city', city, '\n')
            for server in results_json.items():
                if re.search(str(city), server[1][3], re.IGNORECASE):
                    top_servers.append((server[0], server[1][0], server[1][1], server[1][2], server[1][3]))
        else:
            print('\nSearching for', limit, 'servers\n')
            top_servers = [(server[0], server[1][0], server[1][1], server[1][2], server[1][3]) for server in
                           results_json.items()]

        if not top_servers:
            format_output('yellow')
            if country and city:
                print('No results found for', city + ',', country)
                print('Run with --country-stats to see list of all available countries')
                print('Run with --city-stats to see list of all available cities')
            elif country:
                print('No results found for', country)
                print('Run with --country-stats to see list of all available countries')
            else:
                print('No results found for', city)
                print('Run with --city-stats to see list of all available cities')
            format_output('reset')
        else:
            if limit == 'all':
                limit = len(top_servers)
            max_endpoint_len = max(len(l[0]) for l in top_servers[0:limit])
            max_latency_len = max(len(str(l[1])) for l in top_servers[0:limit])
            max_country_len = max(len(l[3]) for l in top_servers[0:limit])
            max_city_len = max(len(l[4]) for l in top_servers[0:limit])
            format_output('bold', 'reverse')
            print('{0:^5} {1:^{max_endpoint}} {2:^{max_latency}} {3:^16} {4:^{max_country}} {5:^{max_city}}'.format(
                '#',
                'ENDPOINT',
                'LATENCY',
                'IP',
                'COUNTRY',
                'CITY',
                max_latency=max_latency_len + 2,
                max_endpoint=max_endpoint_len + 2,
                max_city=max_city_len + 2,
                max_country=max_country_len + 2))
            format_output('reset')
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
                format_output('bold')
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
                format_output('reset')

            format_output('green')
            if limit <= len(top_servers):
                print('\nFound: {0} results'.format(limit))
            else:
                print('\nFound: {0} results'.format(len(top_servers)))
            format_output('reset')

        return top_servers


    def country_stats(self, sort_by=2):
        country_servers = {}
        country_latency = {}
        country_metrics = []

        print("\nReading file", self.res_fl, '\n')
        with open(self.res_fl, 'r') as f:
            results = f.read()
            results_json = loads(results)

        for item in results_json.items():
            latency = item[1][0]
            country = item[1][2]

            if country in country_servers:
                country_servers[country] += 1
                country_latency[country] += latency
            else:
                country_servers[country] = 1
                country_latency[country] = latency

        for country, servers in country_servers.items():
            avg_latency = round(country_latency[country] / servers, 2)
            country_metrics.append((country, servers, avg_latency))

        country_metrics.sort(key=lambda x: x[sort_by])

        max_country_len = max(len(str(l[0])) for l in country_metrics)
        max_latency_len = max(len(str(l[2])) for l in country_metrics)
        format_output('bold', 'reverse')
        print('{0:^5} {1:^{max_country}} {2:^8} {3:^{max_latency}}'.format('#',
                                                                           'COUNTRY',
                                                                           'SERVERS',
                                                                           'LATENCY',
                                                                           max_country=max_country_len + 2,
                                                                           max_latency=max_latency_len + 2))
        format_output('reset')
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
            format_output('bold')
            print('{0:<5} {1:<{max_country}} {2:<8} {3:<{max_latency}}'.format(i,
                                                                               country,
                                                                               servers,
                                                                               latency,
                                                                               max_country=max_country_len + 2,
                                                                               max_latency=max_latency_len + 2))
            format_output('reset')

        format_output('bold', 'green')
        print("\nTotal Countries:", len(country_metrics))
        format_output('reset')


    def city_stats(self, sort_by=2):
        city_servers = {}
        city_latency = {}
        city_metrics = []

        print("\nReading file", self.res_fl, '\n')
        with open(self.res_fl, 'r') as f:
            results = f.read()
            results_json = loads(results)

        for item in results_json.items():
            latency = item[1][0]
            city = item[1][3]

            if city in city_servers:
                city_servers[city] += 1
                city_latency[city] += latency
            else:
                city_servers[city] = 1
                city_latency[city] = latency

        for city, servers in city_servers.items():
            avg_latency = round(city_latency[city] / servers, 2)
            city_metrics.append((city, servers, avg_latency))

        city_metrics.sort(key=lambda x: x[sort_by])

        max_city_len = max(len(str(l[0])) for l in city_metrics)
        max_latency_len = max(len(str(l[2])) for l in city_metrics)
        format_output('bold', 'reverse')
        print('{0:^5} {1:^{max_city}} {2:^8} {3:^{max_latency}}'.format('#',
                                                                        'CITY',
                                                                        'SERVERS',
                                                                        'LATENCY',
                                                                        max_city=max_city_len + 2,
                                                                        max_latency=max_latency_len + 2))
        format_output('reset')
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
            format_output('bold')
            print('{0:<5} {1:<{max_city}} {2:<8} {3:<{max_latency}}'.format(i,
                                                                            city,
                                                                            servers,
                                                                            latency,
                                                                            max_city=max_city_len + 2,
                                                                            max_latency=max_latency_len + 2))
            format_output('reset')

        format_output('bold', 'green')
        print("\nTotal Cities:", len(city_metrics))
        format_output('reset')