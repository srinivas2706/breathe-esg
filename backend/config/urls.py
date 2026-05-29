from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def health_check(request):
    """Public endpoint for Railway healthcheck — no auth required."""
    return JsonResponse({'status': 'ok'})


urlpatterns = [
    path('admin/', admin.site.urls),

    # Public healthcheck — must be before auth middleware
    path('api/v1/health/', health_check),

    # Auth
    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # App routes
    path('api/v1/clients/', include('apps.clients.urls')),
    path('api/v1/ingestion/', include('apps.ingestion.urls')),
    path('api/v1/emissions/', include('apps.emissions.urls')),
    path('api/v1/audit/', include('apps.audit.urls')),
    path('api/v1/users/', include('apps.users.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
