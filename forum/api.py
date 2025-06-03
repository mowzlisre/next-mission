from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from .models import Post, Reaction, Comment, Reply
from .serializers import (
    PostSerializer,
    ReactionCreateSerializer,
    CommentSerializer,
    ReplySerializer,
    PostCreateSerializer
)

class PostCreateView(generics.CreateAPIView):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


# --- Pagination Class for Comments ---
class CommentPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'


# --- List and Create Posts ---
class PostListCreateView(generics.ListCreateAPIView):
    queryset = Post.objects.all().order_by('-created_at')
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


# --- Retrieve Single Post with Top 2 Comments ---
class PostDetailView(generics.RetrieveAPIView):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticated]


# --- React to Post (Like, Love, etc.) ---
class PostReactView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk)
        serializer = ReactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reaction_type = serializer.validated_data['type']

        # Update or create a reaction
        reaction, created = Reaction.objects.update_or_create(
            user=request.user,
            post=post,
            defaults={'type': reaction_type}
        )
        return Response({
            "message": "Reaction recorded",
            "type": reaction.type
        })


# --- Add Comment to a Post ---
class CommentCreateView(generics.CreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        post = get_object_or_404(Post, pk=self.kwargs['pk'])
        serializer.save(author=self.request.user, post=post)


# --- List All Comments for a Post (Paginated) ---
class PostCommentsPaginatedView(generics.ListAPIView):
    serializer_class = CommentSerializer
    pagination_class = CommentPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        post_id = self.kwargs['pk']
        return Comment.objects.filter(post_id=post_id).order_by('-created_at')


# --- Add Reply to a Comment (1-level only) ---
class ReplyCreateView(generics.CreateAPIView):
    serializer_class = ReplySerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        comment = get_object_or_404(Comment, pk=self.kwargs['pk'])

        # Enforce rule: can't reply to a reply
        if Reply.objects.filter(comment=comment).exists():
            # This comment already has replies, it's okay
            serializer.save(author=self.request.user, comment=comment)
        elif Reply.objects.filter(pk=comment.pk).exists():
            # This is a reply being treated as a comment – reject it
            raise Response(
                {"error": "You cannot reply to a reply."},
                status=status.HTTP_400_BAD_REQUEST
            )
        else:
            # It's a valid top-level comment
            serializer.save(author=self.request.user, comment=comment)


class IsAuthorOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow authors to edit or delete their content.
    """

    def has_object_permission(self, request, view, obj):
        # SAFE_METHODS = GET, HEAD, OPTIONS
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author == request.user
    

from .permissions import IsAuthorOrReadOnly


# --- Update/Delete a Post ---
class PostUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Post.objects.all()
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]


# --- Update/Delete a Comment ---
class CommentUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]


# --- Update/Delete a Reply ---
class ReplyUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Reply.objects.all()
    serializer_class = ReplySerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrReadOnly]
