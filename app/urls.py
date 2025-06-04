from django.urls import path
from . import api

urlpatterns = [
    path("chat/", api.chatbot_view, name="chat-ui"),
    path("chats/all", api.FetchChats.as_view()),
    path("jobs/search", api.VeteranJobSearchView.as_view(), name="jobs-search"),
    path("jobs/all", api.FetchRelJobs.as_view(), name="jobs-fetch"),
    path("chat/bookmark", api.BookmarkMessage.as_view()),
    path('chat/bookmark/all', api.BookmarkedChats.as_view()),
    path("mentors/search", api.VeteranMentorSearchView.as_view(), name="mentors-search"),
    path("mentors/all", api.FetchRelMentors.as_view(), name="mentors-fetch"),
    path("events/search", api.VeteranCommunitySearchView.as_view(), name="events-search"),
    path("events/all", api.FetchRelEvents.as_view(), name="events-fetch"),
    path("bio/generate", api.VeteranBioDataView.as_view(), name="bio-fetch"),
    path("bio/download", api.VeteranBioPDFView.as_view(), name="bio-download"),
]