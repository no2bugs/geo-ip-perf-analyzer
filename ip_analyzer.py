#!/usr/bin/env python3

from subprocess import run, PIPE
from json import dump, loads
from collections import OrderedDict
from datetime import timedelta
import time
import geoip2.database
import requests, socket
import tarfile
import sys, os, shutil
import argparse
import re


class ColoredArgParser(argparse.ArgumentParser):
    color_dict = {'RED' : '1;31', 'GREEN' : '0;32',
                  'YELLOW' : '0;33', 'BLUE' : '0;34'}

    def print_usage(self, file = None):
        if file is None:
            file = sys.stdout
        self._print_message(self.format_usage()[0].upper() +
                            self.format_usage()[1:],
                            file, self.color_dict['RED'])

    def print_help(self, file = None):
        if file is None:
            file = sys.stdout
        self._print_message(self.format_help()[0].upper() +
                            self.format_help()[1:],
                            file, self.color_dict['BLUE'])

    def _print_message(self, message, file = None, color = None):
        if message:
            if file is None:
                file = sys.stderr
            if color is None:
                file.write(message)
            else:
                file.write('\x1b[' + color + 'm' + message.strip() + '\x1b[0m\n')


def check_python_version(v):
    v = str(v).split('.')
    try:
        if not 1 < int(v[0]) <= 3:
            raise ValueError('Error: You are requiring invalid Python version', v[0])
    except ValueError as e:
        print(e)
        sys.exit(1)
    if sys.version_info[0] != int(v[0]):
        print('This script requires Python version',v[0] + '+')
        print('You are using {0}.{1}.{2} {3}'.format(sys.version_info[0],
                                                     sys.version_info[1],
                                                     sys.version_info[2],
                                                     sys.version_info[3]))
        sys.exit(1)


def web_request(url, time_out=60):
    try:
        resp = requests.get(url,
                            timeout=time_out,
                            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'})

        if (100 <= resp.status_code < 600) and (resp.status_code != 200):
            raise ConnectionError('Error: Bad response code')
        print("Connected to", url)
    except ConnectionError as e:
        print(e)
        print('Returned:', resp.status_code, resp.reason)
        print()
    except Exception as e:
        print('Error: Something went wrong\n', e)
        return None

    return resp


def format_output(*options):
    choices = []

    formats = {
            'WHITE': "\033[0;97m",
            'RED': "\033[0;31m",
            'BLUE': "\033[0;34m",
            'CYAN': "\033[0;36m",
            'GREEN': "\033[0;32m",
            'YELLOW': "\033[0;33m",
            'BOLD': "\033[;1m",
            'REVERSE': "\033[;7m",
            'RESET': "\033[0m"
    }

    for item in options:
        item = str(item).upper()
        try:
            choices.append(formats[item])
        except KeyError:
            print('\nError: unknown format choice', item)
            print('Pick from:')
            for i in formats:
                print('-', i)
            sys.exit(1)

    formatting = ''.join(choices)

    sys.stdout.write(formatting)

    return formatting


def file_exists(file):
    return True if os.path.isfile(file) else False


def download_geolite_dbs(dbs, force_dl=False):
    db_files = []

    for db_file, db_url in dbs.items():
        if not force_dl:
            print('Looking for geolite db file', db_file)
            if file_exists(db_file):
                print('Found geolite db file', db_file, '\n')
                db_files.append(db_file)
                continue

        if not file_exists(db_file):
            print('No', db_file, 'found')
        else:
            print('Forcing refresh of geolite db', db_file)
            os.remove(db_file)

        r = web_request(db_url)

        print('Downloading', db_url)

        db_tar = db_url.split('/')[-1]
        with open(db_tar, 'wb') as f:
            f.write(r.content)
        print('Finished downloading', db_tar)

        print('Extracting...')
        tf = tarfile.open(db_tar, 'r:gz')
        tf.extractall()

        print('Deleting', db_tar, 'file')
        os.remove(db_tar)

        target_dir = db_tar.split('.')[0]

        for root, dirs, files in os.walk('.'):
            for dir in dirs:
                if dir.find(target_dir) != -1:
                    db_dir_path=os.path.join(root, dir)
                    print('Extracted contents into', db_dir_path)
            for file in files:
                if file.find(db_file) != -1:
                    db_f_path = os.path.join(root, file)
                    print('Moving', db_f_path, 'to current path')
                    shutil.move(db_f_path, '.')

        db_files.append(db_file)

        print('Deleting', db_dir_path, 'folder')
        shutil.rmtree(db_dir_path)
        print('DONE\n')

    return db_files


def get_servers_list(from_file):
    if file_exists(from_file):
        print('Reading targets from:', from_file)
        with open(from_file, 'r') as f:
            lines = f.readlines()
            servers = [line.strip().rstrip('\n') for line in lines if len(line) > 1]

        if len(servers) < 1:
            format_output('bold', 'red')
            print('Error:', from_file, 'does not have any targets\n')
            format_output('reset')
            sys.exit(1)

        servers.sort(key=lambda x: x[0])

        print('\nFound total of', len(servers), 'targets')

        return servers
    else:
        # leaving this open for alternate ways of ingesting servers list
        print(from_file, 'not found\n', 'Nothing to do')
        sys.exit(0)


def scan(domains, city_db, country_db, results_json, exclude_countries, pings_num=1):
    endpoints_list = []
    endpoints_dict = OrderedDict()

    skipped_total = 0
    errors_total = 0

    city_reader = geoip2.database.Reader(city_db)
    country_reader = geoip2.database.Reader(country_db)

    if exclude_countries:
        print('Excluding results from:', exclude_countries)
        exclude_countries.sort()

    format_output('bold')
    print('\nMeasuring latency to', len(domains), 'servers')
    print('Pings:', pings_num)
    print('Started:', time.strftime("%d/%m/%Y %H:%M:%S"))
    format_output('reset')

    start_scan = time.time()
    start_time = time.strftime("%d/%m/%Y %H:%M:%S")

    count = 0
    for domain in domains:
        try:
            resolv = socket.gethostbyname_ex(domain)
            ip = resolv[2][0]
            try:
                country_result = country_reader.country(ip)
                country = country_result.country.name
                if not country:
                    raise ValueError()
            except Exception:
                format_output('yellow')
                print('Unable to determine country for', ip, 'setting country to Unknown')
                country = 'Unknown'
                format_output('reset')
            try:
                city_result = city_reader.city(ip)
                city = city_result.city.name
                if not city:
                    raise ValueError()
            except Exception:
                format_output('yellow')
                print('Unable to determine city for', ip, 'setting city to Unknown')
                city = 'Unknown'
                format_output('reset')
        except socket.gaierror or socket.herror:
            format_output('red')
            print('Unable to resolve', domain, 'Skipping...')
            errors_total += 1
            format_output('reset')
            continue
        except Exception as error:
            format_output('red')
            print('Error with endpoint:', domain, 'Skipping...')
            print(error)
            errors_total += 1
            format_output('reset')
            continue

        if exclude_countries and country in exclude_countries:
            print('Excluding', domain, 'in', country)
            skipped_total += 1
            continue

        result = run(["ping", "-c", str(pings_num), ip], stdout=PIPE).stdout.decode('UTF-8')

        count += 1

        try:
            lines = result.split('\n')

            response = [line.strip().rstrip('\n') for line in lines if len(line) > 1]

            avg_latency = float(response[-1].split('=')[1].split('/')[1])
        except Exception:
            format_output('red')
            print('Error: No response time received from', domain, 'Skipping...')
            errors_total += 1
            format_output('reset')
            continue

        format_output('green')
        print('(' + str(count) + "/" + str(len(domains)) + ')', domain, avg_latency, ip, country, city)
        format_output('reset')

        endpoints_list.append((domain, avg_latency, ip, country, city))

    endpoints_list.sort(key=lambda x: x[1])

    retrieved_total = int(len(domains)) - (skipped_total + errors_total)

    finish_time = time.strftime("%d/%m/%Y %H:%M:%S")
    finish_scan = time.time()
    t_diff = float(finish_scan) - float(start_scan)
    t_finish = timedelta(seconds=int(t_diff))

    format_output('bold')
    print('\nStarted scan:     ', start_time)
    print('Finished scan:    ', finish_time)
    print('Scan duration:    ', t_finish)

    if exclude_countries:
        print('\nExcluded countries:', exclude_countries)
    print('\nExcluded:        ', skipped_total, '/', len(domains))
    print('Errors:           ', errors_total, '/', len(domains))
    print('\nTotal Retrieved: ', retrieved_total, '/', len(domains))

    for item in endpoints_list:
        endpoints_dict[item[0]] = [item[1], item[2], item[3], item[4]]

    if endpoints_list:
        print('\nCreating json file', results_json)
        with open(results_json, 'w') as fp:
            dump(endpoints_dict, fp)
        print('DONE')
        format_output('reset')
    else:
        format_output('red')
        print('\nFailed to ping any targets from the list\n')
        format_output('reset')

    return endpoints_dict


def get_top_performers(res_fl, limit, country, city):
    if not limit:
        limit = 'all'

    top_servers = []

    print("\nReading file", res_fl)
    with open(res_fl, 'r') as f:
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
        top_servers = [(server[0], server[1][0], server[1][1], server[1][2], server[1][3]) for server in results_json.items()]

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
        print('\nFound: {0} results'.format(limit)) if limit <= len(top_servers) else print('\nFound: {0} results'.format(len(top_servers)))
        format_output('reset')

    return top_servers


def exclude_countries(file):
    try:
        with open(file, 'r') as f:
            lines = f.readlines()

            excludes = [line.rstrip('\n') for line in lines if len(line) > 1]
    except FileNotFoundError:
        excludes = None
        format_output('yellow')
        print('INFO: No countries were excluded from scan')
        print('To exclude countries, create file "' + excl_file + '" with country name per line\n')
        format_output('reset')

    return excludes


def country_stats(res_fl, sort_by=2):
    country_servers = {}
    country_latency = {}
    country_metrics = []

    print("\nReading file", res_fl, '\n')
    with open(res_fl, 'r') as f:
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


def city_stats(res_fl, sort_by=2):
    city_servers = {}
    city_latency = {}
    city_metrics = []

    print("\nReading file", res_fl, '\n')
    with open(res_fl, 'r') as f:
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


if __name__ == "__main__":
    check_python_version(3)

    res_file = 'results.json'
    excl_file = 'exclusions.list'

    geolite_dbs = OrderedDict([("GeoLite2-City.mmdb",
                                "https://geolite.maxmind.com/download/geoip/database/GeoLite2-City.tar.gz"),
                               ("GeoLite2-Country.mmdb",
                                "https://geolite.maxmind.com/download/geoip/database/GeoLite2-Country.tar.gz")])

    parser = ColoredArgParser(description='Performs latency scan on each domain/ip and shows top performers by location',
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-s', '--scan',
                        action='store_true',
                        help='''Perform full latency scan and generate performance report
                             ''', default=False)
    parser.add_argument('-p', '--scan-pings',
                        type=int,
                        help='''Number of pings to each IP during scan (increase for better accuracy). Default is 1
                             ''', default=1)
    parser.add_argument('-f', '--servers-file',
                        type=str,
                        help='''Read servers list from file (one domain or ip per line). Default is "servers.list"
                             ''', default='servers.list')
    parser.add_argument('-r', '--results',
                        action='store_true',
                        help='''Show top performing endpoints
                             ''', default=False)
    parser.add_argument('-l', '--results-limit',
                        type=int,
                        help='''Number of results to show
                             ''', default=None)
    parser.add_argument('-c', '--country-stats',
                        action='store_true',
                        help='''Show stats by country
                             ''', default=False)
    parser.add_argument('-t', '--search-country',
                        type=str,
                        help='''Search results by country name
                             ''', default=None)
    parser.add_argument('-i', '--city-stats',
                        action='store_true',
                        help='''Show stats by city
                             ''', default=False)
    parser.add_argument('-y', '--search-city',
                        type=str,
                        help='''Search results by city name
                             ''', default=None)
    parser.add_argument('-b', '--sort-by',
                        type=int,
                        help='''Sort by field/column number (fields start from 1). Default is 3
                             ''', default=3)
    parser.add_argument('-d', '--download-dbs',
                        action='store_true',
                        help='''Force download latest geolite dbs. Default is False
                             ''', default=False)
    args = parser.parse_args()

    pings = args.scan_pings
    top_ips_limit = args.results_limit

    if top_ips_limit is not None and top_ips_limit < 1:
        format_output('bold', 'red')
        print("Error: limit must be > 0")
        format_output('reset')
        sys.exit(1)

    targets_file = args.servers_file

    sort_field = args.sort_by - 1

    if not args.results \
            and not args.scan \
            and not args.download_dbs \
            and not args.country_stats \
            and not args.city_stats \
            and not args.search_country \
            and not args.search_city:
        parser.print_help()
        format_output('bold', 'red')
        print("\n*** Error: Pick one of the options ***\n")
        format_output('reset')
        sys.exit(1)

    if args.scan:
        if not file_exists(targets_file):
            format_output('bold', 'red')
            print('\nError: Nothing to scan\nTargets list file "' + targets_file + '" not found')
            print('Create "' + targets_file + '" with one domain or IP per line')
            print('(or point to another file with --servers-file)\n')
            format_output('reset')
            sys.exit(1)
        exclude = exclude_countries(excl_file)
        city_db, country_db = download_geolite_dbs(geolite_dbs)
        hosts = get_servers_list(from_file=args.servers_file)
        results = scan(hosts,
                        pings_num=pings,
                        city_db=city_db,
                        country_db=country_db,
                        results_json=res_file,
                        exclude_countries=exclude)
        sys.exit(0)

    if args.download_dbs:
        download_geolite_dbs(dbs=geolite_dbs, force_dl=args.download_dbs)
        if not args.results and not args.scan:
            sys.exit(0)

    if not file_exists(res_file):
        format_output('bold', 'red')
        print('\nError: Unable to produce report. Latency scan results file "' + res_file + '" is missing')
        print('Perform --scan to generate new IP/domain performance report (' + res_file + ')')
        format_output('reset')
        sys.exit(1)

    if args.country_stats:
        country_stats(res_file, sort_by=sort_field)
        sys.exit(0)

    if args.city_stats:
        city_stats(res_file, sort_by=sort_field)
        sys.exit(0)

    if args.results or args.search_country or args.search_city:
        get_top_performers(res_file, limit=top_ips_limit, country=args.search_country, city=args.search_city)
        sys.exit(0)
