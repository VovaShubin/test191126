import pytest

from app.weights import WeightError, WeightedOffer, recalculate


def offer(offer_id: int, share: int = 0, removed: bool = False, pinned: bool = False):
    return WeightedOffer(offer_id, share, removed, pinned)


def test_splits_100_exactly_with_remainder():
    assert recalculate([offer(3), offer(1), offer(2)]) == {1: 34, 2: 33, 3: 33}


def test_preserves_pinned_weight_and_splits_remainder():
    assert recalculate(
        [offer(1, 25, pinned=True), offer(2), offer(3), offer(4, removed=True)]
    ) == {1: 25, 2: 38, 3: 37, 4: 0}


def test_removed_offer_has_zero_share():
    assert recalculate([offer(1, removed=True), offer(2)]) == {1: 0, 2: 100}


def test_all_pinned_must_total_100():
    with pytest.raises(WeightError):
        recalculate([offer(1, 25, pinned=True), offer(2, 25, pinned=True)])


def test_empty_stream_is_allowed_as_draft():
    assert recalculate([offer(1, removed=True)]) == {1: 0}

