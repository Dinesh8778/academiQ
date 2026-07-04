from django.db import transaction

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema

from users.permissions import IsAdminOrTeacher, IsAdmin
from students.models import Student
from academics.models import Class, Subject

from .models import Attendance
from .serializers import AttendanceSerializer
from academics.serializers import BulkAttendanceSerializer


class AttendanceViewSet(viewsets.ModelViewSet):
    """
    Attendance records.
    - List/Retrieve: admin, teacher, student (own)
    - Create/Update: admin or teacher
    - Delete: admin only

    Custom action:
      POST /api/attendance/bulk-mark/  — mark full class in one call
    """
    queryset = Attendance.objects.select_related(
        'student', 'subject', 'marked_by__user'
    ).all()
    serializer_class = AttendanceSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'attendance_percentage'):
            return [IsAuthenticated()]
        if self.action == 'destroy':
            return [IsAdmin()]
        return [IsAdminOrTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_staff:
            if hasattr(user, 'student_profile'):
                qs = qs.filter(student=user.student_profile)
        # Optional filters
        student_id = self.request.query_params.get('student')
        subject_id = self.request.query_params.get('subject')
        date = self.request.query_params.get('date')
        class_id = self.request.query_params.get('class_id')
        if student_id:
            qs = qs.filter(student_id=student_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if date:
            qs = qs.filter(date=date)
        if class_id:
            qs = qs.filter(student__student_class_id=class_id)
        return qs

    def perform_create(self, serializer):
        teacher = getattr(self.request.user, 'teacher', None)
        serializer.save(marked_by=teacher)

    @extend_schema(
        summary="Bulk mark attendance for an entire class",
        description=(
            "Mark attendance for every student in a class in a single request. "
            "Existing records for the same (student, subject, date) are updated. "
            "Students missing from the records list are left untouched."
        ),
        request=BulkAttendanceSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "created": {"type": "integer"},
                    "updated": {"type": "integer"},
                    "errors": {"type": "array", "items": {"type": "string"}},
                },
            }
        },
    )
    @action(detail=False, methods=['post'], url_path='bulk-mark',
            permission_classes=[IsAdminOrTeacher])
    def bulk_mark(self, request):
        """
        POST /api/attendance/bulk-mark/

        Mark attendance for an entire class in a single request.
        Existing records for the same (student, subject, date) are updated.
        Missing students in the records list are left untouched.
        """
        serializer = BulkAttendanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        class_id = data['class_id']
        subject_id = data['subject_id']
        date = data['date']
        records = data['records']

        # Validate class and subject exist
        student_class = get_object_or_404_safe(Class, pk=class_id)
        if student_class is None:
            return Response({"detail": f"Class {class_id} not found."}, status=404)

        subject = get_object_or_404_safe(Subject, pk=subject_id)
        if subject is None:
            return Response({"detail": f"Subject {subject_id} not found."}, status=404)

        # Verify teacher has rights to this class
        user = request.user
        if not user.is_staff and hasattr(user, 'teacher'):
            from academics.models import TeacherSubjectClass
            has_access = TeacherSubjectClass.objects.filter(
                teacher=user.teacher,
                subject=subject,
                student_class=student_class,
            ).exists()
            if not has_access:
                return Response(
                    {"detail": "You are not assigned to teach this subject in this class."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        teacher = getattr(user, 'teacher', None)
        created_count = 0
        updated_count = 0
        errors = []

        with transaction.atomic():
            for record in records:
                student_id = record['student_id']
                try:
                    student = Student.objects.get(
                        pk=student_id,
                        student_class=student_class,
                        is_active=True,
                    )
                except Student.DoesNotExist:
                    errors.append(
                        f"Student {student_id} not found in class {class_id}."
                    )
                    continue

                obj, was_created = Attendance.objects.update_or_create(
                    student=student,
                    subject=subject,
                    date=date,
                    defaults={
                        'status': record['status'],
                        'remarks': record.get('remarks', ''),
                        'marked_by': teacher,
                    },
                )
                if was_created:
                    created_count += 1
                else:
                    updated_count += 1

        return Response(
            {"created": created_count, "updated": updated_count, "errors": errors},
            status=status.HTTP_200_OK,
        )


def get_object_or_404_safe(model, **kwargs):
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        return None
