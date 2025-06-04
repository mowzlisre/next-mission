from django.urls import path
from . import api

urlpatterns = [
    path("chat/", api.chatbot_view, name="chat-ui"),
    path("chats/all", api.FetchChats.as_view()),
    path("jobs/search/", api.VeteranJobSearchView.as_view(), name="jobs-search"),
    path("jobs/all/", api.FetchRelJobs.as_view(), name="jobs-fetcha"),
    path("chat/bookmark", api.BookmarkMessage.as_view()),
    path('chat/bookmark/all', api.BookmarkedChats.as_view())

]