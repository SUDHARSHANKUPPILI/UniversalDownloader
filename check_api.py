import requests, json

base = 'http://127.0.0.1:5000/api/v1'
endpoints = [
    ('GET', '/health', None),
    ('GET', '/statistics', None),
    ('GET', '/analytics', None),
    ('GET', '/settings', None),
    ('GET', '/downloads', None),
    ('GET', '/queue', None),
    ('GET', '/history', None),
    ('GET', '/files', None),
    ('GET', '/subtitles', None),
    ('GET', '/network', None),
    ('GET', '/duplicates', None),
    ('GET', '/security/events', None),
]

all_ok = True
for method, path, body in endpoints:
    try:
        r = requests.request(method, base+path, json=body, timeout=8)
        data = r.json()
        shape = type(data).__name__
        if isinstance(data, dict):
            keys = list(data.keys())[:8]
            status = 'OK' if r.status_code == 200 else f'HTTP{r.status_code}'
        elif isinstance(data, list):
            keys = f'list[{len(data)}]'
            status = 'OK' if r.status_code == 200 else f'HTTP{r.status_code}'
        else:
            keys = repr(data)[:40]
            status = f'HTTP{r.status_code}'
        if r.status_code != 200:
            all_ok = False
        print(f'{status:8} {method:4} {path:28} type={shape:6} keys={keys}')
    except Exception as e:
        all_ok = False
        print(f'ERR      {method:4} {path:28} {e}')

print()
print('Overall:', 'ALL OK' if all_ok else 'SOME FAILURES')
