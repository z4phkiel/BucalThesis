from flask import Blueprint, render_template, redirect, request, url_for, session, flash, current_app, send_file, jsonify, abort
from app.models import User, Enrollment, YearlyMetric, Grades, CalendarEvent, LinkItem, FileItem, PictureItem # Make sure to import your User model instead of or alongside myTask
from app import db
from datetime import datetime 
import pandas as pd
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
        username = request.form.get('username')
        password = request.form.get('password')

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

@main_bp.route("/metrics/<int:metric_id>/update", methods=['POST'])
def update_metric(metric_id):
    if 'user_id' not in session:
        return {'error': 'Unauthorized'}, 401
 
    metric = YearlyMetric.query.get_or_404(metric_id)
 
    
    start_year = int(metric.school_year.split('-')[0].strip())
    if start_year <= LOCK_BOUNDARY_YEAR:
        return {'error': 'This school year is locked and cannot be edited.'}, 403
 
    data = request.get_json(silent=True) or {}
    for field in METRIC_FIELDS:
        if field in data:
            setattr(metric, field, data[field])
 
    db.session.commit()
    return {'success': True}

@main_bp.route("/")
def index():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    ensure_current_school_year_metric()
    metrics = YearlyMetric.query.order_by(YearlyMetric.school_year.desc()).all()

    all_metrics_asc = YearlyMetric.query.order_by(YearlyMetric.school_year.asc()).all()
    data = [{
        'school_year': m.school_year,
        'enrollee_count': m.enrollee_count,
        'promotion_rate': m.promotion_rate,
        'dropout_rate': m.dropout_rate,
    } for m in all_metrics_asc]

    pred_next_year = None
    r2_score_val = None
    mape = None
    based_on_year = None

    features = ['enrollee_count', 'promotion_rate', 'dropout_rate']

    if data:
        df = pd.DataFrame(data).sort_values('school_year').reset_index(drop=True)
        df['next_enrollee_count'] = df['enrollee_count'].shift(-1)

        complete = (df['enrollee_count'] > 0) & (df['promotion_rate'] > 0)
        train_df = df[complete & (df['next_enrollee_count'] > 0)]

        if len(train_df) >= 5:
            X = train_df[features].astype(float)
            y = train_df['next_enrollee_count'].astype(float)

            model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))

            # honest error estimate
            cv_pred = cross_val_predict(model, X, y, cv=LeaveOneOut())
            mape = round(float(mean_absolute_percentage_error(y, cv_pred)) * 100, 2)

            model.fit(X, y)
            r2_score_val = round(float(model.score(X, y)), 4)

            latest = df[complete].iloc[[-1]]
            pred_next_year = round(float(model.predict(latest[features].astype(float))[0]))
            based_on_year = latest['school_year'].iloc[0]

    return render_template(
        'dashboard.html',
        username=session['username'],
        metrics=metrics,
        pred_next_year=pred_next_year,
        r2_score=r2_score_val,
        mape=mape,
        based_on_year=based_on_year,
    )

@main_bp.route("/test_signatures")
def test_signatures():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    enrollments = Enrollment.query.order_by(Enrollment.id.desc()).all()
    return render_template('test_signatures.html', enrollments=enrollments)

# Enrollment View
@main_bp.route("/enrollment", methods=['GET', 'POST'])
def enrollment():
    if 'user_id' not in session:
        return redirect(url_for('main.login'))

    if request.method == 'POST':
        try:
            # Handle list inputs (checkboxes)
            disabilities_list = request.form.getlist('disabilities')
            modalities_list = request.form.getlist('distance_learning_modalities')

            # Parse birthdate
            birthdate_str = request.form.get('birthdate')
            birthdate_val = datetime.strptime(birthdate_str, '%Y-%m-%d').date() if birthdate_str else None

            # Parse date signed
            date_signed_str = request.form.get('date_signed')
            date_signed_val = None
            if date_signed_str:
                try:
                    date_signed_val = datetime.strptime(date_signed_str, '%Y-%m-%d').date()
                except ValueError:
                    # Alternative format fallback (e.g., MM/DD/YYYY)
                    date_signed_val = datetime.strptime(date_signed_str, '%m/%d/%Y').date()

            # Create new record
            new_enrollment = Enrollment(
                school_year=request.form.get('school_year'),
                grade_level=request.form.get('grade_level'),
                has_lrn=request.form.get('has_lrn'),
                is_returning=request.form.get('is_returning'),
                psa_birth_cert_no=request.form.get('psa_birth_cert_no'),
                lrn_no=request.form.get('lrn_no'),
                last_name=request.form.get('last_name'),
                first_name=request.form.get('first_name'),
                middle_name=request.form.get('middle_name'),
                extension_name=request.form.get('extension_name'),
                birthdate=birthdate_val,
                birth_place=request.form.get('birth_place'),
                sex=request.form.get('sex'),
                age=request.form.get('age'),
                mother_tongue=request.form.get('mother_tongue'),
                is_ip=request.form.get('is_ip'),
                ip_community=request.form.get('ip_community'),
                is_4ps=request.form.get('is_4ps'),
                four_ps_id_no=request.form.get('four_ps_id_no'),
                is_lwd=request.form.get('is_lwd'),
                disabilities=", ".join(disabilities_list),
                current_house_no=request.form.get('current_house_no'),
                current_street_name=request.form.get('current_street_name'),
                current_barangay=request.form.get('current_barangay'),
                current_municipality_city=request.form.get('current_municipality_city'),
                current_province=request.form.get('current_province'),
                current_country=request.form.get('current_country'),
                current_zip_code=request.form.get('current_zip_code'),
                same_address=request.form.get('same_address'),
                perm_house_no=request.form.get('perm_house_no'),
                perm_street_name=request.form.get('perm_street_name'),
                perm_barangay=request.form.get('perm_barangay'),
                perm_municipality_city=request.form.get('perm_municipality_city'),
                perm_province=request.form.get('perm_province'),
                perm_country=request.form.get('perm_country'),
                perm_zip_code=request.form.get('perm_zip_code'),
                father_last_name=request.form.get('father_last_name'),
                father_first_name=request.form.get('father_first_name'),
                father_middle_name=request.form.get('father_middle_name'),
                father_contact_number=request.form.get('father_contact_number'),
                mother_maiden_last_name=request.form.get('mother_maiden_last_name'),
                mother_maiden_first_name=request.form.get('mother_maiden_first_name'),
                mother_maiden_middle_name=request.form.get('mother_maiden_middle_name'),
                mother_maiden_contact_number=request.form.get('mother_maiden_contact_number'),
                legal_guardian_last_name=request.form.get('legal_guardian_last_name'),
                legal_guardian_first_name=request.form.get('legal_guardian_first_name'),
                legal_guardian_middle_name=request.form.get('legal_guardian_middle_name'),
                legal_guardian_contact_number=request.form.get('legal_guardian_contact_number'),
                last_grade_completed=request.form.get('last_grade_completed'),
                last_school_year_completed=request.form.get('last_school_year_completed'),
                last_school_attended=request.form.get('last_school_attended'),
                school_id=request.form.get('school_id'),
                semester=request.form.get('semester'),
                track=request.form.get('track'),
                strand=request.form.get('strand'),
                distance_learning_modalities=", ".join(modalities_list),
                signature_data=request.form.get('signature_data'),
                parent_guardian_name=request.form.get('parent_guardian_name'),
                date_signed=date_signed_val
            )

            db.session.add(new_enrollment)
            db.session.commit()

            flash('Enrollment application submitted successfully!', 'success')
            return redirect(url_for('main.enrollment'))

        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while saving the data: {str(e)}', 'danger')
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

MAX_REPORT_SIZE = 16 * 1024 * 1024

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

    if not filename or "." not in filename:
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
        flash("The file must be 16 MB or smaller.", "danger")
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
 
 
def _parse_calendar_payload(data):
    """Validate and clean the JSON body. Returns (values, error)."""
    tag = (data.get('tag') or '').strip().lower()
    if tag not in CALENDAR_TAGS:
        return None, 'Invalid tag.'

    link_url = (data.get('link_url') or '').strip()
    if link_url:
        parsed_url = urlparse(link_url)

        if parsed_url.scheme not in ('http', 'https') or not parsed_url.netloc:
            raise ValueError("Enter a valid URL beginning with http:// or https://")
    try:
        event_date = datetime.strptime(data.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        return None, 'Invalid date.'
 
    description = (data.get('description') or '').strip()[:500]
    return {'event_date': event_date, 'tag': tag, 'description': description, 'link_url': link_url}, None
 
 
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
    event.tag = values['tag']
    event.description = values['description']
    db.session.commit()
    return jsonify(event.to_dict())


# LINKAGES

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'pptx'}
 
 
def get_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
 
 
def clean_url(raw):
    """Return a safe http/https link, or None if it isn't valid."""
    url = (raw or '').strip()
    if not url:
        return None
    if '://' not in url:
        url = 'https://' + url          # "example.com" becomes "https://example.com"
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return None                     # blocks things like javascript: links
    return url
 
 
def read_upload(upload):
    """Check an uploaded file. Returns (filename, data, content_type, error)."""
    if not upload or not upload.filename:
        return None, None, None, 'Please choose a file.'
    ext = get_extension(upload.filename)
    if ext not in ALLOWED_EXTENSIONS:
        return None, None, None, 'Only PDF, DOCX and XLSX files are allowed.'
    base = secure_filename(upload.filename.rsplit('.', 1)[0]) or 'file'
    data = upload.read()
    if not data:
        return None, None, None, 'That file is empty.'
    return f"{base}.{ext}", data, upload.mimetype, None
 
 
@main_bp.app_errorhandler(413)
def file_too_large(error):
    # Needs app.config['MAX_CONTENT_LENGTH'] to be set in create_app()
    flash('That file is too large. The maximum size is 10 MB.', 'danger')
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
 
    title = request.form.get('title', '').strip() or filename
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

    if not filename or '.' not in filename:
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