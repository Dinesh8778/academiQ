"""
Tests for CRUD permission enforcement on every major endpoint.
Verifies that:
  - Unauthenticated users get 401
  - Students cannot write to teacher-only endpoints
  - Teachers cannot access admin-only endpoints
  - Students can only see their own data
"""

import pytest
from django.urls import reverse


# ---------------------------------------------------------------------------
# Department permissions
# ---------------------------------------------------------------------------
class TestDepartmentPermissions:

    def test_list_requires_auth(self, api_client):
        response = api_client.get('/api/departments/')
        assert response.status_code == 401

    def test_list_allowed_for_student(self, student_client):
        response = student_client.get('/api/departments/')
        assert response.status_code == 200

    def test_create_forbidden_for_student(self, student_client):
        response = student_client.post('/api/departments/', {'name': 'Hack', 'code': 'HCK'})
        assert response.status_code == 403

    def test_create_forbidden_for_teacher(self, teacher_client):
        response = teacher_client.post('/api/departments/', {'name': 'Hack', 'code': 'HCK'})
        assert response.status_code == 403

    def test_create_allowed_for_admin(self, admin_client):
        response = admin_client.post('/api/departments/', {'name': 'New Dept', 'code': 'NDP'})
        assert response.status_code == 201

    def test_delete_forbidden_for_teacher(self, teacher_client, department):
        response = teacher_client.delete(f'/api/departments/{department.pk}/')
        assert response.status_code == 403

    def test_delete_allowed_for_admin(self, admin_client, department):
        response = admin_client.delete(f'/api/departments/{department.pk}/')
        assert response.status_code == 204


# ---------------------------------------------------------------------------
# Student permissions
# ---------------------------------------------------------------------------
class TestStudentPermissions:

    def test_list_requires_auth(self, api_client):
        response = api_client.get('/api/students/')
        assert response.status_code == 401

    def test_student_sees_only_self(self, student_client, student_user):
        response = student_client.get('/api/students/')
        assert response.status_code == 200
        data = response.json()
        results = data.get('results', data)
        # Student should only see 1 record — themselves
        assert len(results) == 1
        assert results[0]['regno'] == student_user.student_profile.regno

    def test_admin_sees_all_students(self, admin_client, student_user):
        response = admin_client.get('/api/students/')
        assert response.status_code == 200

    def test_student_cannot_create_student(self, student_client, student_class):
        response = student_client.post('/api/students/', {
            'name': 'Another', 'regno': 'X999',
            'student_class': student_class.pk,
        })
        assert response.status_code == 403

    def test_teacher_can_create_student(self, teacher_client, student_class):
        response = teacher_client.post('/api/students/', {
            'name': 'New Student', 'regno': 'NEW001',
            'student_class': student_class.pk,
        })
        assert response.status_code == 201

    def test_student_cannot_delete(self, student_client, student_user):
        response = student_client.delete(f'/api/students/{student_user.student_profile.pk}/')
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Teacher permissions
# ---------------------------------------------------------------------------
class TestTeacherPermissions:

    def test_teacher_list_forbidden_for_student(self, student_client):
        response = student_client.get('/api/teachers/')
        assert response.status_code == 403

    def test_teacher_list_allowed_for_teacher(self, teacher_client):
        response = teacher_client.get('/api/teachers/')
        assert response.status_code == 200

    def test_teacher_sees_only_self(self, teacher_client, teacher_user):
        response = teacher_client.get('/api/teachers/')
        data = response.json()
        results = data.get('results', data)
        assert len(results) == 1
        assert results[0]['teacher_id'] == teacher_user.teacher.teacher_id

    def test_create_teacher_forbidden_for_teacher(self, teacher_client, department):
        response = teacher_client.post('/api/teachers/', {
            'teacher_id': 'T999', 'department': department.pk
        })
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Assignment permissions
# ---------------------------------------------------------------------------
class TestAssignmentPermissions:
    @pytest.fixture
    def assignment(self, db, teacher_user, subject, student_class):
        from academics.models import Assignment
        from django.utils import timezone
        return Assignment.objects.create(
            title='Test Assignment',
            description='desc',
            due_date=timezone.now(),
            subject=subject,
            student_class=student_class,
            created_by=teacher_user.teacher,
        )

    def test_student_can_list_own_class_assignments(self, student_client, assignment):
        response = student_client.get('/api/assignments/')
        assert response.status_code == 200

    def test_student_cannot_create_assignment(self, student_client, subject, student_class):
        from django.utils import timezone
        response = student_client.post('/api/assignments/', {
            'title': 'Fake', 'due_date': timezone.now().isoformat(),
            'subject': subject.pk, 'student_class': student_class.pk,
        })
        assert response.status_code == 403

    def test_teacher_can_create_assignment(self, teacher_client, subject, student_class):
        from django.utils import timezone
        response = teacher_client.post('/api/assignments/', {
            'title': 'Legit', 'due_date': timezone.now().isoformat(),
            'subject': subject.pk, 'student_class': student_class.pk,
        })
        assert response.status_code == 201
