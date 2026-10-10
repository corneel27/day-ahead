import re
from pathlib import Path

from setuptools import setup

CONFIG_YAML = Path(__file__).parent / 'dao' / 'config.yaml'


def get_version(fallback='0.0.0'):
    """Read the version from dao/config.yaml, the single source of truth."""
    try:
        for line in CONFIG_YAML.read_text(encoding='utf-8').splitlines():
            match = re.match(r'^version:\s*(\S+)', line)
            if match:
                return match.group(1).strip('\'"')
    except OSError:
        pass
    return fallback


setup(
    name='day_ahead_opt',
    version=get_version(),
    packages=['dao', 'dao.prog', 'dao.webserver', 'dao.webserver.app'],
    url='https://github.com/corneel27/day-ahead',
    license='Apache License, Version 2.0',
    author='Cees van Beek',
    author_email='cees.van.beek@xs4all.nl',
    description='Optimize your consumption, production and batterystorage of electricity with dynamic prices '
)
