from noesek.core.ratelimit import RateLimiter

def test_allows_up_to_limit_then_blocks():
    rl = RateLimiter(3, 60)
    assert [rl.allow("u", now=t) for t in (0, 1, 2)] == [True, True, True]
    assert not rl.allow("u", now=3)

def test_window_expiry_restores_allowance():
    rl = RateLimiter(2, 10)
    assert rl.allow("u", now=0); assert rl.allow("u", now=1)
    assert not rl.allow("u", now=2)
    assert rl.allow("u", now=11)

def test_keys_are_independent():
    rl = RateLimiter(1, 60)
    assert rl.allow("a", now=0)
    assert rl.allow("b", now=0)

def test_invalid_config_rejected():
    import pytest
    with pytest.raises(ValueError): RateLimiter(0, 60)
