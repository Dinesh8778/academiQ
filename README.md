# AI Student Management System

## Overview

The **AI Student Management System** is a web-based platform designed to digitize and automate common academic operations in educational institutions. Many colleges still rely on manual registers, spreadsheets, and disconnected tools to manage students, attendance, and assignments. This project aims to centralize these processes into a single system.

The platform allows administrators and teachers to manage students, classes, subjects, attendance, and assignments efficiently. Students are organised by **class groups (Department + Year)**, allowing teachers to distribute assignments and manage attendance for an entire class at once, similar to systems like Google Classroom.

---

## Problem Statement

Educational institutions often face:

* Attendance maintained in paper registers
* Student records stored in scattered spreadsheets
* Difficulty tracking academic performance
* No centralised system for assignments and submissions
* Limited data analysis on student performance

---

## Solution

A centralised Django platform covering:

* Student record management and CRUD
* Class-based grouping of students
* Teacher and subject management
* Attendance tracking with bulk-mark support
* Assignment distribution to entire classes
* Report card and attendance percentage views
* REST API with JWT authentication
* Auto-generated Swagger / OpenAPI documentation
* Future: AI-based performance prediction (ai-module placeholder)

---

## System Architecture

```
Browser (Bootstrap 5 templates)
        ↕  session auth
Django backend  ←→  SQLite (dev) / PostgreSQL (prod)
        ↕  JWT
DRF REST API  →  drf-spectacular Swagger UI
```

---

## Project Structure

```
ai-student-management-system/
│
├── backend/
│   └── college_ai/                 ← Django project root
│       ├── college_ai/             ← Settings, root urls, wsgi
│       ├── users/                  ← Teacher model, auth views, permissions
│       ├── students/               ← Student model, CRUD views
│       ├── academics/              ← Department, Subject, Class, Assignment,
│       │                             Submission, Mark, TeacherSubjectClass
│       ├── attendance/             ← Attendance model + bulk-mark endpoint
│       ├── templates/              ← All Django templates (Bootstrap 5)
│       │   ├── base.html
│       │   ├── auth/
│       │   ├── dashboard/
│       │   ├── academics/
│       │   └── students/
│       └── static/                 ← Project-level static files
│
├── ai-module/                      ← Placeholder for ML scripts (future)
├── docs/                           ← Architecture docs (future)
├── requirements.txt
└── README.md
```

> **Note:** There is no top-level `frontend/` directory. All templates live inside
> `backend/college_ai/templates/` and are served directly by Django.
> `TEMPLATES['DIRS']` and `STATICFILES_DIRS` both point inside `backend/college_ai/`.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, Django 5.x |
| REST API | Django REST Framework 3.16, drf-spectacular (Swagger) |
| Auth | Django session auth + JWT (djangorestframework-simplejwt) |
| Frontend | Django templates + Bootstrap 5 (CDN) |
| Database | SQLite (dev), PostgreSQL (prod-ready) |
| ML / AI | scikit-learn, pandas, numpy (installed, future use) |

---

## Installation

```bash
# Clone
git clone https://github.com/yourusername/ai-student-management-system.git
cd ai-student-management-system

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
cd backend/college_ai
cp .env.example .env
# Edit .env — set SECRET_KEY, DEBUG=True, ALLOWED_HOSTS=127.0.0.1,localhost

# Apply migrations
python manage.py migrate

# Create test users (admin + teacher + student)
python manage.py create_test_users

# Run the server
python manage.py runserver
```

Open **http://127.0.0.1:8000/** — redirects to login automatically.

### Default test credentials

| Username | Password | Role |
|---|---|---|
| admin_test | Admin@1234 | Admin |
| teacher_test | Teacher@1234 | Teacher |
| student_test | Student@1234 | Student |

---

## Key URLs

| URL | Description |
|---|---|
| `/` | Redirects to dashboard or login |
| `/auth/login/` | Login page |
| `/auth/dashboard/` | Role-based dashboard redirect |
| `/manage/students/` | Student list (admin/teacher) |
| `/manage/classes/` | Class management (admin) |
| `/manage/subjects/` | Subject management (admin) |
| `/manage/departments/` | Department management (admin) |
| `/teacher/attendance/mark/` | Bulk attendance marking |
| `/teacher/assignments/create/` | Create assignment |
| `/api/docs/` | Swagger UI (all 36 REST endpoints) |
| `/admin/` | Django admin panel |

---

## Running Tests

```bash
cd backend/college_ai
python -m pytest tests/ -v
```

36 tests covering permissions, bulk attendance, report card calculation.

---

## Future Enhancements

* AI-based student performance prediction (ai-module/)
* Risk detection for low-performing students
* Automated attendance analytics dashboard
* PostgreSQL + Docker deployment
* CI/CD pipeline

---

## License

This project is created for educational and academic purposes.
