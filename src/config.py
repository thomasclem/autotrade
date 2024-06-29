import os
import json

import certifi

from models.strategy import MRATParams, NadarayaWatsonEnvelopeParams, StrategyId, StrategyParams
from src.models.exchange import SupportedExchanges

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MEXC_API_KEY = os.environ.get('MEXC_API_KEY')
MEXC_API_SECRET = os.environ.get('MEXC_API_SECRET')
MEXC_TOKEN = os.environ.get('MEXC_TOKEN')
BITGET_API_KEY = os.environ.get('BITGET_API_KEY')
BITGET_SECRET = os.environ.get('BITGET_SECRET')

os.environ['SSL_CERT_FILE'] = certifi.where()


def load_strategy_config(strategy_id: StrategyId, pair) -> StrategyParams:
    with open('params.json', 'r') as file:
        config_data = json.load(file)['strategy']
        strategy_params = config_data[strategy_id.value][pair]

    if strategy_id == StrategyId.MRAT.value:
        strategy_params = MRATParams(**strategy_params)
    elif strategy_id == StrategyId.NADARAYA_WATSON_ENVELOPE.value:
        strategy_params = NadarayaWatsonEnvelopeParams(**strategy_params)
    else:
        raise ValueError(
            f"Unsupported strategy '{strategy_id}'. Supported strategies are: {', '.join([s.name for s in StrategyId])}"
        )

    return strategy_params
