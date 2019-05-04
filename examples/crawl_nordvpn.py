#!/usr/bin/env python3

from bs4 import BeautifulSoup
import os
import requests


def web_request(url, time_out=60):
    try:
        resp = requests.get(url,
                            timeout=time_out,
                            headers={
                                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'})

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


def crawl_nordvpn(raw_content):
    soup = BeautifulSoup(raw_content, "html.parser")

    servers = []

    print('\nSearching for VPN servers...')

    spans = soup.find_all('span', attrs={'mr-2'})

    print('\nFound total of', len(spans), 'VPN servers...')

    for i, host in enumerate(spans, 1):
        print(i, 'Fetched:', host.string)
        servers.append(host.string)

    print('\nFetched total of', len(servers), 'VPN servers\n')

    servers.sort(key=lambda x: x[0])

    return servers


def write_to_file(path, f_name, items):
    save_dir = ''.join((os.path.abspath(path.rstrip('/') + '/'), '/'))

    print('Writing to file:', f_name)
    with open(save_dir + f_name, 'w') as f:
        for item in items:
            f.write(item + '\n')
    print('Created:', save_dir + f_name)


if __name__ == "__main__":
    URL = "https://nordvpn.com/ovpn"

    f_path = '.'
    f_name = 'servers.list'

    data = web_request(URL).content

    servers_list = crawl_nordvpn(data)

    write_to_file(f_path, f_name, servers_list)
