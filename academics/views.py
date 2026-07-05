from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from users.permissions import IsAdmin, IsAdminOrTeacher, IsOwnerOrReadOnly
from attendance.models import Attendance
from students.models import Student

from .models import (
    Department, Subject, Class,
    TeacherSubjectClass, Assignment, Submission, Mark,
)
from .serializers import (
    DepartmentSerializer, SubjectSerializer, ClassSerializer,
    TeacherSubjectClassSerializer, AssignmentSerializer,
    SubmissionSerializer, MarkSerializer, MarkSummarySerializer,
    BulkAttendanceSerializer,
)


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------
class DepartmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for departments.
    - List/Retrieve: any authenticated user
    - Create/Update/Delete: admin only
    """
    queryset = Department.objects.select_related('hod').all()
    serializer_class = DepartmentSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAdmin()]


# ---------------------------------------------------------------------------
# Subject
# ---------------------------------------------------------------------------
class SubjectViewSet(viewsets.ModelViewSet):
    """
    CRUD for subjects.
    - List/Retrieve: any authenticated user
    - Create/Update/Delete: admin only
    """
    queryset = Subject.objects.select_related('department').all()
    serializer_class = SubjectSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_queryset(self):
        qs = super().get_queryset()
        dept = self.request.query_params.get('department')
        if dept:
            qs = qs.filter(department_id=dept)
        return qs


# ---------------------------------------------------------------------------
# Class
# ---------------------------------------------------------------------------
class ClassViewSet(viewsets.ModelViewSet):
    """
    CRUD for classes.
    - List/Retrieve: any authenticated user
    - Create/Update/Delete: admin only
    """
    queryset = Class.objects.select_related('department', 'adviser').all()
    serializer_class = ClassSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_queryset(self):
        qs = super().get_queryset()
        dept = self.request.query_params.get('department')
        year = self.request.query_params.get('year')
        academic_year = self.request.query_params.get('academic_year')
        if dept:
            qs = qs.filter(department_id=dept)
        if year:
            qs = qs.filter(year=year)
        if academic_year:
            qs = qs.filter(academic_year=academic_year)
        return qs


# ---------------------------------------------------------------------------
# TeacherSubjectClass
# ---------------------------------------------------------------------------
class TeacherSubjectClassViewSet(viewsets.ModelViewSet):
    """
    Links teacher → subject → class.
    - List/Retrieve: admin or teacher
    - Create/Update/Delete: admin only
    Teachers see only their own assignments.
    """
    queryset = TeacherSubjectClass.objects.select_related(
        'teacher__user', 'subject', 'student_class'
    ).all()
    serializer_class = TeacherSubjectClassSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAdminOrTeacher()]
        return [IsAdmin()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        # Teachers see only their own assignments
        if not user.is_staff and hasattr(user, 'teacher'):
            qs = qs.filter(teacher=user.teacher)
        return qs


# ---------------------------------------------------------------------------
# Assignment
# ---------------------------------------------------------------------------
class AssignmentViewSet(viewsets.ModelViewSet):
    """
    Assignments created by teachers for a class.
    - List/Retrieve: admin, teacher (own), student (own class)
    - Create/Update/Delete: admin or teacher
    """
    queryset = Assignment.objects.select_related(
        'subject', 'student_class', 'created_by__user'
    ).all()
    serializer_class = AssignmentSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
        return [IsAdminOrTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_staff:
            if hasattr(user, 'teacher'):
                # Teachers see only assignments they created
                qs = qs.filter(created_by=user.teacher)
            elif hasattr(user, 'student_profile'):
                # Students see only assignments for their class
                qs = qs.filter(student_class=user.student_profile.student_class)
        return qs

    @extend_schema(
        summary="Distribute assignment to class",
        description=(
            "Creates a Submission stub for every student in the assignment's class. "
            "Call this after creating an assignment to pre-populate the submission roster. "
            "Idempotent — skips students who already have a stub."
        ),
        responses={200: {"type": "object", "properties": {
            "created": {"type": "integer"},
            "skipped": {"type": "integer"},
        }}},
    )
    @action(detail=True, methods=['post'], url_path='distribute',
            permission_classes=[IsAdminOrTeacher])
    def distribute(self, request, pk=None):
        """
        POST /api/assignments/{id}/distribute/
        Creates submission stubs for all students in the assignment's class.
        """
        assignment = self.get_object()
        students = Student.objects.filter(
            student_class=assignment.student_class,
            is_active=True,
        )
        created = 0
        skipped = 0
        with transaction.atomic():
            for student in students:
                _, was_created = Submission.objects.get_or_create(
                    assignment=assignment,
                    student=student,
                )
                if was_created:
                    created += 1
                else:
                    skipped += 1
        return Response(
            {"created": created, "skipped": skipped},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------
class SubmissionViewSet(viewsets.ModelViewSet):
    """
    Student submissions for assignments.
    - List/Retrieve: admin, teacher (for their assignments), student (own)
    - Create: student only
    - Update (grade/feedback): teacher or admin only
    - Delete: admin only
    """
    queryset = Submission.objects.select_related(
        'assignment__subject', 'student'
    ).all()
    serializer_class = SubmissionSerializer

    def get_permissions(self):
        if self.action == 'create':
            from users.permissions import IsStudent
            return [IsStudent()]
        if self.action in ('update', 'partial_update'):
            return [IsAdminOrTeacher()]
        if self.action == 'destroy':
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_staff:
            if hasattr(user, 'teacher'):
                # Teachers see submissions for assignments they created
                qs = qs.filter(assignment__created_by=user.teacher)
            elif hasattr(user, 'student_profile'):
                # Students see only their own submissions
                qs = qs.filter(student=user.student_profile)
        return qs

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        # Apply IsOwnerOrReadOnly at object level
        perm = IsOwnerOrReadOnly()
        if not perm.has_object_permission(request, self, obj):
            self.permission_denied(request, message=perm.message)


# ---------------------------------------------------------------------------
# Mark
# ---------------------------------------------------------------------------
class MarkViewSet(viewsets.ModelViewSet):
    """
    Academic marks per student per subject per exam type.
    - List/Retrieve: admin, teacher, student (own)
    - Create/Update/Delete: admin or teacher only
    """
    queryset = Mark.objects.select_related('student', 'subject').all()
    serializer_class = MarkSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [IsAuthenticated()]
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
        exam_type = self.request.query_params.get('exam_type')
        if student_id:
            qs = qs.filter(student_id=student_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if exam_type:
            qs = qs.filter(exam_type=exam_type)
        return qs
