#!/usr/bin/env python3

import validate.python_version
from validate.file import exists as file_exists
from generate.scan import Scanner
from generate.report import Analyze
from format.colors import Format
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


def options():
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

    parser.add_argument('-w', '--workers',
                        type=int,
                        help='''Number of concurrent workers for scanning. Default is 20
                             ''', default=20)

    parser.add_argument('-o', '--timeout-ms',
                        type=int,
                        help='''Ping timeout per request in milliseconds. Default is 1000
                             ''', default=1000)

    parser.add_argument('-a', '--all-a-records',
                        action='store_true',
                        help='''Scan all resolved IPv4 addresses for each domain (A records). Default is False
                             ''', default=False)

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
                        help='''Sort --country-stats or --city-stats by field/column number. Default is 4 (LATENCY)
                             ''', default=None)

    parser.add_argument('-n', '--min-latency',
                        type=float,
                        help='''Filter results by minimum latency (integer/float). Default is 0
                             ''', default=None)

    parser.add_argument('-m', '--max-latency',
                        type=float,
                        help='''Filter results by maximum latency (integer/float). Default is no limit
                             ''', default=None)

    parser.add_argument('--include-countries',
                        action='store_true',
                        help='''Optionally include only countries listed in include_countries.list (comma delimited). Others will be skipped.''',
                        default=False)
    return parser


def validate_inputs(args, report_args, filter_args, results_limit, sort_by, mn_latency, mx_latency):
    if not len(sys.argv) > 1:
        options().print_help()
        formatting.output('bold', 'red')
        print("\n*** Error: Pick one of the options ***\n")
        formatting.output('reset')
        sys.exit(1)

    if args.scan and (any(report_args) or any(filter_args)):
        formatting.output('bold', 'red')
        print('\nError: Cannot run scan and report options at the same time\n')
        formatting.output('reset')
        sys.exit(1)

    if any(filter_args) and not any(report_args):
        formatting.output('bold', 'red')
        print('\nError: Cannot apply filters without generating report\n')
        formatting.output('reset')
        sys.exit(1)

    if results_limit and results_limit < 1:
        formatting.output('bold', 'red')
        print("\nError: --results-limit must be > 0\n")
        formatting.output('reset')
        sys.exit(1)

    if mn_latency < 0 or mx_latency < 0:
        formatting.output('bold', 'red')
        print("\nError: latency must be => 0\n")
        formatting.output('reset')
        sys.exit(1)

    if mn_latency != 0:
        formatting.output('bold', 'yellow')
        print('Filtered by min latency:', str(mn_latency) + 'ms\n')
        formatting.output('reset')

    if mx_latency != float("inf"):
        formatting.output('bold', 'yellow')
        print('Filtered by max latency:', str(mx_latency) + 'ms\n')
        formatting.output('reset')

    if sort_by and (args.city_stats or args.country_stats) and (not 0 <= sort_by <= 2):
        formatting.output('bold', 'red')
        print("\nError: invalid stats field number\n")
        formatting.output('reset')
        sys.exit(1)
    elif sort_by and not 0 <= sort_by <= 4:
        formatting.output('bold', 'red')
        print("\nError: invalid results field number\n")
        formatting.output('reset')
        sys.exit(1)


def perform_scan(args, targets_fle, results_fle, country_exclusions, pings=1, include_countries=None):
    if not file_exists(targets_fle):
        formatting.output('bold', 'red')
        print('\nError: Nothing to scan\nTargets list file "' + targets_fle + '" not found')
        print('Create "' + targets_fle + '" with one domain or IP per line')
        print('(or point to another file with --servers-file)\n')
        formatting.output('reset')
        sys.exit(1)

    scanner = Scanner(targets_file=args.servers_file,
                      city_db='GeoLite2-City.mmdb',
                      country_db='GeoLite2-Country.mmdb',
                      results_json=results_fle,
                      excl_countries_fle=country_exclusions,
                      include_countries=include_countries)

    scanner.scan(pings_num=pings,
                 timeout_ms=args.timeout_ms,
                 workers=args.workers,
                 all_a_records=args.all_a_records)


def produce_report(args, results_file, records_limit, stats_sort_fld, res_sort_fld, mn_latency, mx_latency):
    if not file_exists(results_file):
        formatting.output('bold', 'red')
        print('\nError: Unable to produce report. Latency scan results file "' + results_file + '" is missing')
        print('Perform --scan to generate new IP/domain performance report (' + results_file + ')')
        formatting.output('reset')
        sys.exit(1)

    if args.country_stats:
        report.country_stats(sort_by=stats_sort_fld, min_latency_limit=mn_latency, max_latency_limit=mx_latency)

    if args.city_stats:
        report.city_stats(sort_by=stats_sort_fld, min_latency_limit=mn_latency, max_latency_limit=mx_latency)

    if args.results or args.search_country or args.search_city:
        report.get_top_performers(limit=records_limit,
                                  country=args.search_country,
                                  city=args.search_city,
                                  sort_by=res_sort_fld,
                                  min_latency_limit=mn_latency,
                                  max_latency_limit=mx_latency)


if __name__ == "__main__":
    res_file = 'results.json'
    excl_file = 'exclusions.list'

    formatting = Format()

    report = Analyze(res_fl=res_file)

    selections = options().parse_args()

    targets_file = selections.servers_file
    pings = selections.scan_pings
    top_ips_limit = selections.results_limit
    sort_stats = 2 if not selections.sort_by else selections.sort_by - 1
    sort_results = 1 if not selections.sort_by else selections.sort_by - 1
    max_latency = float("inf") if not selections.max_latency else round(float(selections.max_latency), 2)
    min_latency = 0 if not selections.min_latency else round(float(selections.min_latency), 2)

    report_selections = [selections.results,
                         selections.search_country,
                         selections.search_city,
                         selections.country_stats,
                         selections.city_stats]

    report_filters = [selections.results_limit,
                      selections.min_latency,
                      selections.max_latency,
                      selections.sort_by]

    include_countries = None
    if selections.include_countries:
        try:
            with open('include_countries.list', 'r') as f:
                content = f.read().strip()
                include_countries = [c.strip() for c in content.split(',') if c.strip()]
                if not include_countries:
                    include_countries = None
        except FileNotFoundError:
            print('include_countries.list not found, ignoring country filter.')
            include_countries = None

    validate_inputs(selections,
                    report_selections,
                    report_filters,
                    top_ips_limit,
                    selections.sort_by,
                    min_latency,
                    max_latency)

    if selections.scan:
        perform_scan(selections, targets_file, res_file, excl_file, pings, include_countries=include_countries)

    if any(report_selections):
        produce_report(selections,
                       results_file=res_file,
                       records_limit=top_ips_limit,
                       stats_sort_fld=sort_stats,
                       res_sort_fld=sort_results,
                       mn_latency=min_latency,
                       mx_latency=max_latency)
