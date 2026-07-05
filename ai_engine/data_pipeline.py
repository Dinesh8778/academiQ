"""
ai_engine/data_pipeline.py
==========================
Builds a feature DataFrame from the Django ORM for the student risk model.

Each row represents one student with the following engineered features:

  attendance_percentage        float  0–100
  average_marks                float  0–100  (percentage of max marks)
  late_or_missed_submission_rate float  0–1   (fraction of assignments not submitted)
  attendance_trend             float  -1 to +1  (positive = improving)
  grade_trend                  float  -100 to +100  (positive = improving)

LABEL DERIVATION
----------------
The binary label `at_risk` (1 = at risk, 0 = not at risk) is defined by an
explicit rule:

    at_risk = (
        attendance_percentage < 75
        OR average_marks < 40
        OR late_or_missed_submission_rate > 0.30
    )

⚠️  WARNING: These labels are RULE-DERIVED, not from real historical outcomes
(e.g., actual failure/dropout data). The model learns to replicate the rule,
not to predict genuine future academic outcomes. See ai_engine/README.md for
full limitations disclosure.
"""

import django
import os
import sys
import pandas as pd
import numpy as np
from datetime import date, timedelta


def build_student_features(class_id: int = None) -> pd.DataFrame:
    """
    Query the ORM and return a DataFrame of engineered features + risk label.

    Parameters
    ----------
    class_id : int or None
        If given, restrict to students in that class.
        If None, include all active students.

    Returns
    -------
    pd.DataFrame with columns:
        student_id, regno, name,
        attendance_percentage, average_marks,
        late_or_missed_submission_rate,
        attendance_trend, grade_trend,
        at_risk (int 0/1)
    """
    from students.models import Student
    from attendance.models import Attendance
    from academics.models import Mark, Submission, Assignment

    qs = Student.objects.filter(is_active=True).select_related('student_class')
    if class_id is not None:
        qs = qs.filter(student_class_id=class_id)

    today = date.today()
    last_30_start = today - timedelta(days=30)
    prev_30_start = today - timedelta(days=60)

    rows = []
    for student in qs:
        # ------------------------------------------------------------------
        # 1. Attendance percentage (all-time)
        # ------------------------------------------------------------------
        att_qs = Attendance.objects.filter(student=student)
        total_att = att_qs.count()
        present_att = att_qs.filter(status=True).count()
        att_pct = (present_att / total_att * 100) if total_att > 0 else 100.0

        # ------------------------------------------------------------------
        # 2. Average marks (as percentage of max_marks)
        # ------------------------------------------------------------------
        marks_qs = Mark.objects.filter(student=student)
        if marks_qs.exists():
            total_obtained = sum(float(m.marks_obtained) for m in marks_qs)
            total_max = sum(float(m.max_marks) for m in marks_qs)
            avg_marks = (total_obtained / total_max * 100) if total_max > 0 else 0.0
        else:
            # No marks recorded → use neutral value; treated as not-at-risk
            # for this feature alone
            avg_marks = 100.0

        # ------------------------------------------------------------------
        # 3. Late / missed submission rate
        #    = (assignments with no file submitted) / (all assignments for class)
        # ------------------------------------------------------------------
        total_assignments = Assignment.objects.filter(
            student_class=student.student_class
        ).count()
        submitted = Submission.objects.filter(
            student=student,
            file__isnull=False,
        ).exclude(file='').count()
        if total_assignments > 0:
            missed_rate = max(0.0, (total_assignments - submitted) / total_assignments)
        else:
            missed_rate = 0.0

        # ------------------------------------------------------------------
        # 4. Attendance trend  (last 30 days vs prior 30 days)
        #    Positive → improving, Negative → declining, 0 → stable/no data
        # ------------------------------------------------------------------
        last_30 = att_qs.filter(date__gte=last_30_start)
        prev_30 = att_qs.filter(date__gte=prev_30_start, date__lt=last_30_start)

        def _pct(qs_window):
            t = qs_window.count()
            p = qs_window.filter(status=True).count()
            return (p / t * 100) if t > 0 else None

        last_30_pct = _pct(last_30)
        prev_30_pct = _pct(prev_30)

        if last_30_pct is not None and prev_30_pct is not None:
            att_trend = last_30_pct - prev_30_pct   # e.g. +10 = improved 10 pp
        elif last_30_pct is not None:
            att_trend = 0.0   # no prior data to compare
        else:
            att_trend = 0.0

        # ------------------------------------------------------------------
        # 5. Grade trend  (most recent exam vs second-most-recent exam)
        #    Uses percentage scores sorted by date
        # ------------------------------------------------------------------
        marks_ordered = list(
            marks_qs.order_by('-date').values('marks_obtained', 'max_marks')[:2]
        )
        if len(marks_ordered) >= 2:
            def _mark_pct(m):
                return (float(m['marks_obtained']) / float(m['max_marks']) * 100
                        if float(m['max_marks']) > 0 else 0)
            grade_trend = _mark_pct(marks_ordered[0]) - _mark_pct(marks_ordered[1])
        else:
            grade_trend = 0.0

        # ------------------------------------------------------------------
        # 6. Risk label  (rule-derived — see module docstring)
        # ------------------------------------------------------------------
        at_risk = int(
            att_pct < 75
            or avg_marks < 40
            or missed_rate > 0.30
        )

        rows.append({
            'student_id': student.pk,
            'regno': student.regno,
            'name': student.name,
            'attendance_percentage': round(att_pct, 4),
            'average_marks': round(avg_marks, 4),
            'late_or_missed_submission_rate': round(missed_rate, 4),
            'attendance_trend': round(att_trend, 4),
            'grade_trend': round(grade_trend, 4),
            'at_risk': at_risk,
        })

    return pd.DataFrame(rows)


# Feature columns used for model training and inference
FEATURE_COLUMNS = [
    'attendance_percentage',
    'average_marks',
    'late_or_missed_submission_rate',
    'attendance_trend',
    'grade_trend',
]
LABEL_COLUMN = 'at_risk'
