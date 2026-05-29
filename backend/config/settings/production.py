from .base import *

DEBUG = False

# Railway handles HTTPS at the edge — no app-level SSL redirect needed
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Allow Railway's healthcheck hostname + your app domain
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'healthcheck.railway.app',
    '.railway.app',
    '.up.railway.app',
    '*',   # Catch-all — safe since DEBUG=False and behind Railway's proxy
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
