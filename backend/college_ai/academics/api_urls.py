from rest_framework.routers import DefaultRouter
from .views import (
    DepartmentViewSet, SubjectViewSet, ClassViewSet,
    TeacherSubjectClassViewSet, AssignmentViewSet,
    SubmissionViewSet, MarkViewSet,
)

router = DefaultRouter()
router.register(r'departments',           DepartmentViewSet,        basename='department')
router.register(r'subjects',              SubjectViewSet,           basename='subject')
router.register(r'classes',               ClassViewSet,             basename='class')
router.register(r'teacher-subject-class', TeacherSubjectClassViewSet, basename='teachersubjectclass')
router.register(r'assignments',           AssignmentViewSet,        basename='assignment')
router.register(r'submissions',           SubmissionViewSet,        basename='submission')
router.register(r'marks',                 MarkViewSet,              basename='mark')

urlpatterns = router.urls
