from rest_framework.pagination import PageNumberPagination
from rest_framework import permissions
from rest_framework.generics import ListAPIView
from .models import Comment
from .serializers import CommentSerializer

class CommentPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'

class PostCommentsPaginatedView(ListAPIView):
    serializer_class = CommentSerializer
    pagination_class = CommentPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        post_id = self.kwargs['pk']
        return Comment.objects.filter(post_id=post_id).order_by('-created_at')