# Automated Anomaly Detection & Notifications

This module performs automated rule-based anomaly detection across the system and sends alerts to teachers and system administrators.

## Anomaly Detection Rules

The detection script (`python manage.py detect_anomalies`) executes the following checks daily:
1. **Attendance Drop**: Any student whose attendance dropped by more than 20 percentage points in the last 2 weeks vs. the 2 weeks prior. (Category: `attendance_alert`, Related Object: `Student`)
2. **Low Class Attendance**: Any class where average student attendance is below 50% for the current week. (Category: `attendance_alert`, Related Object: `Class`)
3. **Missing Class/Subject Attendance**: Any active `TeacherSubjectClass` assignment where no attendance has been marked for 3+ consecutive class weekdays. (Category: `attendance_alert`, Related Object: `TeacherSubjectClass`)
4. **Consecutive Missed/Late Submissions**: Any student with 3 or more consecutive missed or late assignment submissions. (Category: `anomaly`, Related Object: `Student`)

---

## Scheduling the Command

To running detection automatically on a schedule, set up one of the options below.

### 1. Windows (Local Development & Windows Server)
Use **Windows Task Scheduler** to run a daily task:
*   **Program/script**: `powershell.exe`
*   **Arguments** (assuming the project is at `C:\Users\user\Documents\Project\PROJECTS\ai-student-management-system`):
    ```powershell
    -ExecutionPolicy Bypass -Command "& 'C:\Users\user\Documents\Project\PROJECTS\ai-student-management-system\venv\Scripts\python.exe' 'C:\Users\user\Documents\Project\PROJECTS\ai-student-management-system\manage.py' detect_anomalies"
    ```
*   **Start in** (Optional): `C:\Users\user\Documents\Project\PROJECTS\ai-student-management-system`
*   **Trigger**: Daily at 01:00 AM.

Alternatively, via Command Prompt (Admin):
```cmd
schtasks /create /tn "AI_Student_Management_Anomaly_Detection" /tr "C:\Users\user\Documents\Project\PROJECTS\ai-student-management-system\venv\Scripts\python.exe C:\Users\user\Documents\Project\PROJECTS\ai-student-management-system\manage.py detect_anomalies" /sc daily /st 01:00
```

### 2. Linux (Production environments)
Add a crontab entry for the web user:
```bash
0 1 * * * /home/user/project/venv/bin/python /home/user/project/manage.py detect_anomalies >> /home/user/project/logs/anomalies.log 2>&1
```

### 3. Future Upgrade Path: Celery Beat
If the project later incorporates Celery for async web tasks:
1. Install `django-celery-beat`.
2. Configure Celery Beat schedules in `college_ai/settings.py` or via Django Admin:
    ```python
    CELERY_BEAT_SCHEDULE = {
        'detect-anomalies-daily': {
            'task': 'notifications.tasks.run_anomaly_detection',
            'schedule': crontab(hour=1, minute=0),
        },
    }
    ```
3. Use a simple Celery task wrapper calling management commands:
    ```python
    from celery import shared_task
    from django.core.management import call_command

    @shared_task
    def run_anomaly_detection():
        call_command('detect_anomalies')
    ```
