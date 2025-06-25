import os
import django

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

# ✅ Set environment and initialize Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'interview_platform.settings')
django.setup()

# ✅ Now safe to import routing and anything that hits models
from core.routing import websocket_urlpatterns

# ✅ Prepare ASGI app
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
