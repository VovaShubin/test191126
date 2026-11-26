from dataclasses import dataclass


@dataclass
class WeightedOffer:
    offer_id: int
    share: int
    is_removed: bool
    is_pinned: bool


class WeightError(ValueError):
    pass


def recalculate(offers: list[WeightedOffer]) -> dict[int, int]:
    """Return integer shares that total 100, preserving active pinned shares."""
    active = [offer for offer in offers if not offer.is_removed]
    removed = {offer.offer_id: 0 for offer in offers if offer.is_removed}
    if not active:
        return removed

    pinned = [offer for offer in active if offer.is_pinned]
    floating = [offer for offer in active if not offer.is_pinned]
    pinned_total = sum(offer.share for offer in pinned)
    if pinned_total > 100:
        raise WeightError("Сумма закреплённых весов превышает 100%")
    if not floating:
        if pinned_total != 100:
            raise WeightError(
                "Невозможно распределить остаток: снимите закрепление хотя бы с одного оффера"
            )
        return {**removed, **{offer.offer_id: offer.share for offer in pinned}}

    remaining = 100 - pinned_total
    quotient, remainder = divmod(remaining, len(floating))
    result = {offer.offer_id: offer.share for offer in pinned}
    for index, offer in enumerate(sorted(floating, key=lambda item: item.offer_id)):
        result[offer.offer_id] = quotient + (1 if index < remainder else 0)
    return {**removed, **result}

