#!/usr/bin/env python3

import validate.python_version
from validate.file import exists as file_exists
from generate.geolite import GeoLite
from generate.scan import Scanner
from generate.report import Analyze
from format.colors import output as format_output
import sys
import argparse


class ColoredArgParser(argparse.ArgumentParser):
    color_dict = {'RED': '1;31', 'GREEN': '0;32',
                  'YELLOW': '0;33', 'BLUE': '0;34'}

    def print_usage(self, file=None):
        if file is None:
            file = sys.stdout
        self._print_message(self.format_usage()[0].upper() +
                            self.format_usage()[1:],
                            file, self.color_dict['RED'])

    def print_help(self, file=None):
        if file is None:
            file = sys.stdout
        self._print_message(self.format_help()[0].upper() +
                            self.format_help()[1:],
                            file, self.color_dict['BLUE'])

    def _print_message(self, message, file=None, color=None):
        if message:
            if file is None:
                file = sys.stderr
            if color is None:
                file.write(message)
            else:
                file.write('\x1b[' + color + 'm' + message.strip() + '\x1b[0m\n')


if __name__ == "__main__":
    res_file = 'results.json'
    excl_file = 'exclusions.list'

    geolite2 = GeoLite()
    report = Analyze(res_fl=res_file)

    parser = ColoredArgParser(
        description='Performs latency scan on each domain/ip and shows top performers by location',
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

        geo_city_db, geo_country_db = geolite2.download_dbs(force_dl=False)

        scanner = Scanner(targets_file=args.servers_file,
                          city_db=geo_city_db,
                          country_db=geo_country_db,
                          results_json=res_file,
                          excl_countries_fle=excl_file)

        results = scanner.scan(pings_num=pings)

        sys.exit(0)

    if args.download_dbs:
        geolite2.download_dbs(force_dl=True)
        if not args.results and not args.scan:
            sys.exit(0)

    if not file_exists(res_file):
        format_output('bold', 'red')
        print('\nError: Unable to produce report. Latency scan results file "' + res_file + '" is missing')
        print('Perform --scan to generate new IP/domain performance report (' + res_file + ')')
        format_output('reset')
        sys.exit(1)

    if args.country_stats:
        report.country_stats(sort_by=sort_field)
        sys.exit(0)

    if args.city_stats:
        report.city_stats(sort_by=sort_field)
        sys.exit(0)

    if args.results or args.search_country or args.search_city:
        report.get_top_performers(limit=top_ips_limit, country=args.search_country, city=args.search_city)
        sys.exit(0)
