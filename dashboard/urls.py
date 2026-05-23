from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.login_view, name="login"),
    path("auth/", views.spotify_auth_view, name="spotify_auth"),
    path("callback/", views.callback_view, name="callback"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("friends/add/", views.add_friend, name="add_friend"),
    path("friends/add-bulk/", views.add_friends_bulk, name="add_friends_bulk"),
    path("friends/remove/", views.remove_friend, name="remove_friend"),
    path("friends/export/", views.export_friends, name="export_friends"),
    path("friends/import/", views.import_friends, name="import_friends"),
    path("friends/<str:user_id>/tracks/", views.friend_tracks_view, name="friend_tracks"),
    path("me/following/", views.my_following_view, name="my_following"),
]
