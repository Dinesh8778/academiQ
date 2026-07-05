from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

# Home redirect & Teacher UI Views
from users.views import home_redirect, TeacherListView, TeacherEditView, TeacherDeleteView

# UI views
from academics.views_ui import (
    DepartmentListView, DepartmentEditView, DepartmentDeleteView,
    SubjectListView, SubjectEditView, SubjectDeleteView,
    ClassListView, ClassEditView, ClassDeleteView,
    AssignmentCreateView, AttendanceMarkView,
    TeacherSubjectClassListView, TeacherSubjectClassDeleteView,
    AssignmentListView, AssignmentEditView, AssignmentDeleteView,
    AttendanceListView, AttendanceDeleteView,
    MarksBulkCreateView, MarksListView, MarksEditView, MarksDeleteView,
    StudentAssignmentSubmitView, TeacherAssignmentSubmissionsView,
)
from students.views_ui import (
    StudentListView, StudentCreateView, StudentEditView, StudentDeleteView,
)

from notifications.views import SendDraftNotificationView

urlpatterns = [
    # Root — redirect by auth state
    path('', home_redirect, name='home'),

    # Django admin
    path('admin/', admin.site.urls),

    # Browser auth + dashboards
    path('auth/', include('users.urls')),

    # ---- Admin CRUD: Departments ----
    path('manage/departments/',             DepartmentListView.as_view(),   name='department_list'),
    path('manage/departments/<int:pk>/edit/', DepartmentEditView.as_view(), name='department_edit'),
    path('manage/departments/<int:pk>/delete/', DepartmentDeleteView.as_view(), name='department_delete'),

    # ---- Admin CRUD: Subjects ----
    path('manage/subjects/',               SubjectListView.as_view(),       name='subject_list'),
    path('manage/subjects/<int:pk>/edit/', SubjectEditView.as_view(),       name='subject_edit'),
    path('manage/subjects/<int:pk>/delete/', SubjectDeleteView.as_view(),   name='subject_delete'),

    # ---- Admin CRUD: Classes ----
    path('manage/classes/',               ClassListView.as_view(),          name='class_list'),
    path('manage/classes/assignments/',   TeacherSubjectClassListView.as_view(), name='teacher_subject_class_list'),
    path('manage/classes/assignments/<int:pk>/delete/', TeacherSubjectClassDeleteView.as_view(), name='teacher_subject_class_delete'),
    path('manage/classes/<int:pk>/edit/', ClassEditView.as_view(),          name='class_edit'),
    path('manage/classes/<int:pk>/delete/', ClassDeleteView.as_view(),      name='class_delete'),

    # ---- Admin/Teacher CRUD: Students ----
    path('manage/students/',                  StudentListView.as_view(),    name='student_list'),
    path('manage/students/create/',           StudentCreateView.as_view(),  name='student_create'),
    path('manage/students/<int:pk>/edit/',    StudentEditView.as_view(),    name='student_edit'),
    path('manage/students/<int:pk>/delete/',  StudentDeleteView.as_view(),  name='student_delete'),

    # ---- Admin CRUD: Teachers ----
    path('manage/teachers/',                  TeacherListView.as_view(),    name='teacher_list'),
    path('manage/teachers/<int:pk>/edit/',    TeacherEditView.as_view(),    name='teacher_edit'),
    path('manage/teachers/<int:pk>/delete/',  TeacherDeleteView.as_view(),  name='teacher_delete'),

    # ---- Admin/Teacher: Assignments ----
    path('manage/assignments/',               AssignmentListView.as_view(),   name='assignment_list'),
    path('manage/assignments/<int:pk>/edit/', AssignmentEditView.as_view(),   name='assignment_edit'),
    path('manage/assignments/<int:pk>/delete/', AssignmentDeleteView.as_view(), name='assignment_delete'),

    # ---- Admin/Teacher: Attendance ----
    path('manage/attendance/',                AttendanceListView.as_view(),   name='attendance_list'),
    path('manage/attendance/<int:pk>/delete/', AttendanceDeleteView.as_view(), name='attendance_delete'),

    # ---- Admin/Teacher: Marks ----
    path('manage/marks/',                     MarksListView.as_view(),        name='marks_list'),
    path('manage/marks/add/',                 MarksBulkCreateView.as_view(),  name='marks_bulk_add'),
    path('manage/marks/<int:pk>/edit/',       MarksEditView.as_view(),        name='marks_edit'),
    path('manage/marks/<int:pk>/delete/',     MarksDeleteView.as_view(),      name='marks_delete'),

    # ---- Teacher: Assignments + Attendance (Actions) ----
    path('teacher/assignments/create/', AssignmentCreateView.as_view(), name='assignment_create'),
    path('teacher/attendance/mark/',    AttendanceMarkView.as_view(),   name='attendance_mark'),
    path('student/assignments/<int:pk>/submit/', StudentAssignmentSubmitView.as_view(), name='student_assignment_submit'),
    path('teacher/assignments/<int:pk>/submissions/', TeacherAssignmentSubmissionsView.as_view(), name='teacher_assignment_submissions'),

    # ---- API Auth ----
    path('api/auth/', include('users.api_urls')),

    # ---- API Resources ----
    path('api/', include('users.teacher_api_urls')),
    path('api/', include('students.api_urls')),
    path('api/', include('academics.api_urls')),
    path('api/', include('attendance.api_urls')),

    # ---- API AI Engine ----
    path('api/ai/', include('ai_engine.urls')),

    # ---- API Assistant (Groq) ----
    path('api/assistant/', include('assistant.urls')),

    # ---- Notifications ----
    path('api/notifications/send-draft/', SendDraftNotificationView.as_view(), name='send_draft_notification'),
    path('notifications/', include('notifications.urls')),

    # ---- API Docs ----
    path('api/schema/',      SpectacularAPIView.as_view(),                          name='schema'),
    path('api/docs/',        SpectacularSwaggerView.as_view(url_name='schema'),     name='swagger-ui'),
    path('api/docs/redoc/',  SpectacularRedocView.as_view(url_name='schema'),       name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
