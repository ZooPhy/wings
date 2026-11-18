"""Local Ollama settings and read-only connection checks, shared by app and runner."""
import argparse
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

DEFAULT_MODEL = 'gpt-oss:20b'
DEFAULT_URL = 'http://127.0.0.1:11434/api/chat'
MODEL_PATTERN = r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}'


def validate_model(model):
    if not isinstance(model, str) or not re.fullmatch(MODEL_PATTERN, model):
        raise ValueError('Enter a valid local Ollama model name.')
    return model


def endpoint(url, desktop=False):
    """Only a local HTTP Ollama endpoint; map Mac loopback for Docker Desktop."""
    if not isinstance(url, str) or len(url) > 200 or any(c.isspace() for c in url):
        raise ValueError('Use a local Ollama address such as http://localhost:11434.')
    # Match before parsing so query delimiters, credentials and escaped hosts fail.
    if not re.fullmatch(r'http://(localhost|127\.0\.0\.1|\[::1\]|host\.docker\.internal)(:[0-9]{1,5})?(/api/chat|/)?', url):
        raise ValueError('Use http://localhost:PORT for Ollama on this Mac.')
    parts = urlsplit(url)
    port = parts.port if parts.port is not None else 11434
    if not 1 <= port <= 65535:
        raise ValueError('Ollama port must be between 1 and 65535.')
    host = parts.hostname
    if desktop and host in {'localhost', '127.0.0.1', '::1'}:
        host = 'host.docker.internal'
    authority = '[' + host + ']' if host == '::1' else host
    return f'http://{authority}:{port}/api/chat'


def settings(workspace=None):
    workspace = workspace or os.environ.get('WINGS_DESKTOP_WORKSPACE')
    url, model = DEFAULT_URL, DEFAULT_MODEL
    if workspace:
        root = Path(workspace).resolve()
        path = root / '.desktop' / 'ollama.conf'
        if path.exists() or path.is_symlink():
            if path.is_symlink() or path.resolve().parent != root / '.desktop' or not path.is_file() or path.stat().st_size > 1024:
                raise ValueError('Invalid Ollama settings file. Save it again in WINGS Settings → Configure Ollama.')
            try:
                rows = path.read_text(encoding='utf-8').splitlines()
            except (UnicodeError, OSError):
                raise ValueError('Cannot read Ollama settings. Save them again in WINGS Settings.') from None
            if len(rows) != 2:
                raise ValueError('Invalid Ollama settings. Save them again in WINGS Settings.')
            url, model = rows
    return {'model': validate_model(model), 'url': endpoint(url, desktop=bool(workspace)),
            'display_url': endpoint(url).removesuffix('/api/chat'), 'configured': bool(workspace and path.exists())}


def public_settings():
    try:
        return settings()
    except (ValueError, OSError) as error:
        return {'model': DEFAULT_MODEL, 'url': None, 'display_url': None, 'error': str(error)}


def check_model(model, url, connection_factory=HTTPConnection):
    model = validate_model(model)
    parts = urlsplit(endpoint(url))
    connection = connection_factory(parts.hostname, parts.port, timeout=5)
    try:
        connection.request('GET', '/api/tags')
        response = connection.getresponse()
        if response.status != 200:
            return {'ready': False, 'connected': False, 'detail': 'Ollama did not return its model list. Check the address and port in WINGS Settings.'}
        raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Model list is too large')
        payload = json.loads(raw)
        models = payload.get('models')
        if not isinstance(models, list):
            raise ValueError('Invalid model list')
        def normalize(tag):
            return tag if ':' in tag.rsplit('/', 1)[-1] else tag + ':latest'
        installed = sorted({normalize(tag) for row in models if isinstance(row, dict)
                            for tag in (row.get('name'), row.get('model'))
                            if isinstance(tag, str) and re.fullmatch(MODEL_PATTERN, tag)})
        ready = normalize(model) in installed
        return {'ready': ready, 'connected': True, 'models': installed[:30],
                'detail': 'Ollama is reachable and the selected model is installed.' if ready else
                'Ollama is reachable, but the selected model is not installed. Choose an installed model or install it in Ollama, then check again.'}
    except (OSError, HTTPException, ValueError, AttributeError):
        return {'ready': False, 'connected': False, 'detail':
                'WINGS cannot reach a valid Ollama service at the saved address. Start Ollama on this Mac and check its port. If Ollama is already running, check Docker Desktop access to the Mac host.'}
    finally:
        connection.close()


def runtime_environment(environment):
    """Keep requests to the Mac Ollama server out of configured HTTP proxies."""
    result = dict(environment)
    if result.get('WINGS_DESKTOP_WORKSPACE'):
        entries = []
        for value in (result.get('no_proxy', ''), result.get('NO_PROXY', ''),
                      'localhost,127.0.0.1,::1,host.docker.internal'):
            for item in value.split(','):
                item = item.strip()
                if item and item not in entries:
                    entries.append(item)
        result['no_proxy'] = result['NO_PROXY'] = ','.join(entries)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', required=True)
    args = parser.parse_args()
    try:
        config = settings(args.workspace)
        result = check_model(config['model'], config['url'])
        print(result['detail'])
        print('Selected model: ' + config['model'])
        print('Checked from the WINGS container.')
        print('Refresh the WINGS browser page after changing these settings.')
        if result.get('models') and not result['ready']:
            print('Installed models: ' + ', '.join(result['models']))
        if result['ready']:
            print('This checks availability only; no briefing was generated or model downloaded.')
        return 0  # Readable result is shown by the native dialog even when not ready.
    except (ValueError, OSError) as error:
        print(str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
