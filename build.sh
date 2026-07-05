#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
python manage.py create_test_users
python manage.py seed_ai_data
python manage.py train_risk_model
