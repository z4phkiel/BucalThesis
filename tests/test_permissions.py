"""The role rules of permissions.py. Needs no database:  py -m unittest tests.test_permissions"""
import unittest
from types import SimpleNamespace
from unittest import mock

from flask import Flask, session, url_for

from app.permissions import (ENDPOINT_PERMISSIONS, NAV_PAGES, NAV_SECTIONS, NO_PERMISSION_NEEDED, PERMISSIONS,
                             ROLE_PERMISSIONS, assignable_roles, may_open)
from app.routes import main_bp, outranks_you


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

    def test_signed_out_visitors_are_turned_away(self):
        # Every route but the public ones, including any added later, since no route checks this itself
        app = Flask(__name__)
        app.register_blueprint(main_bp)
        client = app.test_client()
        with app.test_request_context():
            for rule in app.url_map.iter_rules():
                endpoint = rule.endpoint.removeprefix('main.')
                if not rule.endpoint.startswith('main.') or endpoint in NO_PERMISSION_NEEDED:
                    continue
                url = url_for(rule.endpoint, **dict.fromkeys(rule.arguments, 1))
                method = sorted(rule.methods - {'HEAD', 'OPTIONS'})[0]
                opened = client.open(url, method=method)
                self.assertEqual(opened.status_code, 302, endpoint)
                self.assertEqual(opened.location, '/welcome' if endpoint == 'index' else '/login', endpoint)
                fetched = client.open(url, method=method, headers={'Sec-Fetch-Mode': 'cors'})
                self.assertEqual(fetched.status_code, 401, endpoint)

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
            # Admin opens the Archives, restores and deletes permanently
            ('admin', 'archives', 'GET'), ('admin', 'restore_archived', 'POST'), ('admin', 'delete_archived', 'POST'),
            # Editing, new passwords and deleting accounts: Admin and Super Admin (an Admin only below Super Admin)
            ('admin', 'edit_account', 'POST'), ('admin', 'change_account_password', 'POST'),
            ('admin', 'delete_account', 'POST'), ('super_admin', 'delete_account', 'POST'),
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
            ('principal', 'archives', 'GET'), ('faculty', 'restore_archived', 'POST'), ('admin', 'test_signatures', 'GET'),
            ('principal', 'delete_account', 'POST'), ('faculty', 'delete_account', 'POST'),
            ('principal', 'edit_account', 'POST'), ('principal', 'change_account_password', 'POST'),
            ('principal', 'calendar_events', 'POST'), ('principal', 'calendar_event_detail', 'DELETE'),
            ('registrar', 'enrolled', 'GET'), (None, 'index', 'GET'),
            ('faculty', 'activity_log', 'GET'), ('faculty', 'activity_log_unseen', 'GET'),
            ('faculty', 'activity_log_details', 'GET'), ('registrar', 'activity_log', 'GET'),
        ]
        for role, endpoint, method in allowed:
            self.assertTrue(may_open(role, endpoint, method), (role, endpoint, method))
        for role, endpoint, method in denied:
            self.assertFalse(may_open(role, endpoint, method), (role, endpoint, method))


    def test_only_super_admin_accounts_are_out_of_an_admins_reach(self):
        # An Admin may edit, reset or delete every account but a Super Admin's: a new password would hand it over
        app = Flask(__name__)
        app.secret_key = 'test'
        account = lambda role: SimpleNamespace(role=role)
        with app.test_request_context():
            session['role'] = 'admin'
            self.assertTrue(outranks_you(account('super_admin')))
            for role in ('faculty', 'principal', 'admin'):
                self.assertFalse(outranks_you(account(role)), role)
            session['role'] = 'super_admin'
            self.assertFalse(outranks_you(account('super_admin')))

    def test_assignable_roles(self):
        self.assertEqual(assignable_roles('super_admin'), ['faculty', 'principal', 'admin', 'super_admin'])
        self.assertEqual(assignable_roles('admin'), ['faculty', 'principal', 'admin'])
        self.assertEqual(assignable_roles('faculty'), ['faculty'])
        self.assertEqual(assignable_roles('registrar'), [])
        self.assertEqual(assignable_roles(None), [])


if __name__ == '__main__':
    unittest.main()
