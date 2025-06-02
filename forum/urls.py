from django.urls import path
from .api import RecentPosts


urlpatterns = [
    path('forum/recent', RecentPosts.as_view())
]