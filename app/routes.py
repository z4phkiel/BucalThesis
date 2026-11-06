from flask import Blueprint, render_template, redirect, request, url_for, session, flash, current_app, send_file, jsonify, abort
from app.models import User, Enrollment, YearlyMetric, Grades, CalendarEvent, LinkItem, FileItem, PictureItem # Make sure to import your User model instead of or alongside myTask
from app import db
from datetime import datetime, timedelta
import base64
import math
import re
import zipfile
import pandas as pd
from PIL import Image
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.metrics import mean_absolute_percentage_error
import os
import io
from io import BytesIO
from werkzeug.utils import secure_filename
import uuid
from urllib.parse import urlparse



main_bp = Blueprint('main', __name__)






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

        # Check if user exists and password matches
        if user and user.check_password(password):
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
 
    for start_year in range(LOCK_BOUNDARY_YEAR + 1, latest + 1):
        label = f"{start_year}-{start_year + 1}"
        if label not in existing:
            db.session.add(YearlyMetric(school_year=label))
 
    db.session.commit()


MAX_ENROLLEE_COUNT = 2147483647     # largest value the INT column holds
MAX_RATE = 150                      # rates can pass 100; this only catches typos such as 985 for 98.5


def _parse_metric_payload(data):
    """Validate the JSON body of a metric update. Returns (values, error)."""
    if not isinstance(data, dict):
        return None, 'Invalid data.'

    values = {}
    for field in METRIC_FIELDS:
        if field not in data:
            continue

        value = data[field]
        label = field.replace('_', ' ').capitalize()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None, f'{label} must be a number.'

        if field == 'enrollee_count':
            if value != int(value) or not 0 <= value <= MAX_ENROLLEE_COUNT:
                return None, f'{label} must be a whole number that is not negative.'
            value = int(value)
        elif not 0 <= value <= MAX_RATE:
            return None, f'{label} must be between 0 and {MAX_RATE}.'

        values[field] = value
    return values, None


@main_bp.route("/metrics/<int:metric_id>/update", methods=['POST'])
def update_metric(metric_id):
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401
 
    metric = YearlyMetric.query.get_or_404(metric_id)
 
    
    start_year = int(metric.school_year.split('-')[0].strip())
    if start_year <= LOCK_BOUNDARY_YEAR:
        return {'error': 'This school year is locked and cannot be edited.'}, 403
 
    values, error = _parse_metric_payload(request.get_json(silent=True) or {})
    if error:
        return {'error': error}, 400

    for field, value in values.items():
        setattr(metric, field, value)

    db.session.commit()
    return {'success': True}

# LINEAR REGRESSION ALGORITHM


FORECAST_FEATURES = [
    'enrollee_count', 'promotion_rate', 'cohort_survival_rate', 'completion_rate',
    'transition_rate', 'dropout_rate', 'graduation_rate', 'retention_rate',
]


@main_bp.route("/")
def index():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    ensure_current_school_year_metric()
    metrics = YearlyMetric.query.order_by(YearlyMetric.school_year.desc()).all()

    all_metrics_asc = YearlyMetric.query.order_by(YearlyMetric.school_year.asc()).all()
    data = [{
        'school_year': m.school_year,
        **{field: getattr(m, field) for field in METRIC_FIELDS},
    } for m in all_metrics_asc]

    pred_next_year = None
    r2_score_val = None
    mape = None
    based_on_year = None
    target_year = None
    forecast_note = None
    actual_year = None
    actual_count = None

    

    if data:
        df = pd.DataFrame(data)
        df[METRIC_FIELDS] = df[METRIC_FIELDS].apply(pd.to_numeric, errors='coerce').fillna(0)   # a blank field counts as 0
        df['start_year'] = df['school_year'].str.split('-').str[0].str.strip().astype(int)

        # One row per calendar year, so shift() can't pair non-consecutive years
        df = df.drop_duplicates('start_year', keep='last').set_index('start_year').sort_index()
        df = df.reindex(range(df.index.min(), df.index.max() + 1))

        # A year's count and rates are submitted together, so they predict the next year's count
        features = FORECAST_FEATURES

        df['next_enrollee_count'] = df['enrollee_count'].shift(-1)

        has_count = df['enrollee_count'] > 0
        train_df = df[has_count & (df['next_enrollee_count'] > 0)]

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

            if len(train_df) <= len(features):
                forecast_note = (
                    f'Not enough complete years: the model has {len(features)} inputs '
                    f'but only {len(train_df)} usable years.'
                )
            else:
                X = train_df[features]
                y = train_df['next_enrollee_count']

                model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))

                cv_pred = cross_val_predict(model, X, y, cv=LeaveOneOut())
                mape = round(float(mean_absolute_percentage_error(y, cv_pred)) * 100, 2)

                model.fit(X, y)
                r2_score_val = round(float(model.score(X, y)), 4)

                pred_next_year = round(float(model.predict(df.loc[[anchor], features])[0]))

    return render_template(
        'dashboard.html',
        username=session['username'],
        metrics=metrics,
        pred_next_year=pred_next_year,
        r2_score=r2_score_val,
        mape=mape,
        based_on_year=based_on_year,
        target_year=target_year,
        forecast_note=forecast_note,
        actual_year=actual_year,
        actual_count=actual_count,
    )

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


def validate_enrollment(form):
    """Check a submitted enrollment. Returns (values for the Enrollment model, list of errors)."""
    errors = []
    values = {}
    today = school_today()

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
            if birthdate > today or birthdate.year < EARLIEST_BIRTH_YEAR:
                errors.append('Birthdate must be a real date that is not in the future.')
            else:
                values['birthdate'] = birthdate
                values['age'] = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
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

LOCK_BOUNDARY_YEAR = 2024
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
        return redirect(url_for('main_login'))

    student = Enrollment.query.get_or_404(student_id)
    return render_template('student.html', student=student)


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
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    students = Enrollment.query.order_by(
        Enrollment.last_name.asc(),
        Enrollment.first_name.asc()
    ).all()

    return render_template(
        'grades.html',
        students=students,
        student=None,
        grade_levels=GRADE_LEVELS,
        reports= {},
        )

@main_bp.route("/grades/<int:student_id>")
def student_grades(student_id):
    if "user_id" not in session:
        return redirect(url_for("main.login"))

    student = Enrollment.query.get_or_404(student_id)

    reports = {
        level: Grades.query.filter_by(
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

    try:
        if existing_report:
            existing_report.original_filename = filename
            existing_report.stored_filename = (
                f"{uuid.uuid4().hex}.{extension}"
            )
            existing_report.file_data = file_data
            existing_report.mime_type = REPORT_MIME_TYPES[extension]
            existing_report.uploaded_at = datetime.utcnow()

            message = f"{level} report card replaced successfully."
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
    """Delete the report-card row and its binary contents from MySQL."""
    if "user_id" not in session:
        return redirect(url_for("main.login"))

    report = Grades.query.get_or_404(report_id)
    student_id = report.student_id

    try:
        db.session.delete(report)
        db.session.commit()
        flash("Report card deleted successfully.", "success")

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to delete report card from the database."
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
        events = CalendarEvent.query.order_by(CalendarEvent.event_date.asc(), CalendarEvent.id.asc()).all()
        return jsonify([e.to_dict() for e in events])
 
    values, error = _parse_calendar_payload(request.get_json(silent=True) or {})
    if error:
        return {'error': error}, 400
 
    event = CalendarEvent(**values)
    db.session.add(event)
    db.session.commit()
    return jsonify(event.to_dict()), 201
 
 
@main_bp.route("/calendar/events/<int:event_id>", methods=['PUT', 'DELETE'])
def calendar_event_detail(event_id):
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401
 
    event = CalendarEvent.query.get_or_404(event_id)
 
    if request.method == 'DELETE':
        db.session.delete(event)
        db.session.commit()
        return {'success': True}
 
    values, error = _parse_calendar_payload(request.get_json(silent=True) or {})
    if error:
        return {'error': error}, 400
 
    event.event_date = values['event_date']
    event.end_date = values['end_date']
    event.tag = values['tag']
    event.link_url = values['link_url']
    event.description = values['description']
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

    links = LinkItem.query.order_by(LinkItem.created_at.desc()).all()
    files = FileItem.query.order_by(FileItem.uploaded_at.desc()).all()
    pictures = PictureItem.query.order_by(PictureItem.uploaded_at.desc()).all()

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
        db.session.add(LinkItem(title=title, url=url))
        db.session.commit()
        flash('Link added.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkage/links/<int:link_id>/edit", methods=['POST'])
def edit_link(link_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    link = LinkItem.query.get_or_404(link_id)
    title = request.form.get('title', '').strip()
    url = clean_url(request.form.get('url'))
 
    if not title or not url:
        flash('Please enter a title and a valid link (http or https).', 'danger')
    elif len(title) > MAX_TITLE_LENGTH or len(url) > MAX_LINK_LENGTH:
        flash(f'Titles can be up to {MAX_TITLE_LENGTH} characters and links up to {MAX_LINK_LENGTH}.', 'danger')
    else:
        link.title = title
        link.url = url
        db.session.commit()
        flash('Link updated.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkage/links/<int:link_id>/delete", methods=['POST'])
def delete_link(link_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    link = LinkItem.query.get_or_404(link_id)
    db.session.delete(link)
    db.session.commit()
    flash('Link deleted.', 'success')
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
    db.session.add(FileItem(title=title, filename=filename, content_type=content_type,
                            size=len(data), data=data))
    db.session.commit()
    flash('File uploaded.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkage/files/<int:file_id>/edit", methods=['POST'])
def edit_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    item = FileItem.query.get_or_404(file_id)
    title = request.form.get('title', '').strip()
    upload = request.files.get('file')
 
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
    db.session.commit()
    flash('File updated.', 'success')
    return redirect(url_for('main.linkagefiles'))
 
 
@main_bp.route("/linkage/files/<int:file_id>/delete", methods=['POST'])
def delete_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('main.login'))
 
    item = FileItem.query.get_or_404(file_id)
    db.session.delete(item)
    db.session.commit()
    flash('File deleted.', 'success')
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

    picture = PictureItem.query.get_or_404(picture_id)

    try:
        db.session.delete(picture)
        db.session.commit()

        flash('Picture deleted successfully.', 'success')

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Failed to delete picture from the database."
        )
        flash('Could not delete the picture. Please try again.', 'danger')

    return redirect(url_for('main.linkagefiles'))

@main_bp.route('/welcome')
def landing():
    return render_template('landing.html')