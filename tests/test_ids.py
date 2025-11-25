from __future__ import annotations

from expbox.ids import generate_exp_id


def test_generate_default_datetime() -> None:
    exp_id = generate_exp_id()
    # e.g. "250125-1530"
    assert "-" in exp_id
    assert " " not in exp_id
    assert len(exp_id) >= 5  # very loose sanity check


def test_generate_with_prefix_suffix_kebab() -> None:
    exp_id = generate_exp_id(
        style="datetime",
        prefix="rbc",
        suffix="v1",
        link_style="kebab",
    )
    # rbc-YYMMDD-HHMM-v1
    assert exp_id.startswith("rbc-")
    assert "-v1" in exp_id


def test_generate_with_prefix_suffix_snake() -> None:
    exp_id = generate_exp_id(
        style="datetime",
        prefix="rbc",
        suffix="v1",
        link_style="snake",
    )
    # rbc_YYMMDD-HHMM_v1
    assert exp_id.startswith("rbc_")
    assert exp_id.endswith("_v1")
