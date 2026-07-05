import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from datetime import timedelta
from academics.models import Assignment, Submission, Class
from students.models import Student
from django.contrib.auth.models import User

@pytest.mark.django_db
class TestAssignmentSubmissions:

    @pytest.fixture
    def assignment(self, teacher_user, student_class, subject):
        # Create an assignment for the student's class
        return Assignment.objects.create(
            title="Math Homework 1",
            description="Complete exercises 1-5",
            due_date=timezone.now() + timedelta(days=1),
            subject=subject,
            student_class=student_class,
            created_by=teacher_user.teacher
        )

    def test_student_submit_successful(self, student_client, student_user, assignment):
        student_client.force_login(student_user)
        sub_count = Submission.objects.count()
        
        # Prepare file upload
        test_file = SimpleUploadedFile("homework.pdf", b"pdf_content", content_type="application/pdf")
        
        # Post to submit endpoint
        url = f"/student/assignments/{assignment.pk}/submit/"
        response = student_client.post(url, {"file": test_file})
        
        # Verify redirect on success
        assert response.status_code == 302
        
        # Verify Submission created
        assert Submission.objects.count() == sub_count + 1
        sub = Submission.objects.get(assignment=assignment, student=student_user.student_profile)
        assert sub.file is not None
        assert "homework" in sub.file.name
        
        # Resubmit with a different file
        test_file2 = SimpleUploadedFile("homework_revised.pdf", b"pdf_content_v2", content_type="application/pdf")
        response2 = student_client.post(url, {"file": test_file2})
        assert response2.status_code == 302
        
        assert Submission.objects.count() == sub_count + 1
        sub.refresh_from_db()
        assert "homework_revised" in sub.file.name

    def test_student_submit_blocked_for_other_class(self, student_client, student_user, department, subject, teacher_user):
        student_client.force_login(student_user)
        # Create another class
        other_class = Class.objects.create(
            department=department, year=2, section='A', academic_year='2025-2026'
        )
        # Create an assignment for that other class
        assignment = Assignment.objects.create(
            title="History Essay",
            due_date=timezone.now() + timedelta(days=1),
            subject=subject,
            student_class=other_class,
            created_by=teacher_user.teacher
        )
        
        # Submit to it
        url = f"/student/assignments/{assignment.pk}/submit/"
        test_file = SimpleUploadedFile("essay.pdf", b"essay", content_type="application/pdf")
        response = student_client.post(url, {"file": test_file})
        
        assert response.status_code == 302 # Redirected because of access denied
        # Confirm Submission NOT created
        assert not Submission.objects.filter(assignment=assignment).exists()

    def test_student_submit_blocked_after_due_date(self, student_client, student_user, assignment):
        student_client.force_login(student_user)
        # Make assignment overdue
        assignment.due_date = timezone.now() - timedelta(hours=1)
        assignment.save()
        
        url = f"/student/assignments/{assignment.pk}/submit/"
        test_file = SimpleUploadedFile("late.pdf", b"late", content_type="application/pdf")
        response = student_client.post(url, {"file": test_file})
        
        assert response.status_code == 302 # Redirected due to late submission policy (blocked)
        assert not Submission.objects.filter(assignment=assignment).exists()

    def test_teacher_view_submission_status(self, teacher_client, teacher_user, student_user, assignment):
        teacher_client.force_login(teacher_user)
        # Create a submission first
        student = student_user.student_profile
        sub = Submission.objects.create(
            assignment=assignment,
            student=student,
            file=SimpleUploadedFile("doc.pdf", b"doc_bytes")
        )
        
        url = f"/teacher/assignments/{assignment.pk}/submissions/"
        response = teacher_client.get(url)
        assert response.status_code == 200
        
        # Verify details are present in the response
        content = response.content.decode()
        assert student.name in content
        assert "Submitted" in content
        assert "View File" in content

    def test_teacher_grading_affects_student_views(self, teacher_client, student_client, teacher_user, student_user, assignment):
        teacher_client.force_login(teacher_user)
        student_client.force_login(student_user)
        student = student_user.student_profile
        sub = Submission.objects.create(
            assignment=assignment,
            student=student,
            file=SimpleUploadedFile("doc.pdf", b"doc_bytes")
        )
        
        # 1. Post grade + feedback as teacher
        url = f"/teacher/assignments/{assignment.pk}/submissions/"
        response = teacher_client.post(url, {
            f"grade_{student.pk}": "89.5",
            f"feedback_{student.pk}": "Great work!"
        })
        assert response.status_code == 302
        
        sub.refresh_from_db()
        assert float(sub.grade) == 89.5
        assert sub.feedback == "Great work!"
        
        # 2. Get student dashboard & verify grade appears in Assignments and Report Card sections
        dashboard_url = "/auth/dashboard/student/"
        student_dashboard_res = student_client.get(dashboard_url)
        assert student_dashboard_res.status_code == 200
        dashboard_content = student_dashboard_res.content.decode()
        
        assert "Graded: 89.50" in dashboard_content or "Graded: 89.5" in dashboard_content
        assert "Assignment Grades" in dashboard_content
        assert "Math Homework 1" in dashboard_content
        assert "89.50" in dashboard_content or "89.5" in dashboard_content
