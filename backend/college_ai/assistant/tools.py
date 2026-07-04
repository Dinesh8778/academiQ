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


# ===========================================================================
# Tool registry — maps function name → (function, roles_allowed)
# ===========================================================================

TOOL_REGISTRY = {
    'get_my_attendance':             (get_my_attendance,             ['student']),
    'get_my_assignments':            (get_my_assignments,            ['student']),
    'get_my_grades':                 (get_my_grades,                 ['student']),
    'get_class_attendance_summary':  (get_class_attendance_summary,  ['teacher', 'admin']),
    'get_pending_submissions':       (get_pending_submissions,       ['teacher', 'admin']),
    'get_low_attendance_students':   (get_low_attendance_students,   ['teacher', 'admin']),
    'get_department_stats':          (get_department_stats,          ['admin']),
    'get_at_risk_students':          (get_at_risk_students,          ['admin']),
    'get_class_roster':              (get_class_roster,              ['admin']),
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
