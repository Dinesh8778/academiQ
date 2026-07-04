"""
ai_engine/train_model.py
========================
Trains a RandomForestClassifier on rule-derived risk labels from ORM data.

MODEL CHOICE: RandomForestClassifier
  Justification: handles small/imbalanced datasets better than Logistic
  Regression (no assumption of linear separability), is robust to correlated
  features (attendance_percentage and average_marks often correlate), and
  provides feature importance scores for interpretability. Its main downside
  is reduced interpretability compared to Logistic Regression, but the
  feature importance output mitigates this.

USAGE:
  python manage.py shell -c "from ai_engine.train_model import train; train()"
  OR
  python manage.py train_risk_model    (management command)

⚠️  Labels are rule-derived (see data_pipeline.py). The model learns the rule,
not real historical outcomes. See ai_engine/README.md.
"""

import os
import sys
import numpy as np
import pandas as pd


def train(verbose: bool = True) -> dict:
    """
    Run the full training pipeline.

    Returns a dict with keys:
        model_path, accuracy, precision, recall, f1,
        n_samples, n_at_risk, feature_importances
    """
    import django
    # Django setup is handled by manage.py; safe to call again idempotently
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'college_ai.settings')

    from django.conf import settings
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import train_test_split, StratifiedKFold, cross_validate
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        classification_report,
    )
    import joblib

    from ai_engine.data_pipeline import build_student_features, FEATURE_COLUMNS, LABEL_COLUMN

    # ------------------------------------------------------------------
    # 1. Build dataset
    # ------------------------------------------------------------------
    if verbose:
        print("Building feature dataset from ORM...")

    df = build_student_features()

    if verbose:
        print(f"  Total students: {len(df)}")
        if len(df) > 0:
            print(f"  At-risk: {df[LABEL_COLUMN].sum()} / {len(df)}")
            print(f"\nFeature summary:\n{df[FEATURE_COLUMNS].describe().round(2)}")

    if len(df) < 2:
        raise ValueError(
            "Not enough student data to train (need ≥ 2 students). "
            "Run `python manage.py seed_ai_data` to generate synthetic data, "
            "or add real students first."
        )

    X = df[FEATURE_COLUMNS].values
    y = df[LABEL_COLUMN].values

    # ------------------------------------------------------------------
    # 2. Split — use stratify when both classes exist
    # ------------------------------------------------------------------
    unique_classes = np.unique(y)
    can_stratify = len(unique_classes) >= 2 and min(np.bincount(y)) >= 2

    if len(df) >= 10 and can_stratify:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=42, stratify=y
        )
    else:
        # Too few samples for a proper split; train on all, evaluate on all
        # (honest about this limitation in the report)
        X_train, X_test, y_train, y_test = X, X, y, y
        if verbose:
            print(
                "\n⚠️  Dataset too small for a held-out test split "
                f"(n={len(df)}). Evaluating on training data — "
                "metrics will be optimistic. See README.md."
            )

    # ------------------------------------------------------------------
    # 3. Pipeline: scaler + classifier
    # ------------------------------------------------------------------
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('clf', RandomForestClassifier(
            n_estimators=100,
            max_depth=4,           # shallow trees → less overfitting on small data
            min_samples_leaf=1,
            class_weight='balanced',  # handle class imbalance
            random_state=42,
        )),
    ])

    pipeline.fit(X_train, y_train)
    y_pred = pipeline.predict(X_test)

    # ------------------------------------------------------------------
    # 4. Metrics
    # ------------------------------------------------------------------
    accuracy = accuracy_score(y_test, y_pred)
    # Use zero_division=0 to handle cases where a class has no predictions
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)

    feat_imp = dict(zip(
        FEATURE_COLUMNS,
        pipeline.named_steps['clf'].feature_importances_.round(4).tolist()
    ))

    if verbose:
        print("\n" + "=" * 50)
        print("MODEL EVALUATION")
        print("=" * 50)
        print(f"  Accuracy : {accuracy:.4f}")
        print(f"  Precision: {precision:.4f}")
        print(f"  Recall   : {recall:.4f}")
        print(f"  F1 Score : {f1:.4f}")
        print(f"\nClassification Report:\n{classification_report(y_test, y_pred, zero_division=0)}")
        print(f"\nFeature Importances:")
        for feat, imp in sorted(feat_imp.items(), key=lambda x: -x[1]):
            print(f"  {feat:<42} {imp:.4f}")

    # ------------------------------------------------------------------
    # 5. Save model
    # ------------------------------------------------------------------
    model_path = settings.AI_ENGINE_MODEL_PATH
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(pipeline, model_path)

    if verbose:
        print(f"\n✓ Model saved to: {model_path}")
        print("=" * 50)

    return {
        'model_path': str(model_path),
        'n_samples': len(df),
        'n_at_risk': int(df[LABEL_COLUMN].sum()),
        'accuracy': round(accuracy, 4),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4),
        'feature_importances': feat_imp,
    }


if __name__ == '__main__':
    train()
