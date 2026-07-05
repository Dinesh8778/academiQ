from django.shortcuts import redirect, get_object_or_404
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.contrib import messages
from .models import Notification

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from assistant.models import DraftActionLog
from students.models import Student
from academics.models import TeacherSubjectClass

@method_decorator(login_required, name='dispatch')
class MarkNotificationReadView(View):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notification.is_read = True
        notification.save()
        messages.success(request, "Notification marked as read.")
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'dashboard'
        return redirect(next_url)


class SendDraftNotificationView(APIView):
    """
    POST /api/notifications/send-draft/
    
    Accepts:
    {
      "draft_id": 123,
      "action": "confirm" | "discard"
    }
    
    Creates actual Notification warning or weekly stats notification.
    Re-validates permissions independently of Groq.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        draft_id = request.data.get('draft_id')
        action = request.data.get('action')

        if not draft_id or not action:
            return Response(
                {"detail": "Both draft_id and action parameters are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if action not in ['confirm', 'discard']:
            return Response(
                {"detail": "Action must be either 'confirm' or 'discard'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Fetch DraftActionLog
        draft_log = get_object_or_404(DraftActionLog, pk=draft_id)

        # 2. Check draft belongs to current user
        if draft_log.user != request.user and not request.user.is_staff:
            return Response(
                {"detail": "You do not have permission to modify this draft."},
                status=status.HTTP_403_FORBIDDEN
            )

        if draft_log.status != 'drafted':
            return Response(
                {"detail": f"This draft action has already been {draft_log.status}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if action == 'discard':
            draft_log.status = 'discarded'
            draft_log.save()
            return Response({"status": "discarded", "message": "Draft discarded successfully."})

        # 3. Action is confirm. Direct/Recheck permissions per action type.
        if draft_log.action_type == 'low_attendance_notice':
            student_id = draft_log.details.get('student_id')
            title = draft_log.details.get('title')
            message = draft_log.details.get('message')

            if not student_id or not title or not message:
                return Response(
                    {"detail": "Missing draft details for student notification."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Re-fetch student to verify existence and class assignment
            try:
                student = Student.objects.get(pk=student_id, is_active=True)
            except Student.DoesNotExist:
                return Response(
                    {"detail": f"Student with ID {student_id} not found."},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Independent validation: teacher can only send to their own students
            if not request.user.is_staff:
                if not hasattr(request.user, 'teacher'):
                    return Response(
                        {"detail": "Only teachers can send attendance warnings to students."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                owns = TeacherSubjectClass.objects.filter(
                    teacher=request.user.teacher,
                    student_class=student.student_class
                ).exists()
                if not owns:
                    return Response(
                        {"detail": "Permission denied. You do not teach this student's class."},
                        status=status.HTTP_403_FORBIDDEN
                    )

            # Create notification (sent to student's user account)
            recipient = student.user
            if not recipient:
                # Fallback to current user if student has no user account, but let's notify the sender
                recipient = request.user

            Notification.objects.create(
                recipient=recipient,
                title=title,
                message=message,
                category='attendance_alert'
            )

            draft_log.status = 'confirmed'
            draft_log.save()

            return Response({"status": "confirmed", "message": "Attendance alert notification sent successfully."})

        elif draft_log.action_type == 'weekly_summary_report':
            # Recheck: Admins only
            if not request.user.is_staff:
                return Response(
                    {"detail": "Only admins can confirm weekly summaries."},
                    status=status.HTTP_403_FORBIDDEN
                )

            title = draft_log.details.get('title')
            message = draft_log.details.get('message')

            # Create system notification for the admin themselves
            Notification.objects.create(
                recipient=request.user,
                title=title,
                message=message,
                category='system'
            )

            draft_log.status = 'confirmed'
            draft_log.save()

            return Response({"status": "confirmed", "message": "Weekly summary report saved successfully."})

        else:
            return Response(
                {"detail": "Unsupported draft action type."},
                status=status.HTTP_400_BAD_REQUEST
            )

