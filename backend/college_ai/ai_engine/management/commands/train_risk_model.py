"""
Management command: train_risk_model

Runs the full AI training pipeline and saves the model to
ai_engine/models/risk_model.joblib.

Usage:
    python manage.py train_risk_model
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Train the student risk prediction model and save it to disk."

    def handle(self, *args, **options):
        from ai_engine.train_model import train
        try:
            result = train(verbose=True)
            self.stdout.write(self.style.SUCCESS(
                f"\n✓ Training complete. Model saved to: {result['model_path']}"
            ))
            self.stdout.write(f"  Samples: {result['n_samples']} "
                              f"| At-risk: {result['n_at_risk']}")
            self.stdout.write(f"  Accuracy : {result['accuracy']}")
            self.stdout.write(f"  Precision: {result['precision']}")
            self.stdout.write(f"  Recall   : {result['recall']}")
            self.stdout.write(f"  F1       : {result['f1']}")
        except ValueError as e:
            self.stderr.write(self.style.ERROR(str(e)))
