"""
Serializers for the users app.
Covers:
  - Teacher CRUD
  - Teacher registration
  - Student registration
  - JWT token with role payload
  - User profile (/me/)
"""

from __future__ import annotations

from typing import Optional

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from users.models import Teacher
from students.models import Student


# ---------------------------------------------------------------------------
# Custom JWT payload
# ---------------------------------------------------------------------------
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        if user.is_staff:
            token['role'] = 'admin'
        elif hasattr(user, 'teacher'):
            token['role'] = 'teacher'
            token['teacher_id'] = user.teacher.teacher_id
        elif hasattr(user, 'student_profile'):
            token['role'] = 'student'
            token['regno'] = user.student_profile.regno
        else:
            token['role'] = 'unknown'
        token['username'] = user.username
        return token


# ---------------------------------------------------------------------------
# Teacher (CRUD)
# ---------------------------------------------------------------------------
class TeacherSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    full_name = serializers.SerializerMethodField(read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = Teacher
        fields = [
            'id', 'teacher_id', 'username', 'full_name', 'email',
            'department', 'department_name',
        ]

    def get_full_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.username


# ---------------------------------------------------------------------------
# Teacher Registration
# ---------------------------------------------------------------------------
class TeacherRegistrationSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label="Confirm Password")
    email = serializers.EmailField(write_only=True, required=False)
    first_name = serializers.CharField(write_only=True, required=False, default='')
    last_name = serializers.CharField(write_only=True, required=False, default='')

    class Meta:
        model = Teacher
        fields = [
            'username', 'password', 'password2', 'email',
            'first_name', 'last_name',
            'teacher_id', 'department',
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data.pop('username'),
            password=validated_data.pop('password'),
            email=validated_data.pop('email', ''),
            first_name=validated_data.pop('first_name', ''),
            last_name=validated_data.pop('last_name', ''),
        )
        return Teacher.objects.create(user=user, **validated_data)


# ---------------------------------------------------------------------------
# Student Registration
# ---------------------------------------------------------------------------
class StudentRegistrationSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label="Confirm Password")
    email = serializers.EmailField(write_only=True, required=False)

    class Meta:
        model = Student
        fields = [
            'username', 'password', 'password2', 'email',
            'name', 'regno', 'student_class',
            'phone', 'date_of_birth', 'gender',
            'address', 'guardian_name',
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data.pop('username'),
            password=validated_data.pop('password'),
            email=validated_data.pop('email', ''),
        )
        return Student.objects.create(user=user, **validated_data)


# ---------------------------------------------------------------------------
# User Profile (/me/)
# ---------------------------------------------------------------------------
class UserProfileSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    profile_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'profile_id']

    def get_role(self, user) -> str:
        if user.is_staff:
            return 'admin'
        if hasattr(user, 'teacher'):
            return 'teacher'
        if hasattr(user, 'student_profile'):
            return 'student'
        return 'unknown'

    def get_profile_id(self, user) -> Optional[str]:
        if hasattr(user, 'teacher'):
            return user.teacher.teacher_id
        if hasattr(user, 'student_profile'):
            return user.student_profile.regno
        return None
