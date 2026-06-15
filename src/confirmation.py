from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.barrier_engine import Trade


@dataclass(frozen=True)
class OptionLeg:
    reference: str
    option_type: str
    option_seller: str
    option_buyer: str
    strike: float
    call_currency: str
    call_amount: float
    put_currency: str
    put_amount: float
    barrier: float | None = None
    barrier_direction: str | None = None
    window_start_date: date | None = None
    window_end_date: date | None = None


@dataclass(frozen=True)
class ScheduledExpiry:
    expiration_date: date
    settlement_date: date
    legs: tuple[OptionLeg, ...]


@dataclass(frozen=True)
class Confirmation:
    customer: str
    trade_date: date
    pair: str
    base_currency: str
    quote_terms: str
    references: tuple[str, ...]
    expiries: tuple[ScheduledExpiry, ...]
    product_type: str = "Ratio Convertible Forward"
    expiry_time_zone: str = "Tokyo"


@dataclass(frozen=True)
class CorpayTradeInput:
    product_type: str
    client_direction: str
    pair: str
    protected_amount: float
    ratio_amount: float
    amount_currency: str
    strike: float
    barrier: float
    barrier_level_period: str
    expiry_date: date
    expiry_time_zone: str = "Tokyo"
    barrier_direction: str = "up"


def corpay_trade_input_to_trade(
    trade_input: CorpayTradeInput,
    trade_date: date,
    spot: float,
) -> Trade:
    return Trade(
        pair=trade_input.pair,
        trade_date=trade_date,
        spot=spot,
        strike=trade_input.strike,
        barrier=trade_input.barrier,
        expiry_date=trade_input.expiry_date,
        barrier_direction=trade_input.barrier_direction,
        product_type=trade_input.product_type,
        client_direction=trade_input.client_direction,
        protected_amount=trade_input.protected_amount,
        ratio_amount=trade_input.ratio_amount,
        amount_currency=trade_input.amount_currency,
        barrier_level_period=trade_input.barrier_level_period,
        expiry_time_zone=trade_input.expiry_time_zone,
    )


def build_corpay_screenshot_input_example() -> CorpayTradeInput:
    return CorpayTradeInput(
        product_type="Ratio Convertible Forward",
        client_direction="Importer",
        pair="AUD/USD",
        protected_amount=500_000,
        ratio_amount=1_000_000,
        amount_currency="USD",
        strike=0.6850,
        barrier=0.6935,
        barrier_level_period="continuous",
        expiry_date=date(2026, 12, 30),
        expiry_time_zone="Tokyo",
        barrier_direction="down",
    )


def barrier_legs_to_trades(
    confirmation: Confirmation,
    spot: float,
    protected_amount: float | None = None,
    ratio_amount: float | None = None,
    amount_currency: str | None = None,
) -> list[Trade]:
    trades: list[Trade] = []
    for expiry in confirmation.expiries:
        for leg in expiry.legs:
            if leg.barrier is None:
                continue
            if leg.barrier_direction is None:
                raise ValueError(f"barrier leg {leg.reference} is missing barrier_direction")
            trades.append(
                Trade(
                    pair=confirmation.pair,
                    trade_date=confirmation.trade_date,
                    spot=spot,
                    strike=leg.strike,
                    barrier=leg.barrier,
                    expiry_date=expiry.expiration_date,
                    barrier_direction=leg.barrier_direction,
                    product_type=confirmation.product_type,
                    client_direction=None,
                    protected_amount=protected_amount,
                    ratio_amount=ratio_amount,
                    amount_currency=amount_currency,
                    barrier_level_period="continuous",
                    expiry_time_zone=confirmation.expiry_time_zone,
                )
            )
    return trades


def build_uniwell_confirmation_example() -> Confirmation:
    customer = "Australia Uniwell Group Pty Ltd"
    trade_date = date(2026, 4, 15)
    pair = "AUD/USD"
    base_currency = "AUD"
    quote_terms = "USD per 1 AUD"
    return Confirmation(
        customer=customer,
        trade_date=trade_date,
        pair=pair,
        base_currency=base_currency,
        quote_terms=quote_terms,
        references=("4096154", "4096155", "4096156", "4096157", "4096158", "4096159"),
        expiries=(
            ScheduledExpiry(
                expiration_date=date(2026, 8, 28),
                settlement_date=date(2026, 9, 1),
                legs=(
                    OptionLeg(
                        reference="4096154",
                        option_type="European",
                        option_seller="Corpay",
                        option_buyer=customer,
                        strike=0.6900,
                        call_currency="USD",
                        call_amount=500_000,
                        put_currency="AUD",
                        put_amount=724_638,
                    ),
                    OptionLeg(
                        reference="4096155",
                        option_type="Knockout",
                        option_seller=customer,
                        option_buyer="Corpay",
                        strike=0.6900,
                        barrier=0.7050,
                        barrier_direction="down",
                        window_start_date=trade_date,
                        window_end_date=date(2026, 8, 28),
                        call_currency="AUD",
                        call_amount=1_449_275,
                        put_currency="USD",
                        put_amount=1_000_000,
                    ),
                ),
            ),
            ScheduledExpiry(
                expiration_date=date(2026, 9, 29),
                settlement_date=date(2026, 10, 1),
                legs=(
                    OptionLeg(
                        reference="4096156",
                        option_type="European",
                        option_seller="Corpay",
                        option_buyer=customer,
                        strike=0.6900,
                        call_currency="USD",
                        call_amount=500_000,
                        put_currency="AUD",
                        put_amount=724_638,
                    ),
                    OptionLeg(
                        reference="4096157",
                        option_type="Knockout",
                        option_seller=customer,
                        option_buyer="Corpay",
                        strike=0.6900,
                        barrier=0.7050,
                        barrier_direction="down",
                        window_start_date=trade_date,
                        window_end_date=date(2026, 9, 29),
                        call_currency="AUD",
                        call_amount=1_449_275,
                        put_currency="USD",
                        put_amount=1_000_000,
                    ),
                ),
            ),
            ScheduledExpiry(
                expiration_date=date(2026, 10, 29),
                settlement_date=date(2026, 11, 2),
                legs=(
                    OptionLeg(
                        reference="4096158",
                        option_type="European",
                        option_seller="Corpay",
                        option_buyer=customer,
                        strike=0.6900,
                        call_currency="USD",
                        call_amount=500_000,
                        put_currency="AUD",
                        put_amount=724_638,
                    ),
                    OptionLeg(
                        reference="4096159",
                        option_type="Knockout",
                        option_seller=customer,
                        option_buyer="Corpay",
                        strike=0.6900,
                        barrier=0.7050,
                        barrier_direction="down",
                        window_start_date=trade_date,
                        window_end_date=date(2026, 10, 29),
                        call_currency="AUD",
                        call_amount=1_449_275,
                        put_currency="USD",
                        put_amount=1_000_000,
                    ),
                ),
            ),
        ),
    )
