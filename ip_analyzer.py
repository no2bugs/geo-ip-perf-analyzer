#!/usr/bin/env python3

import validate.python_version
from validate.file import exists as file_exists
from generate.geolite import GeoLite
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

    parser.add_argument('-d', '--download-dbs',
                        action='store_true',
                        help='''Force download latest geolite dbs. Default is False
                             ''', default=False)

    parser.add_argument('-m', '--max-latency',
                        type=float,
                        help='''Filter results by maximum latency (integer/float). Default is no limit
                             ''', default=None)

    return parser


def validate_inputs(args, report_args, filter_args, results_limit, sort_by, mx_latency):
    if not len(sys.argv) > 1:
        options().print_help()
        formatting.output('bold', 'red')
        print("\n*** Error: Pick one of the options ***\n")
        formatting.output('reset')
        sys.exit(1)

    if args.scan and report_args:
        formatting.output('bold', 'red')
        print('\nError: Cannot run scan and report options at the same time\n')
        formatting.output('reset')
        sys.exit(1)

    if filter_args and (not report_args and not args.scan and not args.download_dbs):
        formatting.output('bold', 'red')
        print('\nError: Cannot apply filters without generating report\n')
        formatting.output('reset')
        sys.exit(1)

    if results_limit and results_limit < 1:
        formatting.output('bold', 'red')
        print("\nError: --results-limit must be > 0\n")
        formatting.output('reset')
        sys.exit(1)

    if mx_latency < 0:
        formatting.output('bold', 'red')
        print("\nError: --max-latency must be => 0\n")
        formatting.output('reset')
        sys.exit(1)

    if mx_latency != float("inf"):
        formatting.output('bold', 'yellow')
        print('Filtered by max latency:', str(max_latency) + 'ms\n')
        formatting.output('reset')

    if sort_by and (args.city_stats or args.country_stats) and (not 0 <= sort_by <= 3):
        formatting.output('bold', 'red')
        print("\nError: invalid stats field number\n")
        formatting.output('reset')
        sys.exit(1)
    elif sort_by and not 0 <= sort_by <= 5:
        formatting.output('bold', 'red')
        print("\nError: invalid results field number\n")
        formatting.output('reset')
        sys.exit(1)


def perform_scan(args, targets_fle, results_fle, country_exclusions, refresh_geo_dbs=False):
    if not file_exists(targets_fle):
        formatting.output('bold', 'red')
        print('\nError: Nothing to scan\nTargets list file "' + targets_fle + '" not found')
        print('Create "' + targets_fle + '" with one domain or IP per line')
        print('(or point to another file with --servers-file)\n')
        formatting.output('reset')
        sys.exit(1)

    geo_city_db, geo_country_db = geolite2.download_dbs(force_dl=refresh_geo_dbs)

    scanner = Scanner(targets_file=args.servers_file,
                      city_db=geo_city_db,
                      country_db=geo_country_db,
                      results_json=results_fle,
                      excl_countries_fle=country_exclusions)

    scanner.scan(pings_num=pings)


def produce_report(args, results_file, records_limit, stats_sort_fld, res_sort_fld, mx_latency):
    if not file_exists(results_file):
        formatting.output('bold', 'red')
        print('\nError: Unable to produce report. Latency scan results file "' + results_file + '" is missing')
        print('Perform --scan to generate new IP/domain performance report (' + results_file + ')')
        formatting.output('reset')
        sys.exit(1)

    if args.country_stats:
        report.country_stats(sort_by=stats_sort_fld, max_latency_limit=mx_latency)

    if args.city_stats:
        report.city_stats(sort_by=stats_sort_fld, max_latency_limit=mx_latency)

    if args.results or args.search_country or args.search_city:
        report.get_top_performers(limit=records_limit,
                                  country=args.search_country,
                                  city=args.search_city,
                                  sort_by=res_sort_fld,
                                  max_latency_limit=mx_latency)


if __name__ == "__main__":
    res_file = 'results.json'
    excl_file = 'exclusions.list'

    formatting = Format()

    geolite2 = GeoLite()
    report = Analyze(res_fl=res_file)

    selections = options().parse_args()

    targets_file = selections.servers_file
    sort_stats = 2 if not selections.sort_by else selections.sort_by - 1
    sort_results = 1 if not selections.sort_by else selections.sort_by - 1
    pings = selections.scan_pings
    top_ips_limit = selections.results_limit
    max_latency = float("inf") if not selections.max_latency else round(float(selections.max_latency), 2)

    report_selections = [selections.results,
                         selections.search_country,
                         selections.search_city,
                         selections.country_stats,
                         selections.city_stats]

    report_filters = [selections.results_limit,
                      selections.max_latency,
                      selections.sort_by]

    report_requested = True if any(report_selections) else False
    filters_applied = True if any(report_filters) else False

    validate_inputs(selections, report_requested, report_filters, top_ips_limit, selections.sort_by, max_latency)

    if selections.download_dbs:
        geolite2.download_dbs(force_dl=True)

    if selections.scan:
        perform_scan(selections, targets_file, res_file, excl_file, refresh_geo_dbs=False)

    if report_requested:
        produce_report(selections,
                       results_file=res_file,
                       records_limit=top_ips_limit,
                       stats_sort_fld=sort_stats,
                       res_sort_fld=sort_results,
                       mx_latency=max_latency)
