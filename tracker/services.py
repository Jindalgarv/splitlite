from decimal import Decimal, ROUND_HALF_UP
import json
from pywebpush import webpush, WebPushException
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q

from .models import (
    Activity,
    Expense,
    ExpenseSplit,
    Friendship,
    Group,
    GroupMembership,
    Notification,
    Settlement,
    PushSubscription,
)


# ---------------------------------------------------------------------------
# Split Calculations
# ---------------------------------------------------------------------------

def calculate_equal_split(amount, members):
    """
    Divide *amount* equally among *members* (list of User objects).

    Any remainder caused by rounding is added to the first member's share
    so the individual amounts always sum to exactly *amount*.

    Returns ``{user: Decimal}``
    """
    amount = Decimal(str(amount))
    num_members = len(members)
    if num_members == 0:
        return {}

    per_person = (amount / num_members).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    splits = {member: per_person for member in members}

    # Correct rounding drift – assign the remainder to the first member.
    total_assigned = per_person * num_members
    remainder = amount - total_assigned
    if remainder != Decimal('0.00'):
        first = members[0]
        splits[first] = (splits[first] + remainder).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return splits


def calculate_exact_split(amounts_dict):
    """
    Return the provided ``{user: Decimal amount}`` dictionary as-is.

    This is a pass-through for the "exact amounts" split type.
    """
    return {user: Decimal(str(amt)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            for user, amt in amounts_dict.items()}


def calculate_percentage_split(amount, percentages_dict):
    """
    Split *amount* according to percentages.

    ``percentages_dict`` maps ``{user: int/float percentage}`` (values should
    sum to 100).  Returns ``{user: Decimal amount}``.
    """
    amount = Decimal(str(amount))
    splits = {}
    running_total = Decimal('0.00')
    users = list(percentages_dict.keys())

    for i, user in enumerate(users):
        pct = Decimal(str(percentages_dict[user]))
        share = (amount * pct / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if i == len(users) - 1:
            # Last member absorbs any rounding difference.
            share = amount - running_total
        splits[user] = share
        running_total += share

    return splits


def calculate_shares_split(amount, shares_dict):
    """
    Split *amount* by a shares ratio.

    ``shares_dict`` maps ``{user: int shares}``.  Returns ``{user: Decimal}``.
    """
    amount = Decimal(str(amount))
    total_shares = sum(int(s) for s in shares_dict.values())
    if total_shares == 0:
        return {}

    splits = {}
    running_total = Decimal('0.00')
    users = list(shares_dict.keys())

    for i, user in enumerate(users):
        user_shares = Decimal(str(shares_dict[user]))
        share = (amount * user_shares / Decimal(str(total_shares))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        if i == len(users) - 1:
            share = amount - running_total
        splits[user] = share
        running_total += share

    return splits


def create_expense_splits(expense, split_type, members, split_data=None):
    """
    Create ``ExpenseSplit`` rows for *expense*.

    Parameters
    ----------
    expense : Expense
    split_type : str
        One of ``'equal'``, ``'exact'``, ``'percentage'``, ``'shares'``.
    members : list[User]
        Used directly when *split_type* is ``'equal'``.
    split_data : dict | None
        The appropriate mapping for the chosen split type
        (ignored for ``'equal'``).

    Returns the computed splits dict ``{user: Decimal}``.
    """
    if split_type == 'equal':
        splits = calculate_equal_split(expense.amount, members)
    elif split_type == 'exact':
        splits = calculate_exact_split(split_data)
    elif split_type == 'percentage':
        splits = calculate_percentage_split(expense.amount, split_data)
    elif split_type == 'shares':
        splits = calculate_shares_split(expense.amount, split_data)
    else:
        raise ValueError(f"Unknown split type: {split_type}")

    # Persist the split objects.
    objs = [
        ExpenseSplit(expense=expense, user=user, amount_owed=amt)
        for user, amt in splits.items()
    ]
    ExpenseSplit.objects.bulk_create(objs)

    return splits


# ---------------------------------------------------------------------------
# Balance Calculations
# ---------------------------------------------------------------------------

def get_balance_between(user_a, user_b, group=None):
    """
    Net balance between *user_a* and *user_b*.

    A **positive** return value means *user_b* owes *user_a*.
    A **negative** value means *user_a* owes *user_b*.

    If *group* is provided the calculation is scoped to that group.
    """
    # --- expenses where user_a paid and user_b owes ---
    a_paid_filter = Q(expense__paid_by=user_a) & Q(user=user_b)
    # --- expenses where user_b paid and user_a owes ---
    b_paid_filter = Q(expense__paid_by=user_b) & Q(user=user_a)

    if group is not None:
        a_paid_filter &= Q(expense__group=group)
        b_paid_filter &= Q(expense__group=group)

    a_paid_splits = ExpenseSplit.objects.filter(a_paid_filter)
    b_paid_splits = ExpenseSplit.objects.filter(b_paid_filter)

    # Amount user_b owes user_a from expenses.
    b_owes_a = sum((s.amount_owed for s in a_paid_splits), Decimal('0.00'))
    # Amount user_a owes user_b from expenses.
    a_owes_b = sum((s.amount_owed for s in b_paid_splits), Decimal('0.00'))

    # --- settlements ---
    settle_filter_a_to_b = Q(from_user=user_a, to_user=user_b)
    settle_filter_b_to_a = Q(from_user=user_b, to_user=user_a)
    if group is not None:
        settle_filter_a_to_b &= Q(group=group)
        settle_filter_b_to_a &= Q(group=group)

    settled_a_to_b = sum(
        (s.amount for s in Settlement.objects.filter(settle_filter_a_to_b)),
        Decimal('0.00'),
    )
    settled_b_to_a = sum(
        (s.amount for s in Settlement.objects.filter(settle_filter_b_to_a)),
        Decimal('0.00'),
    )

    # Positive means user_b owes user_a.
    balance = (b_owes_a - a_owes_b) - (settled_b_to_a - settled_a_to_b)
    return balance.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_user_total_balance(user):
    """
    Aggregate balance summary for *user* across **all** other users.

    Returns::

        {
            'balances': {other_user: Decimal, ...},
            'total_owed_to_you': Decimal,
            'total_you_owe': Decimal,
            'net_balance': Decimal,
        }
    """
    # Collect every user that shares an expense or settlement with *user*.
    related_user_ids = set()

    # Users from expenses user paid (people who owe user).
    related_user_ids.update(
        ExpenseSplit.objects.filter(expense__paid_by=user)
        .exclude(user=user)
        .values_list('user_id', flat=True)
    )

    # Users who paid for expenses user is part of.
    related_user_ids.update(
        ExpenseSplit.objects.filter(user=user)
        .exclude(expense__paid_by=user)
        .values_list('expense__paid_by_id', flat=True)
    )

    # Users from settlements.
    related_user_ids.update(
        Settlement.objects.filter(from_user=user).values_list('to_user_id', flat=True)
    )
    related_user_ids.update(
        Settlement.objects.filter(to_user=user).values_list('from_user_id', flat=True)
    )

    related_users = User.objects.filter(id__in=related_user_ids)

    balances = {}
    total_owed_to_you = Decimal('0.00')
    total_you_owe = Decimal('0.00')

    for other_user in related_users:
        balance = get_balance_between(user, other_user)
        if balance != Decimal('0.00'):
            balances[other_user] = balance
            if balance > 0:
                total_owed_to_you += balance
            else:
                total_you_owe += abs(balance)

    return {
        'balances': balances,
        'total_owed_to_you': total_owed_to_you.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'total_you_owe': total_you_owe.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'net_balance': (total_owed_to_you - total_you_owe).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
    }


def get_group_balances(group):
    """
    Balance matrix for all members of *group*.

    Returns ``{user: {other_user: Decimal balance, ...}, ...}``
    where a positive value means *other_user* owes *user*.
    """
    member_ids = GroupMembership.objects.filter(group=group).values_list('user_id', flat=True)
    members = list(User.objects.filter(id__in=member_ids))

    matrix = {}
    for user in members:
        matrix[user] = {}
        for other in members:
            if other == user:
                continue
            matrix[user][other] = get_balance_between(user, other, group=group)

    return matrix


# ---------------------------------------------------------------------------
# Debt Simplification
# ---------------------------------------------------------------------------

def simplify_debts(group):
    """
    Minimize the number of transactions needed to settle all debts within
    *group* using a greedy algorithm.

    1. Calculate each member's net balance within the group.
    2. Separate members into creditors (positive net) and debtors (negative net).
    3. Repeatedly match the largest creditor with the largest debtor.

    Returns a list of ``(from_user, to_user, Decimal amount)`` tuples.
    """
    member_ids = GroupMembership.objects.filter(group=group).values_list('user_id', flat=True)
    members = list(User.objects.filter(id__in=member_ids))

    # Net balance per member: positive = others owe them.
    net = {}
    for member in members:
        total = Decimal('0.00')
        for other in members:
            if other == member:
                continue
            total += get_balance_between(member, other, group=group)
        net[member] = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # Split into creditors (owed money) and debtors (owe money).
    creditors = [(user, bal) for user, bal in net.items() if bal > 0]
    debtors = [(user, abs(bal)) for user, bal in net.items() if bal < 0]

    # Sort descending by amount.
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)

    transactions = []

    while creditors and debtors:
        creditor, c_amt = creditors.pop(0)
        debtor, d_amt = debtors.pop(0)

        settle_amt = min(c_amt, d_amt).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        transactions.append((debtor, creditor, settle_amt))

        c_remaining = (c_amt - settle_amt).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        d_remaining = (d_amt - settle_amt).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        if c_remaining > Decimal('0.00'):
            creditors.append((creditor, c_remaining))
            creditors.sort(key=lambda x: x[1], reverse=True)
        if d_remaining > Decimal('0.00'):
            debtors.append((debtor, d_remaining))
            debtors.sort(key=lambda x: x[1], reverse=True)

    return transactions


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def get_friends(user):
    """
    Return a list of ``User`` objects who have an accepted friendship
    with *user* (in either direction).
    """
    sent = Friendship.objects.filter(from_user=user, status='accepted').values_list('to_user_id', flat=True)
    received = Friendship.objects.filter(to_user=user, status='accepted').values_list('from_user_id', flat=True)
    friend_ids = set(sent) | set(received)
    return list(User.objects.filter(id__in=friend_ids))


def get_pending_friend_requests(user):
    """
    Return a QuerySet of ``Friendship`` objects where *user* is the
    recipient and the status is ``'pending'``.
    """
    return Friendship.objects.filter(to_user=user, status='pending')


def log_activity(user, action_type, description, group=None, expense=None, settlement=None):
    """
    Create and return an ``Activity`` record.
    """
    return Activity.objects.create(
        user=user,
        action_type=action_type,
        description=description,
        group=group,
        expense=expense,
        settlement=settlement,
    )


def create_notification(user, message, notification_type='expense', link=''):
    """
    Create and return a ``Notification`` record for *user*.
    """
    notification = Notification.objects.create(
        user=user,
        message=message,
        notification_type=notification_type,
        link=link,
    )
    
    # Send Web Push Notification
    subscriptions = PushSubscription.objects.filter(user=user)
    if subscriptions.exists():
        payload = json.dumps({
            'title': 'SplitLite',
            'body': message,
            'url': link or '/',
            'icon': '/static/tracker/icon-192.png'
        })
        
        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {
                            "p256dh": sub.p256dh,
                            "auth": sub.auth
                        }
                    },
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": settings.VAPID_ADMIN_EMAIL}
                )
            except WebPushException as ex:
                # If subscription is expired or invalid, remove it
                if ex.response and ex.response.status_code in [404, 410]:
                    sub.delete()
                print(f"Web Push Error: {ex}")
            except Exception as e:
                print(f"Web Push Exception: {e}")
                
    return notification
