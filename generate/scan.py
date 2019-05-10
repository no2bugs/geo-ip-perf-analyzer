from validate.file import exists as file_exists
from format.colors import Format
from datetime import timedelta
from collections import OrderedDict
from subprocess import run, PIPE
from json import dump
import geoip2.database
import socket
import sys
import time


class Scanner:
    formatting = Format()

    def __init__(self, targets_file, city_db, country_db, results_json, excl_countries_fle):
        self.targets_file = targets_file
        self.city_db = city_db
        self.country_db = country_db
        self.results_json = results_json
        self.exclude_countries_fle = excl_countries_fle

    @staticmethod
    def write_json_file(json_file, data):
        print('\nCreating json file:', json_file)
        with open(json_file, 'w') as outfile:
            dump(data, outfile, indent=2)
        print('DONE')

    def get_servers_list(self):
        if not file_exists(self.targets_file):
            return None

        print('Reading targets from:', self.targets_file)
        with open(self.targets_file, 'r') as f:
            lines = f.readlines()
            servers = [line.strip().rstrip('\n') for line in lines if len(line) > 1]

        if len(servers) < 1:
            self.formatting.output('bold', 'red')
            print('Error:', self.targets_file, 'does not have any targets\n')
            self.formatting.output('reset')
            sys.exit(1)

        servers.sort(key=lambda x: x[0])

        print('\nFound total of', len(servers), 'targets')

        return servers

    def exclude_countries(self):
        try:
            with open(self.exclude_countries_fle, 'r') as f:
                lines = f.readlines()
                excludes = [line.rstrip('\n') for line in lines if len(line) > 1]
        except FileNotFoundError:
            excludes = None
            self.formatting.output('yellow')
            print('INFO: No countries were excluded from scan')
            print('To exclude countries, create file "' + self.exclude_countries_fle + '" with country name per line\n')
            self.formatting.output('reset')

        return excludes

    def scan(self, pings_num=1):
        domains = self.get_servers_list()
        excl_countries = None

        endpoints_list = []
        endpoints_dict = OrderedDict()

        skipped_total = 0
        errors_total = 0

        city_reader = geoip2.database.Reader(self.city_db)
        country_reader = geoip2.database.Reader(self.country_db)

        if self.exclude_countries():
            excl_countries = sorted(self.exclude_countries())
            print('Excluding results from:', excl_countries)

        self.formatting.output('bold')
        print('\nMeasuring latency to', len(domains), 'servers')
        print('Pings:', pings_num)
        print('Started:', time.strftime("%d/%m/%Y %H:%M:%S"))
        self.formatting.output('reset')

        start_scan = time.time()
        start_time = time.strftime("%d/%m/%Y %H:%M:%S")

        for count, domain in enumerate(domains, 1):
            try:
                resolv = socket.gethostbyname_ex(domain)
                ip = resolv[2][0]
                try:
                    country_result = country_reader.country(ip)
                    country = country_result.country.name
                    if not country:
                        raise ValueError()
                except Exception:
                    self.formatting.output('yellow')
                    print('Unable to determine country for', ip, 'setting country to Unknown')
                    country = 'Unknown'
                    self.formatting.output('reset')
                try:
                    city_result = city_reader.city(ip)
                    city = city_result.city.name
                    if not city:
                        raise ValueError()
                except Exception:
                    self.formatting.output('yellow')
                    print('Unable to determine city for', ip, 'setting city to Unknown')
                    city = 'Unknown'
                    self.formatting.output('reset')
            except socket.gaierror or socket.herror:
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

            if excl_countries and country in excl_countries:
                print('Excluding', domain, 'in', country)
                skipped_total += 1
                continue

            result = run(["ping", "-c", str(pings_num), ip], stdout=PIPE).stdout.decode('UTF-8')

            try:
                lines = result.split('\n')
                response = [line.strip().rstrip('\n') for line in lines if len(line) > 1]
                avg_latency = float(response[-1].split('=')[1].split('/')[1])
            except Exception:
                self.formatting.output('red')
                print('Error: No response time received from', domain, 'Skipping...')
                errors_total += 1
                self.formatting.output('reset')
                continue

            self.formatting.output('green')
            print('(' + str(count) + "/" + str(len(domains)) + ')', domain, avg_latency, ip, country, city)
            self.formatting.output('reset')

            endpoints_list.append((domain, avg_latency, ip, country, city))

        endpoints_list.sort(key=lambda x: x[1])

        retrieved_total = int(len(domains)) - (skipped_total + errors_total)

        finish_time = time.strftime("%d/%m/%Y %H:%M:%S")
        finish_scan = time.time()
        t_diff = float(finish_scan) - float(start_scan)
        t_finish = timedelta(seconds=int(t_diff))

        self.formatting.output('bold')
        print('\nStarted scan:     ', start_time)
        print('Finished scan:    ', finish_time)
        print('Scan duration:    ', t_finish)

        if excl_countries:
            print('\nExcluded countries:', excl_countries)
        print('\nExcluded:        ', skipped_total, '/', len(domains))
        print('Errors:           ', errors_total, '/', len(domains))
        print('\nTotal Retrieved: ', retrieved_total, '/', len(domains))

        for item in endpoints_list:
            endpoints_dict[item[0]] = [item[1], item[2], item[3], item[4]]

        if endpoints_list:
            self.write_json_file(json_file=self.results_json, data=endpoints_dict)
            self.formatting.output('reset')
        else:
            self.formatting.output('red')
            print('\nFailed to ping any targets from the list\n')
            self.formatting.output('reset')

        return endpoints_dict
