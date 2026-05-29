from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IngestionBatchViewSet

router = DefaultRouter()
router.register('batches', IngestionBatchViewSet, basename='batch')

urlpatterns = [
    path('', include(router.urls)),
]
