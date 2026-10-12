"""Validate HA energy-query results against explicit expected outcomes."""
import datetime as dt
import json
import os
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import (Column, Double, Index, Integer, MetaData, String, Table,
                        create_engine, text)
from sqlalchemy.engine import make_url
from dao.lib import db_connections
from dao.prog.da_base import DaBase
from dao.prog.config.loader import ConfigurationLoader
from dao.prog.da_report import Report


@pytest.fixture(params=['sqlite', 'mariadb'], ids=['sqlite', 'mariadb'])
def database(request, tmp_path, monkeypatch):
    if request.param == 'sqlite':
        database_options = {'engine': 'sqlite', 'database': 'ha_query.db',
                            'db_path': str(tmp_path)}
        engine = create_engine('sqlite:///' + str(tmp_path / 'ha_query.db'))
    else:
        dsn = os.getenv('DAO_TEST_MARIADB_URL')
        if not dsn or os.getenv('DAO_TEST_ALLOW_SCHEMA_RESET') != '1':
            pytest.skip('disposable MariaDB test database not configured')
        url = make_url(dsn)
        if url.database != 'dao_query_test' or url.get_backend_name() != 'mysql':
            raise ValueError('MariaDB fixtures require the dedicated dao_query_test schema')
        database_options = {'engine': 'mysql', 'database': url.database,
                            'server': url.host, 'port': url.port or 3306,
                            'username': url.username, 'password': url.password}
        engine = create_engine(url, pool_pre_ping=True)
    md = MetaData()
    statistics = Table('statistics', md, Column('id', Integer, primary_key=True),
                       Column('metadata_id', Integer), Column('start_ts', Double),
                       Column('sum', Double))
    metadata = Table('statistics_meta', md, Column('id', Integer, primary_key=True),
                     Column('statistic_id', String(255)))
    Index('meter_time', statistics.c.metadata_id, statistics.c.start_ts, unique=True)
    try:
        md.drop_all(engine)
        md.create_all(engine)
        with engine.begin() as connection:
            connection.execute(metadata.insert(), [
                {'id': 1, 'statistic_id': 'sensor.a'},
                {'id': 2, 'statistic_id': 'sensor.b'},
                {'id': 3, 'statistic_id': 'sensor.unrelated'},
            ])
        # Follow test_dao.py's options-file/Report construction, using only
        # temporary fixture databases. Stub HA startup, not database execution.
        options_file = tmp_path / ('options_' + database_options['engine'] + '.json')
        options_file.write_text(json.dumps({
            'config_version': 0,
            'meteoserver-key': 'unused-test-key',
            'time_zone': 'Europe/Amsterdam',
            'prices': {
                'last invoice': '2026-01-01',
                **{key: {'2026-01-01': 0.0} for key in (
                    'energy taxes consumption', 'energy taxes production',
                    'cost supplier consumption', 'cost supplier production',
                    'vat consumption', 'vat production')},
            },
            'database ha': database_options,
            'report': {
                'entities grid consumption': ['sensor.a', 'sensor.b'],
                'entities grid production': ['sensor.b'],
            },
        }))
        monkeypatch.setattr(db_connections, '_db_ha', None)
        monkeypatch.setattr(Report, 'periodes', {})

        def initialize_test_base(self, file_name=None):
            self.loader = ConfigurationLoader(Path(file_name))
            self.config = self.loader.load_and_validate()
            self.db_ha = db_connections.make_db_ha(self.config, self.loader.secrets)
            assert self.db_ha is not None
            self.time_zone = self.config.time_zone
            self.prices_options = self.config.prices

        monkeypatch.setattr(DaBase, '__init__', initialize_test_base)
        report = Report(file_name=str(options_file), _now=dt.datetime(2026, 1, 1))
        report.energy_balance_dict.update({
            'missing': {'sensors': ['sensor.unknown']},
            'calculated': {'sensors': 'calc'},
            'empty': {'sensors': []},
        })
        yield SimpleNamespace(engine=engine, report=report, statistics=statistics)
    finally:
        if db_connections._db_ha is not None:
            db_connections._db_ha.engine.dispose()
        md.drop_all(engine)
        engine.dispose()


@pytest.fixture
def start():
    return dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def populate(database, points):
    if points:
        with database.engine.begin() as connection:
            connection.execute(database.statistics.insert(), [
                {'id': i+1, 'metadata_id': meter, 'start_ts': timestamp, 'sum': value}
                for i, (meter, timestamp, value) in enumerate(points)])


def assert_expected(database, start, expected, end=None, step=None, fields=None):
    end = end or start+dt.timedelta(hours=3)
    step = step or dt.timedelta(hours=1)
    query = database.report.get_ha_data_query(start, end, step, fields)
    assert query is not None
    with database.engine.connect() as connection:
        actual = [tuple(row) for row in connection.execute(query)]
    assert len(actual) == len(expected)
    for row, wanted in zip(actual, expected):
        assert row[:2] == wanted[:2]  # timestamps, source codes and ordering
        if wanted[2] is None:
            assert row[2] is None
        else:
            assert row[2] is not None
            assert float(row[2]) == pytest.approx(wanted[2], rel=1e-10, abs=1e-8)
    return query


def test_multiple_meters_boundaries_and_unrelated_history(database, start):
    t = start.timestamp()
    populate(database, [(1, t-3600, 999), (1, t, 10), (1, t+1800, 11),
                        (1, t+3600, 14), (1, t+7200, 17), (1, t+10800, 19),
                        (1, t+10801, 999), (2, t, 5), (2, t+3600, 7),
                        (3, t, 10000), (3, t+3600, 90000)])
    assert_expected(database, start, [
        (int(t), 'cons', 6.0), (int(t), 'prod', 2.0),
        (int(t+3600), 'cons', 3.0), (int(t+3600), 'prod', 0.0),
        (int(t+7200), 'cons', 2.0),
    ], fields=['cons', 'prod'])


def test_null_missing_zero_and_decreases(database, start):
    t = start.timestamp()
    populate(database, [(1, t, None), (1, t+3600, None), (1, t+7200, 0),
                        (1, t+10800, -2), (2, t+7200, 0), (2, t+10800, 0)])
    # Query contract: MAX(sum)-MIN(sum), including lower counter values.
    assert_expected(database, start, [
        (int(t), 'cons', None),
        (int(t+3600), 'cons', 0.0), (int(t+3600), 'prod', 0.0),
        (int(t+7200), 'cons', 2.0), (int(t+7200), 'prod', 0.0),
    ], fields=['cons', 'prod'])


def test_quarter_hours_and_partial_final_interval(database, start):
    t = start.timestamp()
    populate(database, [(1, t+i*300, float(i)) for i in range(15)])
    assert_expected(database, start, [
        (int(t), 'cons', 3.0), (int(t+900), 'cons', 3.0),
        (int(t+1800), 'cons', 3.0), (int(t+2700), 'cons', 3.0),
        (int(t+3600), 'cons', 1.0),
    ], end=start+dt.timedelta(minutes=67), step=dt.timedelta(minutes=15), fields=['cons'])


def test_daily(database, start):
    t = start.timestamp()
    populate(database, [(1, t+i*3600, float(i)) for i in range(49)])
    assert_expected(database, start, [(int(t), 'cons', 24.0), (int(t+86400), 'cons', 24.0)],
                    end=start+dt.timedelta(days=2), step=dt.timedelta(days=1), fields=['cons'])


@pytest.mark.parametrize('date,first_day_hours', [('2026-03-29', 23), ('2026-10-25', 25)])
def test_calendar_day_totals_across_dst(database, date, first_day_hours):
    start = dt.datetime.fromisoformat(date).replace(tzinfo=ZoneInfo('Europe/Amsterdam'))
    end = start+dt.timedelta(days=2)
    populate(database, [(1, timestamp, float(i)) for i, timestamp in enumerate(
        range(int(start.timestamp()), int(end.timestamp())+1, 3600))])
    assert_expected(database, start, [
        (int(start.timestamp()), 'cons', float(first_day_hours)),
        (int(start.timestamp()+first_day_hours*3600), 'cons', 24.0),
    ], end=end, step=dt.timedelta(days=1), fields=['cons'])


def test_unknown_metadata_returns_no_rows(database, start):
    assert_expected(database, start, [], fields=['missing'])


def test_empty_database_does_not_invent_zeroes(database, start):
    assert_expected(database, start, [], fields=['cons'])


def test_no_configured_sensors_returns_none(database, start):
    query = database.report.get_ha_data_query(start, start+dt.timedelta(hours=3),
                                             dt.timedelta(hours=1), ['calculated', 'empty'])
    assert query is None


@pytest.mark.parametrize('fields', [None, []])
def test_empty_field_filters_preserve_all_sources(database, start, fields):
    t = start.timestamp()
    populate(database, [(1, t, 1), (1, t+3600, 3), (2, t, 1), (2, t+3600, 2)])
    assert_expected(database, start, [
        (int(t), 'cons', 3.0), (int(t), 'prod', 1.0),
        (int(t+3600), 'cons', 0.0), (int(t+3600), 'prod', 0.0),
    ], fields=fields)


def test_duplicate_sensor_configuration(database, start):
    database.report.energy_balance_dict['cons']['sensors'] = ['sensor.a', 'sensor.a']
    t = start.timestamp()
    populate(database, [(1, t, 1), (1, t+3600, 3)])
    assert_expected(database, start, [(int(t), 'cons', 2.0), (int(t+3600), 'cons', 0.0)], fields=['cons'])


@pytest.mark.parametrize('hours,minutes,message', [
    (0, 60, 'end moet na start liggen'), (-1, 60, 'end moet na start liggen'),
    (1, 0, 'step moet groter zijn dan 0'),
])
def test_invalid_ranges_and_step_raise_value_error(database, start, hours, minutes, message):
    with pytest.raises(ValueError, match=message):
        database.report.get_ha_data_query(start, start+dt.timedelta(hours=hours),
                                         dt.timedelta(minutes=minutes), ['cons'])


def test_decimal_energy_values(database, start):
    t = start.timestamp()
    populate(database, [(1, t, 0.1), (1, t+3600, 0.4)])
    assert_expected(database, start, [(int(t), 'cons', 0.3), (int(t+3600), 'cons', 0.0)], fields=['cons'])


def test_requested_sources_exclude_other_sources(database, start):
    t = start.timestamp()
    populate(database, [(1, t, 10), (1, t+3600, 100), (2, t, 5), (2, t+3600, 7)])
    assert_expected(database, start, [(int(t), 'prod', 2.0), (int(t+3600), 'prod', 0.0)], fields=['prod'])


def test_meter_and_time_range_index(database, start):
    t = start.timestamp()
    populate(database, [(1, t+i*3600, float(i)) for i in range(-500, 500)])
    query = assert_expected(database, start, [
        (int(t), 'cons', 1.0), (int(t+3600), 'cons', 1.0), (int(t+7200), 'cons', 1.0),
    ], fields=['cons'])
    sql = str(query.compile(database.engine, compile_kwargs={'literal_binds': True}))
    with database.engine.connect() as connection:
        if database.engine.dialect.name == 'sqlite':
            plan = [row[3] for row in connection.execute(text('EXPLAIN QUERY PLAN '+sql))]
            assert any('SEARCH statistics' in line and 'metadata_id=?' in line
                       and 'start_ts>?' in line and 'start_ts<?' in line for line in plan), plan
        else:
            plan = json.loads(connection.execute(text('EXPLAIN FORMAT=JSON '+sql)).scalar())
            def tables(node):
                if isinstance(node, dict):
                    if node.get('table_name') == 'statistics': yield node
                    for child in node.values(): yield from tables(child)
                elif isinstance(node, list):
                    for child in node: yield from tables(child)
            assert any(table.get('access_type') == 'range'
                       and {'metadata_id', 'start_ts'} <= set(table.get('used_key_parts', []))
                       for table in tables(plan)), plan
