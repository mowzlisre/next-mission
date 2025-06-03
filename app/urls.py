from django.urls import path
from . import api

urlpatterns = [
    path('', api.StatView.as_view()),
    path("chat/", api.chatbot_view, name="chat-ui"),
]