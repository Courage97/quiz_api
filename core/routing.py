from django.urls import re_path
from .consumers import LiveSessionConsumer

websocket_urlpatterns = [
    re_path(r'ws/session/(?P<code>\w+)/$', LiveSessionConsumer.as_asgi()),
]
