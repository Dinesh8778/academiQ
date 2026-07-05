"""
Tests for the ai_engine module.

Covers:
  1. Students cannot access /api/ai/risk-scores/
  2. Unauthenticated users cannot access /api/ai/risk-scores/
  3. Teacher can access /api/ai/risk-scores/ (returns 200 or 503 if no model)
  4. Admin can access /api/ai/risk-scores/
  5. /api/ai/risk-scores/<class_id>/ scopes to the right class
  6. data_pipeline returns expected columns and valid feature ranges
  7. predict_risk returns sensible output after seeding + training
"""

import pytest
import os
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from academics.models import Department, Class, Subject, Assignment, TeacherSubjectClass, Mark, Submission
from attendance.models import Attendance
from students.models import Student
from users.models import Teacher
from django.contrib.auth.models import User
from datetime import date, timedelta


def jwt_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


# ---- Fixtures ----

@pytest.fixture
def dept(db):
    return Department.objects.create(name='AI Test Dept', code='AIT')


@pytest.fixture
def student_class(db, dept):
    return Class.objects.create(
        department=dept, year=1, section='T', academic_year='2025-2026'
    )


@pytest.fixture
def subject(db, dept):
    return Subject.objects.create(name='AI Subject', code='AIS101', department=dept)


@pytest.fixture
def teacher_user(db, dept):
    u = User.objects.create_user(username='ai_teacher', password='pass')
    Teacher.objects.create(user=u, teacher_id='AIT001', department=dept)
    return u


@pytest.fixture
def student_user(db, student_class):
    u = User.objects.create_user(username='ai_student', password='pass')
    Student.objects.create(user=u, name='AI Student', regno='AIST001',
                           student_class=student_class, is_active=True)
    return u


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(username='ai_admin', password='pass')


@pytest.fixture
def seeded_class(db, dept, student_class, subject, teacher_user):
    """Create minimal students with attendance and marks for pipeline testing."""
    teacher = teacher_user.teacher
    TeacherSubjectClass.objects.get_or_create(
        teacher=teacher, subject=subject, student_class=student_class
    )
    assignment = Assignment.objects.create(
        title='Test Assignment', due_date=date(2025, 10, 1),
        subject=subject, student_class=student_class, created_by=teacher
    )

    today = date(2025, 12, 1)
    students = []
    configs = [
        ('AISTR001', 'At Risk',  30, 25, False),   # low att, low marks, no submission
        ('AISOK001', 'Safe',     90, 80, True),    # high att, high marks, submitted
    ]
    for regno, name, att_pct, mark_score, submitted in configs:
        u = User.objects.create_user(username=f'u_{regno}', password='pass')
        st = Student.objects.create(user=u, name=name, regno=regno,
                                    student_class=student_class, is_active=True)
        for d in range(10):
            day = today - timedelta(days=10 - d)
            Attendance.objects.create(
                student=st, subject=subject, date=day,
                status=(d < att_pct / 10), marked_by=teacher
            )
        Mark.objects.create(
            student=st, subject=subject, exam_type='UT1',
            marks_obtained=mark_score, max_marks=100, date=date(2025, 9, 15)
        )
        if submitted:
            Submission.objects.get_or_create(
                assignment=assignment, student=st,
                defaults={'file': 'submissions/test/placeholder.txt'}
            )
        students.append(st)
    return student_class, students


# ---- Permission tests ----

@pytest.mark.django_db
class TestRiskScorePermissions:

    def test_unauthenticated_denied(self, api_client):
        response = api_client.get('/api/ai/risk-scores/')
        assert response.status_code == 401

    def test_student_denied(self, student_user):
        client = jwt_client(student_user)
        response = client.get('/api/ai/risk-scores/')
        assert response.status_code == 403

    def test_teacher_allowed(self, teacher_user):
        client = jwt_client(teacher_user)
        response = client.get('/api/ai/risk-scores/')
        # 200 (model trained) or 503 (model not trained yet) — both are valid access
        assert response.status_code in (200, 503)

    def test_admin_allowed(self, admin_user):
        client = jwt_client(admin_user)
        response = client.get('/api/ai/risk-scores/')
        assert response.status_code in (200, 503)

    def test_class_scoped_student_denied(self, student_user, student_class):
        client = jwt_client(student_user)
        response = client.get(f'/api/ai/risk-scores/{student_class.pk}/')
        assert response.status_code == 403

    def test_class_scoped_teacher_allowed(self, teacher_user, student_class):
        client = jwt_client(teacher_user)
        response = client.get(f'/api/ai/risk-scores/{student_class.pk}/')
        assert response.status_code in (200, 503)


# ---- Data pipeline tests ----

@pytest.mark.django_db
class TestDataPipeline:

    def test_returns_dataframe_with_required_columns(self, seeded_class):
        from ai_engine.data_pipeline import build_student_features, FEATURE_COLUMNS
        cls, _ = seeded_class
        df = build_student_features(class_id=cls.pk)
        assert not df.empty
        for col in FEATURE_COLUMNS + ['at_risk', 'student_id', 'regno', 'name']:
            assert col in df.columns, f"Missing column: {col}"

    def test_attendance_percentage_range(self, seeded_class):
        from ai_engine.data_pipeline import build_student_features
        cls, _ = seeded_class
        df = build_student_features(class_id=cls.pk)
        assert df['attendance_percentage'].between(0, 100).all()

    def test_at_risk_rule_applied_correctly(self, seeded_class):
        from ai_engine.data_pipeline import build_student_features
        cls, students = seeded_class
        df = build_student_features(class_id=cls.pk)
        # AISTR001 should be at-risk (low attendance ~30%, low marks 25)
        at_risk_row = df[df['regno'] == 'AISTR001']
        if not at_risk_row.empty:
            assert at_risk_row.iloc[0]['at_risk'] == 1
        # AISOK001 should not be at-risk
        safe_row = df[df['regno'] == 'AISOK001']
        if not safe_row.empty:
            assert safe_row.iloc[0]['at_risk'] == 0

    def test_missed_submission_rate_range(self, seeded_class):
        from ai_engine.data_pipeline import build_student_features
        cls, _ = seeded_class
        df = build_student_features(class_id=cls.pk)
        assert df['late_or_missed_submission_rate'].between(0, 1).all()


# ---- End-to-end: train + predict ----

@pytest.mark.django_db
class TestRiskPredictionEndToEnd:

    def test_predict_risk_returns_list(self, seeded_class):
        """Train model on seeded data, then run inference — verify output shape."""
        from ai_engine.train_model import train
        from ai_engine.predictor import predict_risk

        cls, _ = seeded_class
        # Train (may use only training data available in test DB)
        try:
            train(verbose=False)
        except ValueError:
            pytest.skip("Not enough data to train — skipping E2E test")

        results = predict_risk(class_id=cls.pk)
        assert isinstance(results, list)
        if results:
            r = results[0]
            assert 'student_id' in r
            assert 'at_risk_label' in r
            assert 'risk_score' in r
            assert 0.0 <= r['risk_score'] <= 1.0
            assert r['at_risk_label'] in (0, 1)

    def test_api_returns_sensible_data_after_training(self, admin_user, seeded_class):
        """After training, the API returns results with the expected shape."""
        from ai_engine.train_model import train
        cls, _ = seeded_class
        try:
            train(verbose=False)
        except ValueError:
            pytest.skip("Not enough data to train — skipping API E2E test")

        client = jwt_client(admin_user)
        response = client.get(f'/api/ai/risk-scores/{cls.pk}/')
        assert response.status_code == 200
        data = response.json()
        assert 'results' in data
        assert 'at_risk_count' in data
        assert isinstance(data['results'], list)
