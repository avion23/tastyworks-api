import os
import asyncio
from datetime import date
from decimal import Decimal as D

from tastyworks.models import option_chain, underlying
from tastyworks.models.greeks import Greeks
from tastyworks.models.option import Option, OptionType
from tastyworks.models.order import (Order, OrderDetails, OrderPriceEffect,
                                     OrderType)
from tastyworks.models.session import TastyAPISession
from tastyworks.models.trading_account import TradingAccount
from tastyworks.models.underlying import UnderlyingType
from tastyworks.streamer import DataStreamer
from tastyworks.tastyworks_api import tasty_session
from tastyworks.utils import get_third_friday


async def main_loop(session: TastyAPISession, streamer: DataStreamer):
    accounts = await TradingAccount.get_remote_accounts(session)
    acct = accounts[0]
    print(f'Accounts available: {accounts}')

    orders = await Order.get_remote_orders(session, acct)
    print(f'Number of active orders: {len(orders)}')

    # Execute an order
    details = OrderDetails(
        type=OrderType.LIMIT,
        price=D(400),
        price_effect=OrderPriceEffect.CREDIT)
    new_order = Order(details)

    opt = Option(
        ticker='AKS',
        quantity=1,
        expiry=get_third_friday(date.today()),
        strike=D(3),
        option_type=OptionType.CALL,
        underlying_type=UnderlyingType.EQUITY
    )
    new_order.add_leg(opt)

    res = await acct.execute_order(new_order, session, dry_run=True)
    print(f'Order executed successfully: {res}')

    # Get an options chain
    undl = underlying.Underlying('AKS')

    chain = await option_chain.get_option_chain(session, undl)
    print(f'Chain strikes: {chain.get_all_strikes()}')

    # Get all expirations for the options for the above equity symbol
    exp = chain.get_all_expirations()

    # Choose the next expiration as an example & fetch the entire options chain for that expiration (all strikes)
    next_exp = exp[0]
    chain_next_exp = await option_chain.get_option_chain(session, undl, next_exp)
    options = []
    for option in chain_next_exp.options:
        options.append(option)

    # Get the greeks data for all option symbols via the streamer by subscribing
    options_symbols = [options[x].symbol_dxf for x in range(len(options))]
    greeks_data = await streamer.stream('Greeks', options_symbols)

    for data in greeks_data:
        gd = Greeks().from_streamer_dict(data)
        # gd = Greeks(kwargs=data)
        idx_match = [options[x].symbol_dxf for x in range(len(options))].index(gd.symbol)
        options[idx_match].greeks = gd
        print('> Symbol: {}\tPrice: {}\tDelta {}'.format(gd.symbol, gd.price, gd.delta))

        quote = await streamer.stream('Quote', sub_values)
        print(f'Received item: {quote}')

        await streamer.close()


if __name__ == '__main__':
    # Get environment variables
    user = os.getenv('TASTY_USER')
    password = os.environ.get('TASTY_PASSWORD')
    tasty_client = tasty_session.create_new_session(user, password)
    streamer = DataStreamer(tasty_client)
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(main_loop(tasty_client, streamer))
    except Exception:
        print('Exception in main loop')
    finally:
        # find all futures/tasks still running and wait for them to finish
        pending_tasks = [
            task for task in asyncio.Task.all_tasks() if not task.done()
        ]
        loop.run_until_complete(asyncio.gather(*pending_tasks))
        loop.close()
