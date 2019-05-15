import requests


def request(url, time_out=60):
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
        return resp
    except Exception as e:
        print('Error: Something went wrong\n', e)
        return None

    return resp