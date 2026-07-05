from .models import Notification

def notifications_context(request):
    if request.user.is_authenticated and (request.user.is_staff or hasattr(request.user, 'teacher')):
        unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False)
        return {
            'unread_notifications': unread_notifications,
            'unread_notifications_count': unread_notifications.count(),
        }
    return {
        'unread_notifications': [],
        'unread_notifications_count': 0,
    }
