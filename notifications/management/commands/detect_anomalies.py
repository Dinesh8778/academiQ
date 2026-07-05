import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType

from students.models import Student
from academics.models import Class, TeacherSubjectClass, Assignment, Submission
from attendance.models import Attendance
from notifications.models import Notification

def get_last_weekdays(start_date, limit=3):
    weekdays = []
    curr = start_date
    while len(weekdays) < limit:
        if curr.weekday() < 5:  # 0 to 4 is Mon-Fri
            weekdays.append(curr)
        curr -= datetime.timedelta(days=1)
    return weekdays

class Command(BaseCommand):
    help = 'Analyzes databases for student and class anomalies and creates notifications'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Run detection using this date (YYYY-MM-DD) as today. Defaults to today.'
        )

    def handle(self, *args, **options):
        # 1. Parse baseline date
        date_str = options.get('date')
        if date_str:
            today = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        else:
            today = timezone.localdate()

        # Combine baseline date with time min/max for aware datetime operations
        today_min_dt = timezone.make_aware(datetime.datetime.combine(today, datetime.time.min))
        today_max_dt = timezone.make_aware(datetime.datetime.combine(today, datetime.time.max))

        self.stdout.write(self.style.SUCCESS(f"Running anomaly detection for date: {today}"))

        # Helper notifier method
        def notify(recipient, title, message, category, related_obj):
            content_type = ContentType.objects.get_for_model(related_obj)
            # Avoid creating duplicates of unread notifications for the same recipient, category and related object
            duplicate_exists = Notification.objects.filter(
                recipient=recipient,
                category=category,
                content_type=content_type,
                object_id=related_obj.id,
                is_read=False
            ).exists()
            if not duplicate_exists:
                Notification.objects.create(
                    recipient=recipient,
                    title=title,
                    message=message,
                    category=category,
                    content_type=content_type,
                    object_id=related_obj.id
                )
                self.stdout.write(self.style.SUCCESS(f"Created Notification for {recipient.username}: {title}"))
            else:
                self.stdout.write(self.style.WARNING(f"Duplicate unread Notification skipped for {recipient.username}: {title}"))

        # =========================================================================
        # Rule 1: Student Attendance Drop (20%+ points in last 2 weeks vs prior 2 weeks)
        # =========================================================================
        start_a = today - datetime.timedelta(days=13)
        end_a = today
        start_b = today - datetime.timedelta(days=27)
        end_b = today - datetime.timedelta(days=14)

        active_students = Student.objects.filter(is_active=True)
        for student in active_students:
            # Period A
            att_a = Attendance.objects.filter(student=student, date__range=(start_a, end_a))
            count_a = att_a.count()
            present_a = att_a.filter(status=True).count()

            # Period B
            att_b = Attendance.objects.filter(student=student, date__range=(start_b, end_b))
            count_b = att_b.count()
            present_b = att_b.filter(status=True).count()

            if count_a > 0 and count_b > 0:
                pct_a = (present_a / count_a) * 100.0
                pct_b = (present_b / count_b) * 100.0
                drop = pct_b - pct_a
                if drop > 20.0:
                    # Notify Adviser and Admins
                    recipients = set(User.objects.filter(is_staff=True))
                    if student.student_class.adviser and student.student_class.adviser.user:
                        recipients.add(student.student_class.adviser.user)

                    title = f"Attendance Drop Alert: {student.name}"
                    msg = (
                        f"Student {student.name} ({student.regno}) has experienced a drop in attendance. "
                        f"Attendance in the last 2 weeks was {pct_a:.1f}% ({present_a}/{count_a}) vs. "
                        f"{pct_b:.1f}% ({present_b}/{count_b}) in the prior 2 weeks. Total drop: {drop:.1f}% points."
                    )
                    for r in recipients:
                        notify(r, title, msg, 'attendance_alert', student)

        # =========================================================================
        # Rule 2: Class Average Attendance Below 50% for the current week
        # =========================================================================
        # Current week (Monday to today)
        week_start = today - datetime.timedelta(days=today.weekday())
        week_end = today

        classes = Class.objects.all()
        for class_obj in classes:
            att = Attendance.objects.filter(student__student_class=class_obj, date__range=(week_start, week_end))
            total = att.count()
            present = att.filter(status=True).count()
            if total > 0:
                avg_att = (present / total) * 100.0
                if avg_att < 50.0:
                    recipients = set(User.objects.filter(is_staff=True))
                    if class_obj.adviser and class_obj.adviser.user:
                        recipients.add(class_obj.adviser.user)
                    for tsc in TeacherSubjectClass.objects.filter(student_class=class_obj):
                        if tsc.teacher and tsc.teacher.user:
                            recipients.add(tsc.teacher.user)

                    title = f"Low Class Attendance Alert: {class_obj}"
                    msg = (
                        f"Class {class_obj} average attendance is at {avg_att:.1f}% "
                        f"({present}/{total} present) for the current week ({week_start} to {week_end}), "
                        f"which is below the 50% tracking threshold."
                    )
                    for r in recipients:
                        notify(r, title, msg, 'attendance_alert', class_obj)

        # =========================================================================
        # Rule 3: Class/Subject Combo with no attendance marked for 3+ consecutive class days
        # =========================================================================
        weekdays = get_last_weekdays(today, limit=3)
        for tsc in TeacherSubjectClass.objects.all():
            missing_all = True
            for day in weekdays:
                has_attendance = Attendance.objects.filter(
                    student__student_class=tsc.student_class,
                    subject=tsc.subject,
                    date=day
                ).exists()
                if has_attendance:
                    missing_all = False
                    break
            if missing_all:
                recipients = set(User.objects.filter(is_staff=True))
                if tsc.teacher and tsc.teacher.user:
                    recipients.add(tsc.teacher.user)
                if tsc.student_class.adviser and tsc.student_class.adviser.user:
                    recipients.add(tsc.student_class.adviser.user)

                title = f"Unmarked Attendance Alert: {tsc.student_class} - {tsc.subject.code}"
                msg = (
                    f"No attendance records were found for subject {tsc.subject.name} "
                    f"in class {tsc.student_class} for 3+ consecutive class days: "
                    f"{', '.join([d.strftime('%Y-%m-%d') for d in weekdays])}."
                )
                for r in recipients:
                    notify(r, title, msg, 'attendance_alert', tsc)

        # =========================================================================
        # Rule 4: Student with 3+ consecutive missed/late assignment submissions
        # =========================================================================
        for student in active_students:
            # Query all past assignments for this student's class ordered by due date
            assignments = Assignment.objects.filter(
                student_class=student.student_class,
                due_date__lte=today_max_dt
            ).order_by('due_date')

            consecutive_streak = 0
            max_streak = 0
            for assignment in assignments:
                sub = Submission.objects.filter(assignment=assignment, student=student).first()
                is_missed = (sub is None)
                is_late = (sub is not None and sub.submitted_at > assignment.due_date)

                if is_missed or is_late:
                    consecutive_streak += 1
                else:
                    consecutive_streak = 0
                
                if consecutive_streak > max_streak:
                    max_streak = consecutive_streak

            if max_streak >= 3:
                recipients = set(User.objects.filter(is_staff=True))
                if student.student_class.adviser and student.student_class.adviser.user:
                    recipients.add(student.student_class.adviser.user)
                for tsc in TeacherSubjectClass.objects.filter(student_class=student.student_class):
                    if tsc.teacher and tsc.teacher.user:
                        recipients.add(tsc.teacher.user)

                title = f"Assignment Submission Anomaly: {student.name}"
                msg = (
                    f"Student {student.name} ({student.regno}) has {max_streak} consecutive "
                    f"missed or late assignment submissions."
                )
                for r in recipients:
                    notify(r, title, msg, 'anomaly', student)

        self.stdout.write(self.style.SUCCESS("Anomaly detection complete."))
