"""
tests/test_assistant.py
=======================
Tests for the AI assistant endpoint with a focus on adversarial role isolation.

KEY PRINCIPLE BEING TESTED:
  Permission enforcement lives in the TOOL FUNCTIONS themselves, not in the LLM.
  Even if a user crafts a message asking for another user's data, the tool
  function will refuse because it checks `user` identity internally.

These tests call the tool functions DIRECTLY (bypassing the LLM layer) to
prove that the permission boundary holds regardless of what the LLM does.
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User

from academics.models import Department, Class, Subject, Assignment, TeacherSubjectClass, Mark
from students.models import Student
from users.models import Teacher
from attendance.models import Attendance
from datetime import date


def jwt_client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return client


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dept(db):
    return Department.objects.create(name='Asst Test Dept', code='ATD')


@pytest.fixture
def other_dept(db):
    return Department.objects.create(name='Other Dept', code='OTH')


@pytest.fixture
def cls(db, dept):
    return Class.objects.create(
        department=dept, year=1, section='X', academic_year='2025-2026')


@pytest.fixture
def other_cls(db, other_dept):
    return Class.objects.create(
        department=other_dept, year=1, section='Y', academic_year='2025-2026')


@pytest.fixture
def subject(db, dept):
    return Subject.objects.create(name='Test Sub', code='TST999', department=dept)


@pytest.fixture
def teacher_user(db, dept, cls, subject):
    u = User.objects.create_user(username='asst_teacher', password='pass')
    t = Teacher.objects.create(user=u, teacher_id='ASST001', department=dept)
    TeacherSubjectClass.objects.create(teacher=t, subject=subject, student_class=cls)
    return u


@pytest.fixture
def other_teacher_user(db, other_dept, other_cls, subject):
    u = User.objects.create_user(username='other_teacher', password='pass')
    t = Teacher.objects.create(user=u, teacher_id='ASST002', department=other_dept)
    return u


@pytest.fixture
def student_user(db, cls):
    u = User.objects.create_user(username='asst_student', password='pass')
    Student.objects.create(user=u, name='Asst Student', regno='ASST001',
                           student_class=cls, is_active=True)
    return u


@pytest.fixture
def other_student_user(db, cls):
    u = User.objects.create_user(username='other_student', password='pass')
    Student.objects.create(user=u, name='Other Student', regno='ASST002',
                           student_class=cls, is_active=True)
    return u


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(username='asst_admin', password='pass')


# ---------------------------------------------------------------------------
# 1. Endpoint access control
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEndpointAccess:

    def test_unauthenticated_denied(self):
        client = APIClient()
        resp = client.post('/api/assistant/ask/', {'message': 'hello'}, format='json')
        assert resp.status_code == 401

    def test_authenticated_student_can_reach_endpoint(self, student_user):
        client = jwt_client(student_user)
        resp = client.post('/api/assistant/ask/', {'message': 'hello'}, format='json')
        # 200 with answer (even if GROQ_API_KEY is missing, graceful fallback)
        assert resp.status_code == 200
        assert 'answer' in resp.json()

    def test_authenticated_teacher_can_reach_endpoint(self, teacher_user):
        client = jwt_client(teacher_user)
        resp = client.post('/api/assistant/ask/', {'message': 'hello'}, format='json')
        assert resp.status_code == 200

    def test_empty_message_rejected(self, student_user):
        client = jwt_client(student_user)
        resp = client.post('/api/assistant/ask/', {'message': ''}, format='json')
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. Student tool isolation — adversarial cross-student access
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestStudentToolIsolation:

    def test_student_get_my_attendance_own_data(self, student_user, subject, cls):
        """Student can get their own attendance."""
        from assistant.tools import get_my_attendance
        Attendance.objects.create(student=student_user.student_profile,
                                  subject=subject, date=date(2025, 9, 1), status=True)
        result = get_my_attendance(student_user)
        assert 'error' not in result
        assert result['regno'] == student_user.student_profile.regno

    def test_student_cannot_call_teacher_tool_directly(
            self, student_user, cls):
        """Student calling a teacher-only tool must get ACCESS_DENIED."""
        from assistant.tools import get_class_attendance_summary
        result = get_class_attendance_summary(student_user, class_id=cls.pk)
        assert result.get('error') == 'ACCESS_DENIED'

    def test_student_cannot_call_admin_tool_directly(self, student_user, dept):
        """Student calling an admin-only tool must get ACCESS_DENIED."""
        from assistant.tools import get_department_stats
        result = get_department_stats(student_user, department_id=dept.pk)
        assert result.get('error') == 'ACCESS_DENIED'

    def test_student_cannot_call_at_risk_tool(self, student_user):
        """get_at_risk_students is admin-only."""
        from assistant.tools import get_at_risk_students
        result = get_at_risk_students(student_user)
        assert result.get('error') == 'ACCESS_DENIED'

    def test_student_get_my_grades_returns_only_own(
            self, student_user, other_student_user, subject):
        """Grades returned are only for the authenticated student, never another."""
        from assistant.tools import get_my_grades
        # Add marks for both students
        Mark.objects.create(student=student_user.student_profile, subject=subject,
                            exam_type='UT1', marks_obtained=70, max_marks=100,
                            date=date(2025, 9, 15))
        Mark.objects.create(student=other_student_user.student_profile, subject=subject,
                            exam_type='UT1', marks_obtained=30, max_marks=100,
                            date=date(2025, 9, 15))
        result = get_my_grades(student_user)
        assert 'error' not in result
        # The result should be for student_user only
        assert result['regno'] == student_user.student_profile.regno
        # Must not contain other student's data
        assert result['regno'] != other_student_user.student_profile.regno

    def test_dispatch_blocks_cross_role_tool_call(self, student_user, dept):
        """
        Even if the LLM somehow calls get_department_stats for a student,
        dispatch_tool_call must deny it at the registry level.
        """
        from assistant.tools import dispatch_tool_call
        result = dispatch_tool_call(student_user, 'get_department_stats',
                                   {'department_id': dept.pk})
        assert result.get('error') == 'ACCESS_DENIED'

    def test_dispatch_blocks_unknown_tool(self, student_user):
        """Unknown tool names are rejected."""
        from assistant.tools import dispatch_tool_call
        result = dispatch_tool_call(student_user, 'drop_database', {})
        assert result.get('error') == 'UNKNOWN_TOOL'


# ---------------------------------------------------------------------------
# 3. Teacher tool isolation — adversarial cross-class access
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTeacherToolIsolation:

    def test_teacher_can_access_own_class(self, teacher_user, cls):
        """Teacher can get attendance summary for their own class."""
        from assistant.tools import get_class_attendance_summary
        result = get_class_attendance_summary(teacher_user, class_id=cls.pk)
        assert 'error' not in result
        assert 'students' in result

    def test_teacher_denied_other_class(self, teacher_user, other_cls):
        """Teacher asking about a class they don't teach must be denied."""
        from assistant.tools import get_class_attendance_summary
        result = get_class_attendance_summary(teacher_user, class_id=other_cls.pk)
        assert result.get('error') == 'ACCESS_DENIED'

    def test_teacher_denied_other_class_low_attendance(self, teacher_user, other_cls):
        """get_low_attendance_students also respects class ownership."""
        from assistant.tools import get_low_attendance_students
        result = get_low_attendance_students(teacher_user, class_id=other_cls.pk)
        assert result.get('error') == 'ACCESS_DENIED'

    def test_teacher_cannot_call_admin_tool(self, teacher_user, dept):
        """Teacher cannot call get_department_stats (admin only)."""
        from assistant.tools import get_department_stats
        result = get_department_stats(teacher_user, department_id=dept.pk)
        assert result.get('error') == 'ACCESS_DENIED'

    def test_teacher_cannot_get_at_risk_students(self, teacher_user):
        """get_at_risk_students is admin-only even for teachers."""
        from assistant.tools import get_at_risk_students
        result = get_at_risk_students(teacher_user)
        assert result.get('error') == 'ACCESS_DENIED'

    def test_dispatch_blocks_teacher_calling_student_tool(self, teacher_user):
        """
        A teacher cannot call get_my_grades (student tool) even through dispatch.
        """
        from assistant.tools import dispatch_tool_call
        result = dispatch_tool_call(teacher_user, 'get_my_grades', {})
        assert result.get('error') == 'ACCESS_DENIED'


# ---------------------------------------------------------------------------
# 4. Role detection
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRoleDetection:

    def test_admin_role_detected(self, admin_user):
        from assistant.tools import get_user_role
        assert get_user_role(admin_user) == 'admin'

    def test_teacher_role_detected(self, teacher_user):
        from assistant.tools import get_user_role
        assert get_user_role(teacher_user) == 'teacher'

    def test_student_role_detected(self, student_user):
        from assistant.tools import get_user_role
        assert get_user_role(student_user) == 'student'

    def test_student_gets_only_student_tools(self, student_user):
        from assistant.tools import get_tools_for_role
        tools = get_tools_for_role('student')
        names = [t['function']['name'] for t in tools]
        assert 'get_my_attendance' in names
        assert 'get_my_grades' in names
        assert 'get_department_stats' not in names
        assert 'get_at_risk_students' not in names
        assert 'get_class_attendance_summary' not in names

    def test_teacher_gets_only_teacher_tools(self, teacher_user):
        from assistant.tools import get_tools_for_role
        tools = get_tools_for_role('teacher')
        names = [t['function']['name'] for t in tools]
        assert 'get_class_attendance_summary' in names
        assert 'get_pending_submissions' in names
        assert 'get_my_grades' not in names
        assert 'get_department_stats' not in names

    def test_admin_gets_admin_tools(self, admin_user):
        from assistant.tools import get_tools_for_role
        tools = get_tools_for_role('admin')
        names = [t['function']['name'] for t in tools]
        assert 'get_department_stats' in names
        assert 'get_at_risk_students' in names
        assert 'get_class_roster' in names


@pytest.mark.django_db
def test_assistant_write_intent_fallback(admin_user):
    from assistant.groq_client import call_groq
    response = call_groq(admin_user, "I want to add a teacher")
    assert "I can't create or edit records" in response["answer"]
    assert "Add Teacher" in response["answer"]

    response2 = call_groq(admin_user, "can you delete a class?")
    assert "I can't create or edit records" in response2["answer"]
    assert "Add Class" in response2["answer"]


@pytest.mark.django_db
class TestExamAnalysisToolIsolation:

    def test_teacher_allowed_exam_analysis_on_own_class(self, teacher_user, cls, subject):
        """Teacher can get exam analysis for their assigned class and subject."""
        from assistant.tools import get_exam_analysis
        
        # Create some mark data
        u1 = User.objects.create_user(username='stud_1', password='pwd')
        s1 = Student.objects.create(user=u1, name='Student One', regno='S1',
                                    student_class=cls, is_active=True)
        Mark.objects.create(student=s1, subject=subject, exam_type='final',
                            marks_obtained=90, max_marks=100, date='2025-09-10')

        result = get_exam_analysis(teacher_user, class_id=cls.pk, subject_id=subject.pk, exam_type='final')
        assert 'error' not in result
        assert result['average'] == 90.0
        assert result['highest'] == 90.0
        assert result['pass_rate'] == 100.0

    def test_teacher_denied_exam_analysis_on_other_class(self, other_teacher_user, cls, subject):
        """Teacher asking about an exam for a class they do not teach must be denied."""
        from assistant.tools import get_exam_analysis
        result = get_exam_analysis(other_teacher_user, class_id=cls.pk, subject_id=subject.pk, exam_type='final')
        assert result.get('error') == 'ACCESS_DENIED'

    def test_admin_allowed_exam_analysis_any_class(self, admin_user, cls, subject):
        """Admins can call get_exam_analysis for any class/subject combination without assignment."""
        from assistant.tools import get_exam_analysis
        u1 = User.objects.create_user(username='stud_2', password='pwd')
        s1 = Student.objects.create(user=u1, name='Student Two', regno='S2',
                                    student_class=cls, is_active=True)
        Mark.objects.create(student=s1, subject=subject, exam_type='final',
                            marks_obtained=75, max_marks=100, date='2025-09-10')

        result = get_exam_analysis(admin_user, class_id=cls.pk, subject_id=subject.pk, exam_type='final')
        assert 'error' not in result
        assert result['average'] == 75.0

    def test_teacher_denied_department_exam_comparison(self, teacher_user):
        """Teachers cannot run the admin-only department comparison tool."""
        from assistant.tools import get_department_exam_comparison
        result = get_department_exam_comparison(teacher_user, exam_type='final')
        assert result.get('error') == 'ACCESS_DENIED'

    def test_admin_allowed_department_exam_comparison(self, admin_user, dept, other_dept, cls, other_cls, subject):
        """Admin can run get_department_exam_comparison with system-wide stats."""
        from assistant.tools import get_department_exam_comparison
        
        # Create student and mark for dept
        u1 = User.objects.create_user(username='stud_3', password='pwd')
        s1 = Student.objects.create(user=u1, name='Student Three', regno='S3',
                                    student_class=cls, is_active=True)
        Mark.objects.create(student=s1, subject=subject, exam_type='final',
                            marks_obtained=80, max_marks=100, date='2025-09-10')

        # Create student and mark for other_dept
        other_subject = Subject.objects.create(name='Other Sub', code='OTH888', department=other_dept)
        u2 = User.objects.create_user(username='stud_4', password='pwd')
        s2 = Student.objects.create(user=u2, name='Student Four', regno='S4',
                                    student_class=other_cls, is_active=True)
        Mark.objects.create(student=s2, subject=other_subject, exam_type='final',
                            marks_obtained=60, max_marks=100, date='2025-09-10')

        result = get_department_exam_comparison(admin_user, exam_type='final')
        assert 'error' not in result
        comparison = result['comparison']
        
        # Assert comparison results ordered correctly
        assert len(comparison) >= 2
        assert comparison[0]['department_name'] == dept.name
        assert comparison[0]['average_percentage'] == 80.0
        assert comparison[1]['department_name'] == other_dept.name
        assert comparison[1]['average_percentage'] == 60.0

