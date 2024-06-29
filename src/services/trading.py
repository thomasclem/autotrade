import pandas as pd

from src.models.exchange import SupportedExchanges
from src.database.database import Database
from src.models.order import OrderSide
from src.models.strategy import StrategyId, StrategyParams
from src.services import exchange, utils
from src.services import indicator


def is_order_open(exchange: SupportedExchanges, strategy_id: StrategyId, pair: str):
    db = Database()
    last_order: Order = db.get_last_order(exchange, strategy_id, pair)
    return last_order.close_date is None


def get_strategy_capital(s3_client, exchange, strategy, pair):
    db = Database()
    orders_history = db.get_orders_file_path()
    return orders_history["is_close"]


def open_long(df, exchange_name, strategy_params, pair):
    return df["open_long_signal"] and not is_order_open(exchange_name, strategy_params, pair)


def close_long(df, exchange_name, strategy_params, pair):
    return df["close_long_signal"] and is_order_open(exchange_name, strategy_params, pair)


def get_symbol_data(pair, timeframe: str, ohlcv_window: int, client):
    data = client.fetch_ohlcv(symbol=pair, timeframe=timeframe, limit=ohlcv_window)
    return data

def get_symbol_data_df(client, pair, timeframe: str, ohlcv_window: int):
    data = get_symbol_data(client, pair, timeframe, ohlcv_window, client)
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df


def check_for_signals(client, strategy_params: StrategyParams, pair: str):
    timeframe = strategy_params.timeframe
    ohlcv_window = strategy_params.ohlcv_window
    df_pair = get_symbol_data_df(client, pair, timeframe, ohlcv_window)
    ind = indicator.load(df_pair=df_pair, strategy_params=strategy_params)
    df_with_signals = ind.get_signals()

    return df_with_signals


def handle_signals(client, exchange_id, df_signal, strategy_params: StrategyParams, pair: str):
    if open_long(df_signal):
        order_params = utils.get_new_order_params(OrderSide.BUY, strategy_params, exchange_id, pair)
        response = await client.place_order(
            pair=pair,
            side=order_params.side,
            trade_side=order_params.trade_side,
            amount=order_params.amount,
            type=order_params.type,
            margin_mode=order_params.margin_mode
        )
    elif close_long(df_signal):
        order_params = utils.get_new_order_params(OrderSide.SELL, strategy_params, pair, exchange_id)
        response = await client.place_order(
            pair=pair,
            side=order_params.side,
            trade_side=order_params.trade_side,
            amount=order_params.amount,
            type=order_params.type,
            margin_mode=order_params.margin_mode
        )



def run(exchange_name: SupportedExchanges, strategy_params: StrategyParams, pair: str):
    exchange_client = exchange.load(exchange_name)
    df_signals = check_for_signals(exchange_client, strategy_params, pair)
        if strategy_params.use_long:
            if open_long(df_signals, exchange_name, strategy_params, pair):
                exchange_client.open_long_order(client, )
            elif close_long(df_signals, exchange, strategy_params, pair):

