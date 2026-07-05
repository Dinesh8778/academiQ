from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema

from users.permissions import IsAdmin, IsAdminOrTeacher

from .models import Student
from .serializers import StudentSerializer, StudentListSerializer


class StudentViewSet(viewsets.ModelViewSet):
    """
    Student records.
    - List: admin or teacher (all); student (self only)
    - Retrieve: admin, teacher, or the student themselves
    - Create/Update: admin or teacher
    - Delete: admin only

    Custom actions:
      GET /api/students/{id}/attendance-percentage/
      GET /api/students/{id}/report-card/
    """
    queryset = Student.objects.select_related('student_class__department').all()

    def get_serializer_class(self):
        if self.action == 'list':
            return StudentListSerializer
        return StudentSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'attendance_percentage', 'report_card'):
            return [IsAuthenticated()]
        if self.action == 'destroy':
            return [IsAdmin()]
        return [IsAdminOrTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_staff:
            if hasattr(user, 'student_profile'):
                # Students can only see themselves
                qs = qs.filter(pk=user.student_profile.pk)
        # Filters
        class_id = self.request.query_params.get('class_id')
        is_active = self.request.query_params.get('is_active')
        if class_id:
            qs = qs.filter(student_class_id=class_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == 'true')
        return qs

    def _check_student_access(self, request, student):
        """Raise 403 if a non-admin/teacher tries to access another student's data."""
        user = request.user
        if user.is_staff:
            return True
        if hasattr(user, 'teacher'):
            return True
        if hasattr(user, 'student_profile') and user.student_profile.pk == student.pk:
            return True
        self.permission_denied(request, message="You can only access your own data.")

    @extend_schema(
        summary="Get attendance percentage for a student",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "student_id": {"type": "integer"},
                    "regno": {"type": "string"},
                    "total_classes": {"type": "integer"},
                    "present": {"type": "integer"},
                    "absent": {"type": "integer"},
                    "percentage": {"type": "number"},
                    "by_subject": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subject": {"type": "string"},
                                "subject_code": {"type": "string"},
                                "total": {"type": "integer"},
                                "present": {"type": "integer"},
                                "percentage": {"type": "number"},
                            },
                        },
                    },
                },
            }
        },
    )
    @action(detail=True, methods=['get'], url_path='attendance-percentage')
    def attendance_percentage(self, request, pk=None):
        """
        GET /api/students/{id}/attendance-percentage/
        Returns overall and per-subject attendance percentage.
        """
        student = self.get_object()
        self._check_student_access(request, student)

        from attendance.models import Attendance
        records = Attendance.objects.filter(student=student).select_related('subject')

        total = records.count()
        present = records.filter(status=True).count()
        absent = total - present
        overall_pct = round((present / total * 100), 2) if total > 0 else 0.0

        # Per-subject breakdown
        from django.db.models import Count, Q
        subject_stats = (
            records.values('subject__id', 'subject__name', 'subject__code')
            .annotate(
                total=Count('id'),
                present_count=Count('id', filter=Q(status=True)),
            )
        )
        by_subject = []
        for row in subject_stats:
            t = row['total']
            p = row['present_count']
            by_subject.append({
                'subject': row['subject__name'],
                'subject_code': row['subject__code'],
                'total': t,
                'present': p,
                'percentage': round((p / t * 100), 2) if t > 0 else 0.0,
            })

        return Response({
            'student_id': student.pk,
            'regno': student.regno,
            'name': student.name,
            'total_classes': total,
            'present': present,
            'absent': absent,
            'percentage': overall_pct,
            'by_subject': by_subject,
        })

    @extend_schema(
        summary="Get report card (marks summary) for a student",
        responses={
            200: {
                "type": "object",
                "properties": {
                    "student_id": {"type": "integer"},
                    "regno": {"type": "string"},
                    "name": {"type": "string"},
                    "overall_percentage": {"type": "number"},
                    "marks": {"type": "array"},
                },
            }
        },
    )
    @action(detail=True, methods=['get'], url_path='report-card')
    def report_card(self, request, pk=None):
        """
        GET /api/students/{id}/report-card/
        Returns all marks with per-subject and overall summary.
        """
        student = self.get_object()
        self._check_student_access(request, student)

        from academics.models import Mark
        from academics.serializers import MarkSummarySerializer

        marks_qs = Mark.objects.filter(student=student).select_related('subject')

        total_obtained = sum(float(m.marks_obtained) for m in marks_qs)
        total_max = sum(float(m.max_marks) for m in marks_qs)
        overall_pct = round((total_obtained / total_max * 100), 2) if total_max > 0 else 0.0

        serializer = MarkSummarySerializer(marks_qs, many=True)
        return Response({
            'student_id': student.pk,
            'regno': student.regno,
            'name': student.name,
            'total_marks_obtained': total_obtained,
            'total_max_marks': total_max,
            'overall_percentage': overall_pct,
            'marks': serializer.data,
        })
