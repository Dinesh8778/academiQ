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


# ---------------------------------------------------------------------------
# UI View Tests
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestUIBugFixes:

    def test_class_list_no_adviser_does_not_crash(self, client, admin_user, student_class):
        # Set adviser of the class to None to trigger Bug 1 scenario
        student_class.adviser = None
        student_class.save()

        client.force_login(admin_user)
        response = client.get('/manage/classes/')
        assert response.status_code == 200
        # The content should render safely and contain the class details
        assert student_class.section in response.content.decode()

    def test_teacher_subject_class_assignment_ui(self, client, admin_user, teacher_user, subject, student_class):
        client.force_login(admin_user)

        # GET the assignment list page
        response = client.get('/manage/classes/assignments/')
        assert response.status_code == 200

        # POST to assign the teacher to the subject in class
        teacher = teacher_user.teacher
        assign_response = client.post('/manage/classes/assignments/', {
            'teacher': teacher.pk,
            'subject': subject.pk,
            'student_class': student_class.pk,
        })
        assert assign_response.status_code == 302 # redirect back

        # Verify the assignment exists in the database
        from academics.models import TeacherSubjectClass
        assert TeacherSubjectClass.objects.filter(
            teacher=teacher, subject=subject, student_class=student_class
        ).exists()

        # Delete the assignment
        assignment = TeacherSubjectClass.objects.get(
            teacher=teacher, subject=subject, student_class=student_class
        )
        delete_response = client.post(f'/manage/classes/assignments/{assignment.pk}/delete/')
        assert delete_response.status_code == 302 # redirect back

        # Verify it has been deleted
        assert not TeacherSubjectClass.objects.filter(pk=assignment.pk).exists()

    def test_teacher_list_grouping_and_crud(self, client, admin_user, teacher_user, department):
        from users.models import Teacher
        from django.contrib.auth.models import User
        from academics.models import Department

        # Create another department and different teachers
        dept2 = Department.objects.create(name='Biomedical Engineering', code='BIO')
        u2 = User.objects.create_user(username='teacher_bio', password='pass')
        t2 = Teacher.objects.create(user=u2, teacher_id='BIO001', department=dept2)

        # Create an unassigned department teacher
        u3 = User.objects.create_user(username='teacher_unassigned', password='pass')
        t3 = Teacher.objects.create(user=u3, teacher_id='UNASSIGNED001', department=None)

        client.force_login(admin_user)

        # GET teacher list and verify grouping + no crashes
        response = client.get('/manage/teachers/')
        assert response.status_code == 200
        content = response.content.decode()
        assert department.name in content
        assert dept2.name in content
        assert "Unassigned Department" in content

        # GET edit page for teacher
        edit_get_response = client.get(f'/manage/teachers/{t2.pk}/edit/')
        assert edit_get_response.status_code == 200

        # POST edit page to update teacher details
        edit_post_response = client.post(f'/manage/teachers/{t2.pk}/edit/', {
            'teacher_id': 'BIO999',
            'first_name': 'UpdatedBioFirst',
            'last_name': 'UpdatedBioLast',
            'email': 'bio_updated@example.com',
            'department': dept2.pk,
        })
        assert edit_post_response.status_code == 302 # redirect

        # Reload from DB and verify changes saved & persisted
        t2.refresh_from_db()
        assert t2.teacher_id == 'BIO999'
        assert t2.user.first_name == 'UpdatedBioFirst'
        assert t2.user.last_name == 'UpdatedBioLast'
        assert t2.user.email == 'bio_updated@example.com'

        # POST delete page to delete teacher
        delete_response = client.post(f'/manage/teachers/{t2.pk}/delete/')
        assert delete_response.status_code == 302 # redirect

        # Verify teacher and user have been deleted
        assert not Teacher.objects.filter(pk=t2.pk).exists()
        assert not User.objects.filter(username='teacher_bio').exists()

    def test_student_edit_crud(self, client, admin_user, student_user, student_class):
        from students.models import Student
        client.force_login(admin_user)
        student = student_user.student_profile

        # GET the student edit page to verify no VariableDoesNotExist crash
        response = client.get(f'/manage/students/{student.pk}/edit/')
        assert response.status_code == 200

        # POST student edit to update details
        response_post = client.post(f'/manage/students/{student.pk}/edit/', {
            'name': 'Updated Student Name',
            'student_class': student_class.pk,
            'email': 'student_updated@example.com',
            'phone': '1234567890',
            'gender': 'M',
            'guardian_name': 'Guardian Name',
            'is_active': 'on',
        })
        assert response_post.status_code == 302

        # Verify they saved and persisted in Database
        student.refresh_from_db()
        assert student.name == 'Updated Student Name'
        assert student.email == 'student_updated@example.com'

    def test_assignment_management_crud(self, client, admin_user, teacher_user, subject, student_class):
        from academics.models import Assignment, TeacherSubjectClass
        from django.utils import timezone
        
        # Admin assigns teacher to subject & class first
        teacher = teacher_user.teacher
        TeacherSubjectClass.objects.create(teacher=teacher, subject=subject, student_class=student_class)

        # Create an assignment
        assignment = Assignment.objects.create(
            title="UI Midterm Prep",
            description="Prepare for the midterm exam",
            due_date=timezone.now() + timezone.timedelta(days=7),
            subject=subject,
            student_class=student_class,
            created_by=teacher
        )

        # 1. Test Assignment List View as Admin
        client.force_login(admin_user)
        response = client.get('/manage/assignments/')
        assert response.status_code == 200
        assert "UI Midterm Prep" in response.content.decode()

        # 2. Test Assignment List View as Teacher
        client.force_login(teacher_user)
        response = client.get('/manage/assignments/')
        assert response.status_code == 200
        assert "UI Midterm Prep" in response.content.decode()

        # 3. GET/POST Edit Assignment
        response = client.get(f'/manage/assignments/{assignment.pk}/edit/')
        assert response.status_code == 200
        
        date_str = (timezone.now() + timezone.timedelta(days=10)).strftime('%Y-%m-%dT%H:%M')
        response = client.post(f'/manage/assignments/{assignment.pk}/edit/', {
            'title': 'UI Midterm Prep Updated',
            'description': 'Updated instructions',
            'due_date': date_str,
            'subject': subject.pk,
            'student_class': student_class.pk,
        })
        assert response.status_code == 302
        
        assignment.refresh_from_db()
        assert assignment.title == "UI Midterm Prep Updated"
        assert assignment.description == "Updated instructions"

        # 4. POST Delete Assignment
        response = client.post(f'/manage/assignments/{assignment.pk}/delete/')
        assert response.status_code == 302
        assert not Assignment.objects.filter(pk=assignment.pk).exists()

    def test_attendance_management_crud(self, client, admin_user, teacher_user, student_user, subject, student_class):
        from attendance.models import Attendance
        from academics.models import TeacherSubjectClass
        from django.utils import timezone

        student = student_user.student_profile
        teacher = teacher_user.teacher
        TeacherSubjectClass.objects.create(teacher=teacher, subject=subject, student_class=student_class)

        # Mark attendance
        record = Attendance.objects.create(
            student=student,
            subject=subject,
            date=timezone.now().date(),
            status=True,
            marked_by=teacher,
            remarks="Excellent presence"
        )

        # 1. Test Attendance List View as Admin
        client.force_login(admin_user)
        response = client.get('/manage/attendance/')
        assert response.status_code == 200
        assert student.name in response.content.decode()

        # 2. Test Attendance List View as Teacher
        client.force_login(teacher_user)
        response = client.get('/manage/attendance/')
        assert response.status_code == 200
        assert student.name in response.content.decode()

        # 3. POST Delete Attendance Record
        response = client.post(f'/manage/attendance/{record.pk}/delete/')
        assert response.status_code == 302
        assert not Attendance.objects.filter(pk=record.pk).exists()

    def test_marks_bulk_add_and_permissions(self, client, admin_user, teacher_user, student_user, subject, student_class):
        from academics.models import Mark, TeacherSubjectClass
        from django.utils import timezone

        student = student_user.student_profile
        teacher = teacher_user.teacher

        # 1. Unassigned teacher gets permission denied
        client.force_login(teacher_user)
        response = client.post('/manage/marks/add/', {
            'class_id': student_class.pk,
            'subject_id': subject.pk,
            'exam_type': 'midterm',
            'date': timezone.now().date().strftime('%Y-%m-%d'),
            'max_marks': '100',
            f'marks_{student.pk}': '85'
        })
        assert response.status_code == 302
        assert not Mark.objects.filter(student=student, subject=subject).exists()

        # 2. Assign teacher and try again
        TeacherSubjectClass.objects.create(teacher=teacher, subject=subject, student_class=student_class)
        response = client.get(f'/manage/marks/add/?class_id={student_class.pk}&subject_id={subject.pk}&exam_type=midterm&date=2026-07-06')
        assert response.status_code == 200
        assert student.name in response.content.decode()

        # Try to post marks exceeding max marks
        response = client.post('/manage/marks/add/', {
            'class_id': student_class.pk,
            'subject_id': subject.pk,
            'exam_type': 'midterm',
            'date': '2026-07-06',
            'max_marks': '100',
            f'marks_{student.pk}': '105'
        })
        assert response.status_code == 302
        assert not Mark.objects.filter(student=student, subject=subject).exists()

        # Post correct marks
        response = client.post('/manage/marks/add/', {
            'class_id': student_class.pk,
            'subject_id': subject.pk,
            'exam_type': 'midterm',
            'date': '2026-07-06',
            'max_marks': '100',
            f'marks_{student.pk}': '85'
        })
        assert response.status_code == 302
        assert Mark.objects.filter(student=student, subject=subject, exam_type='midterm').exists()
        mark = Mark.objects.get(student=student, subject=subject, exam_type='midterm')
        assert mark.marks_obtained == 85.0
        assert mark.max_marks == 100.0

    def test_marks_list_and_crud(self, client, admin_user, teacher_user, student_user, subject, student_class):
        from academics.models import Mark, TeacherSubjectClass
        from django.utils import timezone
        
        student = student_user.student_profile
        teacher = teacher_user.teacher
        TeacherSubjectClass.objects.create(teacher=teacher, subject=subject, student_class=student_class)

        mark = Mark.objects.create(
            student=student,
            subject=subject,
            exam_type='midterm',
            marks_obtained=75,
            max_marks=100,
            date=timezone.now().date()
        )

        # 1. View list as admin
        client.force_login(admin_user)
        response = client.get('/manage/marks/')
        assert response.status_code == 200
        assert student.name in response.content.decode()

        # 2. View list as teacher
        client.force_login(teacher_user)
        response = client.get('/manage/marks/')
        assert response.status_code == 200
        assert student.name in response.content.decode()

        # 3. View edit as teacher
        response = client.get(f'/manage/marks/{mark.pk}/edit/')
        assert response.status_code == 200

        # Save edit exceeding max marks
        response = client.post(f'/manage/marks/{mark.pk}/edit/', {
            'subject': subject.pk,
            'exam_type': 'midterm',
            'date': timezone.now().date().strftime('%Y-%m-%d'),
            'marks_obtained': '120',
            'max_marks': '100'
        })
        assert response.status_code == 200
        mark.refresh_from_db()
        assert mark.marks_obtained == 75.0

        # Save corrected edit
        response = client.post(f'/manage/marks/{mark.pk}/edit/', {
            'subject': subject.pk,
            'exam_type': 'midterm',
            'date': timezone.now().date().strftime('%Y-%m-%d'),
            'marks_obtained': '95',
            'max_marks': '100'
        })
        assert response.status_code == 302
        mark.refresh_from_db()
        assert mark.marks_obtained == 95.0

        # Delete record
        response = client.post(f'/manage/marks/{mark.pk}/delete/')
        assert response.status_code == 302
        assert not Mark.objects.filter(pk=mark.pk).exists()

    def test_marks_properties_and_tied_ranking(self, db, student_user, subject, student_class):
        from academics.models import Mark
        from students.models import Student
        from django.utils import timezone
        
        student1 = student_user.student_profile
        
        # Create student2 and student3 in the same class
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        u2 = User.objects.create_user(username='stu2', email='stu2@example.com', password='password123')
        student2 = Student.objects.create(
            user=u2,
            name='Student Two',
            regno='REG2002',
            student_class=student_class,
            gender='M',
            is_active=True
        )

        u3 = User.objects.create_user(username='stu3', email='stu3@example.com', password='password123')
        student3 = Student.objects.create(
            user=u3,
            name='Student Three',
            regno='REG2003',
            student_class=student_class,
            gender='F',
            is_active=True
        )

        u4 = User.objects.create_user(username='stu4', email='stu4@example.com', password='password123')
        student4 = Student.objects.create(
            user=u4,
            name='Student Four',
            regno='REG2004',
            student_class=student_class,
            gender='M',
            is_active=True
        )

        date = timezone.now().date()

        # Grade calculations test:
        # Pass threshold = 40% (PASS_THRESHOLD_PCT)
        # Student 1: 90/100 = 90% (Grade A, Pass, Rank 1)
        m1 = Mark.objects.create(student=student1, subject=subject, exam_type='final', marks_obtained=90, max_marks=100, date=date)
        # Student 2: 90/100 = 90% (Grade A, Pass, Rank 1 - tie)
        m2 = Mark.objects.create(student=student2, subject=subject, exam_type='final', marks_obtained=90, max_marks=100, date=date)
        # Student 3: 80/100 = 80% (Grade B, Pass, Rank 3)
        m3 = Mark.objects.create(student=student3, subject=subject, exam_type='final', marks_obtained=80, max_marks=100, date=date)
        # Student 4: 35/100 = 35% (Grade F, Fail, Rank 4)
        m4 = Mark.objects.create(student=student4, subject=subject, exam_type='final', marks_obtained=35, max_marks=100, date=date)

        # Assert percentages
        assert m1.percentage == 90.0
        assert m3.percentage == 80.0
        assert m4.percentage == 35.0

        # Assert pass/fail
        assert m1.is_pass is True
        assert m4.is_pass is False

        # Assert grades
        assert m1.grade == 'A'
        assert m3.grade == 'B'
        assert m4.grade == 'F'

        # Assert ranks (1, 1, 3, 4)
        assert m1.class_rank == 1
        assert m2.class_rank == 1
        assert m3.class_rank == 3
        assert m4.class_rank == 4



