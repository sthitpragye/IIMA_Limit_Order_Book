from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import Order, Trade, BaseUser
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
from decimal import Decimal, ROUND_HALF_UP
from .models import Order, Trade, StopOrder, MarketControl

logger = logging.getLogger(__name__)


def _visible_available(order):
    quantity = max(int(order.quantity or 0), 0)
    peak_disclosed = max(int(order.disclosed or 0), 0)
    original_quantity = max(int(order.original_quantity or 0), 0)

    if peak_disclosed <= 0:
        return quantity
    if quantity <= 0:
        return 0

    # Iceberg behavior: keep a visible tranche up to disclosed peak size.
    # As fills happen, visible size decreases; once a tranche is fully consumed,
    # the next tranche is released from hidden quantity.
    filled = max(original_quantity - quantity, 0)
    consumed_in_current_tranche = filled % peak_disclosed
    current_tranche_visible = peak_disclosed if consumed_in_current_tranche == 0 else (peak_disclosed - consumed_in_current_tranche)

    return min(quantity, current_tranche_visible)


def _log_fill(new_order, opposite_order, match_quantity, stage):
    logger.info(
        "MATCH_TRACE stage=%s incoming_id=%s incoming_side=%s incoming_mode=%s opposite_id=%s opposite_side=%s fill_qty=%s incoming_remaining=%s opposite_remaining=%s",
        stage,
        new_order.id,
        new_order.order_type,
        new_order.order_mode,
        opposite_order.id,
        opposite_order.order_type,
        match_quantity,
        new_order.quantity,
        opposite_order.quantity,
    )


def _log_match_summary(order, initial_quantity, total_matched, stage, note=''):
    remaining_quantity = max(int(order.quantity or 0), 0)
    logger.info(
        "MATCH_SUMMARY stage=%s order_id=%s side=%s mode=%s initial_qty=%s matched_qty=%s remaining_qty=%s is_matched=%s note=%s",
        stage,
        order.id,
        order.order_type,
        order.order_mode,
        initial_quantity,
        total_matched,
        remaining_quantity,
        order.is_matched,
        note,
    )


# def process_stop_orders():
#     """
#     Check all pending StopOrders against the last traded price.
#     Called at the end of every match_order() run, after trades have been recorded.

#     Trigger conditions:
#       - BUY stop:  triggers when last trade price >= target_price
#       - SELL stop: triggers when last trade price <= target_price

#     On trigger:
#       - A new LIMIT Order is created using the stop order's fields.
#       - match_order() is called on it so it either fills immediately
#         or rests in the book.
#       - The StopOrder row is marked is_matched=True (kept for audit trail).
#     """
#     from .models import StopOrder

#     # Get the last traded price. If no trades exist yet, nothing to check.
#     last_trade = Trade.objects.order_by('-timestamp').first()
#     if last_trade is None:
#         return

#     last_price = last_trade.price

#     pending_stop_orders = StopOrder.objects.filter(is_matched=False)

#     for stop_order in pending_stop_orders:
#         triggered = False

#         if stop_order.order_type == 'BUY' and last_price >= stop_order.target_price:
#             triggered = True
#         elif stop_order.order_type == 'SELL' and last_price <= stop_order.target_price:
#             triggered = True

#         if not triggered:
#             continue

#         logger.info(
#             "STOP_ORDER_TRIGGERED id=%s side=%s target=%s last_price=%s limit_price=%s",
#             stop_order.id,
#             stop_order.order_type,
#             stop_order.target_price,
#             last_price,
#             stop_order.price,
#         )

#         try:
#             with transaction.atomic():
#                 # Convert the stop order into a regular LIMIT order.
#                 new_order = Order(
#                     user=stop_order.user,
#                     user_role=stop_order.user_role,
#                     order_type=stop_order.order_type,
#                     order_mode='LIMIT',
#                     quantity=stop_order.quantity,
#                     disclosed=stop_order.disclosed,
#                     price=stop_order.price,
#                     original_quantity=stop_order.quantity,
#                     is_matched=False,
#                     is_ioc=stop_order.is_ioc,
#                 )
#                 new_order.save()

#                 # Mark the stop order as triggered — kept for audit trail.
#                 stop_order.is_matched = True
#                 # Bypass full_clean() here since order_mode is read-only/editable=False
#                 # and save() calls full_clean() which would re-validate correctly.
#                 stop_order.save()

#                 broadcast_orderbook_update()

#             # Run matching outside the atomic block so that any trades created
#             # by match_order() are visible to subsequent stop order checks.
#             match_order(new_order)

#         except Exception as e:
#             logger.error("STOP_ORDER_ERROR id=%s error=%s", stop_order.id, str(e))

def process_stop_orders():
    """
    Checks all pending StopOrders against the last traded price.
    If triggered, creates the corresponding Order and executes it.
    """
    last_trade = Trade.objects.order_by('-timestamp').first()
    if not last_trade:
        return  # No trades yet to trigger anything

    closing_price = last_trade.price
    pending_stops = StopOrder.objects.filter(is_matched=False)

    for stop_order in pending_stops:
        triggered = False
        
        if stop_order.order_type == "BUY" and closing_price >= stop_order.target_price:
            triggered = True
        elif stop_order.order_type == "SELL" and closing_price <= stop_order.target_price:
            triggered = True

        if triggered:
            new_order = Order(
                user=stop_order.user,
                user_role=stop_order.user_role,
                order_type=stop_order.order_type,
                order_mode=stop_order.order_mode,  # Will cleanly be LIMIT or MARKET
                quantity=stop_order.quantity,
                original_quantity=stop_order.quantity,
                disclosed=stop_order.disclosed,
                price=stop_order.price,            # Will be None for Traders
                is_ioc=stop_order.is_ioc,
                timestamp=timezone.now()
            )
            new_order.save()
            
            stop_order.is_matched = True
            stop_order.save()
            
            match_order(new_order)

def match_order(new_order):
    print("match")

    if new_order.price is not None:
        new_order.price = Decimal(str(new_order.price)).quantize(
            Decimal('0.01'),
            rounding=ROUND_HALF_UP
        )

    initial_quantity = max(int(new_order.quantity or 0), 0)
    total_matched = 0

    with transaction.atomic():
        # For a BUY limit order, look for SELL orders at the same price or lower
        if new_order.order_type == 'BUY' and new_order.order_mode == 'LIMIT':
            opposite_orders = Order.objects.filter(
                order_type='SELL',
                order_mode='LIMIT',
                price__lte=new_order.price,
                is_matched=False
            ).order_by('price', 'timestamp')
            broadcast_orderbook_update()

        # For a SELL limit order, look for BUY orders at the same price or higher
        elif new_order.order_type == 'SELL' and new_order.order_mode == 'LIMIT':
            opposite_orders = Order.objects.filter(
                order_type='BUY',
                order_mode='LIMIT',
                price__gte=new_order.price,
                is_matched=False
            ).order_by('-price', 'timestamp')
            broadcast_orderbook_update()

        # For a BUY market order, look for SELL orders with the lowest price
        elif new_order.order_type == 'BUY' and new_order.order_mode == 'MARKET':
            opposite_orders = Order.objects.filter(
                order_type='SELL',
                is_matched=False
            ).order_by('price', 'timestamp')
            broadcast_orderbook_update()

        # For a SELL market order, look for BUY orders with the highest price
        elif new_order.order_type == 'SELL' and new_order.order_mode == 'MARKET':
            opposite_orders = Order.objects.filter(
                order_type='BUY',
                is_matched=False
            ).order_by('-price', 'timestamp')
            broadcast_orderbook_update()

        # LIMIT order matching
        if new_order.order_mode == "LIMIT":
            remaining_quantity = new_order.quantity
            for opposite_order in opposite_orders:
                while remaining_quantity > 0 and opposite_order.quantity > 0:
                    visible_qty = _visible_available(opposite_order)
                    if visible_qty <= 0:
                        break

                    match_quantity = min(remaining_quantity, visible_qty)
                    match_price = opposite_order.price

                    trade_buyer = new_order.user if new_order.order_type == 'BUY' else opposite_order.user
                    trade_seller = opposite_order.user if new_order.order_type == 'BUY' else new_order.user
                    Trade.objects.create(
                        buyer=trade_buyer,
                        seller=trade_seller,
                        quantity=match_quantity,
                        price=match_price,
                        timestamp=timezone.now()
                    )
                    trade_value = match_price * match_quantity
                    BaseUser.objects.filter(pk=trade_buyer.pk).update(
                        capital=F('capital') - trade_value,
                        inventory=F('inventory') + match_quantity,
                    )
                    BaseUser.objects.filter(pk=trade_seller.pk).update(
                        capital=F('capital') + trade_value,
                        inventory=F('inventory') - match_quantity,
                    )
                    broadcast_orderbook_update()

                    remaining_quantity -= match_quantity
                    total_matched += match_quantity
                    opposite_order.quantity -= match_quantity
                    new_order.quantity -= match_quantity
                    _log_fill(new_order, opposite_order, match_quantity, 'limit')
                    opposite_order.save()
                    new_order.save()
                    broadcast_orderbook_update()

                    if opposite_order.quantity == 0:
                        opposite_order.is_matched = True
                        opposite_order.save()
                        broadcast_orderbook_update()

                    if new_order.quantity == 0:
                        new_order.is_matched = True
                        new_order.save()
                        broadcast_orderbook_update()

                if remaining_quantity <= 0:
                    break

            if new_order.quantity > 0:
                new_order.save()
                broadcast_orderbook_update()
            else:
                new_order.is_matched = True
                new_order.save()
                broadcast_orderbook_update()

            new_order.timestamp = timezone.now()
            new_order.save()
            broadcast_orderbook_update()
            _log_match_summary(new_order, initial_quantity, total_matched, 'limit', 'limit_flow_complete')

        # MARKET order matching
        else:
            remaining_quantity = new_order.quantity
            complete_order = False
            try:
                for opposite_order in opposite_orders:
                    if remaining_quantity <= 0:
                        complete_order = True
                        break

                    while remaining_quantity > 0 and opposite_order.quantity > 0:
                        visible_qty = _visible_available(opposite_order)
                        if visible_qty <= 0:
                            break

                        match_quantity = min(visible_qty, remaining_quantity)
                        trade_buyer = new_order.user if new_order.order_type == 'BUY' else opposite_order.user
                        trade_seller = opposite_order.user if new_order.order_type == 'BUY' else new_order.user
                        trade_price = opposite_order.price
                        Trade.objects.create(
                            buyer=trade_buyer,
                            seller=trade_seller,
                            quantity=match_quantity,
                            price=trade_price,
                            timestamp=timezone.now()
                        )
                        trade_value = trade_price * match_quantity
                        BaseUser.objects.filter(pk=trade_buyer.pk).update(
                            capital=F('capital') - trade_value,
                            inventory=F('inventory') + match_quantity,
                        )
                        BaseUser.objects.filter(pk=trade_seller.pk).update(
                            capital=F('capital') + trade_value,
                            inventory=F('inventory') - match_quantity,
                        )
                        broadcast_orderbook_update()
                        remaining_quantity -= match_quantity
                        total_matched += match_quantity
                        opposite_order.quantity -= match_quantity
                        new_order.quantity -= match_quantity
                        _log_fill(new_order, opposite_order, match_quantity, 'market')

                        if opposite_order.quantity == 0:
                            opposite_order.is_matched = True
                        opposite_order.save()
                        broadcast_orderbook_update()

                        if new_order.quantity == 0:
                            new_order.is_matched = True
                        new_order.save()
                        broadcast_orderbook_update()

                    if remaining_quantity <= 0:
                        complete_order = True
                        break
            except Exception as e:
                print('Some Error Occurred:', e)

            if not complete_order:
                remaining_quantity = 0
                new_order.quantity = 0
                new_order.is_matched = True
                new_order.save()
                broadcast_orderbook_update()
                print("Incomplete order placed")

            _log_match_summary(new_order, initial_quantity, total_matched, 'market', 'market_flow_complete')

    # After all trades from this order are committed, check if any stop orders
    # have been triggered by the last traded price. This runs for both LIMIT
    # and MARKET orders since either can produce trades.
    process_stop_orders()


from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def broadcast_orderbook_update():
    from .models import Order, Trade

    buy_orders = Order.objects.filter(
        order_type='BUY',
        order_mode='LIMIT',
        price__isnull=False,
        is_matched=False,
    ).order_by('-price')
    sell_orders = Order.objects.filter(
        order_type='SELL',
        order_mode='LIMIT',
        price__isnull=False,
        is_matched=False,
    ).order_by('price')
    recent_trades = Trade.objects.order_by('-timestamp')[:10]

    best_bid = buy_orders.first()
    best_ask = sell_orders.first()

    payload = {
        'best_bid': {
            'price': float(best_bid.price),
            'disclosed': _visible_available(best_bid),
        } if best_bid else None,
        'best_ask': {
            'price': float(best_ask.price),
            'disclosed': _visible_available(best_ask),
        } if best_ask else None,
        'buy_orders': [
            {
                'price': float(o.price),
                'disclosed': _visible_available(o),
            } for o in buy_orders
        ],
        'sell_orders': [
            {
                'price': float(o.price),
                'disclosed': _visible_available(o),
            } for o in sell_orders
        ],
        'trades': [
            {
                'buyer': t.buyer.username,
                'seller': t.seller.username,
                'price': float(t.price),
                'quantity': t.quantity,
                'timestamp': t.timestamp.isoformat(),
            } for t in recent_trades
        ]
    }

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'orderbook_group',
        {
            'type': 'send_order_update',
            'payload': payload,
        }
    )
    print("Orderbook updated and broadcasted")