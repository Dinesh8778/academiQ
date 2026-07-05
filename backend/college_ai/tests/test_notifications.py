import pytest
import datetime
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.management import call_command
from django.contrib.contenttypes.models import ContentType

from students.models import Student
from academics.models import Class, Subject, TeacherSubjectClass, Assignment, Submission
from attendance.models import Attendance
from notifications.models import Notification

@pytest.mark.django_db
class TestAnomalyDetection:

    def test_rule_1_attendance_drop(self, admin_user, department, teacher_user, student_class, subject):
        """
        Rule 1: Any student whose attendance dropped more than 20 percentage points
        in the last 2 weeks vs the prior 2 weeks.
        """
        # Create teacher profile to make them adviser
        class_obj = student_class
        class_obj.adviser = teacher_user.teacher
        class_obj.save()

        # Create two students: one triggers (drop from 100% to 50%), one doesn't (stays at 100%)
        student_trigger = Student.objects.create(
            name='Drop Student', regno='REG001', student_class=class_obj, email='drop@test.com'
        )
        student_stable = Student.objects.create(
            name='Stable Student', regno='REG002', student_class=class_obj, email='stable@test.com'
        )

        today = datetime.date(2026, 7, 15)

        # Period B (Prior 2 weeks): 2026-06-18 to 2026-07-01
        # Period A (Last 2 weeks): 2026-07-02 to 2026-07-15

        # Seed attendance:
        # student_trigger: Period B: 2 present, 0 absent (100%). Period A: 1 present, 1 absent (50%). Drop = 50%
        # student_stable: Period B: 2 present, 0 absent (100%). Period A: 2 present, 0 absent (100%). Drop = 0%
        
        Attendance.objects.create(student=student_trigger, subject=subject, date=datetime.date(2026, 6, 20), status=True)
        Attendance.objects.create(student=student_trigger, subject=subject, date=datetime.date(2026, 6, 25), status=True)
        Attendance.objects.create(student=student_trigger, subject=subject, date=datetime.date(2026, 7, 5), status=True)
        Attendance.objects.create(student=student_trigger, subject=subject, date=datetime.date(2026, 7, 10), status=False)

        Attendance.objects.create(student=student_stable, subject=subject, date=datetime.date(2026, 6, 20), status=True)
        Attendance.objects.create(student=student_stable, subject=subject, date=datetime.date(2026, 6, 25), status=True)
        Attendance.objects.create(student=student_stable, subject=subject, date=datetime.date(2026, 7, 5), status=True)
        Attendance.objects.create(student=student_stable, subject=subject, date=datetime.date(2026, 7, 10), status=True)

        # Run command for 2026-07-15
        call_command('detect_anomalies', date='2026-07-15')

        # Check notifications generated
        # Relevant recipients should be admin and adviser (teacher_user)
        # Drop Student should trigger notifications
        adviser_notifs = Notification.objects.filter(recipient=teacher_user, category='attendance_alert')
        admin_notifs = Notification.objects.filter(recipient=admin_user, category='attendance_alert')

        assert adviser_notifs.filter(title__contains=student_trigger.name).exists()
        assert admin_notifs.filter(title__contains=student_trigger.name).exists()

        # Stable student should NOT trigger notifications
        assert not adviser_notifs.filter(title__contains=student_stable.name).exists()

        # Duplicate check: Running it again shouldn't create duplicates since they are still unread
        notif_count_before = Notification.objects.count()
        call_command('detect_anomalies', date='2026-07-15')
        notif_count_after = Notification.objects.count()

        assert notif_count_before == notif_count_after


    def test_rule_2_low_class_attendance(self, admin_user, department, teacher_user, student_class, subject):
        """
        Rule 2: Any class where average attendance is below 50% for the current week.
        """
        class_obj = student_class
        class_obj.adviser = teacher_user.teacher
        class_obj.save()

        # Create student for this class
        student = Student.objects.create(
            name='Class Student', regno='REG003', student_class=class_obj, email='class_std@test.com'
        )

        today = datetime.date(2026, 7, 15)  # Wednesday (Weekday 2)
        # Current Week: Monday 2026-07-13 to Wednesday 2026-07-15

        # Seed attendance: 2 days absent, 0 days present (avg = 0%)
        Attendance.objects.create(student=student, subject=subject, date=datetime.date(2026, 7, 13), status=False)
        Attendance.objects.create(student=student, subject=subject, date=datetime.date(2026, 7, 14), status=False)

        call_command('detect_anomalies', date='2026-07-15')

        # Verify class adviser is notified
        adviser_notifs = Notification.objects.filter(recipient=teacher_user, category='attendance_alert')
        assert adviser_notifs.filter(title__contains="Low Class Attendance").exists()


    def test_rule_3_missing_attendance_marking(self, admin_user, department, teacher_user, student_class, subject, teacher_subject_class):
        """
        Rule 3: Any class/subject combo with no attendance marked for 3+ consecutive class days.
        """
        # Baseline date: Wednesday 2026-07-15 (weekdays to check: Wed 15, Tue 14, Mon 13)
        # For teacher_subject_class, we have no attendance records at all during these days, so it should trigger.
        
        call_command('detect_anomalies', date='2026-07-15')

        # Check teacher was notified
        teacher_notifs = Notification.objects.filter(recipient=teacher_user, category='attendance_alert')
        assert teacher_notifs.filter(title__contains="Unmarked Attendance Alert").exists()

        # Now, if we mark attendance on at least one day, it should not trigger on subsequential check
        # Let's mark attendance for Monday 2026-07-13
        student = Student.objects.create(
            name='S3 Student', regno='REG004', student_class=student_class, email='s3@test.com'
        )
        Attendance.objects.create(student=student, subject=subject, date=datetime.date(2026, 7, 13), status=True)

        # Clear notifications first to isolate the new run
        Notification.objects.all().delete()

        call_command('detect_anomalies', date='2026-07-15')
        teacher_notifs_after = Notification.objects.filter(recipient=teacher_user, category='attendance_alert')
        assert not teacher_notifs_after.filter(title__contains="Unmarked Attendance").exists()


    def test_rule_4_missing_or_late_assignments(self, admin_user, department, teacher_user, student_class, subject):
        """
        Rule 4: Any student with 3+ consecutive missed/late assignment submissions.
        """
        class_obj = student_class
        class_obj.adviser = teacher_user.teacher
        class_obj.save()

        student = Student.objects.create(
            name='Assignment Student', regno='REG005', student_class=class_obj, email='assignment@test.com'
        )

        # Create assignments with past due dates
        a1 = Assignment.objects.create(
            title='Ass1', due_date=timezone.make_aware(datetime.datetime(2026, 7, 5, 23, 59)),
            subject=subject, student_class=student_class, created_by=teacher_user.teacher
        )
        a2 = Assignment.objects.create(
            title='Ass2', due_date=timezone.make_aware(datetime.datetime(2026, 7, 6, 23, 59)),
            subject=subject, student_class=student_class, created_by=teacher_user.teacher
        )
        a3 = Assignment.objects.create(
            title='Ass3', due_date=timezone.make_aware(datetime.datetime(2026, 7, 7, 23, 59)),
            subject=subject, student_class=student_class, created_by=teacher_user.teacher
        )

        # Case 4A: 3 missed assignments (no submissions)
        call_command('detect_anomalies', date='2026-07-15')

        # Check notification
        adviser_notifs = Notification.objects.filter(recipient=teacher_user, category='anomaly')
        assert adviser_notifs.filter(title__contains=student.name).exists()

        # Case 4B: One assignment on time (Ass1), two late (Ass2, Ass3) => streak=2, no trigger.
        # Clear all
        Notification.objects.all().delete()
        Submission.objects.all().delete()

        # Ass1 submitted on time
        sub1 = Submission.objects.create(assignment=a1, student=student)
        Submission.objects.filter(pk=sub1.pk).update(submitted_at=timezone.make_aware(datetime.datetime(2026, 7, 5, 12, 0)))

        # Ass2 submitted late
        sub2 = Submission.objects.create(assignment=a2, student=student)
        Submission.objects.filter(pk=sub2.pk).update(submitted_at=timezone.make_aware(datetime.datetime(2026, 7, 8, 12, 0)))

        # Ass3 not submitted (missed)
        call_command('detect_anomalies', date='2026-07-15')
        adviser_notifs_after = Notification.objects.filter(recipient=teacher_user, category='anomaly')
        assert not adviser_notifs_after.filter(title__contains=student.name).exists()


    def test_student_never_notified(self, student_user, department, teacher_user, student_class, subject):
        """
        Confirm that students never receive anomaly notifications.
        """
        # Create an anomaly for test purposes
        today = datetime.date(2026, 7, 15)
        # Create and verify triggering rule 3: no attendance marked
        call_command('detect_anomalies', date='2026-07-15')
        
        # Verify student_user has no notifications
        student_notifs = Notification.objects.filter(recipient=student_user)
        assert student_notifs.count() == 0
