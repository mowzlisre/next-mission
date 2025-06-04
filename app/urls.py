from django.urls import path
from . import api

urlpatterns = [
    path("chat/", api.chatbot_view, name="chat-ui"),
    path("mcp/search/", api.MCPInternetSearchView.as_view(), name="mcp-search"),
    path("chat/bookmark", api.BookmarkMessage.as_view()),
    path('chat/bookmark/all', api.BookmarkedChats.as_view())
]