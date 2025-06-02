from rest_framework import serializers
from .models import Post, Reaction, Comment, Reply
from django.conf import settings
from django.db import models
User = settings.AUTH_USER_MODEL

class ReplySerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source='author.email', read_only=True)

    class Meta:
        model = Reply
        fields = ['id', 'author_email', 'content', 'created_at']


class CommentSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source='author.email', read_only=True)
    replies = ReplySerializer(many=True, read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'author_email', 'content', 'created_at', 'replies']


class ReactionSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Reaction
        fields = ['id', 'user_email', 'type', 'created_at']


class PostSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source='author.email', read_only=True)
    reactions = serializers.SerializerMethodField()
    comments = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = ['id', 'author_email', 'content', 'image', 'created_at', 'reactions', 'comments']

    def get_reactions(self, post):
        reaction_counts = post.reactions.values('type').order_by().annotate(count=models.Count('type'))
        return {r['type']: r['count'] for r in reaction_counts}

    def get_comments(self, post):
        top_comments = post.comments.all().order_by('-created_at')[:2]
        return CommentSerializer(top_comments, many=True).data


class ReactionCreateSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(choices=Reaction._meta.get_field('type').choices)

    class Meta:
        model = Reaction
        fields = ['type']
