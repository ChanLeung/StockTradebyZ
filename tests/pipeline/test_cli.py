import argparse

from pipeline.cli import _resolve_preselect_end_date


def test_preselect_uses_explicit_end_date_when_provided():
    args = argparse.Namespace(date="2026-03-23", end_date="2026-03-20")

    resolved = _resolve_preselect_end_date(args)

    assert resolved == "2026-03-20"


def test_preselect_defaults_end_date_to_date_for_historical_runs():
    args = argparse.Namespace(date="2026-03-23", end_date=None)

    resolved = _resolve_preselect_end_date(args)

    assert resolved == "2026-03-23"


def test_preselect_keeps_latest_mode_when_no_date_is_provided():
    args = argparse.Namespace(date=None, end_date=None)

    resolved = _resolve_preselect_end_date(args)

    assert resolved is None
