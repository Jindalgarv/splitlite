from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.utils.timezone import now
from django.views.decorators.cache import cache_control
from decimal import Decimal
import csv
import random
from io import StringIO

from .models import (
    UserProfile, Category, Friendship, Group, GroupMembership,
    Expense, ExpenseSplit, Settlement, Activity, Notification
)
from .forms import UserRegisterForm, UserProfileForm, GroupForm, ExpenseForm, SettlementForm
from .services import (
    create_expense_splits, get_balance_between, get_user_total_balance,
    get_group_balances, simplify_debts, get_friends, get_pending_friend_requests,
    log_activity, create_notification
)


# ─────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────

@login_required
def dashboard(request):
    """Main dashboard showing balance summary, recent activity, groups."""
    balance_data = get_user_total_balance(request.user)
    groups = Group.objects.filter(memberships__user=request.user).order_by('-updated_at')[:6]
    recent_activity = Activity.objects.filter(
        Q(user=request.user) |
        Q(group__memberships__user=request.user)
    ).distinct().order_by('-created_at')[:10]
    friends = get_friends(request.user)
    pending_requests = get_pending_friend_requests(request.user)

    # Build friend balances for dashboard
    friend_balances = []
    for friend in friends:
        balance = get_balance_between(request.user, friend)
        if balance != Decimal('0.00'):
            friend_balances.append({'user': friend, 'balance': balance})
    friend_balances.sort(key=lambda x: abs(x['balance']), reverse=True)

    context = {
        'balance_data': balance_data,
        'groups': groups,
        'recent_activity': recent_activity,
        'friend_balances': friend_balances[:5],
        'pending_requests': pending_requests,
        'total_friends': len(friends),
        'total_groups': Group.objects.filter(memberships__user=request.user).count(),
    }
    return render(request, 'tracker/dashboard.html', context)


# ─────────────────────────────────────────────
# Friends
# ─────────────────────────────────────────────

@login_required
def friends_list(request):
    """Show all friends with balances."""
    from .services import get_balance_breakdown_between
    friends = get_friends(request.user)
    pending_requests = get_pending_friend_requests(request.user)
    sent_requests = Friendship.objects.filter(from_user=request.user, status='pending')

    friend_data = []
    total_net_balance = Decimal('0.00')
    
    for friend in friends:
        balance = get_balance_between(request.user, friend)
        total_net_balance += balance
        breakdown = []
        if balance != Decimal('0.00'):
            breakdown = get_balance_breakdown_between(request.user, friend)
            
        friend_data.append({
            'user': friend, 
            'balance': balance,
            'breakdown': breakdown
        })

    context = {
        'friend_data': friend_data,
        'pending_requests': pending_requests,
        'sent_requests': sent_requests,
        'total_net_balance': total_net_balance,
    }
    return render(request, 'tracker/friends/list.html', context)


@login_required
def add_friend(request):
    """Search and add friends by username or email."""
    results = []
    query = ''
    if request.method == 'POST':
        query = request.POST.get('query', '').strip()
        if query:
            # Find users matching query (exclude self and existing friends)
            existing_friend_ids = [f.id for f in get_friends(request.user)]
            pending_ids = list(Friendship.objects.filter(
                from_user=request.user, status='pending'
            ).values_list('to_user_id', flat=True))
            exclude_ids = existing_friend_ids + pending_ids + [request.user.id]

            results = User.objects.filter(
                Q(username__icontains=query) |
                Q(email__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            ).exclude(id__in=exclude_ids)[:10]

    return render(request, 'tracker/friends/add.html', {'results': results, 'query': query})


@login_required
def search_friends_api(request):
    """Live JSON search endpoint for friend suggestions (called on every keypress)."""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    existing_friend_ids = [f.id for f in get_friends(request.user)]
    pending_ids = list(Friendship.objects.filter(
        from_user=request.user, status='pending'
    ).values_list('to_user_id', flat=True))
    exclude_ids = existing_friend_ids + pending_ids + [request.user.id]

    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(email__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).exclude(id__in=exclude_ids)[:10]

    data = []
    for u in users:
        full_name = u.get_full_name()
        initials = ''
        if u.first_name and u.last_name:
            initials = (u.first_name[0] + u.last_name[0]).upper()
        elif u.username:
            initials = u.username[:2].upper()
        data.append({
            'id': u.id,
            'username': u.username,
            'full_name': full_name or u.username,
            'email': u.email,
            'initials': initials,
            'add_url': f'/friends/request/{u.id}/',
        })

    return JsonResponse({'results': data})


@login_required
def send_friend_request(request, user_id):
    """Send a friend request to a user."""
    to_user = get_object_or_404(User, id=user_id)
    if to_user == request.user:
        messages.error(request, "You can't add yourself as a friend!")
        return redirect('friends_list')

    # Check if friendship already exists in either direction
    existing = Friendship.objects.filter(
        Q(from_user=request.user, to_user=to_user) |
        Q(from_user=to_user, to_user=request.user)
    ).first()

    if existing:
        if existing.status == 'accepted':
            messages.info(request, f"You're already friends with {to_user.get_full_name() or to_user.username}!")
        elif existing.status == 'pending':
            messages.info(request, "Friend request already pending!")
        elif existing.status == 'rejected':
            existing.status = 'pending'
            existing.save()
            messages.success(request, f"Friend request re-sent to {to_user.get_full_name() or to_user.username}!")
    else:
        Friendship.objects.create(from_user=request.user, to_user=to_user, status='pending')
        create_notification(
            to_user,
            f"{request.user.get_full_name() or request.user.username} sent you a friend request!",
            notification_type='friend_request',
            link='/friends/'
        )
        messages.success(request, f"Friend request sent to {to_user.get_full_name() or to_user.username}!")

    return redirect('friends_list')


@login_required
def accept_friend(request, friendship_id):
    """Accept a friend request."""
    friendship = get_object_or_404(Friendship, id=friendship_id, to_user=request.user, status='pending')
    friendship.status = 'accepted'
    friendship.save()
    log_activity(request.user, 'friend_added',
                 f"{request.user.get_full_name() or request.user.username} and {friendship.from_user.get_full_name() or friendship.from_user.username} are now friends!")
    create_notification(
        friendship.from_user,
        f"{request.user.get_full_name() or request.user.username} accepted your friend request!",
        notification_type='friend_request',
        link='/friends/'
    )
    messages.success(request, f"You are now friends with {friendship.from_user.get_full_name() or friendship.from_user.username}!")
    return redirect('friends_list')


@login_required
def reject_friend(request, friendship_id):
    """Reject a friend request."""
    friendship = get_object_or_404(Friendship, id=friendship_id, to_user=request.user, status='pending')
    friendship.status = 'rejected'
    friendship.save()
    messages.info(request, "Friend request declined.")
    return redirect('friends_list')


@login_required
def friend_detail(request, user_id):
    """Show expenses and balance with a specific friend."""
    friend = get_object_or_404(User, id=user_id)
    balance = get_balance_between(request.user, friend)

    # Get shared expenses (where both users have splits, or one paid and the other has a split)
    shared_expenses = Expense.objects.filter(
        Q(paid_by=request.user, splits__user=friend) |
        Q(paid_by=friend, splits__user=request.user)
    ).distinct().order_by('-date')[:20]

    # Get settlements between the two
    settlements = Settlement.objects.filter(
        Q(from_user=request.user, to_user=friend) |
        Q(from_user=friend, to_user=request.user)
    ).order_by('-date')[:10]

    context = {
        'friend': friend,
        'balance': balance,
        'shared_expenses': shared_expenses,
        'settlements': settlements,
    }
    return render(request, 'tracker/friends/detail.html', context)
@login_required
def send_reminder(request, friend_id):
    """Send a sarcastic payment reminder to a friend who owes money."""
    friend = get_object_or_404(User, id=friend_id)
    balance = get_balance_between(request.user, friend)
    
    if balance <= 0:
        messages.error(request, f"{friend.get_full_name() or friend.username} doesn't owe you anything!")
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))
        
    sarcastic_messages = [
        f"Hey {friend.get_full_name() or friend.username}, my wallet is feeling a bit light. Coincidence? I think not. Please pay your ₹{balance} debt.",
        f"Dear {friend.get_full_name() or friend.username}, I'm not saying I'll send the mafia, but I'd prefer if you just paid the ₹{balance} you owe me.",
        f"Friendly reminder that you owe me ₹{balance}. Not so friendly reminder: I know where you live.",
        f"Hey {friend.get_full_name() or friend.username}, are you hoarding wealth? Share the ₹{balance} you owe me before I report you.",
        f"I'm accepting donations! Starting with the ₹{balance} you owe me.",
        f"Did you forget about the ₹{balance} you owe me, or are you just pretending to have amnesia?",
        f"Hey {friend.get_full_name() or friend.username}, just doing my daily debt collection routine. You're up! That'll be ₹{balance}.",
        f"It's been 84 years... still waiting for that ₹{balance}, {friend.get_full_name() or friend.username}.",
        f"I accept cash, UPI, and apologies wrapped in ₹{balance}.",
    ]
    
    message = random.choice(sarcastic_messages)
    
    create_notification(
        friend,
        message,
        notification_type='settlement',
        link=f'/friends/{request.user.id}/'
    )
    
    messages.success(request, "Reminder sent!")
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


# ─────────────────────────────────────────────
# Groups
# ─────────────────────────────────────────────

@login_required
def group_list(request):
    """Show all groups the user belongs to."""
    groups = Group.objects.filter(memberships__user=request.user).order_by('-updated_at')
    group_data = []
    for group in groups:
        member_count = group.memberships.count()
        balance = Decimal('0.00')
        # Calculate user's net balance in this group
        members = [m.user for m in group.memberships.exclude(user=request.user)]
        for member in members:
            balance += get_balance_between(request.user, member, group=group)
        group_data.append({
            'group': group,
            'member_count': member_count,
            'balance': balance,
        })
    return render(request, 'tracker/groups/list.html', {'group_data': group_data})


@login_required
def create_group(request):
    """Create a new group."""
    friends = get_friends(request.user)
    if request.method == 'POST':
        form = GroupForm(request.POST)
        if form.is_valid():
            group = form.save(commit=False)
            group.created_by = request.user
            group.save()
            # Add creator as admin
            GroupMembership.objects.create(group=group, user=request.user, role='admin')
            # Add selected members
            member_ids = request.POST.getlist('members')
            for member_id in member_ids:
                try:
                    user = User.objects.get(id=member_id)
                    GroupMembership.objects.create(group=group, user=user, role='member')
                    create_notification(
                        user,
                        f"{request.user.get_full_name() or request.user.username} added you to \"{group.name}\"",
                        notification_type='group',
                        link=f'/groups/{group.id}/'
                    )
                except User.DoesNotExist:
                    pass
            log_activity(request.user, 'group_created', f'Created group "{group.name}"', group=group)
            messages.success(request, f'Group "{group.name}" created!')
            return redirect('group_detail', group_id=group.id)
    else:
        form = GroupForm()
    return render(request, 'tracker/groups/create.html', {'form': form, 'friends': friends})


@login_required
def group_detail(request, group_id):
    """View a group's expenses, members, and balances."""
    group = get_object_or_404(Group, id=group_id)
    # Verify membership
    if not group.memberships.filter(user=request.user).exists():
        messages.error(request, "You're not a member of this group.")
        return redirect('group_list')

    expenses = group.expenses.all().order_by('-date')[:20]
    members = group.memberships.select_related('user', 'user__profile').all()
    settlements = group.settlements.all().order_by('-date')[:5]

    # Calculate user's balance in this group
    user_balance = Decimal('0.00')
    for membership in members:
        if membership.user != request.user:
            user_balance += get_balance_between(request.user, membership.user, group=group)

    context = {
        'group': group,
        'expenses': expenses,
        'members': members,
        'settlements': settlements,
        'user_balance': user_balance,
        'is_admin': group.memberships.filter(user=request.user, role='admin').exists(),
    }
    return render(request, 'tracker/groups/detail.html', context)


@login_required
def edit_group(request, group_id):
    """Edit group settings."""
    group = get_object_or_404(Group, id=group_id)
    if not group.memberships.filter(user=request.user, role='admin').exists():
        messages.error(request, "Only group admins can edit the group.")
        return redirect('group_detail', group_id=group.id)

    if request.method == 'POST':
        form = GroupForm(request.POST, instance=group)
        if form.is_valid():
            form.save()
            messages.success(request, 'Group updated!')
            return redirect('group_detail', group_id=group.id)
    else:
        form = GroupForm(instance=group)
    return render(request, 'tracker/groups/edit.html', {'form': form, 'group': group})


@login_required
def delete_group(request, group_id):
    """Delete a group."""
    group = get_object_or_404(Group, id=group_id)
    if not group.memberships.filter(user=request.user, role='admin').exists():
        messages.error(request, "Only group admins can delete the group.")
        return redirect('group_detail', group_id=group.id)

    if request.method == 'POST':
        group_name = group.name
        group.delete()
        messages.success(request, f'Group "{group_name}" deleted.')
        return redirect('group_list')
    return render(request, 'tracker/groups/delete.html', {'group': group})


@login_required
def add_group_member(request, group_id):
    """Add a friend to a group."""
    group = get_object_or_404(Group, id=group_id)
    if not group.memberships.filter(user=request.user).exists():
        messages.error(request, "You're not a member of this group.")
        return redirect('group_list')

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        try:
            user = User.objects.get(id=user_id)
            if not group.memberships.filter(user=user).exists():
                GroupMembership.objects.create(group=group, user=user, role='member')
                log_activity(request.user, 'member_added',
                             f"{request.user.get_full_name() or request.user.username} added {user.get_full_name() or user.username} to \"{group.name}\"",
                             group=group)
                create_notification(
                    user,
                    f"{request.user.get_full_name() or request.user.username} added you to \"{group.name}\"",
                    notification_type='group',
                    link=f'/groups/{group.id}/'
                )
                messages.success(request, f'{user.get_full_name() or user.username} added to the group!')
            else:
                messages.info(request, 'User is already a member.')
        except User.DoesNotExist:
            messages.error(request, 'User not found.')

    # Get friends not in the group
    friends = get_friends(request.user)
    current_member_ids = group.memberships.values_list('user_id', flat=True)
    available_friends = [f for f in friends if f.id not in current_member_ids]

    return render(request, 'tracker/groups/add_member.html', {
        'group': group,
        'available_friends': available_friends,
    })


@login_required
def remove_group_member(request, group_id, user_id):
    """Remove a member from a group."""
    group = get_object_or_404(Group, id=group_id)
    if not group.memberships.filter(user=request.user, role='admin').exists():
        messages.error(request, "Only group admins can remove members.")
        return redirect('group_detail', group_id=group.id)

    if request.method == 'POST':
        membership = get_object_or_404(GroupMembership, group=group, user_id=user_id)
        if membership.user == group.created_by:
            messages.error(request, "Cannot remove the group creator.")
        else:
            user_name = membership.user.get_full_name() or membership.user.username
            membership.delete()
            log_activity(request.user, 'member_removed',
                         f"{user_name} was removed from \"{group.name}\"", group=group)
            messages.success(request, f'{user_name} removed from the group.')
    return redirect('group_detail', group_id=group.id)


@login_required
def group_balances(request, group_id):
    """View detailed balances within a group."""
    group = get_object_or_404(Group, id=group_id)
    if not group.memberships.filter(user=request.user).exists():
        messages.error(request, "You're not a member of this group.")
        return redirect('group_list')

    balances = get_group_balances(group)
    simplified = simplify_debts(group) if group.simplify_debts else []
    members = [m.user for m in group.memberships.select_related('user').all()]

    # Build balance details for each member
    member_balances = []
    for member in members:
        net = Decimal('0.00')
        for other in members:
            if member != other:
                net += get_balance_between(member, other, group=group)
        member_balances.append({'user': member, 'net_balance': net})

    context = {
        'group': group,
        'balances': balances,
        'simplified': simplified,
        'member_balances': member_balances,
    }
    return render(request, 'tracker/groups/balances.html', context)


@login_required
def join_group_via_link(request, invite_code):
    """Join a group using an invite link."""
    group = get_object_or_404(Group, invite_code=invite_code)
    
    # Check if already a member
    if group.memberships.filter(user=request.user).exists():
        messages.info(request, f"You are already a member of {group.name}.")
        return redirect('group_detail', group_id=group.id)
    
    # Add member
    GroupMembership.objects.create(group=group, user=request.user, role='member')
    
    log_activity(request.user, 'member_added', f'Joined group via invite link', group=group)
    
    messages.success(request, f"You have successfully joined {group.name}!")
    return redirect('group_detail', group_id=group.id)


@login_required
def reset_group_invite_link(request, group_id):
    """Reset the group's invite link."""
    group = get_object_or_404(Group, id=group_id)
    
    # Check if user is admin (or created the group)
    membership = group.memberships.filter(user=request.user).first()
    if not membership or (membership.role != 'admin' and group.created_by != request.user):
        messages.error(request, "Only group admins can reset the invite link.")
        return redirect('group_detail', group_id=group.id)
    
    if request.method == 'POST':
        import uuid
        group.invite_code = uuid.uuid4()
        group.save(update_fields=['invite_code'])
        messages.success(request, "Invite link has been reset.")
        
    return redirect('group_detail', group_id=group.id)


# ─────────────────────────────────────────────
# Expenses
# ─────────────────────────────────────────────

@login_required
def expense_list(request):
    """List all expenses the user is involved in."""
    from datetime import date
    from decimal import Decimal

    expenses = Expense.objects.filter(
        Q(paid_by=request.user) | Q(splits__user=request.user)
    ).distinct().order_by('-date')

    # Filters
    category_id = request.GET.get('category')
    group_id = request.GET.get('group')
    if category_id:
        expenses = expenses.filter(category_id=category_id)
    if group_id:
        expenses = expenses.filter(group_id=group_id)

    categories = Category.objects.all()
    groups = Group.objects.filter(memberships__user=request.user)

    # ── This month's summary ──────────────────────────────────────
    today = date.today()
    month_start = today.replace(day=1)

    # My share of expenses I PAID this month
    # = sum of my own split amounts on expenses where I am the payer
    my_splits_on_my_expenses = ExpenseSplit.objects.filter(
        user=request.user,
        expense__paid_by=request.user,
        expense__date__gte=month_start,
    ).aggregate(total=Sum('amount_owed'))['total'] or Decimal('0')

    # My share of expenses OTHERS paid this month (what I owe others)
    my_splits_on_others_expenses = ExpenseSplit.objects.filter(
        user=request.user,
        expense__date__gte=month_start,
    ).exclude(expense__paid_by=request.user).aggregate(
        total=Sum('amount_owed')
    )['total'] or Decimal('0')

    total_monthly = my_splits_on_my_expenses + my_splits_on_others_expenses
    month_name = today.strftime('%B')

    context = {
        'expenses': expenses[:50],
        'categories': categories,
        'groups': groups,
        'selected_category': category_id,
        'selected_group': group_id,
        # Monthly stats
        'my_expense_share': my_splits_on_my_expenses,
        'owed_to_others_share': my_splits_on_others_expenses,
        'total_monthly': total_monthly,
        'month_name': month_name,
    }
    return render(request, 'tracker/expenses/list.html', context)



@login_required
def add_expense(request):
    """Add a new expense with splits."""
    group_id = request.GET.get('group')
    group = None
    if group_id:
        group = get_object_or_404(Group, id=group_id)
        if not group.memberships.filter(user=request.user).exists():
            messages.error(request, "You're not a member of this group.")
            return redirect('group_list')

    # Calculate members early so we can pass them as choices to the paid_by field
    if group:
        members = [m.user for m in group.memberships.select_related('user', 'user__profile').all()]
    else:
        members = get_friends(request.user)
        members.append(request.user)

    # Convert list of members to a queryset for the form's ModelChoiceField
    member_ids = [m.id for m in members]
    user_choices = User.objects.filter(id__in=member_ids)

    if request.method == 'POST':
        form = ExpenseForm(request.POST, user_choices=user_choices)
        if form.is_valid():
            expense = form.save(commit=False)
            # paid_by is now handled by the form
            expense.created_by = request.user

            # Set group from POST or GET
            post_group_id = request.POST.get('group')
            if post_group_id:
                expense.group = get_object_or_404(Group, id=post_group_id)
            elif group:
                expense.group = group
            expense.save()

            # Process splits
            split_type = expense.split_type
            selected_member_ids = request.POST.getlist('split_members')
            split_members = list(User.objects.filter(id__in=selected_member_ids))

            if not split_members:
                # If no members selected, default to all group members or just self
                if expense.group:
                    split_members = [m.user for m in expense.group.memberships.all()]
                else:
                    split_members = [request.user]

            # Ensure payer is included in splits
            if expense.paid_by not in split_members:
                split_members.append(expense.paid_by)

            split_data = None
            if split_type == 'exact':
                split_data = {}
                for member in split_members:
                    amt = request.POST.get(f'split_amount_{member.id}', '0')
                    split_data[member] = Decimal(amt)
            elif split_type == 'percentage':
                split_data = {}
                for member in split_members:
                    pct = request.POST.get(f'split_pct_{member.id}', '0')
                    split_data[member] = float(pct)
            elif split_type == 'shares':
                split_data = {}
                for member in split_members:
                    shares = request.POST.get(f'split_shares_{member.id}', '1')
                    split_data[member] = int(shares)

            create_expense_splits(expense, split_type, split_members, split_data)

            # Notifications for involved users
            for member in split_members:
                if member != request.user:
                    create_notification(
                        member,
                        f"{request.user.get_full_name() or request.user.username} added \"{expense.description}\" — ₹{expense.amount}",
                        notification_type='expense',
                        link=f'/expenses/{expense.id}/'
                    )

            log_activity(request.user, 'expense_added',
                         f'Added "{expense.description}" — ₹{expense.amount}',
                         group=expense.group, expense=expense)

            messages.success(request, f'Expense "{expense.description}" added!')
            if expense.group:
                return redirect('group_detail', group_id=expense.group.id)
            return redirect('dashboard')
    else:
        from datetime import date
        form = ExpenseForm(initial={'date': date.today(), 'paid_by': request.user}, user_choices=user_choices)

    categories = Category.objects.all()
    groups_list = Group.objects.filter(memberships__user=request.user)

    context = {
        'form': form,
        'group': group,
        'members': members,
        'categories': categories,
        'groups_list': groups_list,
    }
    return render(request, 'tracker/expenses/add.html', context)


@login_required
def expense_detail(request, expense_id):
    """View expense details and splits."""
    expense = get_object_or_404(Expense, id=expense_id)
    # Verify user is involved
    is_involved = (
        expense.paid_by == request.user or
        expense.splits.filter(user=request.user).exists() or
        (expense.group and expense.group.memberships.filter(user=request.user).exists())
    )
    if not is_involved:
        messages.error(request, "You don't have access to this expense.")
        return redirect('dashboard')

    splits = expense.splits.select_related('user', 'user__profile').all()
    context = {
        'expense': expense,
        'splits': splits,
    }
    return render(request, 'tracker/expenses/detail.html', context)


@login_required
def edit_expense(request, expense_id):
    """Edit an existing expense."""
    expense = get_object_or_404(Expense, id=expense_id)
    if expense.created_by != request.user and expense.paid_by != request.user:
        messages.error(request, "You can only edit expenses you created or paid for.")
        return redirect('expense_detail', expense_id=expense.id)

    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            expense = form.save()
            # Recalculate splits
            expense.splits.all().delete()
            split_type = expense.split_type
            member_ids = request.POST.getlist('split_members')
            members = list(User.objects.filter(id__in=member_ids))
            if not members:
                if expense.group:
                    members = [m.user for m in expense.group.memberships.all()]
                else:
                    members = [expense.paid_by]
            if expense.paid_by not in members:
                members.append(expense.paid_by)

            split_data = None
            if split_type == 'exact':
                split_data = {}
                for member in members:
                    amt = request.POST.get(f'split_amount_{member.id}', '0')
                    split_data[member] = Decimal(amt)
            elif split_type == 'percentage':
                split_data = {}
                for member in members:
                    pct = request.POST.get(f'split_pct_{member.id}', '0')
                    split_data[member] = float(pct)
            elif split_type == 'shares':
                split_data = {}
                for member in members:
                    shares = request.POST.get(f'split_shares_{member.id}', '1')
                    split_data[member] = int(shares)

            create_expense_splits(expense, split_type, members, split_data)
            log_activity(request.user, 'expense_edited',
                         f'Edited "{expense.description}"', group=expense.group, expense=expense)
                         
            # Notifications for involved users
            for member in members:
                if member != request.user:
                    create_notification(
                        member,
                        f"{request.user.get_full_name() or request.user.username} updated the expense \"{expense.description}\"",
                        notification_type='expense',
                        link=f'/expenses/{expense.id}/'
                    )
                         
            messages.success(request, 'Expense updated!')
            return redirect('expense_detail', expense_id=expense.id)
    else:
        form = ExpenseForm(instance=expense)

    if expense.group:
        members = [m.user for m in expense.group.memberships.select_related('user').all()]
    else:
        members = [s.user for s in expense.splits.select_related('user').all()]

    context = {
        'form': form,
        'expense': expense,
        'members': members,
        'current_splits': {s.user_id: s.amount_owed for s in expense.splits.all()},
    }
    return render(request, 'tracker/expenses/edit.html', context)


@login_required
def delete_expense(request, expense_id):
    """Delete an expense."""
    expense = get_object_or_404(Expense, id=expense_id)
    if expense.created_by != request.user and expense.paid_by != request.user:
        messages.error(request, "You can only delete expenses you created or paid for.")
        return redirect('expense_detail', expense_id=expense.id)

    if request.method == 'POST':
        group = expense.group
        description = expense.description
        
        # Get members before deleting
        involved_users = [s.user for s in expense.splits.all()]
        
        expense.delete()
        log_activity(request.user, 'expense_deleted', f'Deleted "{description}"', group=group)
        
        # Send notifications
        for member in involved_users:
            if member != request.user:
                create_notification(
                    member,
                    f"{request.user.get_full_name() or request.user.username} deleted the expense \"{description}\"",
                    notification_type='expense',
                    link='#'
                )
                
        messages.success(request, f'Expense "{description}" deleted.')
        if group:
            return redirect('group_detail', group_id=group.id)
        return redirect('dashboard')
    return render(request, 'tracker/expenses/delete.html', {'expense': expense})


# ─────────────────────────────────────────────
# Settlements
# ─────────────────────────────────────────────

@login_required
def settle_up(request):
    """Record a payment to settle debts."""
    friends = get_friends(request.user)
    group_id = request.GET.get('group')
    to_user_id = request.GET.get('to')
    group = None

    if group_id:
        group = get_object_or_404(Group, id=group_id)

    if request.method == 'POST':
        friend_id = request.POST.get('friend_id')
        payer_choice = request.POST.get('payer')
        amount = Decimal(request.POST.get('amount', '0'))
        date_val = request.POST.get('date')
        notes = request.POST.get('notes', '')
        post_group_id = request.POST.get('group', '')

        friend_user = get_object_or_404(User, id=friend_id)
        
        if payer_choice == 'me':
            from_user = request.user
            to_user = friend_user
        else:
            from_user = friend_user
            to_user = request.user

        settle_group = None
        if post_group_id:
            settle_group = Group.objects.filter(id=post_group_id).first()

        settlement = Settlement.objects.create(
            from_user=from_user,
            to_user=to_user,
            amount=amount,
            date=date_val,
            group=settle_group,
            notes=notes,
        )
        
        # Determine names for activity/notification
        from_name = from_user.get_full_name() or from_user.username
        to_name = to_user.get_full_name() or to_user.username
        
        if from_user == request.user:
            log_activity(request.user, 'settlement', f"You paid ₹{amount} to {to_name}", group=settle_group, settlement=settlement)
            create_notification(to_user, f"{from_name} paid you ₹{amount}", notification_type='settlement', link='/settle/history/')
            messages.success(request, f'Payment of ₹{amount} to {to_name} recorded!')
        else:
            log_activity(request.user, 'settlement', f"{from_name} paid you ₹{amount}", group=settle_group, settlement=settlement)
            create_notification(from_user, f"You recorded a payment of ₹{amount} from {from_name} to you.", notification_type='settlement', link='/settle/history/')
            messages.success(request, f'Payment of ₹{amount} from {from_name} recorded!')

        if settle_group:
            return redirect('group_detail', group_id=settle_group.id)
        return redirect('dashboard')

    # Build friend data with balances
    friend_options = []
    for friend in friends:
        balance = get_balance_between(request.user, friend, group=group)
        friend_options.append({'user': friend, 'balance': balance})

    from datetime import date
    context = {
        'friend_options': friend_options,
        'group': group,
        'groups': Group.objects.filter(memberships__user=request.user),
        'preselected_to': int(to_user_id) if to_user_id else None,
        'today': date.today(),
    }
    return render(request, 'tracker/settle/form.html', context)


@login_required
def settlement_history(request):
    """View past settlements."""
    settlements = Settlement.objects.filter(
        Q(from_user=request.user) | Q(to_user=request.user)
    ).order_by('-date')[:50]
    return render(request, 'tracker/settle/history.html', {'settlements': settlements})


# ─────────────────────────────────────────────
# Activity Feed
# ─────────────────────────────────────────────

@login_required
def activity_feed(request):
    """View activity feed."""
    activities = Activity.objects.filter(
        Q(user=request.user) |
        Q(group__memberships__user=request.user)
    ).distinct().order_by('-created_at')[:50]
    return render(request, 'tracker/activity/feed.html', {'activities': activities})


# ─────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────

@login_required
def notifications(request):
    """View all unread notifications."""
    user_notifications = list(Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:50])
    # Mark the fetched notifications as read
    if user_notifications:
        Notification.objects.filter(id__in=[n.id for n in user_notifications]).update(is_read=True)
    return render(request, 'tracker/notifications.html', {'notifications': user_notifications})


@login_required
def mark_notification_read(request, notification_id):
    """Mark a single notification as read."""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    if notification.link:
        return redirect(notification.link)
    return redirect('notifications')


# ─────────────────────────────────────────────
# Profile
# ─────────────────────────────────────────────

@login_required
def profile(request):
    """Edit user profile."""
    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = UserProfileForm(request.POST)
        if form.is_valid():
            request.user.first_name = form.cleaned_data['first_name']
            request.user.last_name = form.cleaned_data['last_name']
            request.user.email = form.cleaned_data['email']
            request.user.save()
            user_profile.phone = form.cleaned_data.get('phone', '')
            user_profile.save()
            messages.success(request, 'Profile updated!')
            return redirect('profile')
    else:
        form = UserProfileForm(initial={
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
            'phone': user_profile.phone,
        })

    context = {
        'form': form,
        'user_profile': user_profile,
    }
    return render(request, 'tracker/profile.html', context)


# ─────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────

def signup(request):
    """User registration."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            messages.success(request, f'Welcome to SplitLite, {user.first_name or user.username}!')
            return redirect('dashboard')
    else:
        form = UserRegisterForm()
    return render(request, 'registration/signup.html', {'form': form})


def google_login(request):
    """Redirect the user to Google's OAuth2 authorization screen."""
    import urllib.parse
    from django.urls import reverse
    from decouple import config
    
    client_id = config('GOOGLE_CLIENT_ID', default='')
    redirect_uri = request.build_absolute_uri(reverse('google_callback'))
    
    if not client_id or client_id == 'placeholder-google-client-id':
        messages.error(request, "Google OAuth is not configured yet! Please set GOOGLE_CLIENT_ID in your .env file.")
        return redirect('login')
        
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'prompt': 'select_account',
    }
    url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode(params)
    return redirect(url)


def google_callback(request):
    """Handle the OAuth2 callback from Google, exchange code for user profile, and log in."""
    import urllib.request
    import urllib.parse
    import json
    from django.urls import reverse
    from decouple import config
    
    code = request.GET.get('code')
    if not code:
        error_msg = request.GET.get('error', 'Google authentication was cancelled.')
        messages.error(request, f"Authentication failed: {error_msg}")
        return redirect('login')

    client_id = config('GOOGLE_CLIENT_ID', default='')
    client_secret = config('GOOGLE_CLIENT_SECRET', default='')
    redirect_uri = request.build_absolute_uri(reverse('google_callback'))

    # Exchange authorization code for access token
    token_url = 'https://oauth2.googleapis.com/token'
    token_data = urllib.parse.urlencode({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }).encode('utf-8')

    try:
        token_req = urllib.request.Request(token_url, data=token_data, method='POST')
        token_req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        
        with urllib.request.urlopen(token_req) as response:
            token_response = json.loads(response.read().decode('utf-8'))
            access_token = token_response.get('access_token')

        if not access_token:
            messages.error(request, "Failed to retrieve access token from Google.")
            return redirect('login')

        # Retrieve user info using access token
        userinfo_url = 'https://www.googleapis.com/oauth2/v3/userinfo'
        userinfo_req = urllib.request.Request(userinfo_url)
        userinfo_req.add_header('Authorization', f'Bearer {access_token}')

        with urllib.request.urlopen(userinfo_req) as response:
            user_data = json.loads(response.read().decode('utf-8'))

        email = user_data.get('email')
        if not email:
            messages.error(request, "Failed to retrieve email address from Google account.")
            return redirect('login')

        # Find or create user
        user = User.objects.filter(email=email).first()
        created = False
        if not user:
            # Generate a clean unique username
            base_username = email.split('@')[0]
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            given_name = user_data.get('given_name', '')
            family_name = user_data.get('family_name', '')
            
            # Create the User object
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=given_name,
                last_name=family_name
            )
            # Create a random password
            user.set_unusable_password()
            user.save()
            created = True

        # Log user in
        if not hasattr(user, 'backend'):
            user.backend = 'django.contrib.auth.backends.ModelBackend'
        auth_login(request, user)
        if created:
            messages.success(request, f'Welcome to SplitLite, {user.first_name or user.username}! Google account registered successfully.')
        else:
            messages.success(request, f'Welcome back, {user.first_name or user.username}! Signed in via Google.')

        return redirect('dashboard')

    except Exception as e:
        messages.error(request, f"Error communicating with Google authentication services: {str(e)}")
        return redirect('login')


# ─────────────────────────────────────────────
# Reports
# ─────────────────────────────────────────────

MONTHS = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April',
    5: 'May', 6: 'June', 7: 'July', 8: 'August',
    9: 'September', 10: 'October', 11: 'November', 12: 'December'
}


@login_required
def monthly_report(request):
    """Monthly expense report."""
    today = now()
    current_year = today.year

    # Expenses user paid
    monthly_paid = Expense.objects.filter(
        paid_by=request.user, date__year=current_year
    ).values('date__month').annotate(total=Sum('amount')).order_by('date__month')

    # Expenses user owes (splits)
    monthly_owed = ExpenseSplit.objects.filter(
        user=request.user, expense__date__year=current_year
    ).exclude(expense__paid_by=request.user).values(
        'expense__date__month'
    ).annotate(total=Sum('amount_owed')).order_by('expense__date__month')

    for item in monthly_paid:
        item['month'] = MONTHS.get(item['date__month'], '')
    for item in monthly_owed:
        item['month'] = MONTHS.get(item['expense__date__month'], '')

    context = {
        'monthly_paid': monthly_paid,
        'monthly_owed': monthly_owed,
        'current_year': current_year,
    }
    return render(request, 'tracker/reports/monthly.html', context)


@login_required
def export_csv(request):
    """Export expenses as CSV."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=expenses.csv'
    writer = csv.writer(response)
    writer.writerow(['Description', 'Amount', 'Date', 'Paid By', 'Category', 'Group', 'Split Type', 'Your Share'])

    expenses = Expense.objects.filter(
        Q(paid_by=request.user) | Q(splits__user=request.user)
    ).distinct().select_related('paid_by', 'category', 'group')

    for expense in expenses:
        split = expense.splits.filter(user=request.user).first()
        your_share = split.amount_owed if split else ''
        writer.writerow([
            expense.description,
            expense.amount,
            expense.date,
            expense.paid_by.get_full_name() or expense.paid_by.username,
            expense.category.name if expense.category else '',
            expense.group.name if expense.group else 'Non-group',
            expense.get_split_type_display(),
            your_share,
        ])
    return response


# ─────────────────────────────────────────────
# PWA Service Worker
# ─────────────────────────────────────────────

@cache_control(max_age=0)
def service_worker(request):
    """Serve the service worker JS from the root scope."""
    import os
    sw_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'static', 'tracker', 'sw.js'
    )
    with open(sw_path, 'r') as f:
        return HttpResponse(f.read(), content_type='application/javascript')


# ─────────────────────────────────────────────
# Web Push Notifications
# ─────────────────────────────────────────────
from django.views.decorators.http import require_POST

@login_required
@require_POST
def subscribe_push(request):
    import json
    from .models import PushSubscription
    try:
        data = json.loads(request.body)
        endpoint = data.get('endpoint')
        keys = data.get('keys', {})
        p256dh = keys.get('p256dh')
        auth = keys.get('auth')

        if not endpoint or not p256dh or not auth:
            return JsonResponse({'status': 'error', 'message': 'Missing data'}, status=400)

        subscription, created = PushSubscription.objects.get_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={'p256dh': p256dh, 'auth': auth}
        )
        
        if not created:
            subscription.p256dh = p256dh
            subscription.auth = auth
            subscription.save()

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
def get_vapid_public_key(request):
    from django.conf import settings
    # Read the PEM file and convert to base64 for frontend, OR if we had it as string we'd just send it.
    # We already extracted it manually:
    public_key = "BH0BAnhPYXGfYR7yTg0_XEYKjjtJPTzdH16oS4r2-Kg8hzzmkdug2yo1U2C1yWrQqyHeQ0BfKNkWjSubHj6WXTw"
    return JsonResponse({'public_key': public_key})
