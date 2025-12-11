# core/permissions.py
"""
RBAC Permission Helpers for Managers vs Agents.
Provides utilities to check permissions and scope data appropriately.
"""


def is_manager(user):
    """Check if user is a Manager (superuser or in Managers group)."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name="Managers").exists()


def is_agent(user):
    """Check if user is an Agent (staff but not manager)."""
    if not user or not user.is_authenticated:
        return False
    return user.is_staff and not is_manager(user)


def can_view_all_bookings(user):
    """Check if user can view all bookings (not just their own)."""
    return is_manager(user) or user.has_perm("core.view_all_bookings")


def can_assign_to_others(user):
    """Check if user can assign bookings to other agents."""
    return is_manager(user) or user.has_perm("core.assign_to_others")


def can_cancel_any_booking(user):
    """Check if user can cancel any booking."""
    return is_manager(user) or user.has_perm("core.cancel_any_booking")


def can_manage_financials(user):
    """Check if user can access financial features (ledger, payments, etc)."""
    return is_manager(user) or user.has_perm("core.manage_financials")


def can_view_financial_dashboard(user):
    """Check if user can view the financial dashboard."""
    return is_manager(user) or user.has_perm("core.view_financial_dashboard")


def can_access_booking(user, booking):
    """
    Check if user can access a specific booking.
    Managers: all bookings
    Agents: only bookings they created or are assigned to
    """
    if is_manager(user):
        return True
    return booking.created_by == user or booking.assigned_to == user


def get_accessible_bookings_queryset(user, base_queryset):
    """
    Filter a booking queryset to only include bookings the user can access.
    Managers: all bookings
    Agents: only their created/assigned bookings
    """
    from django.db.models import Q

    if can_view_all_bookings(user):
        return base_queryset

    return base_queryset.filter(Q(created_by=user) | Q(assigned_to=user))
