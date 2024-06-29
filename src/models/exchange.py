from enum import Enum

from pydantic import BaseModel


class SupportedExchanges(Enum):
    MEXC = "mexc"
    BITGET = "bitget"

    @classmethod
    def get_supported_exchanges(cls):
        return [strategy.value for strategy in cls]

    @classmethod
    def validate_exchange(cls, exchange):
        if exchange in cls.get_supported_exchanges():
            return exchange
        else:
            raise ValueError(
                f"Unsupported strategy '{exchange}'. Supported strategies are: {', '.join(cls.get_supported_exchanges())}"
            )


class BitGetInfo(BaseModel):
    success: bool
    message: str