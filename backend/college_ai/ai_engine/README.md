# AI Engine — Student Risk Prediction Module

## Location

This module lives at `backend/college_ai/ai_engine/` as a Django app.
The top-level `ai-module/` folder in the project root is an empty placeholder
and is **not used** by Django.

---

## What the Model Does

The AI engine predicts whether a student is **at risk of poor academic
performance** based on five engineered features derived from live ORM data:

| Feature | Description |
|---|---|
| `attendance_percentage` | Overall attendance rate (0–100) |
| `average_marks` | Weighted average marks as % of max marks (0–100) |
| `late_or_missed_submission_rate` | Fraction of assignments not submitted (0–1) |
| `attendance_trend` | Attendance change: last 30 days vs prior 30 days (pp) |
| `grade_trend` | Score change: most recent exam vs second-most-recent exam |

The model outputs:
- `at_risk_label` — binary (0 = not at risk, 1 = at risk)
- `risk_score` — probability of being at risk (0.0–1.0)

---

## ⚠️ Label Derivation — READ CAREFULLY

**The ground-truth labels used to train this model are RULE-DERIVED,
not from real historical academic outcome data.**

The rule is:

```python
at_risk = (
    attendance_percentage < 75
    OR average_marks < 40
    OR late_or_missed_submission_rate > 0.30
)
```

This means the model is essentially learning to replicate a rule.
It does **not** predict whether a student will actually fail, drop out,
or struggle — because no such historical outcome data exists in this system.

**Do not use this model's output to make real academic decisions
without expert validation and real outcome data.**

---

## Model Choice — RandomForestClassifier

**Why RandomForest over Logistic Regression:**
- Handles small datasets without requiring linear separability assumptions
- Robust to correlated features (`attendance_percentage` and `average_marks` correlate)
- Provides feature importance scores for interpretability
- `class_weight='balanced'` handles the natural imbalance (more at-risk students)
- `max_depth=4` limits overfitting on small datasets

**Hyperparameters used:**
```python
RandomForestClassifier(
    n_estimators=100,
    max_depth=4,
    class_weight='balanced',
    random_state=42,
)
```

Wrapped in a `sklearn.pipeline.Pipeline` with `StandardScaler`.

---

## Training Output (Current Run)

```
Total students : 31
At-risk        : 24 / 31

Accuracy  : 1.0000
Precision : 1.0000
Recall    : 1.0000
F1 Score  : 1.0000

Classification Report:
              precision  recall  f1-score  support
           0    1.00     1.00      1.00        2
           1    1.00     1.00      1.00        6
    accuracy                       1.00        8

Feature Importances:
  late_or_missed_submission_rate    0.4748
  average_marks                     0.3088
  attendance_percentage             0.1630
  grade_trend                       0.0534
  attendance_trend                  0.0000
```

---

## ⚠️ Known Limitations

| Limitation | Detail |
|---|---|
| **Perfect accuracy is suspicious** | Accuracy = 1.0 on a small test set with rule-derived labels means the model learned the rule perfectly — not that it generalises to real outcomes. This is expected and honest. |
| **Tiny dataset** | 31 students, 8-sample test split. No statistical significance. Metrics are illustrative only. |
| **Rule-derived ground truth** | Labels come from a rule, not real failure/dropout data. The model predicts the rule, not the future. |
| **No temporal validation** | No time-based train/test split. Model has not been tested on future cohorts. |
| **`attendance_trend` = 0.0 importance** | With only 30 days of synthetic data, trend features have low variance and low predictive value. |
| **Production readiness** | This module is a **demonstration**. Before any production use: collect real outcome data, validate on holdout cohorts, involve academic experts, and perform ethical review. |

---

## File Structure

```
ai_engine/
├── __init__.py
├── apps.py
├── data_pipeline.py          # Feature engineering from ORM
├── train_model.py            # Training pipeline
├── predictor.py              # Inference (load model + predict)
├── views.py                  # DRF API views
├── urls.py                   # URL routing
├── README.md                 # This file
├── models/
│   └── risk_model.joblib     # Serialized trained pipeline
└── management/
    └── commands/
        ├── seed_ai_data.py       # Generate synthetic training data
        └── train_risk_model.py   # Run training
```

---

## Usage

```bash
# 1. Generate synthetic training data (30 students, 3 risk profiles)
python manage.py seed_ai_data

# 2. Train the model
python manage.py train_risk_model

# 3. Access predictions via API
GET /api/ai/risk-scores/              # all students
GET /api/ai/risk-scores/<class_id>/   # scoped to one class
```

Access requires **Teacher** or **Admin** role. Students cannot access this endpoint.

---

## API Response Shape

```json
{
  "model_available": true,
  "total_students": 31,
  "at_risk_count": 24,
  "class_id": null,
  "disclaimer": "Labels are rule-derived...",
  "results": [
    {
      "student_id": 5,
      "regno": "SEEDAT001",
      "name": "Seed At Risk 1",
      "at_risk_label": 1,
      "risk_score": 0.97,
      "rule_label": 1,
      "features": {
        "attendance_percentage": 52.3,
        "average_marks": 28.1,
        "late_or_missed_submission_rate": 0.67,
        "attendance_trend": -3.2,
        "grade_trend": -5.4
      }
    }
  ]
}
```

Results are sorted by `risk_score` descending (highest risk first).
