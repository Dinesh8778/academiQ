"""
assistant/tools.py
==================
Role-scoped tool functions for the AI assistant.

SECURITY PRINCIPLE:
  Permission checks live INSIDE each tool function — they are NEVER
  delegated to the LLM's judgment. The LLM receives only tool definitions
  for its own role, and even if it somehow calls a tool outside its role,
  the function itself enforces the permission check using the bound `user`.

Tool functions are plain Python — they query existing ORM models and return
serialisable dicts. They do not expose raw querysets or Django objects.
"""

from __future__ import annotations
from typing import Optional
import json


# ---------------------------------------------------------------------------
# PermissionDenied sentinel — returned (not raised) so the LLM can report it
# ---------------------------------------------------------------------------
def _denied(msg: str) -> dict:
    return {"error": "ACCESS_DENIED", "detail": msg}


# ===========================================================================
# STUDENT TOOLS  — scoped to the authenticated student's own data only
# ===========================================================================

def get_my_attendance(user) -> dict:
    """
    Returns the authenticated student's attendance percentage and recent records.
    ONLY works for the student themselves — no cross-student access.
    """
    if not hasattr(user, 'student_profile'):
        return _denied("Only students can call get_my_attendance.")

    student = user.student_profile
    from attendance.models import Attendance
    from django.db.models import Count, Q

    records = Attendance.objects.filter(student=student).select_related('subject')
    total = records.count()
    present = records.filter(status=True).count()
    att_pct = round((present / total * 100), 1) if total > 0 else 100.0

    # Per-subject breakdown
    subject_stats = (
        records.values('subject__name', 'subject__code')
        .annotate(total=Count('id'), present=Count('id', filter=Q(status=True)))
    )
    by_subject = [
        {
            'subject': row['subject__name'],
            'code': row['subject__code'],
            'total': row['total'],
            'present': row['present'],
            'percentage': round(row['present'] / row['total'] * 100, 1) if row['total'] > 0 else 100.0,
        }
        for row in subject_stats
    ]

    return {
        'student': student.name,
        'regno': student.regno,
        'overall_percentage': att_pct,
        'total_classes': total,
        'present': present,
        'absent': total - present,
        'by_subject': by_subject,
    }


def get_my_assignments(user) -> dict:
    """
    Returns pending and upcoming assignments for the authenticated student's class.
    ONLY returns assignments for this student's class — no cross-class access.
    """
    if not hasattr(user, 'student_profile'):
        return _denied("Only students can call get_my_assignments.")

    student = user.student_profile
    from academics.models import Assignment, Submission
    from django.utils import timezone

    assignments = Assignment.objects.filter(
        student_class=student.student_class
    ).select_related('subject').order_by('due_date')

    submitted_ids = set(
        Submission.objects.filter(student=student)
        .exclude(file='')
        .values_list('assignment_id', flat=True)
    )

    result = []
    now = timezone.now()
    for a in assignments:
        result.append({
            'id': a.pk,
            'title': a.title,
            'subject': a.subject.name,
            'due_date': a.due_date.isoformat(),
            'is_overdue': a.due_date < now,
            'submitted': a.pk in submitted_ids,
        })

    return {
        'student': student.name,
        'class': str(student.student_class),
        'assignments': result,
        'pending_count': sum(1 for r in result if not r['submitted']),
    }


def get_my_grades(user) -> dict:
    """
    Returns the authenticated student's marks per subject.
    ONLY their own grades — no other student's data.
    """
    if not hasattr(user, 'student_profile'):
        return _denied("Only students can call get_my_grades.")

    student = user.student_profile
    from academics.models import Mark

    marks = Mark.objects.filter(student=student).select_related('subject').order_by('subject__name', 'date')

    total_obt = sum(float(m.marks_obtained) for m in marks)
    total_max = sum(float(m.max_marks) for m in marks)
    overall_pct = round(total_obt / total_max * 100, 1) if total_max > 0 else 0.0

    result = [
        {
            'subject': m.subject.name,
            'exam_type': m.get_exam_type_display(),
            'marks_obtained': float(m.marks_obtained),
            'max_marks': float(m.max_marks),
            'percentage': round(float(m.marks_obtained) / float(m.max_marks) * 100, 1)
                         if float(m.max_marks) > 0 else 0.0,
            'date': m.date.isoformat(),
        }
        for m in marks
    ]

    return {
        'student': student.name,
        'regno': student.regno,
        'overall_percentage': overall_pct,
        'marks': result,
    }


# ===========================================================================
# TEACHER TOOLS  — scoped to classes/assignments this teacher owns
# ===========================================================================

def get_class_attendance_summary(user, class_id: int) -> dict:
    """
    Returns attendance summary for a class.
    ENFORCES: teacher must teach a subject in that class.
    """
    if not (hasattr(user, 'teacher') or user.is_staff):
        return _denied("Only teachers or admins can call get_class_attendance_summary.")

    from academics.models import Class, TeacherSubjectClass
    from attendance.models import Attendance
    from django.db.models import Count, Q

    # Permission check — teacher must have a TeacherSubjectClass for this class
    if not user.is_staff:
        owns_class = TeacherSubjectClass.objects.filter(
            teacher=user.teacher, student_class_id=class_id
        ).exists()
        if not owns_class:
            return _denied(f"You are not assigned to teach any subject in class {class_id}.")

    try:
        cls = Class.objects.select_related('department').get(pk=class_id)
    except Class.DoesNotExist:
        return {"error": "NOT_FOUND", "detail": f"Class {class_id} does not exist."}

    students = cls.students.filter(is_active=True)
    result = []
    for student in students:
        records = Attendance.objects.filter(student=student)
        total = records.count()
        present = records.filter(status=True).count()
        pct = round(present / total * 100, 1) if total > 0 else 100.0
        result.append({
            'regno': student.regno,
            'name': student.name,
            'attendance_percentage': pct,
            'at_risk': pct < 75,
        })

    result.sort(key=lambda x: x['attendance_percentage'])
    return {
        'class': str(cls),
        'total_students': len(result),
        'low_attendance_count': sum(1 for r in result if r['at_risk']),
        'students': result,
    }


def get_pending_submissions(user, assignment_id: int) -> dict:
    """
    Returns ungraded submissions for an assignment.
    ENFORCES: teacher must be the creator of the assignment.
    """
    if not (hasattr(user, 'teacher') or user.is_staff):
        return _denied("Only teachers or admins can call get_pending_submissions.")

    from academics.models import Assignment, Submission

    try:
        assignment = Assignment.objects.select_related('subject', 'student_class').get(
            pk=assignment_id
        )
    except Assignment.DoesNotExist:
        return {"error": "NOT_FOUND", "detail": f"Assignment {assignment_id} does not exist."}

    # Permission check — teacher must have created this assignment
    if not user.is_staff and assignment.created_by != user.teacher:
        return _denied(f"Assignment {assignment_id} was not created by you.")

    submissions = Submission.objects.filter(
        assignment=assignment,
        grade__isnull=True,
        file__isnull=False,
    ).exclude(file='').select_related('student')

    result = [
        {
            'student': s.student.name,
            'regno': s.student.regno,
            'submitted_at': s.submitted_at.isoformat(),
            'graded': s.grade is not None,
        }
        for s in submissions
    ]

    return {
        'assignment': assignment.title,
        'subject': assignment.subject.name,
        'class': str(assignment.student_class),
        'pending_count': len(result),
        'submissions': result,
    }


def get_low_attendance_students(user, class_id: int) -> dict:
    """
    Returns students with attendance below 75% in a class.
    ENFORCES: teacher must teach in that class.
    Reuses get_class_attendance_summary with a filter.
    """
    summary = get_class_attendance_summary(user, class_id)
    if 'error' in summary:
        return summary
    low = [s for s in summary['students'] if s['at_risk']]
    return {
        'class': summary['class'],
        'threshold': '75%',
        'low_attendance_count': len(low),
        'students': low,
    }


# ===========================================================================
# ADMIN TOOLS  — unrestricted by class/teacher, scoped only to role check
# ===========================================================================

def get_department_stats(user, department_id: int) -> dict:
    """Returns aggregate stats for a department. Admin only."""
    if not user.is_staff:
        return _denied("Only admins can call get_department_stats.")

    from academics.models import Department
    from students.models import Student

    try:
        dept = Department.objects.get(pk=department_id)
    except Department.DoesNotExist:
        return {"error": "NOT_FOUND", "detail": f"Department {department_id} does not exist."}

    classes = dept.classes.all()
    total_students = Student.objects.filter(
        student_class__department=dept, is_active=True
    ).count()

    return {
        'department': dept.name,
        'code': dept.code,
        'hod': str(dept.hod) if dept.hod else None,
        'total_classes': classes.count(),
        'total_active_students': total_students,
        'subjects': list(dept.subjects.values_list('name', flat=True)),
    }


def get_at_risk_students(user, class_id: Optional[int] = None) -> dict:
    """
    Returns students predicted at-risk by the Phase 5A model. Admin only.
    Calls ai_engine.predictor.predict_risk directly.
    """
    if not user.is_staff:
        return _denied("Only admins can call get_at_risk_students.")

    try:
        from ai_engine.predictor import predict_risk
        results = predict_risk(class_id=class_id)
        at_risk = [r for r in results if r['at_risk_label'] == 1]
        return {
            'total_scanned': len(results),
            'at_risk_count': len(at_risk),
            'class_id': class_id,
            'disclaimer': 'Labels are rule-derived. See ai_engine/README.md.',
            'students': [
                {
                    'regno': r['regno'],
                    'name': r['name'],
                    'risk_score': r['risk_score'],
                    'attendance_pct': r['features']['attendance_percentage'],
                    'avg_marks': r['features']['average_marks'],
                }
                for r in at_risk
            ],
        }
    except FileNotFoundError as e:
        return {"error": "MODEL_NOT_TRAINED", "detail": str(e)}


def get_class_roster(user, class_id: int) -> dict:
    """Returns the full student roster for a class. Admin only."""
    if not user.is_staff:
        return _denied("Only admins can call get_class_roster.")

    from academics.models import Class
    from students.models import Student

    try:
        cls = Class.objects.select_related('department').get(pk=class_id)
    except Class.DoesNotExist:
        return {"error": "NOT_FOUND", "detail": f"Class {class_id} does not exist."}

    students = Student.objects.filter(student_class=cls, is_active=True).order_by('regno')
    return {
        'class': str(cls),
        'total': students.count(),
        'students': [
            {'regno': s.regno, 'name': s.name, 'email': s.email}
            for s in students
        ],
    }


def get_exam_analysis(user, class_id: int, subject_id: int, exam_type: str) -> dict:
    """
    Returns average, median, highest, lowest, pass rate, toppers (top 3), and
    students below pass threshold for a given class, subject, and exam type.
    ENFORCES: teacher must teach this subject in this class.
    """
    if not (hasattr(user, 'teacher') or user.is_staff):
        return _denied("Only teachers or admins can call get_exam_analysis.")

    # Permission check — teacher must have a TeacherSubjectClass for this class and subject
    if not user.is_staff:
        from academics.models import TeacherSubjectClass
        owns = TeacherSubjectClass.objects.filter(
            teacher=user.teacher, student_class_id=class_id, subject_id=subject_id
        ).exists()
        if not owns:
            return _denied(f"You are not assigned to teach subject {subject_id} in class {class_id}.")

    from academics.models import Mark, Class
    try:
        cls = Class.objects.get(pk=class_id)
    except Class.DoesNotExist:
        return {"error": "NOT_FOUND", "detail": f"Class {class_id} does not exist."}

    marks_qs = Mark.objects.filter(
        student__student_class_id=class_id,
        subject_id=subject_id,
        exam_type=exam_type
    ).select_related('student')

    if not marks_qs.exists():
        return {
            "class_id": class_id,
            "subject_id": subject_id,
            "exam_type": exam_type,
            "message": "No marks records found for this combination."
        }

    all_percentages = [float(m.percentage) for m in marks_qs]
    avg_val = sum(all_percentages) / len(all_percentages)
    highest_val = max(all_percentages)
    lowest_val = min(all_percentages)

    sorted_p = sorted(all_percentages)
    n = len(sorted_p)
    if n % 2 == 1:
        med_val = sorted_p[n // 2]
    else:
        med_val = (sorted_p[n // 2 - 1] + sorted_p[n // 2]) / 2.0

    total_count = len(all_percentages)
    passing_count = sum(1 for m in marks_qs if m.is_pass)
    pass_rate = round(passing_count / total_count * 100, 1) if total_count > 0 else 0.0

    # Toppers (top 3)
    toppers_list = sorted(list(marks_qs), key=lambda x: float(x.marks_obtained), reverse=True)
    toppers = []
    for m in toppers_list[:3]:
        toppers.append({
            "name": m.student.name,
            "regno": m.student.regno,
            "marks_obtained": float(m.marks_obtained),
            "max_marks": float(m.max_marks),
            "percentage": float(m.percentage)
        })

    # Students below threshold
    below_threshold = [
        {"name": m.student.name, "regno": m.student.regno, "percentage": float(m.percentage)}
        for m in marks_qs if not m.is_pass
    ]

    return {
        "class_id": class_id,
        "subject_id": subject_id,
        "exam_type": exam_type,
        "average": round(avg_val, 1),
        "median": round(med_val, 1),
        "highest": round(highest_val, 1),
        "lowest": round(lowest_val, 1),
        "pass_rate": pass_rate,
        "toppers": toppers,
        "below_threshold": below_threshold
    }


def get_department_exam_comparison(user, exam_type: str) -> dict:
    """
    Compares average performance across departments for a given exam_type.
    Admin only.
    """
    if not user.is_staff:
        return _denied("Only admins can call get_department_exam_comparison.")

    from academics.models import Department, Mark
    from django.db.models import Avg

    marks_qs = Mark.objects.filter(exam_type=exam_type).select_related('student__student_class__department')
    departments = Department.objects.all()
    comparison = []

    for dept in departments:
        dept_marks = marks_qs.filter(student__student_class__department=dept)
        if dept_marks.exists():
            avg_val = sum(float(m.percentage) for m in dept_marks) / dept_marks.count()
            comparison.append({
                "department_name": dept.name,
                "department_code": dept.code,
                "average_percentage": round(avg_val, 1),
                "total_records": dept_marks.count()
            })
        else:
            comparison.append({
                "department_name": dept.name,
                "department_code": dept.code,
                "average_percentage": 0.0,
                "total_records": 0
            })

    comparison.sort(key=lambda x: x['average_percentage'], reverse=True)

    return {
        "exam_type": exam_type,
        "comparison": comparison
    }


def draft_low_attendance_notice(user, student_id: int) -> dict:
    """
    Generates a draft notification message warning about student's attendance.
    ENFORCES: teacher must teach this student's class.
    """
    if not (hasattr(user, 'teacher') or user.is_staff):
        return _denied("Only teachers or admins can draft low attendance notices.")

    from students.models import Student
    try:
        student = Student.objects.get(pk=student_id, is_active=True)
    except Student.DoesNotExist:
        return {"error": "NOT_FOUND", "detail": f"Student with ID {student_id} not found."}

    if not user.is_staff:
        from academics.models import TeacherSubjectClass
        owns = TeacherSubjectClass.objects.filter(
            teacher=user.teacher, student_class=student.student_class
        ).exists()
        if not owns:
            return _denied(f"You do not teach class {student.student_class} of student {student.name}.")

    from attendance.models import Attendance
    records = Attendance.objects.filter(student=student)
    total = records.count()
    present = records.filter(status=True).count()
    att_pct = round((present / total * 100), 1) if total > 0 else 100.0

    title = f"Low Attendance Warning: {student.name}"
    message = f"Dear {student.name}, your attendance is currently at {att_pct}%, which is below the required 75%. Please attend regular classes to avoid risk flags."

    from assistant.models import DraftActionLog
    log = DraftActionLog.objects.create(
        user=user,
        action_type='low_attendance_notice',
        status='drafted',
        details={
            "student_id": student_id,
            "student_name": student.name,
            "title": title,
            "message": message,
            "attendance_pct": att_pct
        }
    )

    return {
        "draft_id": log.pk,
        "student_id": student_id,
        "student_name": student.name,
        "title": title,
        "message": message,
        "attendance_pct": att_pct,
        "action": "propose_draft",
        "action_type": "low_attendance_notice"
    }


def draft_weekly_summary_report(user) -> dict:
    """
    Compiles current stats into a draft report. Admin only.
    """
    if not user.is_staff:
        return _denied("Only admins can compile weekly summaries.")

    # 1. AI Risk Flag count
    at_risk_count = 0
    try:
        from ai_engine.predictor import predict_risk
        all_results = predict_risk()
        at_risk_count = sum(1 for r in all_results if r['at_risk_label'] == 1)
    except Exception:
        pass

    # 2. Anomalies count from notifications (last 7 days)
    from django.utils import timezone
    from datetime import timedelta
    from notifications.models import Notification
    
    seven_days_ago = timezone.now() - timedelta(days=7)
    anomaly_count = Notification.objects.filter(
        category='anomaly',
        created_at__gte=seven_days_ago
    ).count()

    # 3. Exam averages from the Marks module
    from academics.models import Mark
    marks = Mark.objects.all()
    if marks.exists():
        avg_percentage = round(sum(float(m.percentage) for m in marks) / marks.count(), 1)
    else:
        avg_percentage = 0.0

    title = "Weekly Academic Summary Report"
    message = f"Weekly Summary: AI Risk Flags: {at_risk_count} students. Anomalies detected (last 7 days): {anomaly_count}. System exam average: {avg_percentage}%."

    from assistant.models import DraftActionLog
    log = DraftActionLog.objects.create(
        user=user,
        action_type='weekly_summary_report',
        status='drafted',
        details={
            "title": title,
            "message": message,
            "at_risk_count": at_risk_count,
            "anomaly_count": anomaly_count,
            "avg_percentage": avg_percentage
        }
    )

    return {
        "draft_id": log.pk,
        "title": title,
        "message": message,
        "at_risk_count": at_risk_count,
        "anomaly_count": anomaly_count,
        "avg_percentage": avg_percentage,
        "action": "propose_draft",
        "action_type": "weekly_summary_report"
    }


# ===========================================================================
# Tool registry — maps function name → (function, roles_allowed)
# ===========================================================================

TOOL_REGISTRY = {
    'get_my_attendance':              (get_my_attendance,              ['student']),
    'get_my_assignments':             (get_my_assignments,             ['student']),
    'get_my_grades':                  (get_my_grades,                  ['student']),
    'get_class_attendance_summary':   (get_class_attendance_summary,   ['teacher', 'admin']),
    'get_pending_submissions':        (get_pending_submissions,        ['teacher', 'admin']),
    'get_low_attendance_students':    (get_low_attendance_students,    ['teacher', 'admin']),
    'get_department_stats':           (get_department_stats,           ['admin']),
    'get_at_risk_students':           (get_at_risk_students,           ['admin']),
    'get_class_roster':               (get_class_roster,               ['admin']),
    'get_exam_analysis':              (get_exam_analysis,              ['teacher', 'admin']),
    'get_department_exam_comparison': (get_department_exam_comparison, ['admin']),
    'draft_low_attendance_notice':    (draft_low_attendance_notice,    ['teacher', 'admin']),
    'draft_weekly_summary_report':    (draft_weekly_summary_report,    ['admin']),
}


def get_user_role(user) -> str:
    if user.is_staff:
        return 'admin'
    if hasattr(user, 'teacher'):
        return 'teacher'
    if hasattr(user, 'student_profile'):
        return 'student'
    return 'unknown'


def get_tools_for_role(role: str) -> list[dict]:
    """
    Returns the OpenAI-format tool definitions for the given role.
    These are passed to the Groq API so it knows which functions to call.
    """
    tools_map = {
        'student': [
            {
                "type": "function",
                "function": {
                    "name": "get_my_attendance",
                    "description": "Get the student's own attendance percentage and per-subject breakdown.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_my_assignments",
                    "description": "Get the student's pending and upcoming assignments with submission status.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_my_grades",
                    "description": "Get the student's marks per subject with overall percentage.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ],
        'teacher': [
            {
                "type": "function",
                "function": {
                    "name": "get_class_attendance_summary",
                    "description": "Get attendance summary for a class. Only works for classes this teacher teaches.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "class_id": {"type": "integer", "description": "The database ID of the class."}
                        },
                        "required": ["class_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pending_submissions",
                    "description": "Get ungraded submissions for an assignment. Only works for assignments this teacher created.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "assignment_id": {"type": "integer", "description": "The database ID of the assignment."}
                        },
                        "required": ["assignment_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_low_attendance_students",
                    "description": "Get students below 75% attendance in a class. Only works for classes this teacher teaches.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "class_id": {"type": "integer", "description": "The database ID of the class."}
                        },
                        "required": ["class_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_exam_analysis",
                    "description": "Get analytical metrics (average, highest, lowest, median, pass rate, toppers, and students below threshold) for a specific class, subject, and exam type.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "class_id": {"type": "integer", "description": "The database ID of the class."},
                            "subject_id": {"type": "integer", "description": "The database ID of the subject."},
                            "exam_type": {"type": "string", "description": "The type of exam (choices: UT1, UT2, MID, END, INT, PRJ, LAB, OTH)."}
                        },
                        "required": ["class_id", "subject_id", "exam_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "draft_low_attendance_notice",
                    "description": "Generate a draft attendance warning message/notification warning about a student's attendance. Returns a preview only, does NOT save the notification yet.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "student_id": {"type": "integer", "description": "The database ID of the student."}
                        },
                        "required": ["student_id"],
                    },
                },
            },
        ],
        'admin': [
            {
                "type": "function",
                "function": {
                    "name": "get_department_stats",
                    "description": "Get aggregate statistics for a department including student count and subjects.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "department_id": {"type": "integer", "description": "The database ID of the department."}
                        },
                        "required": ["department_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_at_risk_students",
                    "description": "Get students predicted at-risk by the AI model. Optionally scope to a class.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "class_id": {
                                "type": "integer",
                                "description": "Optional class ID to scope results. Omit for all students."
                            }
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_class_roster",
                    "description": "Get the full list of active students in a class.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "class_id": {"type": "integer", "description": "The database ID of the class."}
                        },
                        "required": ["class_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_exam_analysis",
                    "description": "Get analytical metrics for a specific class, subject, and exam type.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "class_id": {"type": "integer", "description": "The database ID of the class."},
                            "subject_id": {"type": "integer", "description": "The database ID of the subject."},
                            "exam_type": {"type": "string", "description": "The exam type."}
                        },
                        "required": ["class_id", "subject_id", "exam_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_department_exam_comparison",
                    "description": "Compare average academic performance across different departments for a system-wide exam type.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "exam_type": {"type": "string", "description": "The type of exam."}
                        },
                        "required": ["exam_type"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "draft_low_attendance_notice",
                    "description": "Generate a draft attendance warning message/notification warning about a student's attendance. Returns a preview only, does NOT save the notification yet.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "student_id": {"type": "integer", "description": "The database ID of the student."}
                        },
                        "required": ["student_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "draft_weekly_summary_report",
                    "description": "Draft a weekly summary of system status including AI risk scores, anomalies, and grade statistics. Returns draft for approval.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
        ],
    }
    return tools_map.get(role, [])


def dispatch_tool_call(user, function_name: str, arguments: dict) -> dict:
    """
    Executes a tool function by name, always passing `user` as the first
    argument so permission checks inside each function are always enforced.

    The LLM never executes queries directly — it only calls this dispatcher.
    """
    if function_name not in TOOL_REGISTRY:
        return {"error": "UNKNOWN_TOOL", "detail": f"Tool '{function_name}' does not exist."}

    fn, allowed_roles = TOOL_REGISTRY[function_name]
    user_role = get_user_role(user)

    # Belt-and-suspenders: double-check role even if LLM somehow smuggled a
    # cross-role tool call
    if user_role not in allowed_roles:
        return _denied(
            f"Tool '{function_name}' is not available for role '{user_role}'. "
            f"Allowed roles: {allowed_roles}."
        )

    return fn(user, **arguments)
