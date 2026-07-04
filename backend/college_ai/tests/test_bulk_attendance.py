"""
Tests for POST /api/attendance/bulk-mark/
"""

import pytest
from datetime import date

from students.models import Student
from attendance.models import Attendance


@pytest.mark.django_db
class TestBulkMarkAttendance:

    def test_bulk_mark_creates_records(
        self, teacher_client, student_user, student_class,
        subject, teacher_subject_class
    ):
        student = student_user.student_profile
        payload = {
            'class_id': student_class.pk,
            'subject_id': subject.pk,
            'date': '2025-09-01',
            'records': [
                {'student_id': student.pk, 'status': True},
            ],
        }
        response = teacher_client.post('/api/attendance/bulk-mark/', payload, format='json')
        assert response.status_code == 200
        data = response.json()
        assert data['created'] == 1
        assert data['updated'] == 0
        assert Attendance.objects.filter(student=student, date='2025-09-01').exists()

    def test_bulk_mark_updates_existing_record(
        self, teacher_client, student_user, student_class,
        subject, teacher_subject_class
    ):
        student = student_user.student_profile
        teacher = student_user.student_profile.student_class.adviser or \
                  student_user.student_profile  # teacher from fixture

        # Create initial record
        Attendance.objects.create(
            student=student, subject=subject,
            date='2025-09-02', status=False
        )

        payload = {
            'class_id': student_class.pk,
            'subject_id': subject.pk,
            'date': '2025-09-02',
            'records': [
                {'student_id': student.pk, 'status': True},
            ],
        }
        response = teacher_client.post('/api/attendance/bulk-mark/', payload, format='json')
        assert response.status_code == 200
        data = response.json()
        assert data['updated'] == 1
        assert data['created'] == 0
        # Record should now be Present
        record = Attendance.objects.get(student=student, date='2025-09-02')
        assert record.status is True

    def test_bulk_mark_rejects_invalid_student(
        self, teacher_client, student_class, subject, teacher_subject_class
    ):
        """A student not in the class should appear in errors, not crash."""
        payload = {
            'class_id': student_class.pk,
            'subject_id': subject.pk,
            'date': '2025-09-03',
            'records': [
                {'student_id': 99999, 'status': True},
            ],
        }
        response = teacher_client.post('/api/attendance/bulk-mark/', payload, format='json')
        assert response.status_code == 200
        data = response.json()
        assert data['created'] == 0
        assert len(data['errors']) == 1

    def test_bulk_mark_requires_teacher_assignment(
        self, teacher_client, student_user, student_class, department
    ):
        """Teacher without a TeacherSubjectClass record is denied."""
        from academics.models import Subject
        other_subject = Subject.objects.create(
            name='Other', code='OTH999', department=department
        )
        payload = {
            'class_id': student_class.pk,
            'subject_id': other_subject.pk,
            'date': '2025-09-04',
            'records': [
                {'student_id': student_user.student_profile.pk, 'status': True},
            ],
        }
        response = teacher_client.post('/api/attendance/bulk-mark/', payload, format='json')
        assert response.status_code == 403

    def test_bulk_mark_forbidden_for_student(
        self, student_client, student_class, subject
    ):
        payload = {
            'class_id': student_class.pk,
            'subject_id': subject.pk,
            'date': '2025-09-05',
            'records': [],
        }
        response = student_client.post('/api/attendance/bulk-mark/', payload, format='json')
        assert response.status_code == 403

    def test_bulk_mark_requires_auth(self, api_client, student_class, subject):
        payload = {
            'class_id': student_class.pk,
            'subject_id': subject.pk,
            'date': '2025-09-06',
            'records': [],
        }
        response = api_client.post('/api/attendance/bulk-mark/', payload, format='json')
        assert response.status_code == 401
