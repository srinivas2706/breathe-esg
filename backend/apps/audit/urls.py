from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework import viewsets, serializers
from .models import AuditLog

class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'

class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    def get_queryset(self):
        record_id = self.request.query_params.get('record')
        qs = AuditLog.objects.all()
        if record_id:
            qs = qs.filter(record_id=record_id)
        return qs

router = DefaultRouter()
router.register('', AuditLogViewSet, basename='audit')
urlpatterns = [path('', include(router.urls))]
