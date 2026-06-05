from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),

    # Friends
    path('friends/', views.friends_list, name='friends_list'),
    path('friends/add/', views.add_friend, name='add_friend'),
    path('friends/search/', views.search_friends_api, name='search_friends_api'),
    path('friends/request/<int:user_id>/', views.send_friend_request, name='send_friend_request'),
    path('friends/accept/<int:friendship_id>/', views.accept_friend, name='accept_friend'),
    path('friends/reject/<int:friendship_id>/', views.reject_friend, name='reject_friend'),
    path('friends/<int:user_id>/', views.friend_detail, name='friend_detail'),
    path('friends/<int:friend_id>/remind/', views.send_reminder, name='send_reminder'),

    # Groups
    path('groups/', views.group_list, name='group_list'),
    path('groups/create/', views.create_group, name='create_group'),
    path('groups/join/<uuid:invite_code>/', views.join_group_via_link, name='join_group_via_link'),
    path('groups/<int:group_id>/', views.group_detail, name='group_detail'),
    path('groups/<int:group_id>/edit/', views.edit_group, name='edit_group'),
    path('groups/<int:group_id>/delete/', views.delete_group, name='delete_group'),
    path('groups/<int:group_id>/reset-invite/', views.reset_group_invite_link, name='reset_group_invite_link'),
    path('groups/<int:group_id>/members/add/', views.add_group_member, name='add_group_member'),
    path('groups/<int:group_id>/members/<int:user_id>/remove/', views.remove_group_member, name='remove_group_member'),
    path('groups/<int:group_id>/balances/', views.group_balances, name='group_balances'),

    # Expenses
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/add/', views.add_expense, name='add_expense'),
    path('expenses/<int:expense_id>/', views.expense_detail, name='expense_detail'),
    path('expenses/<int:expense_id>/edit/', views.edit_expense, name='edit_expense'),
    path('expenses/<int:expense_id>/delete/', views.delete_expense, name='delete_expense'),

    # Settlements
    path('settle/', views.settle_up, name='settle_up'),
    path('settle/history/', views.settlement_history, name='settlement_history'),
    path('settle/auto/<int:friend_id>/', views.auto_settle, name='auto_settle'),

    # Activity
    path('activity/', views.activity_feed, name='activity_feed'),

    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),

    # Profile
    path('profile/', views.profile, name='profile'),

    # Reports
    path('reports/', views.monthly_report, name='monthly_report'),
    path('reports/export/csv/', views.export_csv, name='export_csv'),

    # Google Authentication
    path('accounts/google/login/', views.google_login, name='google_login'),
    path('accounts/google/callback/', views.google_callback, name='google_callback'),

    # Web Push
    path('api/push/subscribe/', views.subscribe_push, name='subscribe_push'),
    path('api/push/vapid-public-key/', views.get_vapid_public_key, name='vapid_public_key'),
]