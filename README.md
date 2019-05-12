**_Tool for mass latency performance testing and reporting of Domains/IPs based on their location_**

#### Features

- Reads list of domains/IPs, pings them and generates latency report

- Records IP location for each target by country and city

- Records number of servers in each location

- Optionally excludes selected country IPs from the report

- Automatically downloads and configures maxmind geolite2 DBs

- Shows best performing servers and their location

- Allows searching results by country and/or city 


#### Getting Started
1. Create "servers.list" file with one domain/IP per line

2. To exclude countries from scan, add one country name per line in "exclusions.list" file

3. Run script with ```--scan``` to generate new report (results.json)

4. Run script with ```--help``` for more options


```bash
# python3 ip_analyzer.py --help

Usage: ip_analyzer.py [-h] [-s] [-p SCAN_PINGS] [-f SERVERS_FILE] [-r]
                      [-l RESULTS_LIMIT] [-c] [-t SEARCH_COUNTRY] [-i]
                      [-y SEARCH_CITY] [-b SORT_BY] [-d] [-n MIN_LATENCY]
                      [-m MAX_LATENCY]

Performs latency scan on each domain/ip and shows top performers by location

optional arguments:
  -h, --help            show this help message and exit
  -s, --scan            Perform full latency scan and generate performance report

  -p SCAN_PINGS, --scan-pings SCAN_PINGS
                        Number of pings to each IP during scan (increase for better accuracy). Default is 1

  -f SERVERS_FILE, --servers-file SERVERS_FILE
                        Read servers list from file (one domain or ip per line). Default is "servers.list"

  -r, --results         Show top performing endpoints

  -l RESULTS_LIMIT, --results-limit RESULTS_LIMIT
                        Number of results to show

  -c, --country-stats   Show stats by country

  -t SEARCH_COUNTRY, --search-country SEARCH_COUNTRY
                        Search results by country name

  -i, --city-stats      Show stats by city

  -y SEARCH_CITY, --search-city SEARCH_CITY
                        Search results by city name

  -b SORT_BY, --sort-by SORT_BY
                        Sort by field/column number. Default is "LATENCY"

  -d, --download-dbs    Force download latest geolite dbs. Default is False

  -n MIN_LATENCY, --min-latency MIN_LATENCY
                        Filter results by minimum latency (integer/float). Default is 0

  -m MAX_LATENCY, --max-latency MAX_LATENCY
                        Filter results by maximum latency (integer/float). Default is no limit
```