import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
import app.routings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'next_mission_backend.settings')
django.setup()

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(app.routings.websocket_urlpatterns)
    ),
})
