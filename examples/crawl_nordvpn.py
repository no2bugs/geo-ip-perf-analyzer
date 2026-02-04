#!/usr/bin/env python3

import os
import requests
import zipfile
import io


def web_request(url, time_out=60):
    """Make a web request to the given URL with specified timeout."""
    try:
        resp = requests.get(
            url,
            timeout=time_out,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
            }
        )

        if not resp.ok:
            raise ConnectionError(f'Error: Bad response code {resp.status_code}')

    except requests.RequestException as e:
        print('Error:', e)
        return None

    return resp


def get_server_names_from_zip(url):
    """Get server names from the ZIP file without extracting it."""
    servers = []

    try:
        resp = web_request(url)

        if not resp:
            raise Exception("Failed to download ZIP file")

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zip_ref:
            for info in zip_ref.infolist():
                if info.filename.endswith('.udp.ovpn'):
                    # FIX: .udp.ovpn is 9 characters long, not 10.
                    # Previous code [:-10] was cutting off the 'm' in .com
                    server_name = os.path.basename(info.filename)[:-9]
                    servers.append(server_name)

    except Exception as e:
        print('Error:', e)

    return servers


def write_to_file(path, f_name, items):
    """Write server names to a file."""
    # FIX: Use absolute path without joining to root '/'
    save_dir = os.path.abspath(path.strip())

    full_path = os.path.join(save_dir, f_name)
    print(f"Attempting to write to: {full_path}")

    try:
        with open(full_path, 'w') as f:
            for item in items:
                f.write(item + '\n')

        print(f'Created: {full_path}')

    except PermissionError as e:
        print(f'Permission denied when writing to file: {e}')
    except Exception as e:
        print(f'An error occurred while writing to file: {e}')


if __name__ == "__main__":
    URL = "https://downloads.nordcdn.com/configs/archives/servers/ovpn.zip"

    print(f"Current working directory: {os.getcwd()}")

    save_dir = '.'

    servers_list = get_server_names_from_zip(URL)

    if not os.access(save_dir, os.W_OK):
        print(f'Permission denied to write in directory: {save_dir}')
    else:
        if servers_list:
            write_to_file(save_dir, 'servers.list', servers_list)
        else:
            print("No servers found or download failed.")