"""Wiremap analyser against modelled cables (model, not hardware)."""
import pytest

from netscope.cable import wiremap
from netscope.cable.model import (CROSSOVER_10_100, CROSSOVER_GIGABIT, STRAIGHT, CableModel,
                                  simulate_crosstalk, simulate_matrix)


def analyse(cable, xtalk=True):
    return wiremap.analyse(simulate_matrix(cable), simulate_crosstalk(cable) if xtalk else None)


def kinds(a):
    return sorted(f["kind"] for f in a.faults)


@pytest.mark.parametrize("length", [0.5, 30, 100])
@pytest.mark.parametrize("tid", range(1, 9))
def test_good_cable_every_terminator_id_and_length(tid, length):
    a = analyse(CableModel(length, terminator_id=tid))
    assert a.ok and a.far_end == "terminator" and a.terminator_id == tid
    assert a.cable_type == "straight"
    assert a.mapping == STRAIGHT
    assert set(a.pin_status.values()) == {"ok"}


@pytest.mark.parametrize("pin", range(1, 9))
def test_single_open_conductor(pin):
    w = dict(STRAIGHT)
    w[pin] = None
    a = analyse(CableModel(40, wiring=w))
    assert kinds(a) == ["open"]
    assert pin in a.faults[0]["pins"]


@pytest.mark.parametrize("a_pin,b_pin", [(1, 2), (3, 6), (1, 3), (2, 6), (4, 7), (5, 8), (1, 8)])
def test_short(a_pin, b_pin):
    a = analyse(CableModel(40, shorts=[(a_pin, b_pin)]))
    assert "short" in kinds(a)
    short = next(f for f in a.faults if f["kind"] == "short")
    assert short["pins"] == [a_pin, b_pin]
    assert a.pin_status[a_pin] == a.pin_status[b_pin] == "short"


@pytest.mark.parametrize("pair", [(1, 2), (3, 6), (4, 5), (7, 8)])
def test_reversed_pair(pair):
    w = dict(STRAIGHT)
    w[pair[0]], w[pair[1]] = pair[1], pair[0]
    a = analyse(CableModel(20, wiring=w))
    assert kinds(a) == ["reversed"]
    assert a.faults[0]["pins"] == list(pair)


@pytest.mark.parametrize("wiring", [CROSSOVER_10_100, CROSSOVER_GIGABIT])
def test_crossover_is_recognised_not_failed(wiring):
    a = analyse(CableModel(3, wiring=wiring))
    assert a.ok and a.cable_type == "crossover"


def test_crossed_pairs_that_are_not_a_crossover():
    w = dict(STRAIGHT)
    w.update({4: 7, 5: 8, 7: 4, 8: 5})  # only pairs 4-5/7-8 transposed
    a = analyse(CableModel(20, wiring=w))
    assert kinds(a) == ["crossed", "crossed"]


def test_miswire_two_conductors_swapped_between_pairs():
    w = dict(STRAIGHT)
    w[1], w[3] = 3, 1
    a = analyse(CableModel(20, wiring=w))
    assert "miswire" in kinds(a)
    assert a.mapping[1] == 3 and a.mapping[3] == 1


def test_split_pair_needs_ac_measurement():
    cable = CableModel(30, split_pairs=("3-6", "4-5"))
    dc_only = analyse(cable, xtalk=False)
    assert dc_only.ok and not dc_only.split_checked  # DC alone cannot see it
    with_ac = analyse(cable)
    assert kinds(with_ac) == ["split"] and with_ac.split_checked


def test_open_far_end_reports_unverified_not_pass():
    a = analyse(CableModel(55, far_end="open"))
    assert a.far_end == "open" and a.ok
    assert set(a.pin_status.values()) == {"unverified"}


def test_short_with_no_terminator():
    a = analyse(CableModel(55, far_end="open", shorts=[(4, 5)]))
    assert kinds(a) == ["short"]


def test_equipment_signature_is_not_reported_as_shorts():
    a = analyse(CableModel(60, far_end="equipment"))
    assert a.far_end == "equipment" and a.ok
    assert a.equipment_pairs == ["1-2", "3-6", "4-5", "7-8"]
    a = analyse(CableModel(60, far_end="equipment", equipment_pairs=2))
    assert a.equipment_pairs == ["1-2", "3-6"]


def test_one_pair_low_resistance_is_a_short_not_equipment():
    a = analyse(CableModel(60, far_end="open", shorts=[(1, 2)]))
    assert a.far_end != "equipment" and kinds(a) == ["short"]


def test_unknown_resistance_is_flagged():
    m = simulate_matrix(CableModel(10))
    m[0][1] = 330.0  # not an RT-1 value
    a = wiremap.analyse(m)
    assert "resistive" in kinds(a)
