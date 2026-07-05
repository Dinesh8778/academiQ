"""
Tests for:
  GET /api/students/{id}/attendance-percentage/
  GET /api/students/{id}/report-card/
"""

import pytest
from decimal import Decimal
from datetime import date

from attendance.models import Attendance
from academics.models import Mark


@pytest.mark.django_db
class TestAttendancePercentage:

    def _url(self, student):
        return f'/api/students/{student.pk}/attendance-percentage/'

    def test_returns_zero_when_no_records(self, student_client, student_user):
        student = student_user.student_profile
        response = student_client.get(self._url(student))
        assert response.status_code == 200
        data = response.json()
        assert data['total_classes'] == 0
        assert data['percentage'] == 0.0

    def test_correct_percentage_calculation(
        self, student_client, student_user, subject
    ):
        student = student_user.student_profile
        Attendance.objects.create(student=student, subject=subject, date='2025-09-01', status=True)
        Attendance.objects.create(student=student, subject=subject, date='2025-09-02', status=True)
        Attendance.objects.create(student=student, subject=subject, date='2025-09-03', status=False)
        Attendance.objects.create(student=student, subject=subject, date='2025-09-04', status=True)

        response = student_client.get(self._url(student))
        assert response.status_code == 200
        data = response.json()
        assert data['total_classes'] == 4
        assert data['present'] == 3
        assert data['absent'] == 1
        assert data['percentage'] == 75.0

    def test_per_subject_breakdown(self, student_client, student_user, subject, department):
        from academics.models import Subject
        student = student_user.student_profile
        sub2 = Subject.objects.create(name='Maths', code='MTH101', department=department)

        Attendance.objects.create(student=student, subject=subject, date='2025-09-01', status=True)
        Attendance.objects.create(student=student, subject=subject, date='2025-09-02', status=False)
        Attendance.objects.create(student=student, subject=sub2, date='2025-09-01', status=True)
        Attendance.objects.create(student=student, subject=sub2, date='2025-09-02', status=True)

        response = student_client.get(self._url(student))
        data = response.json()
        assert len(data['by_subject']) == 2
        total_records = sum(s['total'] for s in data['by_subject'])
        assert total_records == 4

    def test_student_cannot_see_other_student_percentage(
        self, student_client, admin_user, department, student_class
    ):
        other_user = __import__('django.contrib.auth.models', fromlist=['User']).User.objects.create_user(
            username='other', password='pass'
        )
        from students.models import Student
        other_student = Student.objects.create(
            name='Other', regno='OTH002',
            student_class=student_class
        )
        response = student_client.get(f'/api/students/{other_student.pk}/attendance-percentage/')
        assert response.status_code in (403, 404)

    def test_teacher_can_see_any_student_percentage(
        self, teacher_client, student_user, subject
    ):
        student = student_user.student_profile
        Attendance.objects.create(student=student, subject=subject, date='2025-09-01', status=True)
        response = teacher_client.get(self._url(student))
        assert response.status_code == 200


@pytest.mark.django_db
class TestReportCard:

    def _url(self, student):
        return f'/api/students/{student.pk}/report-card/'

    def test_empty_report_card(self, student_client, student_user):
        student = student_user.student_profile
        response = student_client.get(self._url(student))
        assert response.status_code == 200
        data = response.json()
        assert data['overall_percentage'] == 0.0
        assert data['marks'] == []

    def test_correct_overall_percentage(self, student_client, student_user, subject):
        student = student_user.student_profile
        Mark.objects.create(
            student=student, subject=subject,
            exam_type='UT1', marks_obtained=45, max_marks=50, date='2025-09-10'
        )
        Mark.objects.create(
            student=student, subject=subject,
            exam_type='MID', marks_obtained=70, max_marks=100, date='2025-10-10'
        )
        response = student_client.get(self._url(student))
        data = response.json()
        # (45+70) / (50+100) * 100 = 115/150 * 100 = 76.67
        assert data['total_marks_obtained'] == 115.0
        assert data['total_max_marks'] == 150.0
        assert data['overall_percentage'] == pytest.approx(76.67, 0.01)
        assert len(data['marks']) == 2

    def test_report_card_contains_subject_names(self, student_client, student_user, subject):
        student = student_user.student_profile
        Mark.objects.create(
            student=student, subject=subject,
            exam_type='UT1', marks_obtained=40, max_marks=50, date='2025-09-10'
        )
        response = student_client.get(self._url(student))
        data = response.json()
        assert data['marks'][0]['subject_name'] == subject.name

    def test_student_cannot_see_other_report_card(
        self, student_client, student_class
    ):
        from students.models import Student
        other = Student.objects.create(
            name='Stranger', regno='STR001', student_class=student_class
        )
        response = student_client.get(f'/api/students/{other.pk}/report-card/')
        assert response.status_code in (403, 404)

    def test_admin_can_see_any_report_card(
        self, admin_client, student_user, subject
    ):
        student = student_user.student_profile
        response = admin_client.get(self._url(student))
        assert response.status_code == 200

    def test_report_card_grade_and_class_rank(self, student_client, student_user, subject):
        student = student_user.student_profile
        Mark.objects.create(
            student=student, subject=subject,
            exam_type='final', marks_obtained=95, max_marks=100, date='2025-09-10'
        )
        response = student_client.get(self._url(student))
        data = response.json()
        assert len(data['marks']) == 1
        assert data['marks'][0]['letter_grade'] == 'A'
        assert data['marks'][0]['class_rank'] == 1
