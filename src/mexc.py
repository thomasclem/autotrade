import asyncio
import json
from enum import Enum

import httpx
import hashlib
import time
import os
import certifi
import ccxt

from datetime import datetime

#import telegram_bot

API_KEY_CREATION_DATE = "2024-03-03 15:14:23"
MEXC_API_KEY = os.environ.get('MEXC_API_KEY')
MEXC_API_SECRET = os.environ.get('MEXC_API_SECRET')
MEXC_TOKEN = os.environ.get('MEXC_TOKEN')

os.environ['SSL_CERT_FILE'] = certifi.where()

investment = 30
leverage = 10
gain_percentage = 100

env_file_path = '.env'
temp_file_path = '.env.tmp'


class OrderSide(Enum):
    OPEN_LONG = "1"
    CLOSE_SHORT = "2"
    OPEN_SHORT = "3"
    CLOSE_LONG = "4"


class OrderOpenType(Enum):
    ISOLATED = "1"
    CROSS = "2"


order_side = OrderSide.OPEN_SHORT.value
order_open_type = OrderOpenType.ISOLATED.value


def update_token(token: str):
    with open(env_file_path, 'r') as env_file, open(temp_file_path, 'w') as temp_file:
        for line in env_file:
            if line.startswith(f'export MEXC_TOKEN="'):
                temp_file.write(f'export MEXC_TOKEN="{token}"\n')
            else:
                temp_file.write(line)

    os.replace(temp_file_path, env_file_path)


def get_remaining_days_and_hours_of_api_key() -> dict:
    api_key_creation_date = datetime.strptime(API_KEY_CREATION_DATE, "%Y-%m-%d %H:%M:%S")
    current_date = datetime.now()
    difference = api_key_creation_date - current_date

    days = difference.days
    hours = difference.seconds // 3600
    return {"days": days, "hours": hours}


def calculate_take_profit(entry_price, leverage, gain_percentage, side):
    # Calculate the take_profit1 price based on gain_percentage and leverage
    if side == "Buy":
        take_profit = float(entry_price) * (1 + (float(gain_percentage) / 100) / float(leverage))
    elif side == "Sell":
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


def get_header(param, authorization):
    timestamp = round(time.time() * 1000)
    hash = hashlib.md5((authorization + str(timestamp)).encode('utf-8')).hexdigest()[7:]
    signature = hashlib.md5((str(timestamp) + param + hash).encode('utf-8')).hexdigest()
    headers = {
        "x-mxc-nonce": str(timestamp),
        "sec-ch-ua": "\"Chromium\";v=\"112\", \"Google Chrome\";v=\"112\", \"Not:A-Brand\";v=\"99\"",
        "x-mxc-sign": signature,
        "authorization": authorization,
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

def get_order_params(symbol: str, vol: int, side: OrderSide, leverage: int):
    if side == OrderSide.OPEN_LONG:
        return {
            "symbol": symbol,
            "side": 1,
            "openType": 1,
            "type": "5",
            "vol": vol,
            "leverage": leverage,
            "marketCeiling": False,
            "priceProtect": "0"
        }

    if side == OrderSide.CLOSE_LONG:
        return {
            "flashClose": True,
            "leverage": leverage,
            "openType": 1,
            "priceProtect": "0",
            "side": 4,
            "symbol": symbol,
            "type": "5",
            "vol": vol,
            "marketCeiling": False,
        }



async def place_order(symbol, vol, side, leverage, authorization):
    async with httpx.AsyncClient() as client:
        url = "https://futures.mexc.com/api/v1/private/order/submit"
        order_url = "https://futures.mexc.com/api/v1/private/order/get/"
        order_symbol = symbol.split("/")[0] + "_USDT"

        params = get_order_params(order_symbol, vol, side, leverage)

        param_string = json.dumps(params)
        long_headers = get_header(param_string, authorization)

        # Long
        response = await client.post(url, data=param_string, headers=long_headers)

        order_id = response.json().get("data", '')
        price_header = get_header(param_string, authorization)
        response = await client.get(order_url + str(order_id), headers=price_header)
        #await telegram_bot.send_telegram_message(f"Order status: {response.json()}")
        return response.json()



def get_all_contracts(client):
    market = client.load_markets()
    return market


async def check_auth(client):
    timestamp = round(time.time()*1000)
    hash = hashlib.md5((MEXC_TOKEN + str(timestamp)).encode('utf-8')).hexdigest()[7:]
    signature = hashlib.md5((str(timestamp) + hash).encode('utf-8')).hexdigest()
    url = "https://futures.mexc.com/api/v1/private/position/open_positions?"
    headers = {
        "x-mxc-nonce": str(timestamp),
        "sec-ch-ua": "\"Chromium\";v=\"112\", \"Google Chrome\";v=\"112\", \"Not:A-Brand\";v=\"99\"",
        "x-mxc-sign": signature,
        "authorization": MEXC_TOKEN,
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
        "content-type": "application/json",
        "origin": "https://futures.mexc.com",
        "referer": "https://futures.mexc.com/exchange",
    }
    response = await client.get(url, headers=headers)
    #if not response.json().get("success"):
        #await telegram_bot.send_telegram_message("Web toke have expired")
    print("Auth success")


async def update_contracts_periodically():
    global market
    while True:
        mexc = ccxt.mexc({'apiKey': MEXC_API_KEY, 'secret': MEXC_API_SECRET})
        async with httpx.AsyncClient() as client:
            await check_auth(client)
            market = get_all_contracts(mexc)
            await asyncio.sleep(600)


async def process_token(symbol: str):
    async with httpx.AsyncClient() as client:
        try:
            await place_order(
                token=symbol,
                authorization=MEXC_TOKEN,
                client=client
            )
        except Exception as e:
            print("Mexc-Error: ", e)
