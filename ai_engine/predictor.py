"""
ai_engine/predictor.py
======================
Loads the saved model and runs inference on current ORM data.
Separated from views so it can be called from management commands and tests.
"""

import os
import numpy as np
import pandas as pd


def load_model():
    """Load the serialized pipeline from disk. Raises FileNotFoundError if missing."""
    from django.conf import settings
    import joblib
    model_path = settings.AI_ENGINE_MODEL_PATH
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"Risk model not found at {model_path}. "
            "Run: python manage.py seed_ai_data && python manage.py train_risk_model"
        )
    return joblib.load(model_path)


def predict_risk(class_id: int = None) -> list[dict]:
    """
    Run the trained model on current data and return a list of dicts.

    Each dict:
        student_id, regno, name,
        at_risk_label (0/1),
        risk_score (float 0–1, probability of being at-risk),
        features (dict of raw feature values)

    Parameters
    ----------
    class_id : int or None
        Scope to a single class if provided.
    """
    from ai_engine.data_pipeline import build_student_features, FEATURE_COLUMNS

    df = build_student_features(class_id=class_id)
    if df.empty:
        return []

    pipeline = load_model()
    X = df[FEATURE_COLUMNS].values
    labels = pipeline.predict(X)
    probas = pipeline.predict_proba(X)

    # index 1 = probability of class 1 (at_risk)
    risk_scores = probas[:, 1]

    results = []
    for i, row in df.iterrows():
        results.append({
            'student_id': int(row['student_id']),
            'regno': row['regno'],
            'name': row['name'],
            'at_risk_label': int(labels[i]),
            'risk_score': round(float(risk_scores[i]), 4),
            'rule_label': int(row['at_risk']),  # ground-truth rule for reference
            'features': {
                'attendance_percentage': row['attendance_percentage'],
                'average_marks': row['average_marks'],
                'late_or_missed_submission_rate': row['late_or_missed_submission_rate'],
                'attendance_trend': row['attendance_trend'],
                'grade_trend': row['grade_trend'],
            },
        })

    # Sort by risk score descending (highest risk first)
    results.sort(key=lambda x: x['risk_score'], reverse=True)
    return results
