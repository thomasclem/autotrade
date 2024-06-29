import datetime
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, validator, Field

from src.models.strategy import StrategyId


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    OPEN = "open"
    CLOSE = "close"


class MexcOrderSide(Enum):
    OPEN_LONG = "1"
    CLOSE_SHORT = "2"
    OPEN_SHORT = "3"
    CLOSE_LONG = "4"


class MexcOrderOpenType(Enum):
    ISOLATED = "1"
    CROSS = "2"


class OrderMarginMode(Enum):
    ISOLATED = "isolated"
    CROSS = "cross"


class MexcOpenLongOrderParams(BaseModel):
    symbol: str
    side: MexcOrderSide = MexcOrderSide.OPEN_LONG.value
    openType: MexcOrderOpenType
    type: str = "5"
    vol: int
    leverage: int
    marketCeiling: bool = False
    priceProtect: int = 0


class MexcCloseLongOrderParams(BaseModel):
    flashClose: bool = True
    leverage: int
    openType: MexcOrderOpenType
    priceProtect: int = 0
    side: MexcOrderSide = MexcOrderSide.CLOSE_LONG.value
    symbol: str
    type: str = "5"
    vol: int
    marketCeiling: bool = False


class OrderResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    symbol: str
    open_price: float
    open_size: float
    close_price: Optional[int] = None
    close_size: Optional[int] = None
    start_date: datetime.datetime
    close_date: Optional[datetime.datetime] = None
    leverage: int
    strategy_id: StrategyId
    exchange_id: str
    type: OrderType
    quantity: float
    profit: Optional[float] = 0.0
    status: OrderStatus = OrderStatus.OPEN


class UpdateOrderResult(BaseModel):
    order_id: str
    close_price: float
    close_size: float
    close_date: datetime.datetime
    profit: float
    status: OrderStatus = OrderStatus.CLOSE


class BitGetTradeSide(Enum):
    OPEN = "open"
    CLOSE = "close"


class BitGetOrderParams(BaseModel):
    symbol: str
    type: OrderType
    side: OrderMarginMode
    amount: float
    price: float
    tradeSide: BitGetTradeSide
    marginMode: OrderMarginMode
    presetStopSurplusPrice: Optional[int]
    reduce: bool


class BitGetOrder(BaseModel):
    id: str
    pair: str
    type: str
    side: str
    price: float
    size: float
    filled: float
    remaining: float
    timestamp: int
