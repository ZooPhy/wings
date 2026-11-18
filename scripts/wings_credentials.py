"""Read optional desktop credentials into a fresh child-process environment.

No secrets are added to configuration files, provenance, command lines or
process-wide os.environ. Native launches retain their normal environment.
"""
import os
import re
from pathlib import Path


def runtime_environment(base=None):
    environment = dict(os.environ if base is None else base)
    workspace = environment.get('WINGS_DESKTOP_WORKSPACE')
    if not workspace:
        return environment
    environment.pop('EBIRDST_ACCESS_KEY', None)
    environment.pop('NCBI_EMAIL', None)
    root = Path(workspace).resolve()
    email_path = root / '.desktop' / 'ncbi-email'
    if email_path.exists() or email_path.is_symlink():
        message = 'Invalid NCBI contact email. Save it again in WINGS Settings → Add or update NCBI email.'
        if email_path.is_symlink() or email_path.resolve().parent != root / '.desktop' or not email_path.is_file() or email_path.stat().st_size > 320:
            raise ValueError(message)
        try:
            email = email_path.read_text(encoding='utf-8').strip()
        except (UnicodeError, OSError):
            raise ValueError(message) from None
        if not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', email):
            raise ValueError(message)
        environment['NCBI_EMAIL'] = email
    path = root / '.desktop' / 'ebirdst-access-key'
    if not path.exists() and not path.is_symlink():
        return environment  # Add later, or key removed in Settings.
    if path.is_symlink() or path.resolve().parent != root / '.desktop' or not path.is_file():
        raise ValueError('Invalid eBird key file. Save it again in WINGS Settings.')
    if path.stat().st_size > 4096:
        raise ValueError('Invalid eBird key. Save it again in WINGS Settings.')
    try:
        value = path.read_text(encoding='utf-8').strip()
    except (UnicodeError, OSError):
        raise ValueError('Cannot read the eBird key. Save it again in WINGS Settings.') from None
    if not value or any(ord(c) < 33 or ord(c) > 126 for c in value):
        raise ValueError('Invalid eBird key. Paste the Status and Trends access key in WINGS Settings.')
    environment['EBIRDST_ACCESS_KEY'] = value
    return environment
