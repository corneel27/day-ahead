from dao.prog.day_ahead import _boiler_has_start


def test_boiler_window_requires_a_start_before_the_end():
    temperatures = [50.0] * 10
    fractions = [1.0] * 10
    args = (temperatures, 50.0, 1000.0, 1.0, 1000.0, fractions)

    assert _boiler_has_start(7, 9, *args)
    assert not _boiler_has_start(9, 9, *args)
    # One interval of heating cannot start at interval 9 under the current cutoff.
    assert not _boiler_has_start(9, 10, *args)


def test_boiler_window_rejects_heating_that_cannot_fit():
    temperatures = [40.0] * 10
    fractions = [1.0] * 10
    # Heating requires more intervals than remain after the allowed start.
    assert not _boiler_has_start(7, 9, temperatures, 50.0, 1000.0, 1.0, 1000.0, fractions)
