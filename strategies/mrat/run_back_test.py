import pandas as pd
import ta
import numpy as np
from utilities.data_manager import ExchangeDataManager
from concurrent.futures import ProcessPoolExecutor, as_completed
import itertools
from tqdm import tqdm

pair = "BNB/USDT:USDT"
exchange_name = "binance"
tf = '15m'
train_start_date = "2023-01-01 00:00:00"
train_end_date = "2023-12-31 00:00:00"
test_start_date = "2023-12-31 00:00:00"


class Strategy():
    def __init__(
        self,
        pair,
        type=["long"],
        params={},
    ):
        self.df_pair = None
        self.df = None
        self.pair = pair
        self.initial_wallet = 1000
        self.use_long = "long" in type
        self.use_short = "short" in type
        self.params = params
        self.result_df = None

    def get_pair_data(self, timeframe, start = 2050, end = 2050):
        exchange = ExchangeDataManager(
            exchange_name=exchange_name,
            path_download="./database/exchanges"
        )

        self.df_pair = exchange.load_data(self.pair, timeframe, start)

    def populate_indicators(self):
        params = self.params
        df = self.df_pair
        df.drop(
            columns=df.columns.difference(['open','high','low','close','volume']),
            inplace=True
        )

        # -- Populate indicators --
        df['fast_ma'] = ta.trend.sma_indicator(close=df["close"], window=params["fast_ma"])
        df['slow_ma'] = ta.trend.sma_indicator(close=df["close"], window=params["slow_ma"])
        df['mrat'] = df['fast_ma'] / df['slow_ma']
        df['mean_mrat'] = ta.trend.sma_indicator(close=df['mrat'], window=params["mean_mrat_lenght"])
        df['stdev_mrat'] = df['mrat'].rolling(params["mean_mrat_lenght"]).std(ddof=0)
        df['open_long_signal'] = df['mean_mrat'].shift(1) - df['mrat'].shift(1) >= params['sigma_open'] * df['stdev_mrat'].shift(1)
        df['close_long_signal'] = df['mrat'].shift(1) - df['mean_mrat'].shift(1) >= params['sigma_close'] * df['stdev_mrat'].shift(1)

        df["is_liquidated"] = False
        df["order_open"] = False
        # Trading logic
        order_open = False
        current_order_number = 0
        open_price = 0
        quantity = 0
        trade_result = 0
        # Constants and Initialization
        initial_wallet = self.initial_wallet
        leverage = 1  # Fixed leverage
        maintenance_margin_percent = 0.004
        wallet = initial_wallet

        for i in df.index:
            if df.at[i, 'open_long_signal'] and not order_open:
                # Open a new order
                current_order_number += 1
                order_open = True
                open_price = df.at[i, 'open']
                open_wallet = df.at[i, 'wallet']
                quantity = (wallet / open_price) * leverage
                df.at[i, 'order_number'] = current_order_number
                df.at[i, 'order_open'] = order_open

            # Assign order_number to all rows of the current order
            if order_open:
                df.at[i, 'order_number'] = current_order_number
                df.at[i, 'order_open'] = order_open
                # Calculate hypothetical_wallet
                hypothetical_wallet = wallet + quantity * (df.at[i, 'open'] - open_price)
                df.at[i, 'hypothetical_wallet'] = hypothetical_wallet
                df.at[i, 'quantity'] = quantity

                # Check for liquidation
                maintenance_margin = (wallet / leverage) * maintenance_margin_percent
                if hypothetical_wallet < maintenance_margin:
                    df.at[i, 'is_liquidated'] = True
                    df.at[i, 'trade_result'] = hypothetical_wallet - wallet
                    wallet = 0  # Update wallet with the loss
                    order_open = False  # Close the order

            # Close the order
            if df.at[i, 'close_long_signal'] and order_open:
                trade_result = quantity * (df.at[i, 'open'] - open_price)
                trade_result_perc = trade_result / open_wallet * 100
                wallet += trade_result  # Update wallet with the profit or loss
                order_open = False  # Close the order
                df.at[i, 'trade_result'] = trade_result
                df.at[i, 'trade_result_perc'] = trade_result_perc

            # Set wallet to current wallet value
            df.at[i, 'wallet'] = wallet

        df["drawdown"] = (df["hypothetical_wallet"] - df["wallet"]) / df["wallet"] * 100

        self.df = df

    def get_result_df(self):
        df = self.df
        final_wallet_amount = df.loc[df["order_open"] & df["close_long_signal"], "wallet"].tail(1)
        total_profit = final_wallet_amount - self.initial_wallet
        total_profit_perc = total_profit / self.initial_wallet * 100
        total_trades = df["order_number"].max()
        avg_trade_profit_perc = df["trade_result_perc"].dropna().mean()
        avg_trade_profit = df["trade_result"].dropna().mean()
        max_drawdown = df["drawdown"].min()

        result_df = pd.DataFrame(
            {
                "params": str(self.params),
                "final_wallet_amount": final_wallet_amount,
                "total_profit": total_profit,
                "total_profit_perc": total_profit_perc,
                "total_trades": total_trades,
                "avg_trade_profit_perc": avg_trade_profit_perc,
                "avg_trade_profit": avg_trade_profit,
                "max_drawdown": max_drawdown,
            }
        )

        self.result_df = result_df


def execute_strategy(batch):
    results = []
    for params in batch:
        fma, sma, sgo, sgc = params
        params = {
            "fast_ma": fma,
            "slow_ma": sma,
            "sigma_open": sgo,
            "sigma_close": sgc,
            "mean_mrat_lenght": sma
        }
        strat = Strategy(
            pair=pair,
            type=["long"],
            params=params
        )
        strat.get_pair_data(timeframe=tf, start=train_start_date)
        strat.populate_indicators()
        strat.get_result_df()
        results.append(strat.result_df)

    return results


def main():
    fast_ma = [*np.arange(5, 11, 1), *np.arange(15, 40, 5)]
    slow_ma = np.arange(60, 145, 5)
    sigma_open = np.arange(2, 3, 0.1)
    sigma_close = np.arange(2, 3, 0.1)
    #fast_ma = [*np.arange(5, 6, 1)]
    #slow_ma = np.arange(60, 70, 5)
    #sigma_open = np.arange(2, 3, 0.2)
    #sigma_close = np.arange(2, 3, 0.2)

    param_combinations = list(itertools.product(fast_ma, slow_ma, sigma_open, sigma_close))

    batch_size = 20  # or another number that works well for your setup
    param_batches = [param_combinations[i:i + batch_size] for i in range(0, len(param_combinations), batch_size)]
    progress_bar = tqdm(total=len(param_combinations))

    result_dfs = []

    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(execute_strategy, batch): batch for batch in param_batches}

        for future in as_completed(futures):
            result_dfs.extend(future.result())
            progress_bar.update(batch_size)

    progress_bar.close()
    pd.concat(result_dfs).to_csv(f"mrat_result_{pair.split('/')[0]}_{exchange_name}_{train_start_date.split(' ')[0]}.csv")


if __name__ == "__main__":
    main()
