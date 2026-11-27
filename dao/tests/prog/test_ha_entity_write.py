from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from dao.prog.da_base import DaBase


@pytest.mark.parametrize(
    "entity_id, attributes, requested, expected",
    [
        ("input_number.feedin", {"min": -10000, "max": 10000}, 10320, 10000),
        ("input_number.from_ac", {"min": -10000, "max": 10000}, -10510, -10000),
        ("number.feedin", {"min": -7500, "max": 10000}, -10320, -7500),
        ("number.feedin", {"min": -7500, "max": 10000}, -4000, -4000),
        ("number.feedin", {"max": 10000}, 10320, 10000),
        ("number.feedin", {}, 10320, 10320),
    ],
)
def test_limit_entity_write_to_home_assistant_range(
    entity_id, attributes, requested, expected, caplog
):
    dao = DaBase.__new__(DaBase)
    dao.get_state = Mock(
        side_effect=[
            SimpleNamespace(attributes=attributes),
            SimpleNamespace(state=str(expected)),
        ]
    )
    dao.call_service = Mock()

    dao.set_entity_value(
        "entity from ac",
        SimpleNamespace(entity_from_ac=entity_id),
        requested,
        limit_to_range=True,
    )

    dao.call_service.assert_called_once_with(
        "set_value", entity_id=entity_id, value=expected
    )
    if requested != expected:
        assert (
            f"Waarde voor {entity_id} begrensd van {requested} naar {expected}"
            in caplog.text
        )
    else:
        assert not caplog.records
