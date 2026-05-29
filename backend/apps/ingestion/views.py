from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from django.shortcuts import get_object_or_404

from .models import IngestionBatch, RawRecord
from apps.clients.models import Client
from . import services


class IngestionBatchSerializer(serializers.ModelSerializer):
    success_rate = serializers.ReadOnlyField()
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)

    class Meta:
        model = IngestionBatch
        fields = [
            'id', 'client', 'source_type', 'source_type_display',
            'original_filename', 'uploaded_at', 'processed_at',
            'status', 'row_count', 'parsed_count', 'error_count',
            'success_rate', 'error_summary', 'notes',
        ]
        read_only_fields = [
            'uploaded_at', 'processed_at', 'status',
            'row_count', 'parsed_count', 'error_count',
        ]


class RawRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = ['id', 'row_number', 'raw_data', 'parse_status', 'parse_error', 'created_at']


class IngestionBatchViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IngestionBatchSerializer

    def get_queryset(self):
        user = self.request.user
        qs = IngestionBatch.objects.select_related('client', 'uploaded_by')
        if not user.is_superuser and user.client:
            qs = qs.filter(client=user.client)
        return qs

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser])
    def upload(self, request):
        file_obj = request.FILES.get('file')
        source_type = request.data.get('source_type', '').upper()
        client_id = request.data.get('client_id')

        if not file_obj:
            return Response({'error': 'No file provided'}, status=400)
        if source_type not in ('SAP', 'UTILITY', 'TRAVEL'):
            return Response({'error': 'source_type must be SAP, UTILITY, or TRAVEL'}, status=400)

        # Determine client
        if request.user.is_superuser:
            client = get_object_or_404(Client, pk=client_id)
        else:
            client = request.user.client
            if client is None:
                return Response({'error': 'User has no associated client'}, status=403)

        # ── CRITICAL FIX ──────────────────────────────────────────────
        # Read file bytes FIRST before Django consumes the file pointer
        # when saving to disk via IngestionBatch.objects.create(file=...).
        # After create(), file_obj.read() returns empty bytes.
        file_bytes = file_obj.read()
        file_obj.seek(0)   # Reset so Django can save the file to disk
        # ─────────────────────────────────────────────────────────────

        batch = IngestionBatch.objects.create(
            client=client,
            source_type=source_type,
            original_filename=file_obj.name,
            file=file_obj,
            uploaded_by=request.user,
        )

        try:
            if source_type == 'SAP':
                services.process_sap_batch(batch, file_bytes, request.user)
            elif source_type == 'UTILITY':
                services.process_utility_batch(batch, file_bytes, request.user)
            elif source_type == 'TRAVEL':
                services.process_travel_batch(batch, file_bytes, request.user)
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            batch.status = IngestionBatch.STATUS_FAILED
            batch.error_summary = f"{str(exc)}\n\n{tb}"
            batch.save(update_fields=['status', 'error_summary'])
            return Response({'error': str(exc), 'detail': tb}, status=500)

        return Response(IngestionBatchSerializer(batch).data, status=201)

    @action(detail=True, methods=['get'])
    def raw_records(self, request, pk=None):
        batch = self.get_object()
        records = RawRecord.objects.filter(batch=batch).order_by('row_number')
        page = self.paginate_queryset(records)
        serializer = RawRecordSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)
