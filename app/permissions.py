"""Who may do what.

To change what a role can do, add or remove a permission name in ROLE_PERMISSIONS below.
PERMISSIONS lists every name and what it allows. A Super Admin always has every permission.
The sidebar, the buttons on each page and the server's checks all follow these lists, so nothing else needs editing.
A misspelled name stops the app at startup with a message saying which one.
"""
from app.models import ROLES, SUPER_ADMIN


# ==========================================================
#   Every permission, and what it allows
# ==========================================================
PERMISSIONS = {
    # Dashboard
    'view_dashboard':    "Open the Dashboard: yearly metrics, forecast, recently enrolled students and this week's events",
    'view_metrics':      'Open the statistics page (predicted vs actual enrollment)',
    'edit_metrics':      'Edit the yearly metrics and mark a year abnormal. Needs view_dashboard',

    # Enrollment, Masterlist and grades
    'submit_enrollment': 'Open the Enrollment Form and submit new enrollments',
    'view_masterlist':   'Open the Masterlist (the list of enrolled students)',
    'view_enrollment':   "Open a student's submitted enrollment form. Needs view_masterlist",
    'edit_students':     "Edit a student's submitted enrollment form. Needs view_enrollment",
    'view_grades':       "Open a student's grade files and download them. Needs view_masterlist",
    'submit_grades':     'Upload, replace and delete grade files. Needs view_grades',

    # Calendar
    'view_calendar':     'Open the Calendar',
    'edit_calendar':     'Add, edit and delete calendar events. Needs view_calendar',

    # Linkage/Files
    'view_linkage':      'Open Linkage/Files and download its files and pictures',
    'upload_files':      'Add links, upload files and upload pictures. Needs view_linkage',
    'edit_files':        'Edit links and files, and move links, files and pictures to the Archives. Needs view_linkage',

    # Archives
    'archives':          'Open the Archives, and restore or permanently delete what is there',

    # Accounts
    'view_accounts':     'Open the Accounts page (the list of accounts)',
    'create_accounts':   'Create accounts with your own role or a lower one. Needs view_accounts',
    'edit_accounts':     "Change accounts' names, usernames and roles, and reset passwords. Needs view_accounts",

    # Activity log
    'view_activity':     "The sidebar's bell and each page's Activity Log tab, which show the old and new value of every change",
}


# ==========================================================
#   What each role may do (Super Admin: everything)
# ==========================================================
ROLE_PERMISSIONS = {
    'principal': {
        'view_dashboard', 'view_metrics',
        'view_masterlist', 'view_enrollment', 'view_grades',
        'view_calendar',
        'view_linkage',
        'view_accounts',
        'view_activity',
    },
    'admin': {
        'view_dashboard', 'view_metrics', 'edit_metrics',
        'submit_enrollment', 'view_masterlist', 'view_enrollment', 'edit_students', 'view_grades', 'submit_grades',
        'view_calendar', 'edit_calendar',
        'view_linkage', 'upload_files', 'edit_files',
        'view_accounts', 'create_accounts',
        'view_activity',
    },
    'faculty': {
        'view_masterlist', 'view_grades',
        'view_calendar',
        'view_linkage',
    },
}


# ==========================================================
#   How the app uses the permissions. Changing a role never needs anything below.
# ==========================================================

# Endpoint (the route's function name in routes.py) -> the permission it needs. A route that is not listed
# is Super Admin only, so a new route starts out closed. A view_ permission covers reading only (GET);
# a pair is (to read, to change) for a route that does both.
ENDPOINT_PERMISSIONS = {
    'index': 'view_dashboard', 'dashboard_data': 'view_dashboard',
    'statistics': 'view_metrics', 'update_metric': 'edit_metrics', 'mark_abnormal_year': 'edit_metrics',
    'enrollment': 'submit_enrollment',
    'enrolled': 'view_masterlist', 'grades': 'view_masterlist',
    'student_detail': 'view_enrollment', 'edit_student': 'edit_students',
    'student_grades': 'view_grades', 'view_report_card': 'view_grades', 'download_report_card': 'view_grades',
    'upload_report_card': 'submit_grades', 'delete_report_card': 'submit_grades',
    'calendar': 'view_calendar', 'calendar_events': ('view_calendar', 'edit_calendar'), 'calendar_event_detail': 'edit_calendar',
    'linkagefiles': 'view_linkage', 'download_file': 'view_linkage', 'view_picture': 'view_linkage',
    'add_link': 'upload_files', 'upload_file': 'upload_files', 'upload_picture': 'upload_files',
    'edit_link': 'edit_files', 'edit_file': 'edit_files',
    'delete_link': 'edit_files', 'delete_file': 'edit_files', 'delete_picture': 'edit_files',
    'archives': 'archives', 'restore_archived': 'archives', 'delete_archived': 'archives',
    'accounts': 'view_accounts', 'create_account': 'create_accounts',
    'edit_account': 'edit_accounts', 'change_account_password': 'edit_accounts',
    'activity_log': 'view_activity', 'activity_log_unseen': 'view_activity', 'activity_log_details': 'view_activity',
}

# Open to every role: signing in and out
NO_PERMISSION_NEEDED = {'login', 'logout', 'landing'}

# The sidebar, in order: endpoint -> label. A user sees the pages their role may open and starts on the first.
NAV_PAGES = {'index': 'Dashboard', 'enrollment': 'Enrollment Form', 'enrolled': 'Masterlist', 'calendar': 'Calendar',
             'linkagefiles': 'Linkage/Files', 'archives': 'Archives', 'accounts': 'Accounts'}

# Pages reached from a sidebar page, which keeps its link marked while they are open: endpoint -> sidebar endpoint
NAV_SECTIONS = {'student_grades': 'enrolled', 'statistics': 'index'}

READ_METHODS = ('GET', 'HEAD', 'OPTIONS')


def can(role, permission):
    return role == SUPER_ADMIN or permission in ROLE_PERMISSIONS.get(role, ())


def assignable_roles(role):
    """The roles this role may give an account: its own and every one below it (ROLES lists the least powerful first)."""
    ranks = list(ROLES)
    return ranks[:ranks.index(role) + 1] if role in ranks else []


def may_open(role, endpoint, method='GET'):
    if endpoint in NO_PERMISSION_NEEDED:
        return True
    permission = ENDPOINT_PERMISSIONS.get(endpoint)
    if isinstance(permission, tuple):
        permission = permission[0] if method in READ_METHODS else permission[1]
    elif permission and permission.startswith('view_') and method not in READ_METHODS:
        permission = None
    return can(role, permission)


# A hand edit with a misspelled role or permission would otherwise quietly give that role nothing
for _role, _granted in ROLE_PERMISSIONS.items():
    if _role not in ROLES or _role == SUPER_ADMIN:
        raise ValueError(f"permissions.py: '{_role}' is not a role that can be listed. Use one of: "
                         f"{', '.join(r for r in ROLES if r != SUPER_ADMIN)}")
    if _granted - PERMISSIONS.keys():
        raise ValueError(f"permissions.py: role '{_role}' has unknown permissions {sorted(_granted - PERMISSIONS.keys())}. "
                         'Use the names in PERMISSIONS.')
