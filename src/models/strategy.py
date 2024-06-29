from enum import Enum
from pydantic import BaseModel


class StrategyId(Enum):
    MRAT = "mrat"
    NADARAYA_WATSON_ENVELOPE = "nadaraya_watson_envelope"

    @classmethod
    def get_supported_strategies(cls):
        return [strategy.value for strategy in cls]

    @classmethod
    def validate_strategy(cls, strategy):
        if strategy in cls.get_supported_strategies():
            return strategy
        else:
            raise ValueError(
                f"Unsupported strategy '{strategy}'. Supported strategies are: {', '.join(cls.get_supported_strategies())}"
            )


class StrategyParams(BaseModel):
    use_long: bool
    use_short: bool
    leverage: int
    start_amount: int
    equity_invest_ptc: float
    timeframe: str
    ohlcv_window: int


class MRATParams(StrategyParams):
    id: StrategyId = StrategyId.MRAT
    fast_ma: int
    slow_ma: int
    open_std_alpha: float
    close_std_alpha: float
    tp_pct: float


class NadarayaWatsonEnvelopeParams(StrategyParams):
    id: StrategyId = StrategyId.NADARAYA_WATSON_ENVELOPE
    lookback_window: int
    relative_weighting: float
    start_regression_bar: int
