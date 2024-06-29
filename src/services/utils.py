from src.models.exchange import SupportedExchanges
from src.models.order import MexcOrderSide, OrderSide
from src.models.strategy import StrategyParams, StrategyId


def ext_pair_to_pair(self, ext_pair) -> str:
    return f"{ext_pair}:USDT"


def pair_to_ext_pair(self, pair) -> str:
    return pair.replace(":USDT", "")


def calculate_take_profit(entry_price: int, leverage: int, gain_percentage: float, side: MexcOrderSide) -> float:
    if side == MexcOrderSide.OPEN_LONG:
        take_profit = float(entry_price) * (1 + (float(gain_percentage) / 100) / float(leverage))
    elif side == MexcOrderSide.OPEN_LONG:
        take_profit = float(entry_price) * (1 - (float(gain_percentage) / 100) / float(leverage))
    else:
        take_profit = entry_price

    return take_profit


def get_cs_ps(symbol, market):
    data = market.get(symbol)
    if data:
        info = data["info"]
        cs = float(info.get("contractSize"))
        ps = float(info.get("priceScale"))
        return cs, ps
    return None, None


def get_new_order_amount(
    pair: str, exchange_id: SupportedExchanges, strategie_id: StrategyId, equity_invest_ptc: float
):
    last_order = db.get_last_order(pair, exchange_id, strategie_id)
    new_order_amount = last_order["close_size"] * equity_invest_ptc


def get_new_order_params(
        order_side: OrderSide, strategy_params: StrategyParams, exchange_id: SupportedExchanges, pair
):
    order_amount = db.get_last_order(exchange_id, strategy_params.strategy_id, strategy_params.pair)
