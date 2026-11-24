import json
import logging

from dao.prog.da_base import DaBase


def test_check_neg_baseloads():
    baseload = [100, -20, 50, -10, 0, 200]

    result = DaBase.check_neg_baseloads(0, baseload)

    assert result == [100, 0, 50, 0, 0, 200]


def test_check_neg_baseloads_no_negative_values(caplog):
    baseload = [100, 20, 50, 10, 0, 200]

    with caplog.at_level(logging.WARNING):
        result = DaBase.check_neg_baseloads(0, baseload)

    assert result == baseload
    assert len(caplog.records) == 0


def test_check_neg_baseloads_warning(caplog):
    baseload = [100, -20, 50, -10, -5, 200]

    with caplog.at_level(logging.WARNING):
        result = DaBase.check_neg_baseloads(0, baseload)

    assert result == [100, 0, 50, 0, 0, 200]

    assert len(caplog.records) == 1
    assert "Negative baseload on" in caplog.text
    assert "Monday" in caplog.text
    assert "hour(s) 1, 3, 4" in caplog.text


def test_get_calculated_baseload(tmp_path, monkeypatch, caplog):
    # Maak tijdelijke directorystructuur
    baseload_dir = tmp_path / "data" / "baseload"
    baseload_dir.mkdir(parents=True)

    # Testdata
    weekday = 0
    baseload = [100, -20, 50, -10, 0, 200]

    # Schrijf testdata naar JSON
    in_file = baseload_dir / f"baseload_{weekday}.json"
    in_file.write_text(json.dumps(baseload))

    # Ga één directory onder tmp_path staan
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    # Voer functie uit
    with caplog.at_level(logging.WARNING):
        result = DaBase.get_calculated_baseload(weekday)

    # Controleer resultaat
    assert result == [100, 0, 50, 0, 0, 200]

    # Controleer logging
    assert len(caplog.records) == 1
    assert "Monday" in caplog.text


def test_get_calculated_baseload_no_negative(tmp_path, monkeypatch, caplog):
    baseload_dir = tmp_path / "data" / "baseload"
    baseload_dir.mkdir(parents=True)

    weekday = 1
    baseload = [100, 20, 50, 10, 0, 200]

    in_file = baseload_dir / f"baseload_{weekday}.json"
    in_file.write_text(json.dumps(baseload))

    # Ga één directory onder tmp_path staan
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)

    with caplog.at_level(logging.WARNING):
        result = DaBase.get_calculated_baseload(weekday)

    assert result == baseload
    assert len(caplog.records) == 0