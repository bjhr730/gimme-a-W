from gimme_collectors.derive import _expected, _mov_multiplier


def test_expected_symmetry():
    assert abs(_expected(0) - 0.5) < 1e-9
    assert abs(_expected(400) - 10 / 11) < 1e-9
    assert abs(_expected(200) + _expected(-200) - 1) < 1e-9


def test_mov_multiplier_grows_with_margin_and_shrinks_for_favorites():
    assert _mov_multiplier(1, 0) < _mov_multiplier(21, 0)
    # a heavy favorite winning big earns less than an underdog winning big
    assert _mov_multiplier(21, 300) < _mov_multiplier(21, -300)
