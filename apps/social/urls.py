from django.urls import path

from . import views

app_name = "social"
urlpatterns = [
    path("", views.community, name="community"),
    path("friends/add/", views.friend_add, name="friend_add"),
    path("friends/requests/<int:pk>/respond/", views.friend_respond, name="friend_respond"),
    path("friends/requests/<int:pk>/cancel/", views.friend_cancel, name="friend_cancel"),
    path("friends/<int:user_id>/remove/", views.friend_remove, name="friend_remove"),
    path("share/<int:challenge_id>/", views.share_challenge, name="share"),
    path("shared/<int:pk>/", views.shared_detail, name="shared"),
    path("shared/<int:pk>/invite/", views.shared_invite, name="shared_invite"),
    path("shared/<int:pk>/privacy/", views.shared_privacy, name="shared_privacy"),
    path("shared/<int:pk>/leave/", views.shared_leave, name="shared_leave"),
    path("shared/<int:pk>/close/", views.shared_close, name="shared_close"),
    path("join/<str:code>/", views.join, name="join"),
    path("templates/publish/<int:challenge_id>/", views.template_publish, name="template_publish"),
    path("templates/<int:pk>/unpublish/", views.template_unpublish, name="template_unpublish"),
]
