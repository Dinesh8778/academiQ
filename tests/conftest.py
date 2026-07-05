"""
Shared pytest fixtures for all test modules.
Creates one admin, one teacher, one student, one class, one subject,
one department — used across all test files.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from academics.models import Department, Subject, Class, TeacherSubjectClass
from users.models import Teacher
from students.models import Student


def get_tokens_for_user(user):
    """Return JWT access token string for a given user."""
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)


# ---------------------------------------------------------------------------
# API Client helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_client(db, admin_user):
    client = APIClient()
    token = get_tokens_for_user(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


@pytest.fixture
def teacher_client(db, teacher_user):
    client = APIClient()
    token = get_tokens_for_user(teacher_user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


@pytest.fixture
def student_client(db, student_user):
    client = APIClient()
    token = get_tokens_for_user(student_user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username='test_admin', password='Admin@1234', email='admin@test.com'
    )


@pytest.fixture
def department(db):
    return Department.objects.create(name='Test Dept', code='TST')


@pytest.fixture
def teacher_user(db, department):
    user = User.objects.create_user(
        username='test_teacher', password='Teacher@1234', email='teacher@test.com'
    )
    Teacher.objects.create(user=user, teacher_id='T001', department=department)
    return user


@pytest.fixture
def student_class(db, department):
    return Class.objects.create(
        department=department, year=1, section='A', academic_year='2025-2026'
    )


@pytest.fixture
def student_user(db, student_class):
    user = User.objects.create_user(
        username='test_student', password='Student@1234', email='student@test.com'
    )
    Student.objects.create(
        user=user, name='Test Student', regno='T001REG',
        student_class=student_class, email='student@test.com'
    )
    return user


@pytest.fixture
def subject(db, department):
    return Subject.objects.create(name='Algorithms', code='ALG101', department=department)


@pytest.fixture
def teacher_subject_class(db, teacher_user, subject, student_class):
    return TeacherSubjectClass.objects.create(
        teacher=teacher_user.teacher,
        subject=subject,
        student_class=student_class,
    )
