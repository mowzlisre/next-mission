from django.urls import path
from . import api


urlpatterns = [
    path('', api.PostListCreateView.as_view(), name='post-list-create'),
    path('create/', api.PostCreateView.as_view(), name='post-create'),
    path('<int:pk>/', api.PostDetailView.as_view(), name='post-detail'),
    path('<int:pk>/react/', api.PostReactView.as_view(), name='post-react'),
    path('<int:pk>/comments/', api.CommentCreateView.as_view(), name='post-comment'),
    path('<int:pk>/comments/all/', api.PostCommentsPaginatedView.as_view(), name='post-comments-all'),
    path('comments/<int:pk>/replies/', api.ReplyCreateView.as_view(), name='comment-reply'),
    path('<int:pk>/edit/', api.PostUpdateDeleteView.as_view(), name='post-edit'),
    path('comments/<int:pk>/edit/', api.CommentUpdateDeleteView.as_view(), name='comment-edit'),
    path('replies/<int:pk>/edit/', api.ReplyUpdateDeleteView.as_view(), name='reply-edit'),
]