from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework import viewsets, serializers
from .models import Client, EmissionFactor

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = '__all__'

class ClientViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Client.objects.filter(is_active=True)
    serializer_class = ClientSerializer

router = DefaultRouter()
router.register('', ClientViewSet, basename='client')
urlpatterns = [path('', include(router.urls))]
