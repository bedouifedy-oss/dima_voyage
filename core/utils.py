# core/utils.py
from django.db.models import Q

def badge_callback(request):
    from core.models import Announcement  # Import here to avoid loading errors
    
    if not request.user.is_authenticated:
        return None

    # Count announcements where the user is NOT in the 'acknowledged_by' list
    count = Announcement.objects.exclude(acknowledged_by=request.user).count()
    
    if count == 0:
        return None # Hides the badge if 0
        
    return count
