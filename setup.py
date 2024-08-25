from setuptools import setup

setup(
    name='day_ahead_opt',
    version='2024.8.4',
    packages=['dao', 'dao.prog', 'dao.webserver', 'dao.webserver.app'],
    url='https://github.com/corneel27/day-ahead',
    license='Apache License, Version 2.0',
    author='Cees van Beek',
    author_email='cees.van.beek@xs4all.nl',
    description='Optimize your consumption, production and batterystorage of electricity with dynamic prices '
)
