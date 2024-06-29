import argparse
from services import trading
from src.models.exchange import SupportedExchanges
from src.models.strategy import StrategyId
import config


def main():
    parser = argparse.ArgumentParser(description="Trading Application")
    parser.add_argument('pair', required=True, help="pair to use for trading", type=str)
    parser.add_argument(
        'strategy',
        type=str,
        required=True,
        help="The trading strategy to use",
        choices=StrategyId.get_supported_strategies()
    )
    parser.add_argument(
        'exchange',
        type=str,
        required=True,
        help="The trading exchange to use",
        choices=SupportedExchanges.get_supported_exchanges()
    )

    args = parser.parse_args()
    strategy_params = config.load_strategy_config(args.strategy)
    exchange = args.exchange
    pair = args.pair

    try:
        trading.run(exchange, strategy_params, pair)
    except ValueError as e:
        print(e)


if __name__ == '__main__':
    main()
