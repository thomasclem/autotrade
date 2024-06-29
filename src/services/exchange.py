import asyncio
import hashlib
import json
from datetime import time

import ccxt
import httpx

from src.models.exchange import SupportedExchanges, BitGetInfo
from src.models.order import MexcOrderSide, MexcOpenLongOrderParams, MexcCloseLongOrderParams, BitGetOrder, \
    BitGetMarginMode, OrderType, OrderSide, OrderMarginMode
from src.config import MEXC_TOKEN, BITGET_API_KEY, BITGET_SECRET
from src.models.strategy import StrategyParams
from src.services import utils


class Mexc(ccxt.mexc):
    def __init__(self):
        super().__init__()
        self.token = MEXC_TOKEN
        self.create_future_order_url = "https://futures.mexc.com/api/v1/private/order/submit"
        self.get_future_order_url = "https://futures.mexc.com/api/v1/private/order/get/"

    async def check_auth(self):
        timestamp = round(time.time() * 1000)
        hash = hashlib.md5((self.token + str(timestamp)).encode('utf-8')).hexdigest()[7:]
        signature = hashlib.md5((str(timestamp) + hash).encode('utf-8')).hexdigest()
        url = "https://futures.mexc.com/api/v1/private/position/open_positions?"
        headers = {
            "x-mxc-nonce": str(timestamp),
            "sec-ch-ua": "\"Chromium\";v=\"112\", \"Google Chrome\";v=\"112\", \"Not:A-Brand\";v=\"99\"",
            "x-mxc-sign": signature,
            "authorization": self.token,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
            "content-type": "application/json",
            "origin": "https://futures.mexc.com",
            "referer": "https://futures.mexc.com/exchange",
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            if not response.json().get("success"):
                raise PermissionError("MEXC web token have expired")

    def get_header(self, order_params):
        timestamp = round(time.time() * 1000)
        hash = hashlib.md5((self.token + str(timestamp)).encode('utf-8')).hexdigest()[7:]
        signature = hashlib.md5((str(timestamp) + order_params + hash).encode('utf-8')).hexdigest()
        headers = {
            "x-mxc-nonce": str(timestamp),
            "sec-ch-ua": "\"Chromium\";v=\"112\", \"Google Chrome\";v=\"112\", \"Not:A-Brand\";v=\"99\"",
            "x-mxc-sign": signature,
            "authorization": self.token,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
            "content-type": "application/json",
            "accept": "*/*",
            "origin": "https://futures.mexc.com",
            "sec-fetch-site": "same-site",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://futures.mexc.com/",
            "accept-language": "en-US,en;q=0.9",
        }
        return headers


    def open_long_order(self, client, symbol, vol, leverage, open_type):
        order_params = MexcOpenLongOrderParams(symbol=symbol, vol=vol, leverage=leverage, openType=open_type)
        headers = self.get_header(order_params)
        response = await client.post(
            self.create_future_order_url,
            data=json.dumps(order_params.dict()),
            headers=headers
        )
        return response.json()

    def close_long_order(self, client, symbol, vol, leverage):
        order_params = MexcCloseLongOrderParams(symbol=symbol, vol=vol, leverage=leverage)
        headers = self.get_header(order_params)
        response = await client.post(
            self.create_future_order_url,
            data=json.dumps(order_params.dict()),
            headers=headers
        )
        return response.json()

    def get_order(self, client, order_id):
        headers = self.get_header({})
        response = await client.get(self.get_future_order_url + str(order_id), headers=headers)
        return response.json()

    def create_order(self, pair: str, strategy_params: StrategyParams):
        return None


class BitGet:
    def __init__(self, public_api=None, secret_api=None):
        self.market = None
        bitget_auth_object = {
            "apiKey": BITGET_API_KEY,
            "secret": BITGET_SECRET,
            "enableRateLimit": True,
            "rateLimit": 100,
            "options": {
                "defaultType": "future",
            },
        }
        if bitget_auth_object["secret"] is None:
            self._auth = False
            self._session = ccxt.bitget()
        else:
            self._auth = True
            self._session = ccxt.bitget(bitget_auth_object)

    async def load_markets(self):
        self.market = await self._session.load_markets()

    async def close(self):
        await self._session.close()

    def get_pair_window_ohlc(self, pair, timeframe: str, ohlcv_window: int):
        data = self._session.fetch_ohlcv(symbol=pair, timeframe=timeframe, limit=ohlcv_window)
        return data

    def amount_to_precision(self, pair: str, amount: float) -> float:
        pair = utils.ext_pair_to_pair(pair)
        try:
            return self._session.amount_to_precision(pair, amount)
        except Exception as e:
            return 0

    async def set_margin_mode_and_leverage(self, pair, margin_mode: BitGetMarginMode, leverage: int):
        try:
            await self._session.set_margin_mode(
                margin_mode,
                pair,
                params={"productType": "USDT-FUTURES", "marginCoin": "USDT"},
            )
        except Exception as e:
            pass
        try:
            if margin_mode == BitGetMarginMode.ISOLATED.value:
                tasks = [self._session.set_leverage(
                    leverage,
                    pair,
                    params={
                        "productType": "USDT-FUTURES",
                        "marginCoin": "USDT",
                        "holdSide": "long",
                    },
                ), self._session.set_leverage(
                    leverage,
                    pair,
                    params={
                        "productType": "USDT-FUTURES",
                        "marginCoin": "USDT",
                        "holdSide": "short",
                    },
                )]
                await asyncio.gather(*tasks)
            else:
                await self._session.set_leverage(
                    leverage,
                    pair,
                    params={"productType": "USDT-FUTURES", "marginCoin": "USDT"},
                )
        except Exception as e:
            pass

        return BitGetInfo(
            success=True,
            message=f"Margin mode and leverage set to {margin_mode} and {leverage}x",
        )

    async def place_order(
            self,
            pair: str,
            side: OrderSide,
            trade_side,
            amount: float,
            type: OrderType,
            reduce: bool,
            margin_mode: OrderMarginMode,
            error=False
    ) -> BitGetOrder:
        pair = utils.ext_pair_to_pair(pair)
        amount = self.amount_to_precision(pair, amount)
        try:
            response = await self._session.create_order(
                symbol=pair,
                type=type.value,
                side=side.value,
                amount=amount,
                params={
                    "reduceOnly": reduce,
                    "tradeSide": trade_side,
                    "marginMode": margin_mode.value,
                },
            )
            order_id = response["id"]
            pair = utils.pair_to_ext_pair(response["symbol"])
            order = await self.get_order_by_id(order_id, pair)
            return order
        except Exception as e:
            print(f"Error {type} {side} {size} {pair} - Price {price} - Error => {str(e)}")
            if error:
                raise e
            else:
                return None

    async def get_order_by_id(self, order_id, pair) -> BitGetOrder:
        pair = utils.ext_pair_to_pair(pair)
        response = await self._session.fetch_order(order_id, pair)
        return BitGetOrder(
            id=response["id"],
            pair=utils.pair_to_ext_pair(response["symbol"]),
            type=response["type"],
            side=response["side"],
            price=response["price"],
            size=response["amount"],
            reduce=response["reduceOnly"],
            filled=response["filled"],
            remaining=response["remaining"],
            timestamp=response["timestamp"],
        )


def load(exchange_name: SupportedExchanges):
    if exchange_name == SupportedExchanges.MEXC:
        return Mexc()
    if exchange_name == SupportedExchanges.BITGET:
        return BitGet()
    else:
        raise ValueError(f"Exchange {exchange_name.value} not supported")

