from __future__ import annotations

from typing import Optional

from rest_framework import serializers
from .models import Department, Subject, Class, TeacherSubjectClass, Assignment, Submission, Mark


class DepartmentSerializer(serializers.ModelSerializer):
    hod_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Department
        fields = ['id', 'name', 'code', 'hod', 'hod_name']

    def get_hod_name(self, obj) -> Optional[str]:
        if obj.hod:
            return str(obj.hod)
        return None


class SubjectSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Subject
        fields = ['id', 'name', 'code', 'department', 'department_name']


class ClassSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    adviser_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Class
        fields = [
            'id', 'department', 'department_name',
            'year', 'section', 'academic_year',
            'adviser', 'adviser_name',
        ]

    def get_adviser_name(self, obj) -> Optional[str]:
        if obj.adviser:
            return str(obj.adviser)
        return None


class TeacherSubjectClassSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.__str__', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    class_name = serializers.CharField(source='student_class.__str__', read_only=True)

    class Meta:
        model = TeacherSubjectClass
        fields = [
            'id', 'teacher', 'teacher_name',
            'subject', 'subject_name',
            'student_class', 'class_name',
        ]


class AssignmentSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.__str__', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    class_name = serializers.CharField(source='student_class.__str__', read_only=True)
    submission_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'description', 'due_date',
            'subject', 'subject_name',
            'student_class', 'class_name',
            'created_by', 'created_by_name',
            'created_at', 'submission_count',
        ]
        read_only_fields = ['created_at', 'created_by']

    def get_submission_count(self, obj) -> int:
        return obj.submissions.count()

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request.user, 'teacher'):
            validated_data['created_by'] = request.user.teacher
        return super().create(validated_data)


class SubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id', 'assignment', 'assignment_title',
            'student', 'student_name',
            'file', 'submitted_at',
            'grade', 'feedback',
        ]
        read_only_fields = ['submitted_at', 'student']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request.user, 'student_profile'):
            validated_data['student'] = request.user.student_profile
        return super().create(validated_data)


class MarkSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    exam_type_display = serializers.CharField(source='get_exam_type_display', read_only=True)
    percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = Mark
        fields = [
            'id', 'student', 'student_name',
            'subject', 'subject_name',
            'exam_type', 'exam_type_display',
            'marks_obtained', 'max_marks', 'percentage',
            'date',
        ]


# ---------------------------------------------------------------------------
# Nested / summary serializers
# ---------------------------------------------------------------------------

class MarkSummarySerializer(serializers.ModelSerializer):
    """Used in report card — groups marks per subject."""
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.code', read_only=True)
    exam_type_display = serializers.CharField(source='get_exam_type_display', read_only=True)
    percentage = serializers.FloatField(read_only=True)

    class Meta:
        model = Mark
        fields = [
            'subject_name', 'subject_code',
            'exam_type', 'exam_type_display',
            'marks_obtained', 'max_marks', 'percentage', 'date',
        ]


class BulkAttendanceEntrySerializer(serializers.Serializer):
    """Represents one row in a bulk-mark request."""
    student_id = serializers.IntegerField()
    status = serializers.BooleanField()
    remarks = serializers.CharField(required=False, allow_blank=True, default='')


class BulkAttendanceSerializer(serializers.Serializer):
    """
    Body for POST /api/attendance/bulk-mark/

    {
        "class_id": 1,
        "subject_id": 2,
        "date": "2025-09-01",
        "records": [
            {"student_id": 5, "status": true},
            {"student_id": 6, "status": false, "remarks": "sick leave"}
        ]
    }
    """
    class_id = serializers.IntegerField()
    subject_id = serializers.IntegerField()
    date = serializers.DateField()
    records = BulkAttendanceEntrySerializer(many=True)
