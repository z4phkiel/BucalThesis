"""The role rules of permissions.py. Needs no database:  py -m unittest tests.test_permissions"""
import unittest
from unittest import mock

from flask import Flask

from app.permissions import (ENDPOINT_PERMISSIONS, NAV_PAGES, NAV_SECTIONS, NO_PERMISSION_NEEDED, PERMISSIONS,
                             ROLE_PERMISSIONS, assignable_roles, may_open)
from app.routes import main_bp


class PermissionsTest(unittest.TestCase):
    def test_tables_match_the_routes(self):
        # A renamed route would otherwise drop out of the table and quietly become Super Admin only
        app = Flask(__name__)
        app.register_blueprint(main_bp)
        endpoints = {rule.endpoint.removeprefix('main.') for rule in app.url_map.iter_rules()}
        self.assertLessEqual(set(ENDPOINT_PERMISSIONS) | NO_PERMISSION_NEEDED | set(NAV_PAGES) | set(NAV_SECTIONS), endpoints)
        # The list of permissions and the routes name the same ones: no route needs a permission missing from the
        # list, and every permission in the list does something
        used = set()
        for permission in ENDPOINT_PERMISSIONS.values():
            used.update(permission if isinstance(permission, tuple) else [permission])
        self.assertEqual(used, set(PERMISSIONS))
        self.assertLessEqual(set().union(*ROLE_PERMISSIONS.values()), set(PERMISSIONS))

    def test_a_permission_works_once_added(self):
        # edit_calendar covers adding events too, which go through the Calendar's own route
        self.assertFalse(may_open('principal', 'calendar_events', 'POST'))
        with mock.patch.dict(ROLE_PERMISSIONS, {'principal': ROLE_PERMISSIONS['principal'] | {'edit_calendar'}}):
            for method in ('POST', 'PUT', 'DELETE'):
                endpoint = 'calendar_events' if method == 'POST' else 'calendar_event_detail'
                self.assertTrue(may_open('principal', endpoint, method), method)
        self.assertTrue(may_open('faculty', 'calendar_events', 'GET'))
        self.assertFalse(may_open('faculty', 'calendar_events', 'POST'))

    def test_use_case(self):
        allowed = [
            ('faculty', 'enrolled', 'GET'), ('faculty', 'calendar_events', 'GET'), ('faculty', 'download_file', 'GET'),
            ('faculty', 'student_grades', 'GET'), ('faculty', 'download_report_card', 'GET'),
            ('principal', 'index', 'GET'), ('principal', 'student_grades', 'GET'), ('principal', 'accounts', 'GET'),
            ('admin', 'enrollment', 'POST'), ('admin', 'upload_report_card', 'POST'), ('admin', 'upload_file', 'POST'),
            ('admin', 'update_metric', 'POST'), ('admin', 'create_account', 'POST'), ('admin', 'edit_student', 'POST'),
            # Admin adds, edits and deletes school events
            ('admin', 'calendar_events', 'POST'), ('admin', 'calendar_event_detail', 'PUT'),
            ('admin', 'calendar_event_detail', 'DELETE'),
            ('super_admin', 'edit_account', 'POST'), ('super_admin', 'test_signatures', 'GET'),
            (None, 'logout', 'GET'),
            # The bell's card and the Activity Log tab: every role but Faculty
            ('principal', 'activity_log', 'GET'), ('principal', 'activity_log_details', 'GET'),
            ('admin', 'activity_log_unseen', 'GET'), ('admin', 'activity_log_details', 'GET'),
            ('super_admin', 'activity_log', 'GET'),
        ]
        denied = [
            ('faculty', 'index', 'GET'), ('faculty', 'student_detail', 'GET'), ('faculty', 'upload_report_card', 'POST'),
            ('faculty', 'delete_report_card', 'POST'),
            ('faculty', 'upload_file', 'POST'), ('faculty', 'calendar_events', 'POST'), ('faculty', 'accounts', 'GET'),
            ('principal', 'enrollment', 'GET'), ('principal', 'update_metric', 'POST'),
            ('principal', 'create_account', 'POST'), ('principal', 'edit_file', 'POST'),
            ('admin', 'edit_account', 'POST'), ('admin', 'change_account_password', 'POST'),
            ('admin', 'archives', 'GET'), ('admin', 'restore_archived', 'POST'), ('admin', 'test_signatures', 'GET'),
            ('principal', 'calendar_events', 'POST'), ('principal', 'calendar_event_detail', 'DELETE'),
            ('registrar', 'enrolled', 'GET'), (None, 'index', 'GET'),
            ('faculty', 'activity_log', 'GET'), ('faculty', 'activity_log_unseen', 'GET'),
            ('faculty', 'activity_log_details', 'GET'), ('registrar', 'activity_log', 'GET'),
        ]
        for role, endpoint, method in allowed:
            self.assertTrue(may_open(role, endpoint, method), (role, endpoint, method))
        for role, endpoint, method in denied:
            self.assertFalse(may_open(role, endpoint, method), (role, endpoint, method))


    def test_assignable_roles(self):
        self.assertEqual(assignable_roles('super_admin'), ['faculty', 'principal', 'admin', 'super_admin'])
        self.assertEqual(assignable_roles('admin'), ['faculty', 'principal', 'admin'])
        self.assertEqual(assignable_roles('faculty'), ['faculty'])
        self.assertEqual(assignable_roles('registrar'), [])
        self.assertEqual(assignable_roles(None), [])


if __name__ == '__main__':
    unittest.main()
