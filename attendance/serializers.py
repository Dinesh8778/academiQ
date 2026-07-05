from __future__ import annotations

from typing import Optional

from rest_framework import serializers
from .models import Attendance


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    marked_by_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Attendance
        fields = [
            'id', 'student', 'student_name',
            'subject', 'subject_name',
            'date', 'status', 'remarks',
            'marked_by', 'marked_by_name',
        ]
        read_only_fields = ['marked_by']

    def get_marked_by_name(self, obj) -> Optional[str]:
        if obj.marked_by:
            return str(obj.marked_by)
        return None

    def create(self, validated_data):
        request = self.context.get('request')
        if request and hasattr(request.user, 'teacher'):
            validated_data['marked_by'] = request.user.teacher
        return super().create(validated_data)
