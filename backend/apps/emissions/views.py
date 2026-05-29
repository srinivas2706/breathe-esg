from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters import rest_framework as filters
from django.utils import timezone
from django.db.models import Sum, Count, Q

from .models import EmissionRecord
from apps.audit.models import AuditLog


class EmissionRecordSerializer(serializers.ModelSerializer):
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    review_status_display = serializers.CharField(source='get_review_status_display', read_only=True)
    flag_display = serializers.CharField(source='get_flag_display', read_only=True)
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'client', 'batch', 'source_type', 'source_ref',
            'scope', 'scope_display', 'category', 'subcategory',
            'activity_value', 'activity_unit',
            'normalised_value', 'normalised_unit',
            'emission_factor_value', 'emission_factor_source', 'co2e_kg',
            'period_start', 'period_end', 'reporting_year',
            'facility_id', 'facility_name', 'country',
            'metadata',
            'review_status', 'review_status_display',
            'flag', 'flag_display', 'flag_detail',
            'reviewer', 'reviewer_name', 'reviewed_at', 'reviewer_note',
            'is_locked', 'locked_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'client', 'batch', 'source_type', 'source_ref',
            'scope', 'category', 'subcategory',
            'activity_value', 'activity_unit',
            'normalised_value', 'normalised_unit',
            'co2e_kg', 'period_start', 'period_end', 'reporting_year',
            'facility_id', 'facility_name', 'country', 'metadata',
            'reviewer', 'reviewer_name', 'reviewed_at',
            'is_locked', 'locked_at', 'created_at', 'updated_at',
        ]

    def get_reviewer_name(self, obj):
        return obj.reviewer.get_full_name() if obj.reviewer else None


class EmissionRecordFilter(filters.FilterSet):
    scope = filters.NumberFilter()
    category = filters.CharFilter()
    review_status = filters.CharFilter()
    source_type = filters.CharFilter()
    flag = filters.CharFilter()
    reporting_year = filters.NumberFilter()
    period_start_after = filters.DateFilter(field_name='period_start', lookup_expr='gte')
    period_start_before = filters.DateFilter(field_name='period_start', lookup_expr='lte')
    facility_id = filters.CharFilter()
    country = filters.CharFilter()

    class Meta:
        model = EmissionRecord
        fields = [
            'scope', 'category', 'review_status', 'source_type',
            'flag', 'reporting_year', 'facility_id', 'country',
        ]


class EmissionRecordViewSet(viewsets.ModelViewSet):
    serializer_class = EmissionRecordSerializer
    filterset_class = EmissionRecordFilter
    search_fields = ['source_ref', 'facility_name', 'facility_id', 'subcategory']
    ordering_fields = ['period_start', 'co2e_kg', 'created_at', 'review_status']
    ordering = ['-period_start']

    def get_queryset(self):
        user = self.request.user
        qs = EmissionRecord.objects.select_related(
            'client', 'batch', 'emission_factor', 'reviewer'
        )
        if not user.is_superuser and user.client:
            qs = qs.filter(client=user.client)
        return qs

    def _snapshot(self, record):
        return {
            'review_status': record.review_status,
            'flag': record.flag,
            'reviewer_note': record.reviewer_note,
            'is_locked': record.is_locked,
            'co2e_kg': str(record.co2e_kg),
        }

    @action(detail=True, methods=['patch'])
    def review(self, request, pk=None):
        record = self.get_object()

        if record.is_locked:
            return Response(
                {'error': 'Record is locked. Contact admin to unlock.'},
                status=status.HTTP_403_FORBIDDEN
            )

        new_status = request.data.get('review_status')
        note = request.data.get('note', '')

        if new_status not in ('APPROVED', 'FLAGGED', 'REJECTED'):
            return Response(
                {'error': 'review_status must be APPROVED, FLAGGED, or REJECTED'},
                status=400
            )

        before = self._snapshot(record)
        record.review_status = new_status
        record.reviewer = request.user
        record.reviewed_at = timezone.now()
        record.reviewer_note = note

        if new_status == 'APPROVED':
            record.is_locked = True
            record.locked_at = timezone.now()

        record.save()

        action_map = {
            'APPROVED': AuditLog.ACTION_APPROVED,
            'FLAGGED':  AuditLog.ACTION_FLAGGED,
            'REJECTED': AuditLog.ACTION_REJECTED,
        }
        AuditLog.objects.create(
            record=record, client=record.client,
            action=action_map[new_status],
            changed_by=request.user,
            before_state=before,
            after_state=self._snapshot(record),
            note=note,
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        return Response(EmissionRecordSerializer(record).data)

    @action(detail=False, methods=['post'])
    def bulk_approve(self, request):
        ids = request.data.get('ids', [])
        note = request.data.get('note', 'Bulk approval')

        if not ids:
            return Response({'error': 'No ids provided'}, status=400)

        records = EmissionRecord.objects.filter(
            id__in=ids,
            review_status=EmissionRecord.STATUS_PENDING,
            is_locked=False,
        )
        if not request.user.is_superuser and request.user.client:
            records = records.filter(client=request.user.client)

        now = timezone.now()
        updated = []
        for record in records:
            before = self._snapshot(record)
            record.review_status = EmissionRecord.STATUS_APPROVED
            record.reviewer = request.user
            record.reviewed_at = now
            record.reviewer_note = note
            record.is_locked = True
            record.locked_at = now
            record.save()

            AuditLog.objects.create(
                record=record, client=record.client,
                action=AuditLog.ACTION_BULK_APPROVED,
                changed_by=request.user,
                before_state=before,
                after_state=self._snapshot(record),
                note=note,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            updated.append(str(record.id))

        return Response({'approved': len(updated), 'ids': updated})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        GET /api/v1/emissions/summary/
        Returns totals by scope and review status.
        If reporting_year param is given, filters by that year.
        If not given, returns ALL records (no year filter).
        FIXED: removed default year=current_year which excluded
        historical sample data (2024) when running in 2026.
        """
        user = request.user
        qs = EmissionRecord.objects.all()
        if not user.is_superuser and user.client:
            qs = qs.filter(client=user.client)

        # Only filter by year if explicitly requested
        year_param = request.query_params.get('reporting_year')
        if year_param:
            qs = qs.filter(reporting_year=year_param)

        by_scope = (
            qs.values('scope')
            .annotate(total_co2e=Sum('co2e_kg'), count=Count('id'))
            .order_by('scope')
        )
        by_status = (
            qs.values('review_status')
            .annotate(count=Count('id'))
            .order_by('review_status')
        )
        by_source = (
            qs.values('source_type')
            .annotate(total_co2e=Sum('co2e_kg'), count=Count('id'))
            .order_by('source_type')
        )
        flagged_count = qs.exclude(flag='').count()
        total = qs.aggregate(t=Sum('co2e_kg'))['t'] or 0

        # Get available years for the year selector
        available_years = list(
            qs.values_list('reporting_year', flat=True)
            .distinct()
            .order_by('-reporting_year')
        )

        return Response({
            'reporting_year': year_param or 'all',
            'available_years': available_years,
            'total_co2e_kg': total,
            'by_scope':  list(by_scope),
            'by_status': list(by_status),
            'by_source': list(by_source),
            'flagged_count': flagged_count,
        })
