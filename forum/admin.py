from django.contrib import admin
from .models import Post, Reaction, Comment, Reply

admin.site.register(Post)
admin.site.register(Reaction)
admin.site.register(Comment)
admin.site.register(Reply)