from types import SimpleNamespace

from bot.usage import record, start_tracking


def test_tracking_accumulates():
    usage = start_tracking()
    record(SimpleNamespace(input_tokens=100, output_tokens=20))
    record(SimpleNamespace(input_tokens=50, output_tokens=10))
    assert usage.input_tokens == 150
    assert usage.output_tokens == 30
    assert usage.total == 180
    assert usage.calls == 2


def test_record_without_tracking_is_noop():
    start_tracking()  # reset
    record(None)  # metriche mancanti → ignorate
    usage = start_tracking()
    assert usage.calls == 0


def test_start_resets():
    usage1 = start_tracking()
    record(SimpleNamespace(input_tokens=10, output_tokens=1))
    usage2 = start_tracking()
    record(SimpleNamespace(input_tokens=5, output_tokens=2))
    assert usage1.total == 11
    assert usage2.total == 7
