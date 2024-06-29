from typing import Union

import numpy as np
import pandas as pd
import ta

from src.models.strategy import StrategyParams, StrategyId


class Strategy:
    def __init__(
            self,
            df_pair: pd.DataFrame,
            df_signals: pd.DataFrame,
            strategy_params: StrategyParams
    ):
        self.df_signal = None
        self.df_pair = df_pair
        self.df_backtest_result = None
        self.strategy_params = strategy_params

    def clean_signals_df(self):
        df_signal = self.df_signal.copy()
        df_pair = self.df_pair.copy()
        leverage = self.strategy_params.leverage
        wallet = self.strategy_params.start_amount

        df_signal = df_signal.loc[
            df_signal["open_long_signal"] | df_signal["close_long_signal"],
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
            ~ (~ df_order_tmp["close_signal_lag"] & ~ df_order_tmp["open_signal_lag"] & df_order_tmp[
                "close_long_signal"])
        ]
        df_order["order_number"] = df_order["open_long_signal"].cumsum()
        df_order["open_lag"] = df_order["open"].shift(-1)
        df_order["open_order"] = df_order["open"].shift()
        df_order.loc[df_order["open_long_signal"], "open_order"] = df_order.loc[df_order["open_long_signal"], "open"]

        maintenance_margin_percent = 0.004
        quantity = 0
        df_order['quantity'] = 0.0
        df_order['trade_result'] = 0.0
        df_order['trade_result_pct'] = 0.0

        for i, row in df_order.iterrows():
            if row['open_long_signal']:
                quantity = wallet * leverage / row['open']
                df_order.at[i, 'quantity'] = quantity
                df_order.at[i, 'wallet'] = wallet
                open = row['open']
            elif row['close_long_signal']:
                trade_result = (row['open'] - open) * quantity
                df_order.at[i, 'trade_result'] = trade_result
                df_order.at[i, 'trade_result_pct'] = trade_result / wallet * 100
                wallet += trade_result
                df_order.at[i, 'quantity'] = quantity
                quantity = 0

            df_order.at[i, 'wallet'] = wallet

        df_order_tmp = df_order[
            ["order_number", "quantity", "trade_result", "trade_result_pct", "wallet", "open_order"]
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

        return df_order_final

    def get_result_df(self):
        try:
            df = self.clean_signals_df()
            if df is not None:
                total_trades = df.order_number.max()
                final_wallet_amount = df.loc[df["open_long_signal"], "wallet"].tail(1)
                total_profit = final_wallet_amount - self.strategy_params.start_amount
                total_profit_perc = total_profit / self.strategy_params.start_amount * 100
                avg_trade_profit_perc = df["trade_result_pct"].dropna().mean()
                avg_trade_profit = df["trade_result"].dropna().mean()
                max_drawdown = df["drawdown"].min()

                result_df = pd.DataFrame(
                    {
                        "params": str(self.strategy_params),
                        "final_wallet_amount": final_wallet_amount,
                        "total_profit": total_profit,
                        "total_profit_perc": total_profit_perc,
                        "total_trades": total_trades,
                        "avg_trade_profit_perc": avg_trade_profit_perc,
                        "avg_trade_profit": avg_trade_profit,
                        "max_drawdown": max_drawdown,
                    }
                )

                return result_df
            else:
                return None
        except Exception as e:
            print(e)
            print(self.strategy_params)
            return None


class MRATStrategy(Strategy):
    def __init__(self, df_pair: pd.DataFrame, df_signals: pd.DataFrame, strategy_params):
        super().__init__(df_pair, df_signals, strategy_params)

    def get_indicators(self):
        df = self.df_pair
        df['fast_ma'] = ta.trend.sma_indicator(close=df["close"], window=self.strategy_params.fast_ma)
        df['slow_ma'] = ta.trend.sma_indicator(close=df["close"], window=self.strategy_params.slow_ma)
        df['mrat'] = df['fast_ma'] / df['slow_ma']
        df['mean_mrat'] = ta.trend.sma_indicator(close=df['mrat'], window=self.strategy_params.slow_ma)
        df['stdev_mrat'] = df['mrat'].rolling(self.strategy_params.slow_ma).std(ddof=0)

        return df

    def get_signals(self):
        df_indicators = self.get_indicators()
        df_indicators['open_long_signal'] = (
                df_indicators['mean_mrat'].shift(1) - df_indicators['mrat'].shift(1) >=
                self.strategy_params.open_std_alpha * df_indicators['stdev_mrat'].shift(1)
        )
        df_indicators['close_long_signal'] = (
                df_indicators['mrat'].shift(1) - df_indicators['mean_mrat'].shift(1) >=
                self.strategy_params.close_std_alpha * df_indicators['stdev_mrat'].shift(1)
        )

        return df_indicators.iloc[-1, :]


class NadarayaWatsonEnvelope(Strategy):
    def __init__(self, df_pair: pd.DataFrame, df_signals: pd.DataFrame, strategy_params):
        super().__init__(df_pair, df_signals, strategy_params)

    def custom_kernel(self, x):
        """
        Calculate the kernel weighted average using a window of data points from pandas Series.

        Args:
        x (pandas Series): Rolling window of data points.
        h (int): Number of data points to consider (window size).
        alpha (float): Decay factor controlling weight curvature.
        x_0 (int): Position index to calculate relative weights, usually the last index of the window.

        Returns:
        float: Kernel weighted average of the window.
        """
        if len(x) < self.strategy_params.lookback_window + 1:
            return np.nan  # Not enough data to compute the kernel

        x = np.log(x)

        indices = np.arange(
            self.strategy_params.start_regression_bar - self.strategy_params.lookback_window,
            self.strategy_params.start_regression_bar + 1
        )
        weights = np.power(
            1 + (
                    np.power(
                        (self.strategy_params.start_regression_bar - indices), 2) /
                    (2 * self.strategy_params.relative_weighting * self.strategy_params.lookback_window**2)
            ), -self.strategy_params.relative_weighting
        )
        sum_weights = np.sum(weights)
        sum_x_weights = np.dot(weights, x)

        return np.exp(sum_x_weights / sum_weights) if sum_weights != 0 else np.nan

    def get_envelope_values(self, df) -> pd.Series:
        envelope_values = (
            df
            .rolling(window=self.strategy_params.lookback_window + 1)
            .apply(
                lambda x: self.custom_kernel(),
                raw=True
            )
        )

        return envelope_values

    def get_indicators(self) -> pd.DataFrame:
        df = self.df_pair
        df["envelope_low"] = self.get_envelope_values(df["low"])
        df["envelope_high"] = self.get_envelope_values(df["high"])

        return df

    def get_signals(self) -> pd.DataFrame:
        df_indicators = self.get_indicators()
        df_indicators["open_long_signal"] = df_indicators["envelope_low"].shift(1) < df_indicators["close"].shift(1)
        df_indicators["close_long_signal"] = df_indicators["envelope_high"].shift(1) > df_indicators["close"].shift(1)

        return df_indicators


def load(df_pair, strategy_params: StrategyParams) -> Union[MRATStrategy, NadarayaWatsonEnvelope]:
    if strategy_params.id == StrategyId.MRAT:
        return MRATStrategy(df_pair, strategy_params)
    elif strategy_params.id == StrategyId.NADARAYA_WATSON_ENVELOPE:
        return MRATStrategy(df_pair, strategy_params)
    else:
        raise ValueError(f"Unsupported strategy '{strategy_params.id}'")