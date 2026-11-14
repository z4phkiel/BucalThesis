from flask import Blueprint, render_template, redirect, request, url_for, session, flash, current_app, send_file, jsonify, abort
from app.models import User, Enrollment, YearlyMetric, Grades, CalendarEvent, LinkItem, FileItem, PictureItem, ActivityLog # Make sure to import your User model instead of or alongside myTask
from app import db
from datetime import date, datetime, timedelta
import base64
import math
import re
import threading
import time
import zipfile
import pandas as pd
from PIL import Image
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import os
import io
from io import BytesIO
from werkzeug.utils import secure_filename
import uuid
from urllib.parse import urlparse



main_bp = Blueprint('main', __name__)


@main_bp.after_request
def keep_private_pages_out_of_browser_history(response):
    # Otherwise the Back button can show a logged-in page again after logging out
    if 'user_id' in session and response.mimetype in ('text/html', 'application/json'):
        response.headers['Cache-Control'] = 'no-store'
    return response


# SOFT DELETE
# Deleting a report card, calendar event, link, file or picture only sets its archived_at, which moves it
# to the Archives page. Only that page deletes for good.

def active(model):
    """Rows that are not in the Archives."""
    return model.query.filter_by(archived_at=None)


# ACTIVITY LOG
# Every add (POST), change (UPDATE) and delete (DELETE) on the Masterlist, Calendar and Linkage/Files.
# The sidebar's bell opens a card with the latest entries (/activity-log). Each of those pages also has an
# Activity Log tab (/activity-log/<area>) with every entry's details: the item's values, or what changed.

ACTIVITY_AREAS = {'masterlist': 'Masterlist', 'calendar': 'Calendar', 'linkage': 'Linkage/Files'}
ACTIVITY_PAGES = {'masterlist': 'main.enrolled', 'calendar': 'main.calendar', 'linkage': 'main.linkagefiles'}
ACTIVITY_SHOWN = 30
NAME_IN_LOG_LENGTH = 60
VALUE_IN_LOG_LENGTH = 200

# The values an entry's details list for each kind of item: column -> label
LOG_FIELDS = {
    Grades: {'grade_level': 'Grade level', 'original_filename': 'File'},
    CalendarEvent: {'tag': 'Tag', 'description': 'Description', 'event_date': 'Start date', 'end_date': 'End date', 'link_url': 'Link'},
    LinkItem: {'title': 'Title', 'url': 'Link'},
    FileItem: {'title': 'Title', 'filename': 'File', 'size': 'Size'},
    PictureItem: {'title': 'Title', 'filename': 'File', 'size': 'Size'},
}


def log_activity(area, action, description, details=None):
    """Adds the entry to the session, so it is saved by the same commit as the change, or not at all.
    details is a list of [label, old value, new value]; see log_changes()."""
    db.session.add(ActivityLog(username=session.get('username', ''), area=area, action=action,
                               description=description[:255], details=details))


def named(text):
    """A title or description, quoted and kept short for a log entry."""
    text = ' '.join((text or '').split())
    if len(text) > NAME_IN_LOG_LENGTH:
        text = text[:NAME_IN_LOG_LENGTH - 3] + '...'
    return f'"{text}"' if text else ''


def log_value(column, value):
    """A value as an entry's details show it."""
    if value is None or value == '':
        return ''
    if column == 'size':
        return f'{value / 1048576:.1f} MB' if value >= 1048576 else f'{value / 1024:.1f} KB'
    if isinstance(value, date):
        return f'{value:%b} {value.day}, {value.year}'
    text = ' '.join(str(value).split())
    if column == 'grade_level':
        text = text.replace('_', ' ')
    return text if len(text) <= VALUE_IN_LOG_LENGTH else text[:VALUE_IN_LOG_LENGTH - 3] + '...'


def log_snapshot(item, columns):
    """{label: value} of an item's columns, taken before or after a change."""
    return {label: log_value(column, getattr(item, column)) for column, label in columns.items()}


def log_changes(before, after):
    """[label, old, new] for each value that differs, so every filled-in value for an add (before is {})
    or a delete (after is {}), and only the changed ones for an edit."""
    return [[label, before.get(label, ''), after.get(label, '')] for label in {**before, **after}
            if before.get(label, '') != after.get(label, '')]


def full_name(student):
    return ', '.join(filter(None, [student.last_name, student.first_name]))


def event_label(event):
    """e.g. exam "Quarterly Exam" on Nov 13, 2026"""
    start, end = event.event_date, event.end_date or event.event_date
    dates = start.strftime('%b %d, %Y') + ('' if end == start else ' to ' + end.strftime('%b %d, %Y'))
    return ' '.join(filter(None, [event.tag, named(event.description), 'on', dates]))


def activity_time(logged_at):
    """(short, day, clock): 'Just now', '5 min ago' or '3 hr ago' within a day, else the day and time;
    then the day and the time at the school."""
    local = logged_at + timedelta(hours=8)
    day = f'{local:%b} {local.day}, {local.year}'
    clock = f"{int(local.strftime('%I'))}:{local:%M %p}"
    seconds = (datetime.utcnow() - logged_at).total_seconds()
    if seconds < 60:
        short = 'Just now'
    elif seconds < 3600:
        short = f'{int(seconds // 60)} min ago'
    elif seconds < 86400:
        short = f'{int(seconds // 3600)} hr ago'
    else:
        short = f'{day}, {clock}'
    return short, day, clock


@main_bp.app_context_processor
def activity_areas():
    # The card's filter buttons are in the layout, so every page needs the area names
    return {'activity_areas': ACTIVITY_AREAS}


def latest_activity(area='', before=None, limit=ACTIVITY_SHOWN):
    logs = ActivityLog.query
    if area in ACTIVITY_AREAS:
        logs = logs.filter_by(area=area)
    if before:
        logs = logs.filter(ActivityLog.id < before)
    return logs.order_by(ActivityLog.id.desc()).limit(limit).all()


def mark_activity_seen(logs, areas):
    """Records that this user has seen every entry up to the newest of logs (newest first) in each of areas."""
    user = db.session.get(User, session['user_id'])
    if not logs or user is None:
        return
    seen = dict(user.activity_seen or {})
    seen.update({area: max(seen.get(area, 0), logs[0].id) for area in areas})
    if seen != user.activity_seen:
        user.activity_seen = seen
        db.session.commit()


@main_bp.route("/activity-log")
def activity_log():
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401

    area = request.args.get('area', '')
    logs = latest_activity(area)
    # Opening the card counts as seeing everything up to its newest entry, in the area it is filtered to or in all
    mark_activity_seen(logs, [area] if area in ACTIVITY_AREAS else ACTIVITY_AREAS)
    return render_template('activity_log.html', logs=logs, pages=ACTIVITY_PAGES, when=activity_time)


@main_bp.route("/activity-log/unseen")
def activity_log_unseen():
    """The areas with entries by other users newer than this user has seen, for the red dots (activity-log.js)."""
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401

    user = db.session.get(User, session['user_id'])
    seen = (user and user.activity_seen) or {}
    newest = (db.session.query(ActivityLog.area, db.func.max(ActivityLog.id))
              .filter(ActivityLog.username != session.get('username', ''),
                      ActivityLog.id > min(seen.get(area, 0) for area in ACTIVITY_AREAS))   # older rows are all seen
              .group_by(ActivityLog.area).all())
    return {'areas': [area for area, last in newest if area in ACTIVITY_AREAS and last > seen.get(area, 0)]}


@main_bp.route("/activity-log/<area>")
def activity_log_details(area):
    """One page of an Activity Log tab; ?before=<id> gives the page after the entry with that id."""
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401
    if area not in ACTIVITY_AREAS:
        abort(404)

    # One extra entry shows whether there is an older page
    before = request.args.get('before', type=int)
    logs = latest_activity(area, before, ACTIVITY_SHOWN + 1)
    if not before:
        mark_activity_seen(logs, [area])
    return render_template('activity_log_details.html', logs=logs[:ACTIVITY_SHOWN],
                           has_more=len(logs) > ACTIVITY_SHOWN, when=activity_time)






# RESTRICT MOBILE ACCESS

def is_mobile_device():
    user_agent = request.headers.get('User-Agent', '').lower()

    mobile_keywords = [
        'android',
        'iphone',
        'ipod',
        'blackberry',
        'windows phone',
        'mobile',
        'opera mini'
    ]

    return any(keyword in user_agent for keyword in mobile_keywords)


def restrict_mobile_access():
    if is_mobile_device():
        abort(403)


# LOGIN

LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
# (ip, account) -> (attempt count, time of first attempt). Kept oldest first, so expired entries sit at the front.
login_attempts = {}
login_attempts_lock = threading.Lock()


def count_login_attempt(key):
    # Returns the minutes left in a lockout, or 0 if this attempt may go ahead.
    # Counted before the password check, so guesses sent in parallel can't share one slot.
    with login_attempts_lock:
        now = time.monotonic()
        while login_attempts:
            oldest_key = next(iter(login_attempts))
            if now - login_attempts[oldest_key][1] < LOGIN_WINDOW_SECONDS:
                break
            del login_attempts[oldest_key]

        count, first_attempt = login_attempts.get(key, (0, now))
        if count >= LOGIN_MAX_ATTEMPTS:
            return math.ceil((LOGIN_WINDOW_SECONDS - (now - first_attempt)) / 60)
        login_attempts[key] = (count + 1, first_attempt)
        return 0


@main_bp.before_request
def end_session_of_deleted_user():
    # The signed cookie can't know the account was removed, so check that it still exists
    user_id = session.get('user_id')
    if user_id is not None and db.session.get(User, user_id) is None:
        session.clear()


@main_bp.route("/login", methods=['GET', 'POST'])
def login():
    # If the user is already logged in, skip the login page and send them to dashboard
    if 'user_id' in session:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')

        # Query the database for the user
        user = User.query.filter_by(username=username).first()

        # Keyed on the account id when it exists, so case or accent variants of a username share one count
        attempt_key = (request.remote_addr, user.id if user else username.lower())
        wait_minutes = count_login_attempt(attempt_key)
        if wait_minutes:
            flash(f'Too many failed attempts. Try again in {wait_minutes} min.', 'danger')
            return render_template('login.html'), 429

        # Check if user exists and password matches
        if user and user.check_password(password):
            with login_attempts_lock:
                login_attempts.pop(attempt_key, None)
            session.clear()           # nothing from before login carries over
            session.permanent = True  # applies the 30-minute PERMANENT_SESSION_LIFETIME
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            flash('Login successful!', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@main_bp.route("/logout")
def logout():
    session.clear()  # Wipes out the login session completely
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.login'))


# Dashboard/Base View
# DASHBOARD
METRIC_FIELDS = [
    'enrollee_count', 'promotion_rate', 'cohort_survival_rate',
    'completion_rate', 'transition_rate', 'dropout_rate',
    'graduation_rate', 'retention_rate',
]

def get_current_start_year():

    # for testing date
    # today = datetime(2027, 6, 1)

    today = datetime.utcnow()
    return today.year if today.month >= SCHOOL_YEAR_ROLLOVER_MONTH else today.year - 1
 
 
def ensure_current_school_year_metric():
    latest = get_current_start_year()
 
    existing = {m.school_year.replace(' ', '') for m in YearlyMetric.query.all()}
 
    for start_year in range(FIRST_AUTO_CREATED_YEAR, latest + 1):
        label = f"{start_year}-{start_year + 1}"
        if label not in existing:
            db.session.add(YearlyMetric(school_year=label))
 
    db.session.commit()


MAX_ENROLLEE_COUNT = 2147483647     # largest value the INT column holds
MAX_RATE = 150                      # rates can pass 100; this only catches typos such as 985 for 98.5
MAX_REASON_LENGTH = 255             # what the abnormal_reason column holds


def _parse_metric_payload(data):
    """Validate the JSON body of a metric update. Returns (values, error)."""
    if not isinstance(data, dict):
        return None, 'Invalid data.'

    # values = {}
    # for field in METRIC_FIELDS:
    #     if field not in data:
    #         continue

    #     value = data[field]

    if any(field not in data for field in METRIC_FIELDS):
        return None, "Invalid Data."

    blank = [field for field in METRIC_FIELDS if data[field] is None]
    if len(blank) == len(METRIC_FIELDS):
        return {field: None for field in METRIC_FIELDS}, None
    if blank:
        names = ", ".join(field.replace('_',' ') for field in blank)
        return None, f'Fill in every field, or leave the whole year blank. Missing: {names}.'

    values = {}
    for field in METRIC_FIELDS:
        value = data[field]
        label = field.replace('_', ' ').capitalize()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None, f'{label} must be a number.'

        if field == 'enrollee_count':
        #     if value != int(value) or not 0 <= value <= MAX_ENROLLEE_COUNT:
        #         return None, f'{label} must be a whole number that is not negative.'
        #     value = int(value)
        # elif not 0 <= value <= MAX_RATE:
        #     return None, f'{label} must be between 0 and {MAX_RATE}.'

            if value != int(value) or not 1 <= value <= MAX_ENROLLEE_COUNT:
                return None, f'{label} must be a whole number of at least 1. Leave the whole year blank if it is not submitted yet.'
            value = int(value)

        elif not 0 <= value <= MAX_RATE:
            return None, f'{label} must be between 0 and {MAX_RATE}.'
        
        elif value == 0 and field in NONZERO_RATES:
            return None, f'{label} cannot be 0. Enter the real rate, or leave the whole year blank.'

        values[field] = value
    return values, None


@main_bp.route("/metrics/<int:metric_id>/update", methods=['POST'])
def update_metric(metric_id):
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401
 
    metric = YearlyMetric.query.get_or_404(metric_id)

    values, error = _parse_metric_payload(request.get_json(silent=True) or {})
    if error:
        return {'error': error}, 400

    for field, value in values.items():
        setattr(metric, field, value)

    db.session.commit()
    return {'success': True}

# RIDGE REGRESSION ALGORITHM


# The model's inputs: this year's count, the share of students who stay, and how well the school holds students over time
FORECAST_RATES = ['retention_rate', 'cohort_survival_rate']
FORECAST_FEATURES = ['enrollee_count', *FORECAST_RATES]

# A real school year can have 0% dropout, but not 0% on these
NONZERO_RATES = [
    'promotion_rate', 'cohort_survival_rate', 'completion_rate',
    'transition_rate', 'graduation_rate', 'retention_rate',
]

MIN_FORECAST_YEARS = 9      # usable years needed to forecast or score, which leaves at least 4 past predictions to score
MIN_BACKTEST_YEARS = 5      # fewest earlier years a past prediction is trained on; must stay below MIN_FORECAST_YEARS
RANGE_SHARE = 0.8          # share of past misses the forecast range is built to cover
FEW_TESTS = 10             # with fewer past predictions than this, the scores can't prove which method is better
FAR_INPUT_SDS = 3          # an input this many standard deviations from the training years' average gets a warning

# What the model is scored against, from the same past years. The simplest comes first, so it wins a tie.
RIVAL_FEATURES = ['enrollee_count']     # the same model without the two rates, which shows whether the rates help
METHODS = {
    'baseline_mape': "copying the previous year's count",
    'count_only_mape': 'the model without the two rates',
    'mape': 'the model',
}


def _new_forecast_model():
    return make_pipeline(StandardScaler(), Ridge(alpha=1.0))


def _far_inputs(train_X, row):
    """The inputs in row that are far from every value the model was trained on, where its straight line is a guess."""
    distance = ((row.iloc[0] - train_X.mean()) / train_X.std(ddof=0)).abs()
    return [name.replace('_', ' ') for name in train_X.columns if distance[name] > FAR_INPUT_SDS]


def _predicted_count(model, row):
    """The model's prediction for one row, as a whole number of enrollees that can't be negative."""
    return max(0, round(float(model.predict(row)[0])))


def _forecast_frame(metrics_oldest_first):
    """One row per calendar year, plus which of those years the model can use."""
    df = pd.DataFrame([{
        'id': m.id,
        'school_year': m.school_year,
        'abnormal_reason': m.abnormal_reason,
        **{field: getattr(m, field) for field in METRIC_FIELDS},
    } for m in metrics_oldest_first])
    df[METRIC_FIELDS] = df[METRIC_FIELDS].apply(pd.to_numeric, errors='coerce')
    df['start_year'] = df['school_year'].str.split('-').str[0].str.strip().astype(int)

    # One row per calendar year, so shift() can't pair non-consecutive years. Blank rows sort first, so a duplicate keeps its submitted row
    df = df.sort_values('enrollee_count', na_position='first', kind='stable')
    df = df.drop_duplicates('start_year', keep='last').set_index('start_year').sort_index()
    df = df.reindex(range(df.index.min(), df.index.max() + 1))

    # A year's count and rates are submitted together, so they predict the next year's count
    df['next_enrollee_count'] = df['enrollee_count'].shift(-1)

    # Only the rates the model uses need to be filled in
    has_count = df['enrollee_count'] > 0
    is_complete = (df[FORECAST_RATES] > 0).all(axis=1)

    # An abnormal year misleads the model both as the inputs and as the count to predict, so neither pairing is used
    df['is_abnormal'] = df['abnormal_reason'].fillna('').ne('')
    is_normal_pair = ~(df['is_abnormal'] | df['is_abnormal'].shift(-1, fill_value=False))
    train_df = df[has_count & is_complete & (df['next_enrollee_count'] > 0) & is_normal_pair]
    return df, has_count, is_complete, train_df


def _backtest(train_df):
    """Predict each past year from a model trained only on the years before it, as a real forecast would be."""
    X = train_df[FORECAST_FEATURES]
    y = train_df['next_enrollee_count']

    tests = []
    for i in range(MIN_BACKTEST_YEARS, len(train_df)):
        model = _new_forecast_model().fit(X.iloc[:i], y.iloc[:i])
        predicted = _predicted_count(model, X.iloc[[i]])
        rival = _new_forecast_model().fit(X[RIVAL_FEATURES].iloc[:i], y.iloc[:i])
        actual = int(y.iloc[i])
        tests.append({
            'start_year': int(train_df.index[i]) + 1,
            'predicted': predicted,
            'count_only': _predicted_count(rival, X[RIVAL_FEATURES].iloc[[i]]),
            'actual': actual,
            'previous_count': int(X['enrollee_count'].iloc[i]),
            'earlier_average': float(y.iloc[:i].mean()),
            'trained_on': i,
            'difference': predicted - actual,
            'percent_off': round(abs(predicted - actual) / actual * 100, 1),
        })
    return tests


def _score_backtest(tests):
    """The figures both pages report, all from the same past predictions."""
    misses = sorted(abs(test['difference']) for test in tests)
    covered = min(len(tests), math.ceil((len(tests) + 1) * RANGE_SHARE))
    baseline = [abs(test['previous_count'] - test['actual']) / test['actual'] * 100 for test in tests]
    count_only = [abs(test['count_only'] - test['actual']) / test['actual'] * 100 for test in tests]

    # R2 against guessing the average of the earlier years, since the test years' own average wasn't known yet.
    # That is an easy rival on a trending school, so the pages lead with the average miss beside the two rivals instead.
    model_error = sum(test['difference'] ** 2 for test in tests)
    average_error = sum((test['actual'] - test['earlier_average']) ** 2 for test in tests)

    scores = {
        'mape': round(sum(test['percent_off'] for test in tests) / len(tests), 1),
        'baseline_mape': round(sum(baseline) / len(baseline), 1),
        'count_only_mape': round(sum(count_only) / len(count_only), 1),
        # Above 0 the model ran high, below 0 low: Ridge pulls a growing or shrinking school toward its past average
        'average_difference': round(sum(test['difference'] for test in tests) / len(tests)),
        'r2_score': round(1 - model_error / average_error, 2) if average_error else None,
        'tested_years': len(tests),
        'few_tests': len(tests) < FEW_TESTS,
        'range_margin': misses[covered - 1],
        'range_covered': covered,
    }
    scores['best_method'] = METHODS[min(METHODS, key=scores.get)]
    return scores


def forecast_values(metrics_oldest_first):
    """Train the model on the yearly metrics and return what the dashboard and statistics pages show."""
    pred_next_year = None
    based_on_year = None
    target_year = None
    forecast_note = None
    forecast_warning = None
    abnormal_years = 0
    actual_year = None
    actual_count = None
    range_low = None
    range_high = None
    tests = []
    trained_years = 0
    scores = dict.fromkeys(['mape', 'baseline_mape', 'count_only_mape', 'average_difference', 'r2_score', 'tested_years',
                            'few_tests', 'range_margin', 'range_covered', 'best_method'])

    if metrics_oldest_first:
        df, has_count, is_complete, train_df = _forecast_frame(metrics_oldest_first)
        features = FORECAST_FEATURES
        abnormal_years = int(df['is_abnormal'].sum())
        trained_years = len(train_df)
        tests = _backtest(train_df)

        # The same minimum as the forecast, so both pages report scores under one rule
        if len(train_df) >= MIN_FORECAST_YEARS:
            scores = _score_backtest(tests)

        if has_count.any():
            anchor = int(df.index[has_count][-1])   # latest recorded enrollment
            target_year = f'{anchor + 1}-{anchor + 2}'
            based_on_year = f'{anchor}-{anchor + 1}'

            # Show the current year's submitted count; until then, the forecast year's actual is pending
            if anchor >= get_current_start_year():
                actual_year = based_on_year
                actual_count = int(df.loc[anchor, 'enrollee_count'])
            else:
                actual_year = target_year

            # if len(train_df) <= len(features):
            #     forecast_note = (
            #         f'Not enough complete years: the model has {len(features)} inputs '
            #         f'but only {len(train_df)} usable years.'
            #     )

            if not is_complete.loc[anchor]:
                forecast_note = (
                    f'No forecast yet: S.Y. {based_on_year} has a blank or 0% retention or cohort survival rate. '
                    'Complete that year to see the forecast.'
                )

            elif len(train_df) < MIN_FORECAST_YEARS:
                forecast_note = (
                    f'Not enough complete years: the forecast needs {MIN_FORECAST_YEARS} usable years '
                    f'but there are only {len(train_df)}.'
                )

            else:
                X = train_df[features]
                y = train_df['next_enrollee_count']

                model = _new_forecast_model().fit(X, y)
                pred_next_year = _predicted_count(model, df.loc[[anchor], features])
                range_low = max(0, pred_next_year - scores['range_margin'])
                range_high = pred_next_year + scores['range_margin']

                # The forecast still shows, since the model can't tell a real change from a typo, but not without a warning
                doubts = []
                if df.loc[anchor, 'is_abnormal']:
                    doubts.append(f'S.Y. {based_on_year} is marked as an abnormal year.')
                # A growing school's count is a new high every year, so its change from the year before is checked instead
                checked = df[features].assign(enrollee_count=df['enrollee_count'].diff())
                checked = checked.rename(columns={'enrollee_count': 'change_in_enrollee_count'})
                far = _far_inputs(checked.loc[X.index], checked.loc[[anchor]])
                if far:
                    doubts.append(f"S.Y. {based_on_year}'s {' and '.join(far)} {'is' if len(far) == 1 else 'are'} "
                                  'far from anything in the years the model learned from.')
                if doubts:
                    forecast_warning = ' '.join(doubts) + ' Treat this forecast as less reliable than usual.'

    return {
        'pred_next_year': pred_next_year,
        'based_on_year': based_on_year,
        'target_year': target_year,
        'forecast_note': forecast_note,
        'forecast_warning': forecast_warning,
        'abnormal_years': abnormal_years,
        'actual_year': actual_year,
        'actual_count': actual_count,
        'range_low': range_low,
        'range_high': range_high,
        'tests': tests,
        'trained_years': trained_years,
        **scores,
    }


def prediction_history(metrics_oldest_first):
    """The dashboard's forecast and scores, plus each year's actual count beside its past prediction."""
    forecast = forecast_values(metrics_oldest_first)
    history = {**forecast, 'years': [], 'min_years': MIN_BACKTEST_YEARS}
    if not metrics_oldest_first:
        return history

    df, has_count, _, _ = _forecast_frame(metrics_oldest_first)
    actual = {int(year): int(df.loc[year, 'enrollee_count']) for year in df.index[has_count]}
    abnormal = {int(year): df.loc[year, 'abnormal_reason'] for year in df.index[df['is_abnormal']]}
    tested = {test['start_year']: test for test in forecast['tests']}

    forecast_year = None
    if forecast['pred_next_year'] is not None:
        forecast_year = int(forecast['target_year'].split('-')[0])

    known = sorted({*actual, *tested, *([forecast_year] if forecast_year else [])})
    if not known:
        return history

    # Every calendar year stays on the list, so a missing year shows as a gap in the chart
    for year in range(known[0], known[-1] + 1):
        test = tested.get(year, {})
        is_forecast = year == forecast_year
        left_out = None     # why a year in the middle of the history has no past prediction
        if year in abnormal:
            left_out = 'Not predicted: marked as an abnormal year'
        elif year - 1 in abnormal:
            left_out = 'Not predicted: the year before it was abnormal'
        history['years'].append({
            'id': int(df.loc[year, 'id']) if year in actual else None,     # only a year with a count can be marked abnormal
            'abnormal_reason': abnormal.get(year),
            'left_out': left_out,
            'year': f'{year}-{year + 1}',
            'actual': actual.get(year),
            'predicted': forecast['pred_next_year'] if is_forecast else test.get('predicted'),
            'trained_on': forecast['trained_years'] if is_forecast else test.get('trained_on'),
            'is_forecast': is_forecast,
            'difference': test.get('difference'),
            'percent_off': test.get('percent_off'),
            'range': [forecast['range_low'], forecast['range_high']] if is_forecast else None,
        })
    return history


@main_bp.route("/")
def index():
    # Visitors who are not logged in start on the public landing page
    if 'user_id' not in session:
        return redirect(url_for('main.landing'))

    # The table and forecast load separately from /dashboard/data, so the page can appear straight away
    return render_template('dashboard.html', username=session['username'])


@main_bp.route("/dashboard/data")
def dashboard_data():
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401

    ensure_current_school_year_metric()
    metrics = YearlyMetric.query.order_by(YearlyMetric.school_year.desc()).all()
    all_metrics_asc = YearlyMetric.query.order_by(YearlyMetric.school_year.asc()).all()

    # Newest first, as on the Masterlist. Only the columns the card shows: a full row carries the signature image.
    recent_students = Enrollment.query.with_entities(
        Enrollment.id, Enrollment.last_name, Enrollment.first_name, Enrollment.middle_name,
        Enrollment.extension_name, Enrollment.grade_level, Enrollment.age, Enrollment.sex,
    ).order_by(Enrollment.id.desc()).limit(4).all()

    # Today and the next 6 days (school time), including events already under way
    today = school_today()
    week_end = today + timedelta(days=6)
    week_events = active(CalendarEvent).filter(
        CalendarEvent.event_date <= week_end,
        db.func.coalesce(CalendarEvent.end_date, CalendarEvent.event_date) >= today,
    ).order_by(CalendarEvent.event_date.asc(), CalendarEvent.id.asc()).all()

    return render_template('dashboard_data.html', metrics=metrics, recent_students=recent_students,
                           today=today, week_end=week_end, week_events=week_events,
                           **forecast_values(all_metrics_asc))


@main_bp.route("/statistics")
def statistics():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    metrics = YearlyMetric.query.order_by(YearlyMetric.school_year.asc()).all()
    return render_template('statistics.html', **prediction_history(metrics))


@main_bp.route("/statistics/abnormal-year", methods=['POST'])
def mark_abnormal_year():
    """The statistics page's form: a reason marks the year abnormal, which leaves it out of the forecast's
    training and scoring; a blank reason makes it a normal year again."""
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    metric = db.session.get(YearlyMetric, request.form.get('metric_id', type=int) or 0)
    if metric is None:
        abort(404)

    reason = ' '.join(request.form.get('reason', '').split())
    if len(reason) > MAX_REASON_LENGTH:
        flash(f'The reason must be {MAX_REASON_LENGTH} characters or fewer.', 'danger')
    else:
        metric.abnormal_reason = reason or None
        db.session.commit()
        flash(f'S.Y. {metric.school_year} is marked abnormal and left out of the forecast.' if reason
              else f'S.Y. {metric.school_year} counts as a normal year.', 'success')
    return redirect(url_for('main.statistics'))


@main_bp.route("/test_signatures")
def test_signatures():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    enrollments = Enrollment.query.order_by(Enrollment.id.desc()).all()
    return render_template('test_signatures.html', enrollments=enrollments)

# Enrollment rules (the page's JavaScript is only a convenience, these are what count)
ENROLLMENT_LABELS = {
    'grade_level': 'Grade level to enroll',
    'has_lrn': 'With LRN',
    'is_returning': 'Returning (Balik-Aral)',
    'psa_birth_cert_no': 'PSA Birth Certificate No.',
    'lrn_no': 'Learner Reference No.',
    'last_name': 'Last name',
    'first_name': 'First name',
    'middle_name': 'Middle name',
    'extension_name': 'Extension name',
    'birth_place': 'Place of birth',
    'sex': 'Sex',
    'mother_tongue': 'Mother tongue',
    'is_ip': 'Indigenous Peoples community',
    'ip_community': 'Indigenous Peoples community name',
    'is_4ps': '4Ps beneficiary',
    'four_ps_id_no': '4Ps Household ID',
    'is_lwd': 'Learner with disability',
    'current_house_no': 'Current house no.',
    'current_street_name': 'Current street name',
    'current_barangay': 'Current barangay',
    'current_municipality_city': 'Current municipality/city',
    'current_province': 'Current province',
    'current_country': 'Current country',
    'current_zip_code': 'Current zip code',
    'same_address': 'Same address',
    'perm_house_no': 'Permanent house no.',
    'perm_street_name': 'Permanent street name',
    'perm_barangay': 'Permanent barangay',
    'perm_municipality_city': 'Permanent municipality/city',
    'perm_province': 'Permanent province',
    'perm_country': 'Permanent country',
    'perm_zip_code': 'Permanent zip code',
    'father_last_name': "Father's last name",
    'father_first_name': "Father's first name",
    'father_middle_name': "Father's middle name",
    'father_contact_number': "Father's contact number",
    'mother_maiden_last_name': "Mother's last name",
    'mother_maiden_first_name': "Mother's first name",
    'mother_maiden_middle_name': "Mother's middle name",
    'mother_maiden_contact_number': "Mother's contact number",
    'legal_guardian_last_name': "Guardian's last name",
    'legal_guardian_first_name': "Guardian's first name",
    'legal_guardian_middle_name': "Guardian's middle name",
    'legal_guardian_contact_number': "Guardian's contact number",
    'last_grade_completed': 'Last grade level completed',
    'last_school_year_completed': 'Last school year completed',
    'last_school_attended': 'Last school attended',
    'school_id': 'School ID',
    'semester': 'Semester',
    'track': 'Track',
    'strand': 'Strand',
    'parent_guardian_name': 'Printed name of parent/guardian',
}

ENROLLMENT_CHOICES = {
    'grade_level': {'Kindergarten', 'Grade_1', 'Grade_2', 'Grade_3', 'Grade_4', 'Grade_5', 'Grade_6'},
    'has_lrn': {'yes', 'no'},
    'is_returning': {'yes', 'no'},
    'sex': {'male', 'female'},
    'is_ip': {'yes', 'no'},
    'is_4ps': {'yes', 'no'},
    'is_lwd': {'yes', 'no'},
    'same_address': {'yes', 'no'},
}

ENROLLMENT_REQUIRED_TEXT = [
    'last_name', 'first_name', 'middle_name', 'birth_place', 'mother_tongue',
    'current_house_no', 'current_street_name', 'current_barangay', 'current_municipality_city',
    'current_province', 'current_country',
    'legal_guardian_last_name', 'legal_guardian_first_name', 'legal_guardian_middle_name',
    'parent_guardian_name',
]

ENROLLMENT_OPTIONAL_TEXT = [
    'extension_name', 'father_last_name', 'father_first_name', 'father_middle_name',
    'mother_maiden_last_name', 'mother_maiden_first_name', 'mother_maiden_middle_name',
    'track', 'strand',
]

PERMANENT_ADDRESS_FIELDS = ['house_no', 'street_name', 'barangay', 'municipality_city', 'province', 'country']

DISABILITY_OPTIONS = {
    'Visual Impairment', 'Visual Impairment - Blind', 'Visual Impairment - Low Vision', 'Multiple Disorder',
    'Hearing Impairment', 'Autism Spectrum Disorder', 'Speech/Language Disorder', 'Learning Disability',
    'Emotional-Behavioral Disorder', 'Cerebral Palsy', 'Intellectual Disability',
    'Orthopedic/Physical Handicap', 'Special Health Problem/Chronic Disease', 'Special Health Problem - Cancer',
}

MODALITY_OPTIONS = {
    'Modular (Print)', 'Modular (Digital)', 'Online', 'Educational Television',
    'Radio-Based Instruction', 'Homeschooling', 'Blended',
}

PHONE_PATTERN = re.compile(r'[0-9]{4}-[0-9]{3}-[0-9]{4}')
SIGNATURE_PREFIX = 'data:image/png;base64,'
MAX_SIGNATURE_LENGTH = 65000    # signature_data is a TEXT column on MySQL
MAX_SIGNATURE_SIDE = 2000       # the signature canvas is 400 x 180
EARLIEST_BIRTH_YEAR = 1900
EARLIEST_LAST_SCHOOL_YEAR_END = 2002


def school_today():
    """Today's date at the school (Philippine time), whatever timezone the server uses."""
    return (datetime.utcnow() + timedelta(hours=8)).date()


def signature_problem(signature):
    """Return what is wrong with a signature, or None if it is a real drawn PNG."""
    if not signature:
        return 'Please add a signature.'
    if len(signature) > MAX_SIGNATURE_LENGTH:
        return 'The signature is too large. Please draw it again.'
    if not signature.startswith(SIGNATURE_PREFIX):
        return 'The signature is not valid. Please draw it again.'
    try:
        image = Image.open(BytesIO(base64.b64decode(signature[len(SIGNATURE_PREFIX):], validate=True)))
        if image.format != 'PNG' or max(image.size) > MAX_SIGNATURE_SIDE:
            return 'The signature is not valid. Please draw it again.'
        # Nothing drawn: every pixel of the canvas is still transparent
        if image.convert('RGBA').getchannel('A').getbbox() is None:
            return 'Please add a signature.'
    except Exception:   # a damaged image can fail in many ways, none of them are a valid signature
        return 'The signature is not valid. Please draw it again.'
    return None


def validate_enrollment(form, age_on=None):
    """Check a submitted enrollment. Returns (values for the Enrollment model, list of errors).
    The age is worked out for the date age_on, or for today if it isn't given."""
    errors = []
    values = {}
    today = school_today()
    age_on = age_on or today

    def text(name):
        return form.get(name, '').strip()

    def require(name):
        value = text(name)
        if not value:
            errors.append(f'{ENROLLMENT_LABELS[name]} is required.')
        return value

    def require_zip(name):
        value = require(name)
        if value and not re.fullmatch(r'[0-9]{4}', value):
            errors.append(f'{ENROLLMENT_LABELS[name]} must be exactly 4 digits.')
        return value

    def contact_number(name, required):
        value = require(name) if required else text(name)
        if value and not PHONE_PATTERN.fullmatch(value):
            errors.append(f'{ENROLLMENT_LABELS[name]} must look like 0912-345-6789.')
        return value

    def chosen(name, options):
        picked = form.getlist(name)
        if not set(picked) <= options:
            errors.append(f'{name.replace("_", " ").capitalize()} has an invalid option.')
        return picked

    for name, options in ENROLLMENT_CHOICES.items():
        values[name] = text(name)
        if values[name] not in options:
            errors.append(f'{ENROLLMENT_LABELS[name]}: please select a valid option.')

    for name in ENROLLMENT_REQUIRED_TEXT:
        values[name] = require(name)
    for name in ENROLLMENT_OPTIONAL_TEXT:
        values[name] = text(name)
    values['psa_birth_cert_no'] = text('psa_birth_cert_no') or None

    # The server works these out itself, so what the browser sends for them is ignored
    values['school_year'] = f'{today.year}-{today.year + 1}'
    values['date_signed'] = today
    values['age'] = None
    values['birthdate'] = None

    birthdate_text = text('birthdate')
    if not birthdate_text:
        errors.append('Birthdate is required.')
    else:
        try:
            birthdate = datetime.strptime(birthdate_text, '%Y-%m-%d').date()
            if birthdate > age_on or birthdate.year < EARLIEST_BIRTH_YEAR:
                errors.append('Birthdate must be a real date that is not in the future.')
            else:
                values['birthdate'] = birthdate
                values['age'] = age_on.year - birthdate.year - ((age_on.month, age_on.day) < (birthdate.month, birthdate.day))
        except ValueError:
            errors.append('Birthdate is not a valid date.')

    # With LRN?
    values['lrn_no'] = ''
    if values['has_lrn'] == 'yes':
        values['lrn_no'] = require('lrn_no')
        if values['lrn_no'] and not re.fullmatch(r'[0-9]{12}', values['lrn_no']):
            errors.append('Learner Reference No. must be exactly 12 digits.')

    # If Yes, specify: these are only kept when the answer is Yes
    values['ip_community'] = require('ip_community') if values['is_ip'] == 'yes' else None
    values['four_ps_id_no'] = require('four_ps_id_no') if values['is_4ps'] == 'yes' else None

    disabilities = chosen('disabilities', DISABILITY_OPTIONS)
    if values['is_lwd'] == 'yes':
        if not disabilities:
            errors.append('Please specify the type of disability.')
        if 'Visual Impairment' in disabilities and not {'Visual Impairment - Blind', 'Visual Impairment - Low Vision'} & set(disabilities):
            errors.append('Please choose blind or low vision.')
    else:
        disabilities = []
    values['disabilities'] = ', '.join(disabilities)

    # Addresses: "same as current" copies the current address here, not in the browser
    values['current_zip_code'] = require_zip('current_zip_code')
    if values['same_address'] == 'yes':
        for field in PERMANENT_ADDRESS_FIELDS:
            values[f'perm_{field}'] = values[f'current_{field}']
        values['perm_zip_code'] = values['current_zip_code']
    else:
        for field in PERMANENT_ADDRESS_FIELDS:
            values[f'perm_{field}'] = require(f'perm_{field}')
        values['perm_zip_code'] = require_zip('perm_zip_code')

    values['father_contact_number'] = contact_number('father_contact_number', required=False)
    values['mother_maiden_contact_number'] = contact_number('mother_maiden_contact_number', required=False)
    values['legal_guardian_contact_number'] = contact_number('legal_guardian_contact_number', required=True)

    # Returning learners must give their last school details; everyone else's are cleared
    values['last_grade_completed'] = ''
    values['last_school_year_completed'] = None
    values['last_school_attended'] = ''
    values['school_id'] = ''
    if values['is_returning'] == 'yes':
        values['last_grade_completed'] = require('last_grade_completed')
        if values['last_grade_completed'] and not re.fullmatch(r'[0-9]', values['last_grade_completed']):
            errors.append('Last grade level completed must be a single digit.')

        last_year = require('last_school_year_completed')
        if last_year:
            match = re.fullmatch(r'([0-9]{4})-([0-9]{4})', last_year)
            if not match or int(match[2]) != int(match[1]) + 1 or not EARLIEST_LAST_SCHOOL_YEAR_END <= int(match[2]) <= today.year - 1:
                errors.append('Last school year completed is not a valid school year.')
        values['last_school_year_completed'] = last_year or None

        values['last_school_attended'] = require('last_school_attended')
        values['school_id'] = require('school_id')
        if values['school_id'] and not re.fullmatch(r'[0-9]{1,6}', values['school_id']):
            errors.append('School ID must be up to 6 digits.')

    values['semester'] = text('semester') or None
    if values['semester'] not in (None, 'first_semester', 'second_semester'):
        errors.append('Semester: please select a valid option.')

    modalities = chosen('distance_learning_modalities', MODALITY_OPTIONS)
    if not modalities:
        errors.append('Please choose at least one distance learning modality.')
    values['distance_learning_modalities'] = ', '.join(modalities)

    values['signature_data'] = form.get('signature_data', '')
    problem = signature_problem(values['signature_data'])
    if problem:
        errors.append(problem)

    # Nothing may be longer than its database column
    for name, value in values.items():
        limit = getattr(Enrollment.__table__.c[name].type, 'length', None)
        if limit and isinstance(value, str) and len(value) > limit:
            errors.append(f'{ENROLLMENT_LABELS.get(name, name)} must be {limit} characters or fewer.')

    return values, errors


def enrollment_form_data(form):
    """What was typed, so a rejected form can be shown again instead of coming back empty."""
    data = {name: form.getlist(name) for name in form if name != 'csrf_token'}
    if signature_problem(form.get('signature_data', '')):
        data.pop('signature_data', None)
        data.pop('date_signed', None)
    return data


# Enrollment View
@main_bp.route("/enrollment", methods=['GET', 'POST'])
def enrollment():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        values, errors = validate_enrollment(request.form)
        if errors:
            flash('Please correct the following: ' + ' '.join(errors), 'danger')
            return render_template('enrollment.html', form_data=enrollment_form_data(request.form)), 400

        try:
            db.session.add(Enrollment(**values))
            db.session.commit()

            flash('Enrollment application submitted successfully!', 'success')
            return redirect(url_for('main.enrollment'))

        except Exception:
            db.session.rollback()
            current_app.logger.exception("Failed to save the enrollment.")
            flash('Could not save the enrollment. Please try again.', 'danger')
            return render_template('enrollment.html', form_data=enrollment_form_data(request.form)), 500
    return render_template('enrollment.html')

# Enrolled Student View
# ENROLLED

FIRST_AUTO_CREATED_YEAR = 2025      # blank rows are only added from this year on, so earlier gaps stay as they are
SCHOOL_YEAR_ROLLOVER_MONTH = 6

@main_bp.route("/enrolled")
def enrolled():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
    
    students = Enrollment.query.order_by(Enrollment.id.desc()).all()

    # Display number of enrollees in terminal for testing
    # print(f"DEBUG: found {len(students)} enrollments")

    return render_template('enrolled.html', students=students)

@main_bp.route("/enrolled/<int:student_id>")
def student_detail(student_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    student = Enrollment.query.get_or_404(student_id)
    return render_template('student.html', student=student)


def student_form_data(student):
    """A saved record in the shape of a submitted form, so the edit page fills in the same way as a rejected form."""
    data = {name: ['' if getattr(student, name) is None else str(getattr(student, name))] for name in ENROLLMENT_LABELS}
    data['birthdate'] = [student.birthdate.isoformat() if student.birthdate else '']
    data['disabilities'] = (student.disabilities or '').replace(', ', ',').split(',')
    data['distance_learning_modalities'] = (student.distance_learning_modalities or '').replace(', ', ',').split(',')
    data['signature_data'] = [student.signature_data or '']
    return data


@main_bp.route("/enrolled/<int:student_id>/edit", methods=['GET', 'POST'])
def edit_student(student_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    student = Enrollment.query.get_or_404(student_id)

    if request.method == 'GET':
        return render_template('student.html', student=student, editing=True, form_data=student_form_data(student))

    def show_rejected(status):
        # A field missing from the submission was left empty, so it comes back empty and not as it was saved
        typed = {**dict.fromkeys(student_form_data(student), ['']), **enrollment_form_data(request.form)}
        return render_template('student.html', student=student, editing=True, rejected=True, form_data=typed), status

    # The age stays the student's age when the form was signed, not their age on the day it is corrected
    values, errors = validate_enrollment(request.form, age_on=student.date_signed)
    if errors:
        flash('Please correct the following: ' + ' '.join(errors), 'danger')
        return show_rejected(400)

    # These record when the form was first submitted, so correcting it later doesn't change them
    del values['school_year'], values['date_signed']

    # The log lists each changed field; the signature only as changed, not the drawing itself
    fields = {name: ENROLLMENT_LABELS.get(name, name.replace('_', ' ').capitalize()) for name in values if name != 'signature_data'}
    before, signature_before = log_snapshot(student, fields), student.signature_data

    try:
        for name, value in values.items():
            setattr(student, name, value)
        changes = log_changes(before, log_snapshot(student, fields))
        if student.signature_data != signature_before:
            changes.append(['Signature', 'Previous signature', 'New signature'])
        log_activity('masterlist', 'UPDATE', f'Edited the enrollment form of {full_name(student)}', changes)
        db.session.commit()
        flash('Enrollment form updated.', 'success')
        return redirect(url_for('main.student_detail', student_id=student.id))

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Failed to update the enrollment.")
        flash('Could not save the changes. Please try again.', 'danger')
        return show_rejected(500)


# Grade View

# GRADES

GRADE_LEVELS = [
    'Kindergarten', 'Grade 1', 'Grade 2', 'Grade 3', 'Grade 4',
    'Grade 5', 'Grade 6'
]

ALLOWED_REPORT_EXTENSIONS = { "xlsx" }

REPORT_MIME_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

MAX_REPORT_SIZE = 10 * 1024 * 1024
MAX_FILENAME_LENGTH = 255


def is_real_document(extension, data):
    """Check the file's contents match its extension, so a renamed file can't get through."""
    if extension == 'pdf':
        return data.startswith(b'%PDF-')

    folders = {'docx': 'word/', 'xlsx': 'xl/'}
    if extension not in folders:
        return False
    try:
        with zipfile.ZipFile(BytesIO(data)) as document:
            names = document.namelist()
    except zipfile.BadZipFile:
        return False
    return '[Content_Types].xml' in names and any(name.startswith(folders[extension]) for name in names)


@main_bp.route("/grades")
def grades():
    # The student list moved to the Masterlist. This stays so old links and bookmarks still work.
    return redirect(url_for('main.enrolled'))

@main_bp.route("/grades/<int:student_id>")
def student_grades(student_id):
    if "user_id" not in session:
        return redirect(url_for("main.login"))

    student = Enrollment.query.get_or_404(student_id)

    reports = {
        level: active(Grades).filter_by(
            student_id=student.id,
            grade_level=level
        ).first()
        for level in GRADE_LEVELS
    }

    return render_template(
        "student_grades.html",
        student=student,
        grade_levels=GRADE_LEVELS,
        reports=reports
    )

@main_bp.route(
    "/grades/<int:student_id>/upload/<string:level>",
    methods=["POST"]
)

def upload_report_card(student_id, level):
    if "user_id" not in session:
        return redirect(url_for("main.login"))

    student = Enrollment.query.get_or_404(student_id)

    if level not in GRADE_LEVELS:
        flash("Invalid grade level.", "danger")
        return redirect(
            url_for("main.student_grades", student_id=student.id)
        )

    uploaded_file = request.files.get("report_card")

    if not uploaded_file or not uploaded_file.filename:
        flash("Please select a report card file.", "warning")
        return redirect(
            url_for("main.student_grades", student_id=student.id)
        )

    filename = secure_filename(uploaded_file.filename)

    if not filename or "." not in filename or len(filename) > MAX_FILENAME_LENGTH:
        flash("Invalid filename.", "danger")
        return redirect(
            url_for("main.student_grades", student_id=student.id)
        )

    extension = filename.rsplit(".", 1)[1].lower()

    if extension not in ALLOWED_REPORT_EXTENSIONS:
        flash(
            "Invalid file type. Upload an Excel (.xlsx) file only",
            "danger",
        )
        return redirect(
            url_for("main.student_grades", student_id=student.id)
        )

    file_data = uploaded_file.read()

    if not file_data:
        flash("The selected file is empty.", "warning")
        return redirect(
            url_for("main.student_grades", student_id=student.id)
        )

    if len(file_data) > MAX_REPORT_SIZE:
        flash("The file must be 10 MB or smaller.", "danger")
        return redirect(
            url_for("main.student_grades", student_id=student.id)
        )

    if not is_real_document(extension, file_data):
        flash("That file is not a valid Excel (.xlsx) file.", "danger")
        return redirect(
            url_for("main.student_grades", student_id=student.id)
        )

    existing_report = Grades.query.filter_by(
        student_id=student.id,
        grade_level=level,
    ).first()

    # One row per student and level (unique_student_grade_level), so an archived one would be overwritten
    if existing_report and existing_report.archived_at:
        flash(
            f"The {level} report card is in the Archives. Restore it or delete it permanently there first.",
            "warning",
        )
        return redirect(
            url_for("main.student_grades", student_id=student.id)
        )

    who = full_name(student)
    try:
        if existing_report:
            old_filename = existing_report.original_filename
            existing_report.original_filename = filename
            existing_report.stored_filename = (
                f"{uuid.uuid4().hex}.{extension}"
            )
            existing_report.file_data = file_data
            existing_report.mime_type = REPORT_MIME_TYPES[extension]
            existing_report.uploaded_at = datetime.utcnow()

            message = f"{level} report card replaced successfully."
            log_activity("masterlist", "UPDATE", f"Replaced the {level} report card of {who}",
                         [["Student", who, who], ["Grade level", level, level], ["File", old_filename, filename]])
        else:
            report = Grades(
                student_id=student.id,
                grade_level=level,
                original_filename=filename,
                stored_filename=f"{uuid.uuid4().hex}.{extension}",
                file_data=file_data,
                mime_type=REPORT_MIME_TYPES[extension],
            )
            db.session.add(report)
            message = f"{level} report card uploaded successfully."
            log_activity("masterlist", "POST", f"Uploaded the {level} report card of {who}",
                         log_changes({}, {"Student": who, **log_snapshot(report, LOG_FIELDS[Grades])}))

        db.session.commit()
        flash(message, "success")

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to store report card in the database."
        )
        flash(
            "Could not save the report card. Please try again.",
            "danger",
        )

    return redirect(
        url_for("main.student_grades", student_id=student.id)
    )


@main_bp.route("/report-cards/<int:report_id>/view")
def view_report_card(report_id):
    """Display a report card retrieved from the MySQL BLOB column."""
    if "user_id" not in session:
        return redirect(url_for("main.login"))

    report = Grades.query.get_or_404(report_id)

    if not report.file_data:
        flash(
            "This report card has no file data stored in the database.",
            "warning",
        )
        return redirect(
            url_for("main.student_grades", student_id=report.student_id)
        )

    return send_file(
        BytesIO(report.file_data),
        mimetype=report.mime_type or "application/octet-stream",
        as_attachment=False,
        download_name=report.original_filename,
    )

@main_bp.route("/report-cards/<int:report_id>/download")
def download_report_card(report_id):
    """Download a report card retrieved from the MySQL BLOB column."""
    if "user_id" not in session:
        return redirect(url_for("main.login"))

    report = Grades.query.get_or_404(report_id)

    if not report.file_data:
        flash(
            "This report card has no file data stored in the database.",
            "warning",
        )
        return redirect(
            url_for("main.student_grades", student_id=report.student_id)
        )

    return send_file(
        BytesIO(report.file_data),
        mimetype=report.mime_type or "application/octet-stream",
        as_attachment=True,
        download_name=report.original_filename,
    )

@main_bp.route(
    "/report-cards/<int:report_id>/delete",
    methods=["POST"]
)
def delete_report_card(report_id):
    """Move the report card to the Archives."""
    if "user_id" not in session:
        return redirect(url_for("main.login"))

    report = active(Grades).filter_by(id=report_id).first_or_404()
    student_id = report.student_id

    # Only the name columns: a full student row carries the signature image
    student = Enrollment.query.with_entities(Enrollment.last_name, Enrollment.first_name).filter_by(id=student_id).one()

    try:
        report.archived_at = datetime.utcnow()
        log_activity("masterlist", "DELETE", f"Moved the {report.grade_level} report card of {full_name(student)} to the Archives",
                     log_changes({"Student": full_name(student), **log_snapshot(report, LOG_FIELDS[Grades])}, {}))
        db.session.commit()
        flash("Report card moved to the Archives.", "success")

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to archive the report card."
        )
        flash("Could not delete the report card. Please try again.", "danger")

    return redirect(
        url_for("main.student_grades", student_id=student_id)
    )

# Calendar View
@main_bp.route("/calendar")
def calendar():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    return render_template('calendar.html')


CALENDAR_TAGS = {'holiday', 'event', 'exam'}
CALENDAR_MIN_YEAR = 1000   # catches typos like 0026 (same limit as calendar.js)
CALENDAR_MAX_DESCRIPTION = 500
 
 
def is_valid_http_url(url):
    """True for a complete http/https link (blocks things like javascript: links)."""
    try:
        parsed = urlparse(url)
        parsed.port                     # raises on a non-numeric port
    except ValueError:                  # e.g. "http://[bad"
        return False
    return parsed.scheme in ('http', 'https') and bool(parsed.netloc) and not any(c.isspace() for c in url)


def _parse_calendar_payload(data):
    """Validate and clean the JSON body. Returns (values, error)."""
    if not isinstance(data, dict):
        return None, 'Invalid data.'

    def text(name):
        value = data.get(name)
        return value.strip() if isinstance(value, str) else ''

    tag = text('tag').lower()
    if tag not in CALENDAR_TAGS:
        return None, 'Invalid tag.'

    link_url = text('link_url')
    if link_url and (len(link_url) > 2048 or not is_valid_http_url(link_url)):
        return None, 'Enter a valid link beginning with http:// or https://'
    try:
        event_date = datetime.strptime(text('date'), '%Y-%m-%d').date()
        # A missing end date means a single-day event
        end_date = datetime.strptime(text('end_date') or text('date'), '%Y-%m-%d').date()
    except ValueError:
        return None, 'Invalid date.'

    if event_date.year < CALENDAR_MIN_YEAR or end_date.year < CALENDAR_MIN_YEAR:
        return None, 'Invalid date.'
    if end_date < event_date:
        return None, 'End date cannot be before the start date.'

    description = text('description')
    if len(description) > CALENDAR_MAX_DESCRIPTION:
        return None, f'Description must be {CALENDAR_MAX_DESCRIPTION} characters or fewer.'
    return {'event_date': event_date, 'end_date': end_date, 'tag': tag, 'description': description, 'link_url': link_url}, None
 
 
@main_bp.route("/calendar/events", methods=['GET', 'POST'])
def calendar_events():
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401
 
    if request.method == 'GET':
        events = active(CalendarEvent).order_by(CalendarEvent.event_date.asc(), CalendarEvent.id.asc()).all()
        return jsonify([e.to_dict() for e in events])
 
    values, error = _parse_calendar_payload(request.get_json(silent=True) or {})
    if error:
        return {'error': error}, 400
 
    event = CalendarEvent(**values)
    db.session.add(event)
    log_activity('calendar', 'POST', f'Added {event_label(event)}', log_changes({}, log_snapshot(event, LOG_FIELDS[CalendarEvent])))
    db.session.commit()
    return jsonify(event.to_dict()), 201
 
 
@main_bp.route("/calendar/events/<int:event_id>", methods=['PUT', 'DELETE'])
def calendar_event_detail(event_id):
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401
 
    event = active(CalendarEvent).filter_by(id=event_id).first_or_404()
 
    if request.method == 'DELETE':
        event.archived_at = datetime.utcnow()
        log_activity('calendar', 'DELETE', f'Moved {event_label(event)} to the Archives',
                     log_changes(log_snapshot(event, LOG_FIELDS[CalendarEvent]), {}))
        db.session.commit()
        return {'success': True}
 
    values, error = _parse_calendar_payload(request.get_json(silent=True) or {})
    if error:
        return {'error': error}, 400
 
    before = log_snapshot(event, LOG_FIELDS[CalendarEvent])
    event.event_date = values['event_date']
    event.end_date = values['end_date']
    event.tag = values['tag']
    event.link_url = values['link_url']
    event.description = values['description']
    log_activity('calendar', 'UPDATE', f'Edited {event_label(event)}',
                 log_changes(before, log_snapshot(event, LOG_FIELDS[CalendarEvent])))
    db.session.commit()
    return jsonify(event.to_dict())


# LINKAGES

FILE_MIME_TYPES = {
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}
ALLOWED_EXTENSIONS = set(FILE_MIME_TYPES)
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TITLE_LENGTH = 150
MAX_LINK_LENGTH = 500


def get_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
 
 
def clean_url(raw):
    """Return a safe http/https link, or None if it isn't valid."""
    url = (raw or '').strip()
    if not url:
        return None
    if '://' not in url:
        url = 'https://' + url          # "example.com" becomes "https://example.com"
    return url if is_valid_http_url(url) else None
 
 
def read_upload(upload):
    """Check an uploaded file. Returns (filename, data, content_type, error)."""
    if not upload or not upload.filename:
        return None, None, None, 'Please choose a file.'
    ext = get_extension(upload.filename)
    if ext not in ALLOWED_EXTENSIONS:
        return None, None, None, 'Only PDF, DOCX and XLSX files are allowed.'
    base = secure_filename(upload.filename.rsplit('.', 1)[0]) or 'file'
    filename = f"{base}.{ext}"
    if len(filename) > MAX_FILENAME_LENGTH:
        return None, None, None, 'That filename is too long.'
    data = upload.read()
    if not data:
        return None, None, None, 'That file is empty.'
    if len(data) > MAX_FILE_SIZE:
        return None, None, None, 'That file is too large. The maximum size is 10 MB.'
    if not is_real_document(ext, data):
        return None, None, None, f'That file is not a valid {ext.upper()} file.'
    return filename, data, FILE_MIME_TYPES[ext], None


@main_bp.app_errorhandler(413)
def file_too_large(error):
    # Needs app.config['MAX_CONTENT_LENGTH'] to be set in create_app()
    if request.is_json:
        return {'error': 'That request is too large.'}, 413
    if request.endpoint == 'main.enrollment':
        flash('That submission is too large.', 'danger')
        return redirect(url_for('main.enrollment'))
    flash('That file is too large. The maximum size is 10 MB.', 'danger')
    if request.endpoint == 'main.upload_report_card':
        return redirect(url_for('main.student_grades', student_id=request.view_args['student_id']))
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkagefiles")
def linkagefiles():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    links = active(LinkItem).order_by(LinkItem.created_at.desc()).all()
    files = active(FileItem).order_by(FileItem.uploaded_at.desc()).all()
    pictures = active(PictureItem).order_by(PictureItem.uploaded_at.desc()).all()

    return render_template(
        'linkagefiles.html',
        links=links,
        files=files,
        pictures=pictures
    )
 
 
# ----- Links -----
 
@main_bp.route("/linkage/links/add", methods=['POST'])
def add_link():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    title = request.form.get('title', '').strip()
    url = clean_url(request.form.get('url'))

    if not title or not url:
        flash('Please enter a title and a valid link (http or https).', 'danger')
    elif len(title) > MAX_TITLE_LENGTH or len(url) > MAX_LINK_LENGTH:
        flash(f'Titles can be up to {MAX_TITLE_LENGTH} characters and links up to {MAX_LINK_LENGTH}.', 'danger')
    else:
        link = LinkItem(title=title, url=url)
        db.session.add(link)
        log_activity('linkage', 'POST', f'Added link {named(title)}', log_changes({}, log_snapshot(link, LOG_FIELDS[LinkItem])))
        db.session.commit()
        flash('Link added.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkage/links/<int:link_id>/edit", methods=['POST'])
def edit_link(link_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    link = active(LinkItem).filter_by(id=link_id).first_or_404()
    title = request.form.get('title', '').strip()
    url = clean_url(request.form.get('url'))
 
    if not title or not url:
        flash('Please enter a title and a valid link (http or https).', 'danger')
    elif len(title) > MAX_TITLE_LENGTH or len(url) > MAX_LINK_LENGTH:
        flash(f'Titles can be up to {MAX_TITLE_LENGTH} characters and links up to {MAX_LINK_LENGTH}.', 'danger')
    else:
        before = log_snapshot(link, LOG_FIELDS[LinkItem])
        link.title = title
        link.url = url
        log_activity('linkage', 'UPDATE', f'Edited link {named(title)}', log_changes(before, log_snapshot(link, LOG_FIELDS[LinkItem])))
        db.session.commit()
        flash('Link updated.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkage/links/<int:link_id>/delete", methods=['POST'])
def delete_link(link_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    link = active(LinkItem).filter_by(id=link_id).first_or_404()
    link.archived_at = datetime.utcnow()
    log_activity('linkage', 'DELETE', f'Moved link {named(link.title)} to the Archives', log_changes(log_snapshot(link, LOG_FIELDS[LinkItem]), {}))
    db.session.commit()
    flash('Link moved to the Archives.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
# ----- Files -----
 
@main_bp.route("/linkage/files/upload", methods=['POST'])
def upload_file():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    filename, data, content_type, error = read_upload(request.files.get('file'))
    if error:
        flash(error, 'danger')
        return redirect(url_for('main.linkagefiles'))
 
    title = request.form.get('title', '').strip() or filename[:MAX_TITLE_LENGTH]
    if len(title) > MAX_TITLE_LENGTH:
        flash(f'Titles can be up to {MAX_TITLE_LENGTH} characters.', 'danger')
        return redirect(url_for('main.linkagefiles'))
    item = FileItem(title=title, filename=filename, content_type=content_type, size=len(data), data=data)
    db.session.add(item)
    log_activity('linkage', 'POST', f'Uploaded file {named(title)}', log_changes({}, log_snapshot(item, LOG_FIELDS[FileItem])))
    db.session.commit()
    flash('File uploaded.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkage/files/<int:file_id>/edit", methods=['POST'])
def edit_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    item = active(FileItem).filter_by(id=file_id).first_or_404()
    title = request.form.get('title', '').strip()
    upload = request.files.get('file')
    before = log_snapshot(item, LOG_FIELDS[FileItem])
 
    if not title:
        flash('Please enter a title.', 'danger')
        return redirect(url_for('main.linkagefiles'))
    if len(title) > MAX_TITLE_LENGTH:
        flash(f'Titles can be up to {MAX_TITLE_LENGTH} characters.', 'danger')
        return redirect(url_for('main.linkagefiles'))

    # Optional: replace the stored file with a new one
    if upload and upload.filename:
        filename, data, content_type, error = read_upload(upload)
        if error:
            flash(error, 'danger')
            return redirect(url_for('main.linkagefiles'))
        item.filename = filename
        item.data = data
        item.content_type = content_type
        item.size = len(data)

    item.title = title
    replaced = f' and replaced it with {named(item.filename)}' if upload and upload.filename else ''
    log_activity('linkage', 'UPDATE', f'Edited file {named(title)}{replaced}', log_changes(before, log_snapshot(item, LOG_FIELDS[FileItem])))
    db.session.commit()
    flash('File updated.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkage/files/<int:file_id>/delete", methods=['POST'])
def delete_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    item = active(FileItem).filter_by(id=file_id).first_or_404()
    item.archived_at = datetime.utcnow()
    log_activity('linkage', 'DELETE', f'Moved file {named(item.title)} to the Archives', log_changes(log_snapshot(item, LOG_FIELDS[FileItem]), {}))
    db.session.commit()
    flash('File moved to the Archives.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkage/files/<int:file_id>/download")
def download_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    item = FileItem.query.get_or_404(file_id)
    return send_file(
        io.BytesIO(item.data),
        as_attachment=True,
        download_name=item.filename,
        mimetype=item.content_type or 'application/octet-stream',
    )

# ----- Pictures -----

ALLOWED_PICTURE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

PICTURE_MIME_TYPES = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'webp': 'image/webp'
}

MAX_PICTURE_SIZE = 5 * 1024 * 1024  # 5 MB


def read_picture(upload):
    """Validate an image and return its filename, data, MIME type, and error."""

    if not upload or not upload.filename:
        return None, None, None, 'Please choose an image.'

    filename = secure_filename(upload.filename)

    if not filename or '.' not in filename or len(filename) > MAX_FILENAME_LENGTH:
        return None, None, None, 'Invalid image filename.'

    extension = filename.rsplit('.', 1)[1].lower()

    if extension not in ALLOWED_PICTURE_EXTENSIONS:
        return None, None, None, 'Only PNG, JPG, JPEG, and WEBP images are allowed.'

    data = upload.read()

    if not data:
        return None, None, None, 'The selected image is empty.'

    if len(data) > MAX_PICTURE_SIZE:
        return None, None, None, 'Image size must not exceed 5 MB.'

    # Basic file signature validation
    valid_signatures = {
        'png': data.startswith(b'\x89PNG\r\n\x1a\n'),
        'jpg': data.startswith(b'\xff\xd8\xff'),
        'jpeg': data.startswith(b'\xff\xd8\xff'),
        'webp': (
            len(data) >= 12
            and data[:4] == b'RIFF'
            and data[8:12] == b'WEBP'
        )
    }

    if not valid_signatures[extension]:
        return None, None, None, 'The uploaded file is not a valid image.'

    return filename, data, PICTURE_MIME_TYPES[extension], None


@main_bp.route("/linkage/pictures/upload", methods=['POST'])
def upload_picture():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    filename, data, content_type, error = read_picture(
        request.files.get('picture')
    )

    if error:
        flash(error, 'danger')
        return redirect(url_for('main.linkagefiles'))

    title = request.form.get('title', '').strip()

    if not title:
        flash('Please enter a picture title.', 'danger')
        return redirect(url_for('main.linkagefiles'))
    if len(title) > MAX_TITLE_LENGTH:
        flash(f'Titles can be up to {MAX_TITLE_LENGTH} characters.', 'danger')
        return redirect(url_for('main.linkagefiles'))

    try:
        picture = PictureItem(
            title=title,
            filename=filename,
            content_type=content_type,
            size=len(data),
            data=data
        )

        db.session.add(picture)
        log_activity('linkage', 'POST', f'Uploaded picture {named(title)}', log_changes({}, log_snapshot(picture, LOG_FIELDS[PictureItem])))
        db.session.commit()

        flash('Picture uploaded successfully.', 'success')

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to upload picture to the database."
        )
        flash('Could not upload the picture. Please try again.', 'danger')

    return redirect(url_for('main.linkagefiles'))


@main_bp.route("/linkage/pictures/<int:picture_id>/view")
def view_picture(picture_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    picture = PictureItem.query.get_or_404(picture_id)

    if not picture.data:
        abort(404)

    return send_file(
        BytesIO(picture.data),
        mimetype=picture.content_type or 'application/octet-stream',
        as_attachment=False
    )


@main_bp.route(
    "/linkage/pictures/<int:picture_id>/delete",
    methods=['POST']
)
def delete_picture(picture_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    picture = active(PictureItem).filter_by(id=picture_id).first_or_404()

    try:
        picture.archived_at = datetime.utcnow()
        log_activity('linkage', 'DELETE', f'Moved picture {named(picture.title)} to the Archives',
                     log_changes(log_snapshot(picture, LOG_FIELDS[PictureItem]), {}))
        db.session.commit()

        flash('Picture moved to the Archives.', 'success')

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to archive the picture."
        )
        flash('Could not delete the picture. Please try again.', 'danger')

    return redirect(url_for('main.linkagefiles'))


# ARCHIVES

# The kind in an archive URL: (model, name used in messages, activity log area, column that names the item)
ARCHIVE_KINDS = {
    'report-cards': (Grades, 'Report card', 'masterlist', 'original_filename'),
    'events': (CalendarEvent, 'Event', 'calendar', 'description'),
    'links': (LinkItem, 'Link', 'linkage', 'title'),
    'files': (FileItem, 'File', 'linkage', 'title'),
    'pictures': (PictureItem, 'Picture', 'linkage', 'title'),
}


def archived(model):
    """Rows in the Archives, most recently deleted first."""
    return model.query.filter(model.archived_at.isnot(None)).order_by(model.archived_at.desc())


@main_bp.route("/archives")
def archives():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    # Only the columns the page shows: a full report card row carries the file itself
    report_cards = archived(Grades).outerjoin(Enrollment, Grades.student_id == Enrollment.id).with_entities(
        Grades.id, Grades.grade_level, Grades.original_filename, Grades.archived_at,
        Enrollment.last_name, Enrollment.first_name,
    ).all()

    return render_template(
        'archives.html',
        report_cards=report_cards,
        events=archived(CalendarEvent).all(),
        links=archived(LinkItem).all(),
        files=archived(FileItem).all(),
        pictures=archived(PictureItem).all(),
    )


def change_archived(kind, item_id, restore):
    """Restores an archived item, or deletes it for good. An item that isn't archived is never touched."""
    if kind not in ARCHIVE_KINDS:
        abort(404)
    model, label, area, name_column = ARCHIVE_KINDS[kind]

    # Queries, so a report card's file is never loaded: only the columns the log lists
    columns = LOG_FIELDS[model]
    rows = model.query.filter(model.id == item_id, model.archived_at.isnot(None))
    values = rows.with_entities(*[getattr(model, column) for column in columns]).first()
    changed = values is not None and (rows.update({'archived_at': None}) if restore else rows.delete())

    # Nothing changed when the item already left the Archives, e.g. a second click or another open tab
    if not changed:
        flash('That item is no longer in the Archives.', 'warning')
        return redirect(url_for('main.archives'))

    snapshot = log_snapshot(values, columns)
    item = f'{label.lower()} {named(getattr(values, name_column))}'.strip()     # an event can have no description
    if restore:
        # The item itself is unchanged, so its values are listed as they are
        details = [['Status', 'In the Archives', 'Restored']] + [[field, value, value] for field, value in snapshot.items() if value]
        log_activity(area, 'UPDATE', f'Restored {item} from the Archives', details)
    else:
        log_activity(area, 'DELETE', f'Permanently deleted {item}', log_changes(snapshot, {}))
    db.session.commit()
    flash(f'{label} restored.' if restore else f'{label} deleted permanently.', 'success')
    return redirect(url_for('main.archives'))


@main_bp.route("/archives/<kind>/<int:item_id>/restore", methods=['POST'])
def restore_archived(kind, item_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    return change_archived(kind, item_id, restore=True)


@main_bp.route("/archives/<kind>/<int:item_id>/delete", methods=['POST'])
def delete_archived(kind, item_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    return change_archived(kind, item_id, restore=False)


@main_bp.route('/welcome')
def landing():
    return render_template('landing.html')