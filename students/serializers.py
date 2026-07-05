from rest_framework import serializers
from .models import Student


class StudentSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source='student_class.__str__', read_only=True)
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)

    class Meta:
        model = Student
        fields = [
            'id', 'regno', 'name',
            'student_class', 'class_name',
            'email', 'phone', 'date_of_birth',
            'gender', 'gender_display',
            'address', 'guardian_name',
            'date_enrolled', 'is_active',
        ]
        # user link is intentionally excluded from the public API
        # it is managed internally during registration


class StudentListSerializer(serializers.ModelSerializer):
    """Lightweight version for list endpoints."""
    class_name = serializers.CharField(source='student_class.__str__', read_only=True)

    class Meta:
        model = Student
        fields = ['id', 'regno', 'name', 'student_class', 'class_name', 'is_active']
