import pandas as pd
import ta
import numpy as np
from utilities.data_manager import ExchangeDataManager
from concurrent.futures import ProcessPoolExecutor, as_completed
import itertools
from tqdm import tqdm

pair = "ETH/USDT:USDT"
exchange_name = "binance"
tf = '15m'
train_start_date = "2023-01-01 00:00:00"
train_end_date = "2023-12-31 00:00:00"
test_start_date = "2023-12-31 00:00:00"

pd.options.mode.chained_assignment = None  # default='warn'


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

        self.df_pair = exchange.load_data(self.pair, timeframe, start, end)

    def populate_indicators(self):
        params = self.params
        df = self.df_pair.copy()
        df.drop(
            columns=df.columns.difference(['open', 'high', 'low', 'close', 'volume']),
            inplace=True
        )
        df['fast_ma'] = ta.trend.sma_indicator(close=df["close"], window=params["fast_ma"])
        df['slow_ma'] = ta.trend.sma_indicator(close=df["close"], window=params["slow_ma"])
        df['mrat'] = df['fast_ma'] / df['slow_ma']
        df['mean_mrat'] = ta.trend.sma_indicator(close=df['mrat'], window=params["mean_mrat_lenght"])
        df['stdev_mrat'] = df['mrat'].rolling(params["mean_mrat_lenght"]).std(ddof=0)
        df['open_long_signal'] = df['mean_mrat'].shift(1) - df['mrat'].shift(1) >= params['sigma_open'] * df[
            'stdev_mrat'].shift(1)
        df['close_long_signal'] = df['mrat'].shift(1) - df['mean_mrat'].shift(1) >= params['sigma_close'] * df[
            'stdev_mrat'].shift(1)

        try:
            df_signal = df.loc[
                df["open_long_signal"] | df["close_long_signal"],
                ["open_long_signal", "close_long_signal", "open", "close"]
            ]
            df_signal["open_signal_lag"] = df_signal["open_long_signal"].shift(fill_value=False)
            df_signal["close_signal_lag"] = df_signal["close_long_signal"].shift(fill_value=False)
            df_first_signal = df_signal[
                (~ df_signal["open_signal_lag"] & (
                            df_signal["open_long_signal"] | df_signal["open_long_signal"].isnull())) |
                (~ df_signal["close_signal_lag"] & df_signal["close_long_signal"])
                ]
            df_first_signal["open_signal_lag"] = df_first_signal["open_long_signal"].shift(fill_value=False)
            df_first_signal["close_signal_lag"] = df_first_signal["close_long_signal"].shift(fill_value=False)

            df_order_tmp = df_first_signal[
                (df_first_signal["open_long_signal"] & (
                            ~df_first_signal["open_signal_lag"] | df_first_signal["open_long_signal"].isnull())) |
                (df_first_signal["close_long_signal"] & ~ df_first_signal["close_signal_lag"])
                ]
            df_order = df_order_tmp.loc[
                ~ (
                        ~ df_order_tmp["close_signal_lag"] &
                        ~ df_order_tmp["open_signal_lag"] &
                        df_order_tmp["close_long_signal"]
                )
            ]
            df_order["order_number"] = df_order["open_long_signal"].cumsum()
            df_order["open_lag"] = df_order["open"].shift(-1)
            df_order["open_order"] = df_order["open"].shift()
            df_order.loc[df_order["open_long_signal"], "open_order"] = df_order.loc[df_order["open_long_signal"], "open"]

            leverage = params["leverage"]  # Fixed leverage
            maintenance_margin_percent = 0.004
            wallet = 1000  # Initial wallet balance
            quantity = 0  # Initial quantity
            open = 0

            # Ensure the DataFrame has 'quantity' and 'trade_result' columns initialized
            df_order['quantity'] = 0.0
            df_order['trade_result'] = 0.0
            df_order['trade_result_pct'] = 0.0

            # Iterating over DataFrame rows to process trading signals
            for i, row in df_order.iterrows():
                # Check if there is a signal to open a long position
                if row['open_long_signal']:
                    # Calculate the new quantity based on the current wallet and leverage
                    quantity = wallet * leverage / row['open']
                    # Update the 'quantity' column with the new quantity
                    df_order.at[i, 'quantity'] = quantity
                    # No change in wallet yet as the position has just opened
                    df_order.at[i, 'wallet'] = wallet
                    # Track the price at which the position was opened
                    open = row['open']
                elif row['close_long_signal']:
                    # Calculate the trade result based on the difference between current and open price
                    trade_result = (row['open'] - open) * quantity
                    # Update the 'trade_result' column with the result of the closed trade
                    df_order.at[i, 'trade_result'] = trade_result
                    df_order.at[i, 'trade_result_pct'] = trade_result / wallet * 100
                    # Update the wallet with the result of the trade
                    wallet += trade_result
                    # Reset quantity as the trade is closed
                    df_order.at[i, 'quantity'] = quantity
                    quantity = 0

                # Update the wallet and quantity for the current row
                df_order.at[i, 'wallet'] = wallet

            df_order_tmp = df_order[
                ["order_number", "quantity", "trade_result", "trade_result_pct", "wallet", "open_order"]
            ]
            df_pair = df[
                ["open", "close", "low", "high", "mrat", "mean_mrat", "stdev_mrat", "open_long_signal", "close_long_signal"]
             ]
            df_order_final = df_pair.join(df_order_tmp)

            f = df_order_final['order_number'].ffill()
            b = df_order_final['order_number'].bfill()

            df_order_final['order_number'] = df_order_final['order_number'].mask(f == b, f)

            f = df_order_final['open_order'].ffill()
            b = df_order_final['open_order'].bfill()

            df_order_final['open_order'] = df_order_final['open_order'].mask(f == b, f)
            df_order_final['wallet'] = df_order_final['wallet'].ffill()
            df_order_final["hypothetical_wallet"] = df_order_final["wallet"].shift() + df_order_final["quantity"] * (
                        df_order_final['open'] - df_order_final["open_order"])
            df_order_final["hypothetical_low_result"] = ((df_order_final["quantity"] * df_order_final["low"]) -
                                                         df_order_final["wallet"]) / df_order_final["wallet"]
            df_order_final["drawdown"] = (df_order_final["low"] - df_order_final["open_order"]) / df_order_final[
                "open_order"] * 100 * leverage
            df_order_final["is_liquidated"] = df_order_final['hypothetical_wallet'] < (
                        df_order_final["wallet"] / leverage) * maintenance_margin_percent

            self.df = df_order_final
        except Exception as e:
            self.df = None

    def get_result_df(self):
        try:
            df = self.df
            if df is not None:
                total_trades = df.order_number.max()
                final_wallet_amount = df.loc[df["open_long_signal"], "wallet"].tail(1)
                total_profit = final_wallet_amount - self.initial_wallet
                total_profit_perc = total_profit / self.initial_wallet * 100
                avg_trade_profit_perc = df["trade_result_pct"].dropna().mean()
                avg_trade_profit = df["trade_result"].dropna().mean()
                max_drawdown = df["drawdown"].min()
                hold_profit = (
                    df.sort_index().iloc[-1]["open"] - df.sort_index().iloc[0]["open"]
                              ) / df.sort_index().iloc[0]["open"] * 100

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
                        "hold_profit": hold_profit
                    }
                )

                self.result_df = result_df
            else:
                self.result_df = None
        except Exception as e:
            print(e)
            print(self.params)
            self.result_df = None


def execute_strategy(batch):
    try:
        results = []
        for params in batch:
            fma, sma, sgo, sgc = params
            if fma < sma:
                params = {
                    "fast_ma": fma,
                    "slow_ma": sma,
                    "sigma_open": round(sgo, 2),
                    "sigma_close": round(sgc, 2),
                    "mean_mrat_lenght": sma,
                    "leverage": 1
                }
                strat = Strategy(
                    pair=pair,
                    type=["long"],
                    params=params
                )
                strat.get_pair_data(timeframe=tf, start=train_start_date, end=train_end_date)
                strat.populate_indicators()
                strat.get_result_df()
                if strat.result_df is not None:
                    results.append(strat.result_df)

        if len(results) > 0:
            return results
    except Exception as e:
        print(e)
        print(params)


def main():
    fast_ma = [*np.arange(5, 15, 1), *np.arange(15, 50, 5)]
    slow_ma = np.arange(50, 150, 5)
    sigma_open = np.arange(1, 3, 0.1)
    sigma_close = np.arange(1, 3, 0.1)
    #fast_ma = [*np.arange(5, 6, 1)]
    #slow_ma = np.arange(60, 70, 5)
    #sigma_open = np.arange(2, 3, 0.2)
    #sigma_close = np.arange(2, 3, 0.2)

    param_combinations = list(itertools.product(fast_ma, slow_ma, sigma_open, sigma_close))

    batch_size = 50  # or another number that works well for your setup
    param_batches = [param_combinations[i:i + batch_size] for i in range(0, len(param_combinations), batch_size)]
    progress_bar = tqdm(total=len(param_combinations))

    result_dfs = []

    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(execute_strategy, batch): batch for batch in param_batches}

        for future in as_completed(futures):
            result_dfs.extend(future.result())
            progress_bar.update(batch_size)

    progress_bar.close()
    pd.concat(result_dfs).to_csv(
        f"{pair.split('/')[0]}_{exchange_name}_{tf}_{train_start_date.split(' ')[0]}_{train_end_date.split(' ')[0]}_2.csv"
    )


if __name__ == "__main__":
    main()
