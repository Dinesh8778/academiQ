import pytest
from django.contrib.auth.models import User
from assistant.models import DraftActionLog
from notifications.models import Notification
from students.models import Student
from academics.models import Class, TeacherSubjectClass
from assistant.tools import draft_low_attendance_notice, draft_weekly_summary_report

@pytest.mark.django_db
class TestDraftActions:

    def test_draft_low_attendance_notice_tool_permissions(self, teacher_user, admin_user, student_user, student_class, teacher_subject_class, department):
        # Student in teacher's class
        student = student_user.student_profile
        # Clean existing draft action log for a fresh start
        DraftActionLog.objects.all().delete()
        
        # 1. Teacher drafts for their student
        result = draft_low_attendance_notice(teacher_user, student_id=student.id)
        assert result["action"] == "propose_draft"
        assert result["action_type"] == "low_attendance_notice"
        assert result["student_id"] == student.id
        
        # 2. Teacher attempts to draft for student in a class they do not teach
        other_class = Class.objects.create(
            department=department, year=1, section='B', academic_year='2025-2026'
        )
        other_student_user = User.objects.create_user(
            username='other_student', password='Student@1234', email='other_student@test.com'
        )
        other_student = Student.objects.create(
            user=other_student_user, name='Other Student', regno='T002REG',
            student_class=other_class, email='other_student@test.com'
        )
        
        err_result = draft_low_attendance_notice(teacher_user, student_id=other_student.id)
        assert "error" in err_result
        assert err_result["error"] == "ACCESS_DENIED"

        # 3. Admin can draft for anyone (even other_student in B section)
        admin_result = draft_low_attendance_notice(admin_user, student_id=other_student.id)
        assert admin_result["action"] == "propose_draft"
        assert admin_result["student_id"] == other_student.id

    def test_draft_weekly_summary_report_tool_permissions(self, admin_user, teacher_user):
        # 1. Admin drafts report
        admin_res = draft_weekly_summary_report(admin_user)
        assert admin_res["action"] == "propose_draft"
        
        # 2. Teacher lacks system-wide permission
        teacher_res = draft_weekly_summary_report(teacher_user)
        assert "error" in teacher_res
        assert teacher_res["error"] == "ACCESS_DENIED"

    def test_api_send_draft_validation_and_discard(self, teacher_client, teacher_user, student_user):
        student = student_user.student_profile
        
        # 1. Create a draft log for the teacher manually
        draft = DraftActionLog.objects.create(
            user=teacher_user,
            action_type="low_attendance_notice",
            status="drafted",
            details={
                "student_id": student.id,
                "title": "Low Attendance Warning",
                "message": "Please attend your classes."
            }
        )
        
        # 2. Call API to discard
        url = "/api/notifications/send-draft/"
        response = teacher_client.post(url, {"draft_id": draft.id, "action": "discard"}, format="json")
        assert response.status_code == 200
        assert response.data["status"] == "discarded"
        
        draft.refresh_from_db()
        assert draft.status == "discarded"
        
        # No Notification should have been created
        assert not Notification.objects.filter(recipient=student_user).exists()

    def test_api_send_draft_confirm_success(self, teacher_client, teacher_user, student_user, teacher_subject_class):
        student = student_user.student_profile
        
        draft = DraftActionLog.objects.create(
            user=teacher_user,
            action_type="low_attendance_notice",
            status="drafted",
            details={
                "student_id": student.id,
                "title": "Low Attendance Warning",
                "message": "Warning content here."
            }
        )
        
        # Confirming draft
        url = "/api/notifications/send-draft/"
        response = teacher_client.post(url, {"draft_id": draft.id, "action": "confirm"}, format="json")
        assert response.status_code == 200
        assert response.data["status"] == "confirmed"
        
        draft.refresh_from_db()
        assert draft.status == "confirmed"
        
        # Check Notification created
        notif = Notification.objects.get(recipient=student_user)
        assert notif.title == "Low Attendance Warning"
        assert notif.message == "Warning content here."
        assert notif.category == "attendance_alert"

    def test_api_send_draft_tamper_re_validation(self, teacher_client, teacher_user, department):
        # Create other student in a class the teacher doesn't teach
        other_class = Class.objects.create(
            department=department, year=1, section='C', academic_year='2025-2026'
        )
        other_student_user = User.objects.create_user(
            username='tampered_student', password='Student@1234', email='tampered@test.com'
        )
        other_student = Student.objects.create(
            user=other_student_user, name='Tampered Student', regno='T003REG',
            student_class=other_class, email='tampered@test.com'
        )

        # Create a draft belonging to teacher but targeting other_student (simulate tampered payload)
        draft = DraftActionLog.objects.create(
            user=teacher_user,
            action_type="low_attendance_notice",
            status="drafted",
            details={
                "student_id": other_student.id,
                "title": "Tampered Warning",
                "message": "Should fail re-validation."
            }
        )

        url = "/api/notifications/send-draft/"
        response = teacher_client.post(url, {"draft_id": draft.id, "action": "confirm"}, format="json")
        
        # Should be forbidden
        assert response.status_code == 403
        assert "Permission denied" in response.data["detail"]

        # Ensure draft is NOT confirmed in DB, and notification is NOT sent
        draft.refresh_from_db()
        assert draft.status == "drafted"
        assert not Notification.objects.filter(recipient=other_student_user).exists()
