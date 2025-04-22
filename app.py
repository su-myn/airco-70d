from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from functools import wraps
import os
import pytz
from models import db, User, Complaint, Issue, Repair, Replacement, Company, Role, Unit, AccountType, IssueItem, BookingForm, CalendarSource, Contact
from models import Category, ReportedBy, Priority, Status, Type, ExpenseData
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import requests
from icalendar import Calendar

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///propertyhub.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

# Initialize extensions
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
#db.init_app(app)


# Add template filter for Malaysia timezone
@app.template_filter('malaysia_time')
def malaysia_time_filter(utc_dt):
    """Convert UTC datetime to Malaysia timezone"""
    if utc_dt is None:
        return ""
    malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)
    malaysia_time = utc_dt.astimezone(malaysia_tz)
    return malaysia_time.strftime('%b %d, %Y, %I:%M %p')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Permission-based decorators
def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_permission(permission):
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)

    return decorated_function


# Specific permission decorators
def complaints_view_required(f):
    return permission_required('can_view_complaints')(f)


def complaints_manage_required(f):
    return permission_required('can_manage_complaints')(f)


def issues_view_required(f):
    return permission_required('can_view_issues')(f)


def issues_manage_required(f):
    return permission_required('can_manage_issues')(f)


def repairs_view_required(f):
    return permission_required('can_view_repairs')(f)


def repairs_manage_required(f):
    return permission_required('can_manage_repairs')(f)


def replacements_view_required(f):
    return permission_required('can_view_replacements')(f)


def replacements_manage_required(f):
    return permission_required('can_manage_replacements')(f)


def check_unit_availability(unit_id, check_in_date, check_out_date, exclude_booking_id=None):
    """
    Check if a unit is available for the given date range
    Returns True if available, False if there's a conflict
    """
    # Query for overlapping bookings
    query = BookingForm.query.filter(
        BookingForm.unit_id == unit_id,
        BookingForm.check_in_date < check_out_date,
        BookingForm.check_out_date > check_in_date
    )

    # Exclude the current booking if we're updating
    if exclude_booking_id:
        query = query.filter(BookingForm.id != exclude_booking_id)

    # If any booking exists in this range, the unit is not available
    return query.count() == 0



@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash('You have been logged in successfully', 'success')

            # Redirect cleaners to their dashboard
            if user.is_cleaner:
                return redirect(url_for('cleaner_dashboard'))

            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login failed. Please check your email and password', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check if password and confirm_password match
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('register'))

        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already registered. Please use a different email or login', 'danger')
            return redirect(url_for('register'))

        # Get default company and role
        default_company = Company.query.first()
        if not default_company:
            default_company = Company(name="Default Company")
            db.session.add(default_company)
            db.session.commit()

        # Find a non-admin role
        user_role = Role.query.filter_by(name="Manager").first()
        if not user_role:
            user_role = Role.query.filter(Role.is_admin.is_(False)).first()
        if not user_role:
            # If no non-admin role exists, create a basic user role
            user_role = Role(name="User",
                             can_view_complaints=True,
                             can_view_issues=True,
                             can_view_repairs=True,
                             can_view_replacements=True)
            db.session.add(user_role)
            db.session.commit()

        # Get default account type (Standard)
        default_account_type = AccountType.query.filter_by(name="Standard Account").first()
        if not default_account_type:
            default_account_type = AccountType.query.first()

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
            company_id=default_company.id,
            role_id=user_role.id,
            account_type_id=default_account_type.id  # Set default account type
        )

        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! You can now sign in', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    # Redirect cleaners to cleaner dashboard
    if current_user.is_cleaner:
        return redirect(url_for('cleaner_dashboard'))

    # Filter records to only show those belonging to the user's company
    # but respect the role permissions
    user_company_id = current_user.company_id

    complaints = []
    repairs = []
    replacements = []
    units = []

    if current_user.has_permission('can_view_complaints'):
        complaints = Complaint.query.filter_by(company_id=user_company_id).all()

    if current_user.has_permission('can_view_issues'):
        issues = Issue.query.filter_by(company_id=user_company_id).all()

    if current_user.has_permission('can_view_repairs'):
        repairs = Repair.query.filter_by(company_id=user_company_id).all()

    if current_user.has_permission('can_view_replacements'):
        replacements = Replacement.query.filter_by(company_id=user_company_id).all()

    # Get units for this company
    units = Unit.query.filter_by(company_id=user_company_id).all()

    return render_template('dashboard.html', complaints=complaints, repairs=repairs, replacements=replacements,
                           units=units)



# I add (Manually)
@app.route('/issues')
@login_required
@issues_view_required
def issues():
    # Filter records to only show those belonging to the user's company
    user_company_id = current_user.company_id
    issues = []

    if current_user.has_permission('can_view_issues'):
        issues = Issue.query.filter_by(company_id=user_company_id).all()

    # Get units for this company for the form
    units = Unit.query.filter_by(company_id=user_company_id).all()

    # Get categories, priorities, statuses, etc.
    categories = Category.query.all()
    reported_by_options = ReportedBy.query.all()
    priorities = Priority.query.all()
    statuses = Status.query.all()
    types = Type.query.all()

    # Get issue items with their categories
    issue_items_by_category = {}
    for category in categories:
        issue_items_by_category[category.id] = IssueItem.query.filter_by(category_id=category.id).all()

    # Add current date/time for template calculations
    now = datetime.now()

    return render_template('issues.html',
                           issues=issues,
                           units=units,
                           categories=categories,
                           reported_by_options=reported_by_options,
                           priorities=priorities,
                           statuses=statuses,
                           types=types,
                           issue_items_by_category=issue_items_by_category,
                           now=now,
                           timedelta=timedelta)


# Update your add_issue route to handle the issue_item field:
@app.route('/add_issue', methods=['POST'])
@login_required
@permission_required('can_manage_issues')
def add_issue():
    description = request.form['description']
    unit_id = request.form['unit_id']

    # New fields
    category_id = request.form.get('category_id') or None
    reported_by_id = request.form.get('reported_by_id') or None
    priority_id = request.form.get('priority_id') or None
    status_id = request.form.get('status_id') or None
    type_id = request.form.get('type_id') or None
    issue_item_id = request.form.get('issue_item_id') or None

    # Handle custom issue item
    custom_issue = request.form.get('custom_issue', '').strip()
    if custom_issue and category_id:
        # Check if this custom issue already exists
        existing_item = IssueItem.query.filter_by(name=custom_issue, category_id=category_id).first()
        if existing_item:
            issue_item_id = existing_item.id
        else:
            # Create a new issue item
            new_issue_item = IssueItem(name=custom_issue, category_id=category_id)
            db.session.add(new_issue_item)
            db.session.flush()  # Get the ID before committing
            issue_item_id = new_issue_item.id

    solution = request.form.get('solution', '')
    guest_name = request.form.get('guest_name', '')

    # Fix for cost field - convert empty string to None
    cost_value = request.form.get('cost', '')
    cost = float(cost_value) if cost_value.strip() else None

    assigned_to = request.form.get('assigned_to', '')

    # Get the unit number from the selected unit
    unit = Unit.query.get(unit_id)
    if not unit:
        flash('Invalid unit selected', 'danger')
        return redirect(url_for('issues'))

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to add issues for this unit', 'danger')
        return redirect(url_for('issues'))

    new_issue = Issue(
        description=description,
        unit=unit.unit_number,
        unit_id=unit_id,
        category_id=category_id,
        reported_by_id=reported_by_id,
        priority_id=priority_id,
        status_id=status_id,
        type_id=type_id,
        issue_item_id=issue_item_id,
        solution=solution,
        guest_name=guest_name,
        cost=cost,
        assigned_to=assigned_to,
        author=current_user,
        company_id=current_user.company_id
    )
    db.session.add(new_issue)
    db.session.commit()

    flash('Issue added successfully', 'success')
    return redirect(url_for('issues'))


# Update your update_issue route to handle the issue_item field:
@app.route('/update_issue/<int:id>', methods=['POST'])
@login_required
@permission_required('can_manage_issues')
def update_issue(id):
    issue = Issue.query.get_or_404(id)

    # Ensure the current user's company matches the issue's company
    if issue.company_id != current_user.company_id:
        flash('You are not authorized to update this issue', 'danger')
        return redirect(url_for('issues'))

    unit_id = request.form.get('unit_id')

    # Get the unit if unit_id is provided
    if unit_id:
        unit = Unit.query.get(unit_id)
        if not unit:
            flash('Invalid unit selected', 'danger')
            return redirect(url_for('issues'))

        # Check if the unit belongs to the user's company
        if unit.company_id != current_user.company_id:
            flash('You do not have permission to use this unit', 'danger')
            return redirect(url_for('issues'))

        issue.unit = unit.unit_number
        issue.unit_id = unit_id

    # Update fields
    issue.description = request.form['description']

    # Handle optional fields
    issue.category_id = request.form.get('category_id') or None
    issue.reported_by_id = request.form.get('reported_by_id') or None
    issue.priority_id = request.form.get('priority_id') or None
    issue.status_id = request.form.get('status_id') or None
    issue.type_id = request.form.get('type_id') or None

    # Handle issue item
    issue_item_id = request.form.get('issue_item_id') or None
    custom_issue = request.form.get('custom_issue', '').strip()

    if custom_issue and issue.category_id:
        # Check if this custom issue already exists
        existing_item = IssueItem.query.filter_by(name=custom_issue, category_id=issue.category_id).first()
        if existing_item:
            issue_item_id = existing_item.id
        else:
            # Create a new issue item
            new_issue_item = IssueItem(name=custom_issue, category_id=issue.category_id)
            db.session.add(new_issue_item)
            db.session.flush()  # Get the ID before committing
            issue_item_id = new_issue_item.id

    issue.issue_item_id = issue_item_id
    issue.solution = request.form.get('solution', '')
    issue.guest_name = request.form.get('guest_name', '')

    # Fix for cost field
    cost_value = request.form.get('cost', '')
    issue.cost = float(cost_value) if cost_value.strip() else None

    issue.assigned_to = request.form.get('assigned_to', '')

    db.session.commit()
    flash('Issue updated successfully', 'success')
    return redirect(url_for('issues'))


@app.route('/delete_issue/<int:id>')
@login_required
@permission_required('can_manage_issues')
def delete_issue(id):
    issue = Issue.query.get_or_404(id)

    # Ensure the current user's company matches the issue's company
    if issue.company_id != current_user.company_id:
        flash('You are not authorized to delete this issue', 'danger')
        return redirect(url_for('issues'))

    db.session.delete(issue)
    db.session.commit()

    flash('Issue deleted successfully', 'success')
    return redirect(url_for('issues'))


# Add a new API endpoint to get issue items for a category:
@app.route('/api/get_issue_items/<int:category_id>')
@login_required
def get_issue_items(category_id):
    issue_items = IssueItem.query.filter_by(category_id=category_id).all()
    items_list = [{'id': item.id, 'name': item.name} for item in issue_items]
    return jsonify(items_list)


# Update your get_issue API endpoint to include issue_item_id:
@app.route('/api/issue/<int:id>')
@login_required
@permission_required('can_view_issues')
def get_issue(id):
    issue = Issue.query.get_or_404(id)

    # Ensure the current user's company matches the issue's company
    if issue.company_id != current_user.company_id:
        return jsonify({'error': 'Not authorized'}), 403

    return jsonify({
        'id': issue.id,
        'description': issue.description,
        'unit_id': issue.unit_id,
        'category_id': issue.category_id,
        'reported_by_id': issue.reported_by_id,
        'priority_id': issue.priority_id,
        'status_id': issue.status_id,
        'type_id': issue.type_id,
        'issue_item_id': issue.issue_item_id,
        'solution': issue.solution,
        'guest_name': issue.guest_name,
        'cost': float(issue.cost) if issue.cost else 0,
        'assigned_to': issue.assigned_to
    })

# Create routes for unit management
@app.route('/manage_units')
@login_required
def manage_units():
    # Redirect cleaners to cleaner dashboard
    if current_user.is_cleaner:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('cleaner_dashboard'))

    # Get current user's units
    user_company_id = current_user.company_id
    units = Unit.query.filter_by(company_id=user_company_id).all()

    return render_template('manage_units.html', units=units)




# Modify the edit_unit route in app.py to handle the address field
# Find the existing route and update it:

@app.route('/edit_unit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_unit(id):
    unit = Unit.query.get_or_404(id)

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to edit this unit', 'danger')
        return redirect(url_for('manage_units'))

    if request.method == 'POST':
        unit.unit_number = request.form['unit_number']
        unit.building = request.form['building']
        unit.address = request.form.get('address')  # Add this line
        unit.is_occupied = 'is_occupied' in request.form

        # Update new fields
        # Process the new fields
        unit.letterbox_code = request.form.get('letterbox_code') or None
        unit.smartlock_code = request.form.get('smartlock_code') or None
        unit.wifi_name = request.form.get('wifi_name') or None
        unit.wifi_password = request.form.get('wifi_password') or None

        # Handle numeric fields
        bedrooms = request.form.get('bedrooms') or None
        if bedrooms:
            unit.bedrooms = int(bedrooms)
        else:
            unit.bedrooms = None

        bathrooms = request.form.get('bathrooms') or None
        if bathrooms:
            unit.bathrooms = float(bathrooms)
        else:
            unit.bathrooms = None

        sq_ft = request.form.get('sq_ft') or None
        if sq_ft:
            unit.sq_ft = int(sq_ft)
        else:
            unit.sq_ft = None

        # Original fields
        toilet_count = request.form.get('toilet_count') or None
        if toilet_count:
            unit.toilet_count = int(toilet_count)
        else:
            unit.toilet_count = None

        towel_count = request.form.get('towel_count') or None
        if towel_count:
            unit.towel_count = int(towel_count)
        else:
            unit.towel_count = None

        # New supply defaults
        default_toilet_paper = request.form.get('default_toilet_paper') or None
        if default_toilet_paper:
            unit.default_toilet_paper = int(default_toilet_paper)
        else:
            unit.default_toilet_paper = None

        default_towel = request.form.get('default_towel') or None
        if default_towel:
            unit.default_towel = int(default_towel)
        else:
            unit.default_towel = None

        default_garbage_bag = request.form.get('default_garbage_bag') or None
        if default_garbage_bag:
            unit.default_garbage_bag = int(default_garbage_bag)
        else:
            unit.default_garbage_bag = None

        monthly_rent = request.form.get('monthly_rent') or None
        if monthly_rent:
            unit.monthly_rent = float(monthly_rent)
        else:
            unit.monthly_rent = None

        max_pax = request.form.get('max_pax') or None
        if max_pax:
            unit.max_pax = int(max_pax)
        else:
            unit.max_pax = None

        db.session.commit()
        flash('Unit updated successfully', 'success')
        return redirect(url_for('manage_units'))

    return render_template('edit_unit_user.html', unit=unit)

@app.route('/delete_unit/<int:id>')
@login_required
def delete_unit(id):
    unit = Unit.query.get_or_404(id)

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to delete this unit', 'danger')
        return redirect(url_for('manage_units'))

    # Check if unit is in use
    if unit.complaints or unit.repairs or unit.replacements:
        flash('Cannot delete unit that is referenced by complaints, repairs, or replacements', 'danger')
        return redirect(url_for('manage_units'))

    db.session.delete(unit)
    db.session.commit()

    flash('Unit deleted successfully', 'success')
    return redirect(url_for('manage_units'))


# API route to get units for the current user's company
@app.route('/api/get_units')
@login_required
def get_units():
    company_id = current_user.company_id
    units = Unit.query.filter_by(company_id=company_id).all()
    units_list = [{'id': unit.id, 'unit_number': unit.unit_number} for unit in units]
    return jsonify(units_list)


# Repair routes
@app.route('/add_repair', methods=['POST'])
@login_required
@permission_required('can_manage_repairs')
def add_repair():
    item = request.form['item']
    remark = request.form['remark']
    unit_id = request.form['unit_id']
    status = request.form['status']

    # Get the unit
    unit = Unit.query.get(unit_id)
    if not unit:
        flash('Invalid unit selected', 'danger')
        return redirect(url_for('dashboard'))

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to add repairs for this unit', 'danger')
        return redirect(url_for('dashboard'))

    new_repair = Repair(
        item=item,
        remark=remark,
        unit=unit.unit_number,  # Keep the unit number for backward compatibility
        unit_id=unit_id,  # Store the reference to the unit model
        status=status,
        author=current_user,
        company_id=current_user.company_id
    )
    db.session.add(new_repair)
    db.session.commit()

    flash('Repair request added successfully', 'success')
    return redirect(url_for('dashboard'))


@app.route('/update_repair/<int:id>', methods=['POST'])
@login_required
@permission_required('can_manage_repairs')
def update_repair(id):
    repair = Repair.query.get_or_404(id)

    # Ensure the current user's company matches the repair's company
    if repair.company_id != current_user.company_id:
        flash('You are not authorized to update this repair request', 'danger')
        return redirect(url_for('dashboard'))

    unit_id = request.form.get('unit_id')

    # Get the unit if unit_id is provided
    if unit_id:
        unit = Unit.query.get(unit_id)
        if not unit:
            flash('Invalid unit selected', 'danger')
            return redirect(url_for('dashboard'))

        # Check if the unit belongs to the user's company
        if unit.company_id != current_user.company_id:
            flash('You do not have permission to use this unit', 'danger')
            return redirect(url_for('dashboard'))

        repair.unit = unit.unit_number
        repair.unit_id = unit_id

    repair.item = request.form['item']
    repair.remark = request.form['remark']
    repair.status = request.form['status']

    db.session.commit()
    flash('Repair request updated successfully', 'success')
    return redirect(url_for('dashboard'))


@app.route('/delete_repair/<int:id>')
@login_required
@permission_required('can_manage_repairs')
def delete_repair(id):
    repair = Repair.query.get_or_404(id)

    # Ensure the current user's company matches the repair's company
    if repair.company_id != current_user.company_id:
        flash('You are not authorized to delete this repair request', 'danger')
        return redirect(url_for('dashboard'))

    db.session.delete(repair)
    db.session.commit()

    flash('Repair request deleted successfully', 'success')
    return redirect(url_for('dashboard'))


# Replacement routes
@app.route('/add_replacement', methods=['POST'])
@login_required
@permission_required('can_manage_replacements')
def add_replacement():
    item = request.form['item']
    remark = request.form['remark']
    unit_id = request.form['unit_id']
    status = request.form['status']

    # Get the unit
    unit = Unit.query.get(unit_id)
    if not unit:
        flash('Invalid unit selected', 'danger')
        return redirect(url_for('dashboard'))

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to add replacements for this unit', 'danger')
        return redirect(url_for('dashboard'))

    new_replacement = Replacement(
        item=item,
        remark=remark,
        unit=unit.unit_number,  # Keep the unit number for backward compatibility
        unit_id=unit_id,  # Store the reference to the unit model
        status=status,
        author=current_user,
        company_id=current_user.company_id
    )
    db.session.add(new_replacement)
    db.session.commit()

    flash('Replacement request added successfully', 'success')
    return redirect(url_for('dashboard'))


@app.route('/update_replacement/<int:id>', methods=['POST'])
@login_required
@permission_required('can_manage_replacements')
def update_replacement(id):
    replacement = Replacement.query.get_or_404(id)

    # Ensure the current user's company matches the replacement's company
    if replacement.company_id != current_user.company_id:
        flash('You are not authorized to update this replacement request', 'danger')
        return redirect(url_for('dashboard'))

    unit_id = request.form.get('unit_id')

    # Get the unit if unit_id is provided
    if unit_id:
        unit = Unit.query.get(unit_id)
        if not unit:
            flash('Invalid unit selected', 'danger')
            return redirect(url_for('dashboard'))

        # Check if the unit belongs to the user's company
        if unit.company_id != current_user.company_id:
            flash('You do not have permission to use this unit', 'danger')
            return redirect(url_for('dashboard'))

        replacement.unit = unit.unit_number
        replacement.unit_id = unit_id

    replacement.item = request.form['item']
    replacement.remark = request.form['remark']
    replacement.status = request.form['status']

    db.session.commit()
    flash('Replacement request updated successfully', 'success')
    return redirect(url_for('dashboard'))


@app.route('/delete_replacement/<int:id>')
@login_required
@permission_required('can_manage_replacements')
def delete_replacement(id):
    replacement = Replacement.query.get_or_404(id)

    # Ensure the current user's company matches the replacement's company
    if replacement.company_id != current_user.company_id:
        flash('You are not authorized to delete this replacement request', 'danger')
        return redirect(url_for('dashboard'))

    db.session.delete(replacement)
    db.session.commit()

    flash('Replacement request deleted successfully', 'success')
    return redirect(url_for('dashboard'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))


# Admin routes
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.query.all()
    companies = Company.query.all()
    roles = Role.query.all()
    complaints = Complaint.query.all()
    repairs = Repair.query.all()
    replacements = Replacement.query.all()
    units = Unit.query.all()
    issues = Issue.query.all()

    # Get count of each type by company
    company_stats = []
    for company in companies:
        company_users = User.query.filter_by(company_id=company.id).count()
        company_complaints = Complaint.query.filter_by(company_id=company.id).count()
        company_issues = Issue.query.filter_by(company_id=company.id).count()
        company_repairs = Repair.query.filter_by(company_id=company.id).count()
        company_replacements = Replacement.query.filter_by(company_id=company.id).count()
        company_units = Unit.query.filter_by(company_id=company.id).count()

        company_stats.append({
            'name': company.name,
            'users': company_users,
            'complaints': company_complaints,
            'issues': company_issues,
            'repairs': company_repairs,
            'replacements': company_replacements,
            'units': company_units
        })

    return render_template('admin/dashboard.html',
                           users=users,
                           companies=companies,
                           roles=roles,
                           complaints=complaints,
                           issues=issues,
                           repairs=repairs,
                           replacements=replacements,
                           units=units,
                           company_stats=company_stats)


# Admin routes for units
@app.route('/admin/units')
@login_required
@admin_required
def admin_units():
    units = Unit.query.all()
    return render_template('admin/units.html', units=units)


# Modify the add_unit route in app.py to handle the address field
# Find the existing route and update it:

@app.route('/add_unit', methods=['GET', 'POST'])
@login_required
def add_unit():
    if request.method == 'POST':
        unit_number = request.form['unit_number']
        building = request.form['building']
        address = request.form.get('address')  # Add this line
        is_occupied = 'is_occupied' in request.form

        # Get values for all fields
        letterbox_code = request.form.get('letterbox_code') or None
        smartlock_code = request.form.get('smartlock_code') or None
        wifi_name = request.form.get('wifi_name') or None
        wifi_password = request.form.get('wifi_password') or None

        # Process numeric fields
        bedrooms = request.form.get('bedrooms') or None
        bathrooms = request.form.get('bathrooms') or None
        sq_ft = request.form.get('sq_ft') or None
        toilet_count = request.form.get('toilet_count') or None
        towel_count = request.form.get('towel_count') or None
        default_toilet_paper = request.form.get('default_toilet_paper') or None
        default_towel = request.form.get('default_towel') or None
        default_garbage_bag = request.form.get('default_garbage_bag') or None
        monthly_rent = request.form.get('monthly_rent') or None
        max_pax = request.form.get('max_pax') or None

        # Convert to appropriate types if not None
        if bedrooms:
            bedrooms = int(bedrooms)
        if bathrooms:
            bathrooms = float(bathrooms)
        if sq_ft:
            sq_ft = int(sq_ft)
        if toilet_count:
            toilet_count = int(toilet_count)
        if towel_count:
            towel_count = int(towel_count)
        if default_toilet_paper:
            default_toilet_paper = int(default_toilet_paper)
        if default_towel:
            default_towel = int(default_towel)
        if default_garbage_bag:
            default_garbage_bag = int(default_garbage_bag)
        if monthly_rent:
            monthly_rent = float(monthly_rent)
        if max_pax:
            max_pax = int(max_pax)

        # Get current user's company
        company_id = current_user.company_id
        company = Company.query.get(company_id)

        # Check if unit number already exists in this company only
        existing_unit = Unit.query.filter_by(unit_number=unit_number, company_id=company_id).first()
        if existing_unit:
            flash('This unit number already exists in your company', 'danger')
            return redirect(url_for('add_unit'))

        # Check if company has reached their unit limit
        current_units_count = Unit.query.filter_by(company_id=company_id).count()
        max_units = company.account_type.max_units

        if current_units_count >= max_units:
            flash(
                f'Your company has reached the limit of {max_units} units. Please contact admin to upgrade your account.',
                'danger')
            return redirect(url_for('manage_units'))

        # Create new unit with all fields
        new_unit = Unit(
            unit_number=unit_number,
            building=building,
            address=address,  # Add this line
            company_id=company_id,
            is_occupied=is_occupied,
            letterbox_code=letterbox_code,
            smartlock_code=smartlock_code,
            wifi_name=wifi_name,
            wifi_password=wifi_password,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            sq_ft=sq_ft,
            toilet_count=toilet_count,
            towel_count=towel_count,
            default_toilet_paper=default_toilet_paper,
            default_towel=default_towel,
            default_garbage_bag=default_garbage_bag,
            monthly_rent=monthly_rent,
            max_pax=max_pax
        )

        db.session.add(new_unit)
        db.session.commit()

        flash('Unit added successfully', 'success')
        return redirect(url_for('manage_units'))

    return render_template('add_unit_user.html')


@app.route('/admin/edit_unit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_unit(id):
    unit = Unit.query.get_or_404(id)
    companies = Company.query.all()

    if request.method == 'POST':
        unit.unit_number = request.form['unit_number']
        unit.description = request.form['description']
        unit.floor = request.form['floor'] or None
        unit.building = request.form['building']
        unit.company_id = request.form['company_id']
        unit.is_occupied = 'is_occupied' in request.form

        # Update new fields
        toilet_count = request.form.get('toilet_count') or None
        towel_count = request.form.get('towel_count') or None
        max_pax = request.form.get('max_pax') or None

        # Convert to integers if not None
        if toilet_count:
            unit.toilet_count = int(toilet_count)
        else:
            unit.toilet_count = None

        if towel_count:
            unit.towel_count = int(towel_count)
        else:
            unit.towel_count = None

        if max_pax:
            unit.max_pax = int(max_pax)
        else:
            unit.max_pax = None

        db.session.commit()
        flash('Unit updated successfully', 'success')
        return redirect(url_for('admin_units'))

    return render_template('admin/edit_unit.html', unit=unit, companies=companies)

@app.route('/admin/delete_unit/<int:id>')
@login_required
@admin_required
def admin_delete_unit(id):
    unit = Unit.query.get_or_404(id)

    # Check if unit is in use
    if unit.complaints or unit.repairs or unit.replacements:
        flash('Cannot delete unit that is referenced by complaints, repairs, or replacements', 'danger')
        return redirect(url_for('admin_units'))

    db.session.delete(unit)
    db.session.commit()

    flash('Unit deleted successfully', 'success')
    return redirect(url_for('admin_units'))


@app.route('/unit/<int:id>')
@login_required
def unit_info(id):
    # Get the unit by id
    unit = Unit.query.get_or_404(id)

    # Check if the unit belongs to the user's company
    if unit.company_id != current_user.company_id:
        flash('You do not have permission to view this unit', 'danger')
        return redirect(url_for('manage_units'))

    # Get issues for this unit
    issues = Issue.query.filter_by(unit_id=unit.id).order_by(Issue.date_added.desc()).limit(10).all()

    return render_template('unit_info.html', unit=unit, issues=issues)


# User management routes
@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)


@app.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_user():
    # Get all companies and roles for the form
    companies = Company.query.all()
    roles = Role.query.all()

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        company_id = request.form['company_id']
        role_id = request.form['role_id']
        is_cleaner = 'is_cleaner' in request.form  # Check if is_cleaner checkbox is checked

        # Check if user already exists
        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already registered', 'danger')
            return redirect(url_for('admin_add_user'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(
            name=name,
            email=email,
            password=hashed_password,
            company_id=company_id,
            role_id=role_id,
            is_cleaner=is_cleaner  # Add is_cleaner field
        )
        db.session.add(new_user)
        db.session.commit()

        flash('User added successfully', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin/add_user.html', companies=companies, roles=roles)



@app.route('/admin/edit_user/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(id):
    user = User.query.get_or_404(id)
    companies = Company.query.all()
    roles = Role.query.all()

    if request.method == 'POST':
        user.name = request.form['name']
        user.email = request.form['email']
        user.company_id = request.form['company_id']
        user.role_id = request.form['role_id']
        user.is_cleaner = 'is_cleaner' in request.form  # Update is_cleaner field

        # Only update password if provided
        if request.form['password'].strip():
            user.password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')

        db.session.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin/edit_user.html', user=user, companies=companies, roles=roles)


@app.route('/admin/delete_user/<int:id>')
@login_required
@admin_required
def admin_delete_user(id):
    if id == current_user.id:
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('admin_users'))

    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()

    flash('User deleted successfully', 'success')
    return redirect(url_for('admin_users'))


# Company routes
@app.route('/admin/companies')
@login_required
@admin_required
def admin_companies():
    companies = Company.query.all()
    return render_template('admin/companies.html', companies=companies)


@app.route('/admin/add_company', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_company():
    # Get all account types for the form
    account_types = AccountType.query.all()

    if request.method == 'POST':
        name = request.form['name']
        account_type_id = request.form['account_type_id']

        # Check if company already exists
        company = Company.query.filter_by(name=name).first()
        if company:
            flash('Company already exists', 'danger')
            return redirect(url_for('admin_add_company'))

        new_company = Company(
            name=name,
            account_type_id=account_type_id
        )
        db.session.add(new_company)
        db.session.commit()

        flash('Company added successfully', 'success')
        return redirect(url_for('admin_companies'))

    return render_template('admin/add_company.html', account_types=account_types)


@app.route('/admin/edit_company/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_company(id):
    company = Company.query.get_or_404(id)
    account_types = AccountType.query.all()

    if request.method == 'POST':
        company.name = request.form['name']
        company.account_type_id = request.form['account_type_id']
        db.session.commit()
        flash('Company updated successfully', 'success')
        return redirect(url_for('admin_companies'))

    return render_template('admin/edit_company.html', company=company, account_types=account_types)


@app.route('/admin/delete_company/<int:id>')
@login_required
@admin_required
def admin_delete_company(id):
    company = Company.query.get_or_404(id)

    # Check if company has users or units
    if company.users or company.units:
        flash('Cannot delete company with existing users or units', 'danger')
        return redirect(url_for('admin_companies'))

    db.session.delete(company)
    db.session.commit()

    flash('Company deleted successfully', 'success')
    return redirect(url_for('admin_companies'))


# Role routes
@app.route('/admin/roles')
@login_required
@admin_required
def admin_roles():
    roles = Role.query.all()
    return render_template('admin/roles.html', roles=roles)


@app.route('/admin/add_role', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_role():
    if request.method == 'POST':
        name = request.form['name']

        # Check if role already exists
        role = Role.query.filter_by(name=name).first()
        if role:
            flash('Role already exists', 'danger')
            return redirect(url_for('admin_add_role'))

        # Create new role with permissions
        new_role = Role(
            name=name,
            can_view_complaints='can_view_complaints' in request.form,
            can_view_issues='can_view_issues' in request.form,
            can_manage_complaints='can_manage_complaints' in request.form,
            can_view_repairs='can_view_repairs' in request.form,
            can_manage_repairs='can_manage_repairs' in request.form,
            can_view_replacements='can_view_replacements' in request.form,
            can_manage_replacements='can_manage_replacements' in request.form,
            is_admin='is_admin' in request.form,
            can_manage_users='can_manage_users' in request.form
        )

        db.session.add(new_role)
        db.session.commit()

        flash('Role added successfully', 'success')
        return redirect(url_for('admin_roles'))

    return render_template('admin/add_role.html')


@app.route('/admin/edit_role/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_role(id):
    role = Role.query.get_or_404(id)

    if request.method == 'POST':
        role.name = request.form['name']

        # Update permissions
        role.can_view_complaints = 'can_view_complaints' in request.form
        role.can_manage_complaints = 'can_manage_complaints' in request.form
        role.can_view_issues = 'can_view_issues' in request.form
        role.can_manage_issues = 'can_manage_issues' in request.form
        role.can_view_repairs = 'can_view_repairs' in request.form
        role.can_manage_repairs = 'can_manage_repairs' in request.form
        role.can_view_replacements = 'can_view_replacements' in request.form
        role.can_manage_replacements = 'can_manage_replacements' in request.form
        role.is_admin = 'is_admin' in request.form
        role.can_manage_users = 'can_manage_users' in request.form

        db.session.commit()
        flash('Role updated successfully', 'success')
        return redirect(url_for('admin_roles'))

    return render_template('admin/edit_role.html', role=role)


@app.route('/admin/delete_role/<int:id>')
@login_required
@admin_required
def admin_delete_role(id):
    role = Role.query.get_or_404(id)

    # Check if role has users
    if role.users:
        flash('Cannot delete role with existing users', 'danger')
        return redirect(url_for('admin_roles'))

    db.session.delete(role)
    db.session.commit()

    flash('Role deleted successfully', 'success')
    return redirect(url_for('admin_roles'))


@app.route('/admin/complaints')
@login_required
@admin_required
def admin_complaints():
    complaints = Complaint.query.all()
    return render_template('admin/complaints.html', complaints=complaints)


@app.route('/admin/repairs')
@login_required
@admin_required
def admin_repairs():
    repairs = Repair.query.all()
    return render_template('admin/repairs.html', repairs=repairs)


@app.route('/admin/replacements')
@login_required
@admin_required
def admin_replacements():
    replacements = Replacement.query.all()
    return render_template('admin/replacements.html', replacements=replacements)


# Function to create default roles and a default company
def create_default_data():

    admin_user = User.query.filter_by(email='admin@example.com').first()
    if not admin_user:

        # Create account types first
        create_account_types()

        # Check if default company exists
        default_company = Company.query.filter_by(name="Default Company").first()
        if not default_company:
            # Get standard account type
            standard_account = AccountType.query.filter_by(name="Standard Account").first()

            default_company = Company(
                name="Default Company",
                account_type_id=standard_account.id if standard_account else 1
            )
            db.session.add(default_company)
            db.session.commit()
            print("Default company created")

        # Create default roles if they don't exist
        roles = {
            "Admin": {
                "can_view_complaints": True,
                "can_manage_complaints": True,
                "can_view_issues": True,
                "can_manage_issues": True,
                "can_view_repairs": True,
                "can_manage_repairs": True,
                "can_view_replacements": True,
                "can_manage_replacements": True,
                "can_view_bookings": True,
                "can_manage_bookings": True,
                "is_admin": True,
                "can_manage_users": True
            },
            "Manager": {
                "can_view_complaints": True,
                "can_manage_complaints": True,
                "can_view_issues": True,
                "can_manage_issues": True,
                "can_view_repairs": True,
                "can_manage_repairs": True,
                "can_view_replacements": True,
                "can_manage_replacements": True,
                "can_view_bookings": True,
                "can_manage_bookings": True,
                "is_admin": False,
                "can_manage_users": False
            },
            "Technician": {
                "can_view_complaints": True,
                "can_manage_complaints": False,
                "can_view_repairs": True,
                "can_manage_repairs": True,
                "can_view_replacements": False,
                "can_manage_replacements": False,
                "is_admin": False,
                "can_manage_users": False
            },
            "Cleaner": {
                "can_view_complaints": False,
                "can_manage_complaints": False,
                "can_view_repairs": False,
                "can_manage_repairs": False,
                "can_view_replacements": True,
                "can_manage_replacements": True,
                "is_admin": False,
                "can_manage_users": False
            }
        }

        for role_name, permissions in roles.items():
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                role = Role(name=role_name, **permissions)
                db.session.add(role)
                db.session.commit()
                print(f"Role '{role_name}' created")

        # Create admin user if no admin exists
        admin_role = Role.query.filter_by(name="Admin").first()
        admin = User.query.filter_by(is_admin=True).first()

        if not admin and admin_role:
            password = 'admin123'  # Default password
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            admin = User(
                name='Admin',
                email='admin@example.com',
                password=hashed_password,
                role_id=admin_role.id,
                company_id=default_company.id
            )
            db.session.add(admin)
            db.session.commit()
            print('Admin user created with email: admin@example.com and password: admin123')

        # Create a few sample units for the default company
        if Unit.query.count() == 0:
            sample_units = [
                {"unit_number": "A-101", "building": "Block A", "floor": 1, "description": "Corner unit",
                 "is_occupied": True},
                {"unit_number": "A-102", "building": "Block A", "floor": 1, "description": "Middle unit",
                 "is_occupied": True},
                {"unit_number": "B-201", "building": "Block B", "floor": 2, "description": "End unit", "is_occupied": True},
                {"unit_number": "C-301", "building": "Block C", "floor": 3, "description": "Penthouse",
                 "is_occupied": False},
            ]

            for unit_data in sample_units:
                unit = Unit(
                    unit_number=unit_data["unit_number"],
                    building=unit_data["building"],
                    floor=unit_data["floor"],
                    description=unit_data["description"],
                    is_occupied=unit_data["is_occupied"],
                    company_id=default_company.id
                )
                db.session.add(unit)

            db.session.commit()
            print("Default data created successfully")
        else:
            print("Default data already exists")

    # Call the create_issue_defaults function
    create_issue_defaults()

    # Add the create_cleaner_role function definition here
    def create_cleaner_role():
        # Check if Cleaner role exists
        cleaner_role = Role.query.filter_by(name="Cleaner").first()
        if not cleaner_role:
            cleaner_role = Role(
                name="Cleaner",
                can_view_complaints=True,
                can_manage_complaints=False,
                can_view_issues=True,
                can_manage_issues=False,
                can_view_repairs=False,
                can_manage_repairs=False,
                can_view_replacements=False,
                can_manage_replacements=False,
                is_admin=False,
                can_manage_users=False
            )
            db.session.add(cleaner_role)
            db.session.commit()
            print("Cleaner role created")

    # Call the function at the end of create_default_data
    create_cleaner_role()


def create_account_types():
    # Check if account types exist
    if AccountType.query.count() == 0:
        account_types = [
            {"name": "Standard Account", "max_units": 20},
            {"name": "Premium Account", "max_units": 40},
            {"name": "Pro Account", "max_units": 80},
            {"name": "Elite Account", "max_units": 160},
            {"name": "Ultimate Account", "max_units": 2000}
        ]

        for type_data in account_types:
            account_type = AccountType(
                name=type_data["name"],
                max_units=type_data["max_units"]
            )
            db.session.add(account_type)

        db.session.commit()
        print("Account types created")


def create_issue_items():
    # Define issue items by category
    issue_items_by_category = {
        "Building Issue": [
            "Carpark - Not Enough",
            "Carpark - Too High",
            "Lift - Waiting too long",
            "Swimming pool",
            "Noisy neighbour"
        ],
        "Cleaning Issue": [
            "Dusty",
            "Bedsheet - Not Clean",
            "Bedsheet - Smelly",
            "Toilet - Smelly",
            "Toilet Not Clean",
            "House - Smelly",
            "Got Ants",
            "Got Cockroach",
            "Got Insects",
            "Got mouse",
            "Not enough towels",
            "Not enough toiletries"
        ],
        "Plumbing Issues": [
            "Basin stucked",
            "Basin dripping",
            "Faucet Dripping",
            "Bidet dripping",
            "Toilet bowl stuck",
            "Shower head",
            "Toilet fitting lose",
            "Water pressure Low",
            "Drainage problem"
        ],
        "Electrical Issue": [
            "TV Box",
            "Internet WiFi",
            "Water Heater",
            "Fan",
            "Washing machine",
            "House No Electric",
            "Light",
            "Hair dryer",
            "Iron",
            "Microwave",
            "Kettle",
            "Remote control",
            "Induction Cooker",
            "Rice Cooker",
            "Water Filter",
            "Fridge"
        ],
        "Furniture Issue": [
            "Chair",
            "Sofa",
            "Wardrobe",
            "Kitchenware",
            "Bed",
            "Pillow",
            "Bedframe",
            "Iron board Cover",
            "Windows",
            "Coffee Table",
            "Cabinet",
            "Dining Table"
        ],
        "Check-in Issue": [
            "Access card Holder",
            "Access card",
            "key",
            "Letterbox - cant open",
            "Letterbox - left open",
            "Letterbox - missing",
            "Door",
            "Door Password"
        ],
        "Aircond Issue": [
            "AC not cold",
            "AC leaking",
            "AC noisy",
            "AC empty - tank"
        ]
    }

    # Get or create categories
    for category_name, items in issue_items_by_category.items():
        # Get or create the category
        category = Category.query.filter_by(name=category_name).first()
        if not category:
            category = Category(name=category_name)
            db.session.add(category)
            db.session.flush()  # Flush to get the category ID

        # Create issue items for this category
        for item_name in items:
            # Check if the issue item already exists
            existing_item = IssueItem.query.filter_by(name=item_name, category_id=category.id).first()
            if not existing_item:
                issue_item = IssueItem(name=item_name, category_id=category.id)
                db.session.add(issue_item)

    db.session.commit()
    print("Issue items created successfully")


def create_issue_defaults():
    # Create categories
    categories = ["Building Issue", "Cleaning Issue", "Plumbing Issues", "Electrical Issue", "Furniture Issue",
                  "Check-in Issue", "Aircond Issue"]
    for category_name in categories:
        if not Category.query.filter_by(name=category_name).first():
            category = Category(name=category_name)
            db.session.add(category)

    # Create reported by options
    reporters = ["Cleaner", "Guest", "Operator", "Head"]
    for reporter_name in reporters:
        if not ReportedBy.query.filter_by(name=reporter_name).first():
            reporter = ReportedBy(name=reporter_name)
            db.session.add(reporter)

    # Create priorities
    priorities = ["High", "Medium", "Low"]
    for priority_name in priorities:
        if not Priority.query.filter_by(name=priority_name).first():
            priority = Priority(name=priority_name)
            db.session.add(priority)

    # Create statuses
    statuses = ["Pending", "In Progress", "Resolved", "Rejected"]
    for status_name in statuses:
        if not Status.query.filter_by(name=status_name).first():
            status = Status(name=status_name)
            db.session.add(status)

    # Create types
    types = ["Repair", "Replace"]
    for type_name in types:
        if not Type.query.filter_by(name=type_name).first():
            type_obj = Type(name=type_name)
            db.session.add(type_obj)

    db.session.commit()

    # Create the issue items
    create_issue_items()
    print("Issue defaults created")


@app.route('/bookings')
@login_required
@permission_required('can_view_bookings')
def bookings():
    # Filter records to only show those belonging to the user's company
    user_company_id = current_user.company_id
    bookings_list = BookingForm.query.filter_by(company_id=user_company_id).order_by(
        BookingForm.date_added.desc()).all()

    # Get units for this company for the form
    units = Unit.query.filter_by(company_id=user_company_id).all()

    # Calculate analytics for the dashboard
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)  # Get tomorrow's date

    # Calculate total units
    unit_total = Unit.query.filter_by(company_id=user_company_id).count()

    # Calculate occupancy today (units where check-in <= today < check-out)
    occupancy_current = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_in_date <= today,
        BookingForm.check_out_date > today
    ).count()

    # Calculate check-ins today
    check_ins_today = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_in_date == today
    ).count()

    # Calculate revenue today (total price of bookings with check-in today)
    today_check_ins = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_in_date == today
    ).all()
    revenue_today = sum(float(booking.price) for booking in today_check_ins if booking.price)

    # Currently staying (check-in <= today < check-out)
    currently_staying = occupancy_current

    # Calculate check-ins tomorrow (NEW)
    check_ins_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_in_date == tomorrow
    ).count()

    # Calculate check-outs today (NEW)
    check_outs_today = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_out_date == today
    ).count()

    # Calculate check-outs tomorrow (NEW)
    check_outs_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_out_date == tomorrow
    ).count()

    # Create stats dictionary
    stats = {
        'unit_total': unit_total,
        'occupancy_current': occupancy_current,
        'check_ins_today': check_ins_today,
        'revenue_today': '{:,.2f}'.format(revenue_today),
        'currently_staying': currently_staying,
        'check_ins_tomorrow': check_ins_tomorrow,  # New stat
        'check_outs_today': check_outs_today,  # New stat
        'check_outs_tomorrow': check_outs_tomorrow
    }

    return render_template('bookings.html', bookings=bookings_list, units=units, stats=stats, active_filter=None)


@app.route('/add_booking', methods=['GET', 'POST'])
@login_required
@permission_required('can_manage_bookings')
def add_booking():
    if request.method == 'POST':
        guest_name = request.form['guest_name']
        contact_number = request.form['contact_number']
        check_in_date = datetime.strptime(request.form['check_in_date'], '%Y-%m-%d').date()
        check_out_date = datetime.strptime(request.form['check_out_date'], '%Y-%m-%d').date()
        property_name = request.form['property_name']
        unit_id = request.form['unit_id']
        number_of_nights = (check_out_date - check_in_date).days

        # Calculate number_of_guests from the sum
        adults = int(request.form.get('adults', 0) or 0)
        children = int(request.form.get('children', 0) or 0)
        infants = int(request.form.get('infants', 0) or 0)
        number_of_guests = adults + children + infants

        price = request.form['price']
        booking_source = request.form['booking_source']
        payment_status = request.form['payment_status']
        notes = request.form['notes']

        # Handle new fields
        confirmation_code = request.form.get('confirmation_code', '')

        # Process booking date (if provided)
        booking_date = None
        if request.form.get('booking_date'):
            booking_date = datetime.strptime(request.form['booking_date'], '%Y-%m-%d').date()

        # Check for date conflicts with existing bookings
        is_available = check_unit_availability(
            unit_id,
            check_in_date,
            check_out_date
        )

        if not is_available:
            flash(f'Unit is not available for these dates. There is already a booking that overlaps with this period.',
                  'danger')
            # Get units for the form again
            units = Unit.query.filter_by(company_id=current_user.company_id).all()
            return render_template('booking_form.html', units=units)

        # Get the unit
        unit = Unit.query.get(unit_id)
        if not unit:
            flash('Invalid unit selected', 'danger')
            return redirect(url_for('add_booking'))

        # Check if the unit belongs to the user's company
        if unit.company_id != current_user.company_id:
            flash('You do not have permission to book this unit', 'danger')
            return redirect(url_for('add_booking'))

        new_booking = BookingForm(
            guest_name=guest_name,
            contact_number=contact_number,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            property_name=property_name,
            unit_id=unit_id,
            number_of_nights=number_of_nights,
            number_of_guests=number_of_guests,
            price=price,
            booking_source=booking_source,
            payment_status=payment_status,
            notes=notes,
            # New fields
            confirmation_code=confirmation_code,
            booking_date=booking_date,
            adults=adults,
            children=children,
            infants=infants,
            # Existing fields
            company_id=current_user.company_id,
            user_id=current_user.id
        )

        db.session.add(new_booking)
        db.session.commit()

        # Set session variable with the new booking ID
        session['highlight_booking_id'] = new_booking.id

        flash('Booking added successfully', 'success')
        return redirect(url_for('bookings', highlight_id=new_booking.id))

    # Get units for the form
    units = Unit.query.filter_by(company_id=current_user.company_id).all()

    return render_template('booking_form.html', units=units)


@app.route('/update_booking/<int:id>', methods=['POST'])
@login_required
@permission_required('can_manage_bookings')
def update_booking(id):
    booking = BookingForm.query.get_or_404(id)

    # Ensure the current user's company matches the booking's company
    if booking.company_id != current_user.company_id:
        flash('You are not authorized to update this booking', 'danger')
        return redirect(url_for('bookings'))

    # Update fields
    booking.guest_name = request.form.get('guest_name', '')
    booking.contact_number = request.form.get('contact_number', '')

    check_in_date = datetime.strptime(request.form['check_in_date'], '%Y-%m-%d').date()
    check_out_date = datetime.strptime(request.form['check_out_date'], '%Y-%m-%d').date()

    # Add validation to ensure check_out_date is after check_in_date
    if check_out_date <= check_in_date:
        flash('Check-out date must be after check-in date', 'danger')
        return redirect(url_for('bookings'))

    booking.check_in_date = check_in_date
    booking.check_out_date = check_out_date
    booking.number_of_nights = (check_out_date - check_in_date).days

    booking.property_name = request.form.get('property_name', '')
    booking.unit_id = request.form['unit_id']
    adults = int(request.form.get('adults', 0) or 0)
    children = int(request.form.get('children', 0) or 0)
    infants = int(request.form.get('infants', 0) or 0)
    number_of_guests = adults + children + infants
    booking.number_of_guests = number_of_guests
    booking.price = request.form['price']
    booking.booking_source = request.form['booking_source']
    booking.payment_status = request.form.get('payment_status', 'Pending')
    booking.notes = request.form.get('notes', '')

    # Update new fields
    booking.confirmation_code = request.form.get('confirmation_code', '')

    # Process booking date (if provided)
    if request.form.get('booking_date'):
        booking.booking_date = datetime.strptime(request.form['booking_date'], '%Y-%m-%d').date()

    # Check for date conflicts with existing bookings (excluding this booking)
    is_available = check_unit_availability(
        booking.unit_id,
        check_in_date,
        check_out_date,
        exclude_booking_id=id
    )

    if not is_available:
        flash(f'Unit is not available for these dates. There is already a booking that overlaps with this period.',
              'danger')
        return redirect(url_for('bookings'))

    # Process numeric fields
    adults = request.form.get('adults', '')
    booking.adults = int(adults) if adults.strip() else None

    children = request.form.get('children', '')
    booking.children = int(children) if children.strip() else None

    infants = request.form.get('infants', '')
    booking.infants = int(infants) if infants.strip() else None

    db.session.commit()
    session['highlight_booking_id'] = id
    flash('Booking updated successfully', 'success')
    return redirect(url_for('bookings', highlight_id=id))


@app.route('/api/booking/<int:id>')
@login_required
@permission_required('can_view_bookings')
def get_booking(id):
    booking = BookingForm.query.get_or_404(id)

    # Ensure the current user's company matches the booking's company
    if booking.company_id != current_user.company_id:
        return jsonify({'error': 'Not authorized'}), 403

    return jsonify({
        'id': booking.id,
        'guest_name': booking.guest_name,
        'contact_number': booking.contact_number,
        'check_in_date': booking.check_in_date.strftime('%Y-%m-%d'),
        'check_out_date': booking.check_out_date.strftime('%Y-%m-%d'),
        'property_name': booking.property_name,
        'unit_id': booking.unit_id,
        'number_of_nights': booking.number_of_nights,
        'number_of_guests': booking.number_of_guests,
        'price': float(booking.price) if booking.price else 0,
        'booking_source': booking.booking_source,
        'payment_status': booking.payment_status,
        'notes': booking.notes,
        # Add new fields
        'confirmation_code': booking.confirmation_code,
        'booking_date': booking.booking_date.strftime('%Y-%m-%d') if booking.booking_date else '',
        'adults': booking.adults if booking.adults is not None else '',
        'children': booking.children if booking.children is not None else '',
        'infants': booking.infants if booking.infants is not None else ''
    })


@app.route('/delete_booking/<int:id>')
@login_required
@permission_required('can_manage_bookings')
def delete_booking(id):
    booking = BookingForm.query.get_or_404(id)

    # Ensure the current user's company matches the booking's company
    if booking.company_id != current_user.company_id:
        flash('You are not authorized to delete this booking', 'danger')
        return redirect(url_for('bookings'))

    db.session.delete(booking)
    db.session.commit()

    flash('Booking deleted successfully', 'success')
    return redirect(url_for('bookings'))


@app.route('/bookings/<filter_type>')
@login_required
@permission_required('can_view_bookings')
def bookings_filter(filter_type):
    # Filter records to only show those belonging to the user's company
    user_company_id = current_user.company_id

    # Get units for this company for the form
    units = Unit.query.filter_by(company_id=user_company_id).all()

    # Calculate analytics for the dashboard
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    # Calculate all the stats (same as in regular bookings route)
    unit_total = Unit.query.filter_by(company_id=user_company_id).count()

    occupancy_current = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_in_date <= today,
        BookingForm.check_out_date > today
    ).count()

    check_ins_today = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_in_date == today
    ).count()

    today_check_ins = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_in_date == today
    ).all()
    revenue_today = sum(float(booking.price) for booking in today_check_ins if booking.price)

    currently_staying = occupancy_current

    check_ins_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_in_date == tomorrow
    ).count()

    check_outs_today = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_out_date == today
    ).count()

    check_outs_tomorrow = BookingForm.query.filter(
        BookingForm.company_id == user_company_id,
        BookingForm.check_out_date == tomorrow
    ).count()

    # Apply specific filter based on filter_type
    if filter_type == 'occupancy_current':
        bookings_list = BookingForm.query.filter(
            BookingForm.company_id == user_company_id,
            BookingForm.check_in_date <= today,
            BookingForm.check_out_date > today
        ).all()
        filter_message = "Showing currently occupied units"
    elif filter_type == 'check_ins_today':
        bookings_list = BookingForm.query.filter(
            BookingForm.company_id == user_company_id,
            BookingForm.check_in_date == today
        ).all()
        filter_message = f"Showing check-ins for today ({today.strftime('%b %d, %Y')})"
    elif filter_type == 'revenue_today':
        bookings_list = BookingForm.query.filter(
            BookingForm.company_id == user_company_id,
            BookingForm.check_in_date == today
        ).all()
        filter_message = f"Showing revenue for today ({today.strftime('%b %d, %Y')})"
    elif filter_type == 'currently_staying':
        bookings_list = BookingForm.query.filter(
            BookingForm.company_id == user_company_id,
            BookingForm.check_in_date <= today,
            BookingForm.check_out_date > today
        ).all()
        filter_message = "Showing currently staying guests"
    elif filter_type == 'check_ins_tomorrow':
        bookings_list = BookingForm.query.filter(
            BookingForm.company_id == user_company_id,
            BookingForm.check_in_date == tomorrow
        ).all()
        filter_message = f"Showing check-ins for tomorrow ({tomorrow.strftime('%b %d, %Y')})"
    elif filter_type == 'check_outs_today':
        bookings_list = BookingForm.query.filter(
            BookingForm.company_id == user_company_id,
            BookingForm.check_out_date == today
        ).all()
        filter_message = f"Showing check-outs for today ({today.strftime('%b %d, %Y')})"
    elif filter_type == 'check_outs_tomorrow':
        bookings_list = BookingForm.query.filter(
            BookingForm.company_id == user_company_id,
            BookingForm.check_out_date == tomorrow
        ).all()
        filter_message = f"Showing check-outs for tomorrow ({tomorrow.strftime('%b %d, %Y')})"
    else:
        # Default - show all bookings
        bookings_list = BookingForm.query.filter_by(company_id=user_company_id).all()
        filter_message = None

    # Create stats dictionary
    stats = {
        'unit_total': unit_total,
        'occupancy_current': occupancy_current,
        'check_ins_today': check_ins_today,
        'revenue_today': '{:,.2f}'.format(revenue_today),
        'currently_staying': currently_staying,
        'check_ins_tomorrow': check_ins_tomorrow,
        'check_outs_today': check_outs_today,
        'check_outs_tomorrow': check_outs_tomorrow
    }

    return render_template('bookings.html',
                           bookings=bookings_list,
                           units=units,
                           stats=stats,
                           filter_message=filter_message,
                           active_filter=filter_type)  # Pass the active filter to highlight the current selection


@app.route('/api/unit_bookings/<int:unit_id>')
@login_required
def get_unit_bookings(unit_id):
    """
    Get all bookings for a specific unit to determine unavailable dates
    """
    # Check if the unit belongs to the user's company
    unit = Unit.query.get_or_404(unit_id)
    if unit.company_id != current_user.company_id:
        return jsonify({'error': 'You do not have permission to access this unit'}), 403

    # Get all bookings for this unit
    bookings = BookingForm.query.filter_by(unit_id=unit_id).all()

    # Format the booking data
    booking_data = []
    for booking in bookings:
        booking_data.append({
            'id': booking.id,
            'check_in_date': booking.check_in_date.isoformat(),
            'check_out_date': booking.check_out_date.isoformat(),
            'guest_name': booking.guest_name
        })

    return jsonify({
        'unit_id': unit_id,
        'unit_number': unit.unit_number,
        'bookings': booking_data
    })

@app.route('/api/check_availability')
@login_required
def check_availability():
    unit_id = request.args.get('unit_id', type=int)
    check_in = request.args.get('check_in')
    check_out = request.args.get('check_out')
    booking_id = request.args.get('booking_id', type=int)  # Optional, for updates

    if not unit_id or not check_in or not check_out:
        return jsonify({'available': False, 'error': 'Missing parameters'})

    try:
        # Convert string dates to datetime objects
        check_in_date = datetime.strptime(check_in, '%Y-%m-%d').date()
        check_out_date = datetime.strptime(check_out, '%Y-%m-%d').date()

        # Validate dates (check-out must be after check-in)
        if check_out_date <= check_in_date:
            return jsonify({
                'available': False,
                'error': 'Check-out date must be after check-in date'
            })

        # Check availability
        is_available = check_unit_availability(unit_id, check_in_date, check_out_date, booking_id)

        # If not available, find the conflicting bookings
        conflicting_bookings = []
        if not is_available:
            conflicts = BookingForm.query.filter(
                BookingForm.unit_id == unit_id,
                BookingForm.check_in_date < check_out_date,
                BookingForm.check_out_date > check_in_date
            )

            # Exclude the current booking if we're updating
            if booking_id:
                conflicts = conflicts.filter(BookingForm.id != booking_id)

            # Format the conflicts
            for booking in conflicts:
                conflicting_bookings.append({
                    'id': booking.id,
                    'check_in_date': booking.check_in_date.isoformat(),
                    'check_out_date': booking.check_out_date.isoformat(),
                    'guest_name': booking.guest_name
                })

        return jsonify({
            'available': is_available,
            'unit_id': unit_id,
            'check_in_date': check_in,
            'check_out_date': check_out,
            'conflicts': conflicting_bookings
        })
    except Exception as e:
        return jsonify({'available': False, 'error': str(e)})

# Route for managers to view cleaners
@app.route('/manage_cleaners')
@login_required
def manage_cleaners():
    # Check if user is a manager - we'll use the Manager role
    manager_role = Role.query.filter_by(name="Manager").first()
    if not current_user.role_id == manager_role.id and not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    # Get all cleaners from the current user's company
    company_id = current_user.company_id
    cleaners = User.query.filter_by(company_id=company_id, is_cleaner=True).all()

    return render_template('manage_cleaners.html', cleaners=cleaners)


# Route for managers to update cleaner info
@app.route('/update_cleaner/<int:id>', methods=['GET', 'POST'])
@login_required
def update_cleaner(id):
    # Check if user is a manager
    manager_role = Role.query.filter_by(name="Manager").first()
    if not current_user.role_id == manager_role.id and not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    # Get the cleaner
    cleaner = User.query.get_or_404(id)

    # Make sure the cleaner belongs to the same company as the manager
    if cleaner.company_id != current_user.company_id:
        flash('You do not have permission to update this cleaner.', 'danger')
        return redirect(url_for('manage_cleaners'))

    # Get company units
    company_units = Unit.query.filter_by(company_id=current_user.company_id).all()

    if request.method == 'POST':
        # Update cleaner information
        cleaner.phone_number = request.form.get('phone_number', '')

        # Update assigned units
        # First, clear current assignments
        cleaner.assigned_units = []

        # Then add new assignments
        selected_units = request.form.getlist('assigned_units')
        for unit_id in selected_units:
            unit = Unit.query.get(unit_id)
            if unit and unit.company_id == current_user.company_id:
                cleaner.assigned_units.append(unit)

        db.session.commit()
        flash('Cleaner information updated successfully', 'success')
        return redirect(url_for('manage_cleaners'))

    return render_template('update_cleaner.html', cleaner=cleaner, units=company_units)


# Route for cleaner dashboard
@app.route('/cleaner_dashboard')
@login_required
def cleaner_dashboard():
    # Check if the user is a cleaner
    if not current_user.is_cleaner:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    # Get assigned units
    assigned_units = current_user.assigned_units

    # Get issues related to those units
    issues = []
    for unit in assigned_units:
        unit_issues = Issue.query.filter_by(unit_id=unit.id).all()
        issues.extend(unit_issues)

    # Sort issues by date, most recent first
    issues.sort(key=lambda x: x.date_added, reverse=True)

    return render_template('cleaner_dashboard.html', units=assigned_units, issues=issues)


# Add these routes to app.py

@app.route('/cleaning-schedule')
@login_required
def cleaning_schedule():
    # Only cleaners and managers can access this page
    if not current_user.is_cleaner and current_user.role.name != 'Manager' and not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    tomorrow = datetime.now().date() + timedelta(days=1)

    # Get tomorrow's checkouts and check-ins
    checkouts_tomorrow = BookingForm.query.filter(
        BookingForm.check_out_date == tomorrow
    ).all()

    checkins_tomorrow = BookingForm.query.filter(
        BookingForm.check_in_date == tomorrow
    ).all()

    # Map unit_id to checkin booking for fast lookups
    checkin_map = {booking.unit_id: booking for booking in checkins_tomorrow}

    # For managers, show all cleaners' schedules
    if current_user.role.name == 'Manager' or current_user.is_admin:
        cleaners = User.query.filter_by(company_id=current_user.company_id, is_cleaner=True).all()

        cleaner_schedules = []
        for cleaner in cleaners:
            # Get units assigned to this cleaner that have checkouts tomorrow
            assigned_units = cleaner.assigned_units
            cleaner_checkouts = []

            for unit in assigned_units:
                for checkout in checkouts_tomorrow:
                    if checkout.unit_id == unit.id:
                        # Check if there's a check-in tomorrow for this unit
                        has_checkin = unit.id in checkin_map
                        checkin_booking = checkin_map.get(unit.id)

                        # Calculate supplies based on whether there's a check-in tomorrow
                        if has_checkin:
                            towels = checkin_booking.number_of_guests
                            rubbish_bags = checkin_booking.number_of_nights
                            toilet_rolls = checkin_booking.number_of_nights * (unit.toilet_count or 1)
                        else:
                            towels = unit.towel_count or 2
                            rubbish_bags = 2
                            toilet_rolls = 2 * (unit.toilet_count or 1)

                        cleaner_checkouts.append({
                            'unit': unit,
                            'checkout': checkout,
                            'has_checkin': has_checkin,
                            'checkin_booking': checkin_booking,
                            'towels': towels,
                            'rubbish_bags': rubbish_bags,
                            'toilet_rolls': toilet_rolls
                        })

            if cleaner_checkouts:
                cleaner_schedules.append({
                    'cleaner': cleaner,
                    'checkouts': cleaner_checkouts
                })

        return render_template('cleaning_schedule_manager.html',
                               cleaner_schedules=cleaner_schedules,
                               tomorrow=tomorrow)

    # For cleaners, show only their assigned units
    else:
        assigned_units = current_user.assigned_units
        my_checkouts = []

        for unit in assigned_units:
            for checkout in checkouts_tomorrow:
                if checkout.unit_id == unit.id:
                    # Check if there's a check-in tomorrow for this unit
                    has_checkin = unit.id in checkin_map
                    checkin_booking = checkin_map.get(unit.id)

                    # Calculate supplies based on whether there's a check-in tomorrow
                    if has_checkin:
                        towels = checkin_booking.number_of_guests
                        rubbish_bags = checkin_booking.number_of_nights
                        toilet_rolls = checkin_booking.number_of_nights * (unit.toilet_count or 1)
                    else:
                        towels = unit.towel_count or 2
                        rubbish_bags = 2
                        toilet_rolls = 2 * (unit.toilet_count or 1)

                    my_checkouts.append({
                        'unit': unit,
                        'checkout': checkout,
                        'has_checkin': has_checkin,
                        'checkin_booking': checkin_booking,
                        'towels': towels,
                        'rubbish_bags': rubbish_bags,
                        'toilet_rolls': toilet_rolls
                    })

        return render_template('cleaning_schedule.html',
                               checkouts=my_checkouts,
                               tomorrow=tomorrow)


# Add this route to app.py to support the calendar view

@app.route('/calendar_view')
@login_required
@permission_required('can_view_bookings')
def calendar_view():
    # Get units for this company for the filters
    user_company_id = current_user.company_id
    units = Unit.query.filter_by(company_id=user_company_id).all()

    return render_template('calendar_view.html', units=units)


@app.route('/api/calendar/bookings')
@login_required
@permission_required('can_view_bookings')
def get_calendar_bookings():
    # Filter records to only show those belonging to the user's company
    user_company_id = current_user.company_id
    bookings = BookingForm.query.filter_by(company_id=user_company_id).all()

    # Format the data for the calendar
    calendar_data = []
    for booking in bookings:
        calendar_data.append({
            'id': booking.id,
            'unit_id': booking.unit_id,
            'unit_number': booking.unit.unit_number,
            'guest_name': booking.guest_name,
            'check_in_date': booking.check_in_date.isoformat(),
            'check_out_date': booking.check_out_date.isoformat(),
            'nights': booking.number_of_nights,
            'guests': booking.number_of_guests,
            'price': str(booking.price),
            'source': booking.booking_source,
            'payment_status': booking.payment_status,
            'contact': booking.contact_number
        })

    return jsonify(calendar_data)

from flask import jsonify, request
from datetime import datetime, timedelta
from sqlalchemy import func
import json


# Main analytics page route
@app.route('/analytics')
@login_required
def analytics():
    # Get data for filters
    categories = Category.query.all()
    priorities = Priority.query.all()
    statuses = Status.query.all()

    # Add this: Get unique units for current company
    user_company_id = current_user.company_id
    units = Unit.query.filter_by(company_id=user_company_id).all()

    return render_template('analytics_reporting.html',
                           categories=categories,
                           priorities=priorities,
                           statuses=statuses,
                           units=units)


# Add or update this route in app.py

@app.route('/api/analytics/issues')
@login_required
def get_analytics_issues():
    # Filter for current user's company
    company_id = current_user.company_id

    # Get filter parameters
    days = request.args.get('days', type=int)
    time_filter = request.args.get('time_filter')  # New parameter for special time filters
    category_id = request.args.get('category_id', type=int)
    priority_id = request.args.get('priority_id', type=int)
    status_id = request.args.get('status_id', type=int)
    unit = request.args.get('unit')
    view_type = request.args.get('view_type')  # New parameter: 'hourly' or 'monthly'

    # Start with base query for issues in user's company
    query = Issue.query.filter_by(company_id=company_id)

    # Apply date filter with calendar-based logic
    if days:
        # Standard days-based filtering
        date_threshold = datetime.utcnow() - timedelta(days=days)
        query = query.filter(Issue.date_added >= date_threshold)
    elif time_filter:
        # Special time filters
        now = datetime.utcnow()
        malaysia_tz = pytz.timezone('Asia/Kuala_Lumpur')
        now_local = now.replace(tzinfo=pytz.utc).astimezone(malaysia_tz)

        if time_filter == 'hour':
            # Last 1 hour
            hour_ago = now - timedelta(hours=1)
            query = query.filter(Issue.date_added >= hour_ago)

        elif time_filter == 'today':
            # Today (00:00:00 to now)
            today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
            today_start_utc = today_start.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= today_start_utc)

        elif time_filter == 'yesterday':
            # Yesterday (00:00:00 to 23:59:59)
            yesterday_start = (now_local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday_start.replace(hour=23, minute=59, second=59, microsecond=999999)
            yesterday_start_utc = yesterday_start.astimezone(pytz.utc)
            yesterday_end_utc = yesterday_end.astimezone(pytz.utc)
            query = query.filter(Issue.date_added >= yesterday_start_utc, Issue.date_added <= yesterday_end_utc)

    # Apply other filters if specified
    if category_id:
        query = query.filter_by(category_id=category_id)

    if priority_id:
        query = query.filter_by(priority_id=priority_id)

    if status_id:
        query = query.filter_by(status_id=status_id)

    if unit:
        query = query.filter_by(unit=unit)

    # Execute query
    issues = query.all()

    # Convert to serializable format with related data
    result = []
    for issue in issues:
        issue_data = {
            'id': issue.id,
            'description': issue.description,
            'unit': issue.unit,
            'date_added': issue.date_added.isoformat(),
            'solution': issue.solution,
            'guest_name': issue.guest_name,
            'cost': float(issue.cost) if issue.cost else None,
            'assigned_to': issue.assigned_to,

            # Include related data
            'category_id': issue.category_id,
            'category_name': issue.category.name if issue.category else None,

            'reported_by_id': issue.reported_by_id,
            'reported_by_name': issue.reported_by.name if issue.reported_by else None,

            'priority_id': issue.priority_id,
            'priority_name': issue.priority.name if issue.priority else None,

            'status_id': issue.status_id,
            'status_name': issue.status.name if issue.status else None,

            'type_id': issue.type_id,
            'type_name': issue.type.name if issue.type else None,

            'issue_item_id': issue.issue_item_id,
            'issue_item_name': issue.issue_item.name if issue.issue_item else None,
        }
        result.append(issue_data)

    return jsonify(result)


# API endpoint to get summary statistics
@app.route('/api/analytics/summary')
@login_required
def get_analytics_summary():
    company_id = current_user.company_id

    # Get total issues count
    total_issues = Issue.query.filter_by(company_id=company_id).count()

    # Get open issues count (Pending or In Progress)
    pending_status = Status.query.filter_by(name='Pending').first()
    in_progress_status = Status.query.filter_by(name='In Progress').first()

    open_issues_filter = []
    if pending_status:
        open_issues_filter.append(Issue.status_id == pending_status.id)
    if in_progress_status:
        open_issues_filter.append(Issue.status_id == in_progress_status.id)

    open_issues = 0
    if open_issues_filter:
        open_issues = Issue.query.filter_by(company_id=company_id).filter(db.or_(*open_issues_filter)).count()

    # Get resolved issues count
    resolved_status = Status.query.filter_by(name='Resolved').first()
    resolved_issues = 0
    if resolved_status:
        resolved_issues = Issue.query.filter_by(company_id=company_id, status_id=resolved_status.id).count()

    # Calculate average cost
    avg_cost_result = db.session.query(func.avg(Issue.cost)).filter(
        Issue.company_id == company_id,
        Issue.cost.isnot(None)
    ).scalar()
    avg_cost = float(avg_cost_result) if avg_cost_result else 0

    # Get top issue categories
    category_counts = db.session.query(
        Category.name,
        func.count(Issue.id).label('count')
    ).join(
        Issue, Issue.category_id == Category.id
    ).filter(
        Issue.company_id == company_id
    ).group_by(
        Category.name
    ).order_by(
        func.count(Issue.id).desc()
    ).limit(5).all()

    top_categories = [{'name': name, 'count': count} for name, count in category_counts]

    # Return JSON summary
    return jsonify({
        'total_issues': total_issues,
        'open_issues': open_issues,
        'resolved_issues': resolved_issues,
        'avg_cost': avg_cost,
        'top_categories': top_categories
    })



####### ics#################
def process_ics_calendar(calendar_data, unit_id, source):
    """Process ICS calendar data and handle bookings based on confirmation codes"""
    from icalendar import Calendar
    from datetime import datetime
    import re

    # Parse the ICS data
    try:
        cal = Calendar.from_ical(calendar_data)
    except Exception as e:
        print(f"Error parsing calendar: {str(e)}")
        return 0, 0, 0  # Return (added, updated, cancelled)

    unit = Unit.query.get(unit_id)
    if not unit:
        return 0, 0, 0

    bookings_added = 0
    bookings_updated = 0
    bookings_cancelled = 0

    # Collect all confirmation codes and their details from the ICS calendar
    current_bookings = {}  # Dict to store confirmation_code -> booking details

    for component in cal.walk():
        if component.name == "VEVENT":
            # Skip blocked dates or unavailable periods
            summary = str(component.get('summary', 'Booking'))
            if "blocked" in summary.lower() or "unavailable" in summary.lower():
                continue

            description = str(component.get('description', ''))

            # Extract confirmation code from the description field
            confirmation_code = ""

            # For Airbnb: Extract from URL like https://www.airbnb.com/hosting/reservations/details/HMN8ZKWAQE
            if source == "Airbnb":
                url_match = re.search(r'reservations/details/([A-Z0-9]+)', description)
                if url_match:
                    confirmation_code = url_match.group(1)

            # For other platforms - adapt as needed
            elif source == "Booking.com":
                booking_match = re.search(r'Booking ID:\s*(\d+)', description)
                if booking_match:
                    confirmation_code = booking_match.group(1)

            # If no valid confirmation code found, skip this entry
            if not confirmation_code:
                continue

            # Get start and end dates
            start_date = component.get('dtstart').dt
            end_date = component.get('dtend').dt

            # Convert datetime objects to date objects if needed
            if isinstance(start_date, datetime):
                start_date = start_date.date()
            if isinstance(end_date, datetime):
                end_date = end_date.date()

            # Calculate number of nights
            nights = (end_date - start_date).days

            # Extract guest name from summary or description
            guest_name = extract_guest_name(summary, description) or f"Guest from {source}"

            # Store booking details
            current_bookings[confirmation_code] = {
                'check_in_date': start_date,
                'check_out_date': end_date,
                'number_of_nights': nights,
                'guest_name': guest_name,
                'description': description
            }

    # Get existing bookings from database for this unit and source
    existing_bookings = BookingForm.query.filter_by(
        unit_id=unit_id,
        booking_source=source
    ).all()

    # Check existing bookings against current calendar data
    existing_codes = set()
    for booking in existing_bookings:
        # Skip bookings without a confirmation code
        if not booking.confirmation_code:
            continue

        existing_codes.add(booking.confirmation_code)

        if booking.confirmation_code in current_bookings:
            # Booking still exists, check if details need updating
            current_data = current_bookings[booking.confirmation_code]

            needs_update = (
                    booking.check_in_date != current_data['check_in_date'] or
                    booking.check_out_date != current_data['check_out_date'] or
                    booking.number_of_nights != current_data['number_of_nights']
            )

            if needs_update:
                # Update booking details but preserve other fields
                booking.check_in_date = current_data['check_in_date']
                booking.check_out_date = current_data['check_out_date']
                booking.number_of_nights = current_data['number_of_nights']
                # Only update guest name if it's not already set to something more specific
                if booking.guest_name == f"Guest from {source}" or not booking.guest_name:
                    booking.guest_name = current_data['guest_name']
                booking.notes = f"Updated from {source} calendar: {current_data['description']}"
                bookings_updated += 1
        else:
            # Booking no longer exists in calendar - handle as cancelled
            db.session.delete(booking)
            bookings_cancelled += 1

    # Add new bookings (those in calendar but not in database)
    for confirmation_code, details in current_bookings.items():
        if confirmation_code not in existing_codes:
            # This is a new booking to add
            new_booking = BookingForm(
                guest_name=details['guest_name'],
                contact_number=f"Imported from {source}",
                check_in_date=details['check_in_date'],
                check_out_date=details['check_out_date'],
                property_name=unit.building or "Property",
                unit_id=unit_id,
                number_of_nights=details['number_of_nights'],
                number_of_guests=2,  # Default value
                price=0,  # Default value, to be updated later
                booking_source=source,
                payment_status="Pending",
                notes=f"Imported from {source} calendar: {details['description']}",
                company_id=unit.company_id,
                user_id=current_user.id,
                confirmation_code=confirmation_code
            )

            db.session.add(new_booking)
            bookings_added += 1

    # Commit all changes
    if bookings_added > 0 or bookings_updated > 0 or bookings_cancelled > 0:
        db.session.commit()

    return bookings_added, bookings_updated, bookings_cancelled


def extract_guest_name(summary, description):
    """Extract guest name from summary or description"""
    # Different platforms use different formats for guest information

    # Try to find patterns like "Booking for John Doe" or "Guest: John Doe"
    import re

    # Try various patterns
    patterns = [
        r"(?:Booking for|Guest:|Reserved by|Reservation for)\s+([A-Za-z\s]+)",
        r"([A-Za-z\s]+)'s reservation"
    ]

    for pattern in patterns:
        # Search in summary
        match = re.search(pattern, summary)
        if match:
            return match.group(1).strip()

        # Search in description
        match = re.search(pattern, description)
        if match:
            return match.group(1).strip()

    # If no pattern matches, try to use the summary as is
    if summary and len(summary) < 50 and not any(x in summary.lower() for x in ["booking", "reservation", "blocked"]):
        return summary

    return None


def update_calendar_source(unit_id, source_name, source_url=None):
    """Update or create a calendar source record"""
    calendar_source = CalendarSource.query.filter_by(
        unit_id=unit_id,
        source_name=source_name
    ).first()

    if calendar_source:
        # Update existing record
        calendar_source.last_updated = datetime.utcnow()
        if source_url:
            calendar_source.source_url = source_url
    else:
        # Create new record
        calendar_source = CalendarSource(
            unit_id=unit_id,
            source_name=source_name,
            source_url=source_url,
            last_updated=datetime.utcnow()
        )
        db.session.add(calendar_source)

    db.session.commit()
    return calendar_source


def sync_all_calendars():
    """Sync all calendar sources that have URLs"""
    calendar_sources = CalendarSource.query.filter(CalendarSource.source_url.isnot(None)).all()

    for source in calendar_sources:
        try:
            # Download the ICS file
            response = requests.get(source.source_url)
            if response.status_code == 200:
                calendar_data = response.text
                # Process the calendar
                process_ics_calendar(calendar_data, source.unit_id, source.source_name)
                # Update the last_updated timestamp
                source.last_updated = datetime.utcnow()
                db.session.commit()
        except Exception as e:
            print(f"Error syncing calendar for {source.unit.unit_number} from {source.source_name}: {str(e)}")


from flask_apscheduler import APScheduler

scheduler = APScheduler()


# Initialize the scheduler with the app
def init_scheduler(app):
    scheduler.init_app(app)
    scheduler.start()

    # Schedule the sync task to run every day at 2 AM
    scheduler.add_job(func=sync_all_calendars, trigger='cron', hour=2, id='sync_calendars')
    ## Schedule the sync task to run every minute
    #scheduler.add_job(
    #    func=sync_all_calendars,
    #    trigger='interval',
    #    minutes=1,
    #    id='sync_calendars'
    #)


@app.route('/import_ics', methods=['GET', 'POST'])
@login_required
@permission_required('can_manage_bookings')
def import_ics():
    if request.method == 'POST':
        # Check if a unit was selected
        unit_id = request.form.get('unit_id')
        if not unit_id:
            flash('Please select a unit', 'danger')
            return redirect(url_for('import_ics'))

        # Check if it's a URL import or file upload
        import_type = request.form.get('import_type')

        calendar_data = None
        source = request.form.get('booking_source', 'Airbnb')  # Default to Airbnb

        if import_type == 'url':
            # Get the ICS URL
            ics_url = request.form.get('ics_url')
            if not ics_url:
                flash('Please enter an ICS URL', 'danger')
                return redirect(url_for('import_ics'))

            try:
                # Download the ICS file
                response = requests.get(ics_url)
                if response.status_code != 200:
                    flash(f'Error downloading ICS file: {response.status_code}', 'danger')
                    return redirect(url_for('import_ics'))

                calendar_data = response.text
            except Exception as e:
                flash(f'Error downloading ICS file: {str(e)}', 'danger')
                return redirect(url_for('import_ics'))

        elif import_type == 'file':
            # Check if a file was uploaded
            if 'ics_file' not in request.files:
                flash('No file provided', 'danger')
                return redirect(url_for('import_ics'))

            file = request.files['ics_file']
            if file.filename == '':
                flash('No file selected', 'danger')
                return redirect(url_for('import_ics'))

            # Read the file contents
            try:
                calendar_data = file.read().decode('utf-8')
            except UnicodeDecodeError:
                # Try again without decoding if it's already binary
                file.seek(0)
                calendar_data = file.read()
            except Exception as e:
                flash(f'Error reading file: {str(e)}', 'danger')
                return redirect(url_for('import_ics'))
        else:
            flash('Invalid import type', 'danger')
            return redirect(url_for('import_ics'))

        # Process the ICS data
        if calendar_data:
            try:
                bookings_added, bookings_updated, bookings_cancelled = process_ics_calendar(calendar_data, unit_id,
                                                                                            source)

                # Get the latest booking ID for highlighting (if any were added)
                latest_booking = None
                if bookings_added > 0:
                    latest_booking = BookingForm.query.filter_by(unit_id=unit_id).order_by(
                        BookingForm.date_added.desc()).first()

                # Update calendar source
                source_url = request.form.get('ics_url') if import_type == 'url' else None
                update_calendar_source(unit_id, source, source_url)

                message_parts = []
                if bookings_added > 0:
                    message_parts.append(f"{bookings_added} bookings added")
                if bookings_updated > 0:
                    message_parts.append(f"{bookings_updated} bookings updated")
                if bookings_cancelled > 0:
                    message_parts.append(f"{bookings_cancelled} bookings cancelled")

                if message_parts:
                    flash(f"Calendar synchronized: {', '.join(message_parts)}", 'success')
                else:
                    flash(f"Calendar synchronized: No changes detected", 'info')

                # Redirect with highlight parameter if we added bookings
                if latest_booking:
                    return redirect(url_for('bookings', highlight_id=latest_booking.id))

            except Exception as e:
                flash(f'Error processing calendar: {str(e)}', 'danger')
                return redirect(url_for('import_ics'))

        return redirect(url_for('bookings'))

    # GET request - show the import form
    user_company_id = current_user.company_id
    units = Unit.query.filter_by(company_id=user_company_id).all()

    # Get existing calendar sources for each unit
    calendar_sources = {}
    for unit in units:
        sources = CalendarSource.query.filter_by(unit_id=unit.id).all()
        if sources:
            calendar_sources[unit.id] = sources

    return render_template('import_ics.html', units=units, calendar_sources=calendar_sources)


@app.route('/refresh_calendar/<int:source_id>')
@login_required
@permission_required('can_manage_bookings')
def refresh_calendar(source_id):
    calendar_source = CalendarSource.query.get_or_404(source_id)

    # Check if user has access to this unit
    if calendar_source.unit.company_id != current_user.company_id:
        flash('You do not have permission to manage this calendar', 'danger')
        return redirect(url_for('import_ics'))

    # Check if the source has a URL
    if not calendar_source.source_url:
        flash('This calendar source does not have a URL for refreshing', 'danger')
        return redirect(url_for('import_ics'))

    try:
        # Download the ICS file
        response = requests.get(calendar_source.source_url)
        if response.status_code != 200:
            flash(f'Error downloading ICS file: {response.status_code}', 'danger')
            return redirect(url_for('import_ics'))

        calendar_data = response.text

        # Process the calendar
        bookings_added, bookings_updated, bookings_cancelled = process_ics_calendar(calendar_data,
                                                                                    calendar_source.unit_id,
                                                                                    calendar_source.source_name)

        # Get the latest booking ID for highlighting (if any were added or updated)
        latest_booking = None
        if bookings_added > 0 or bookings_updated > 0:
            latest_booking = BookingForm.query.filter_by(unit_id=calendar_source.unit_id).order_by(
                BookingForm.date_added.desc()).first()

        # Update the last_updated timestamp
        calendar_source.last_updated = datetime.utcnow()
        db.session.commit()

        message_parts = []
        if bookings_added > 0:
            message_parts.append(f"{bookings_added} bookings added")
        if bookings_updated > 0:
            message_parts.append(f"{bookings_updated} bookings updated")
        if bookings_cancelled > 0:
            message_parts.append(f"{bookings_cancelled} bookings cancelled")

        if message_parts:
            flash(f"Calendar synchronized: {', '.join(message_parts)}", 'success')
        else:
            flash(f"Calendar synchronized: No changes detected", 'info')

        # Redirect with highlight parameter if we added or updated bookings
        if latest_booking:
            return redirect(url_for('bookings', highlight_id=latest_booking.id))

    except Exception as e:
        flash(f'Error refreshing calendar: {str(e)}', 'danger')

    return redirect(url_for('import_ics'))


@app.route('/delete_calendar_source/<int:source_id>')
@login_required
@permission_required('can_manage_bookings')
def delete_calendar_source(source_id):
    calendar_source = CalendarSource.query.get_or_404(source_id)

    # Check if user has access to this unit
    if calendar_source.unit.company_id != current_user.company_id:
        flash('You do not have permission to manage this calendar', 'danger')
        return redirect(url_for('import_ics'))

    # Delete the calendar source
    db.session.delete(calendar_source)
    db.session.commit()

    flash('Calendar source deleted successfully', 'success')
    return redirect(url_for('import_ics'))


# Add this helper function to parse dates in various formats
def parse_date(date_str):
    if not date_str or not date_str.strip():
        return None

    date_str = date_str.strip()

    # Try standard formats
    formats = [
        '%b %d, %Y',  # Jan 03, 2025
        '%B %d, %Y',  # January 03, 2025
        '%Y-%m-%d',  # 2025-01-03
        '%d/%m/%Y',  # 03/01/2025
        '%m/%d/%Y'  # 01/03/2025
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # Try to handle formats with single-digit days (without leading zeros)
    # This is trickier in Python as strptime expects exact format matches

    # Parse month names manually
    month_names = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5, 'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }

    # Check if it matches pattern like "Jan 3, 2025"
    import re
    match = re.match(r'([a-zA-Z]+)\s+(\d{1,2}),\s+(\d{4})', date_str)
    if match:
        month_name, day, year = match.groups()
        month_num = month_names.get(month_name.lower())
        if month_num:
            try:
                return datetime(int(year), month_num, int(day)).date()
            except ValueError:
                pass

    # If all attempts fail, return None
    print(f"Could not parse date: {date_str}")
    return None


# Add this endpoint to app.py
@app.route('/api/import_airbnb_csv', methods=['POST'])
@login_required
@permission_required('can_manage_bookings')
def import_airbnb_csv():
    # Get the bookings data from the request
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Invalid request format. JSON expected.'}), 400

    data = request.json
    bookings = data.get('bookings', [])

    if not bookings:
        return jsonify({'success': False, 'message': 'No booking data provided.'}), 400

    # Get the user's company ID
    company_id = current_user.company_id

    # Counters for tracking what happened
    created_count = 0
    updated_count = 0
    error_count = 0

    for booking_data in bookings:
        try:
            # Check if confirmation code exists
            confirmation_code = booking_data.get('confirmation_code')
            if not confirmation_code:
                error_count += 1
                continue

            # Check if we already have this booking in our database
            existing_booking = BookingForm.query.filter_by(
                confirmation_code=confirmation_code,
                company_id=company_id
            ).first()

            # If booking exists, update it with new information
            if existing_booking:
                # Convert date strings to date objects
                try:
                    check_in_date = datetime.strptime(booking_data.get('check_in_date', ''), '%Y-%m-%d').date()
                    check_out_date = datetime.strptime(booking_data.get('check_out_date', ''), '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    # Try different date format (like MM/DD/YYYY)
                    try:
                        check_in_date = datetime.strptime(booking_data.get('check_in_date', ''), '%m/%d/%Y').date()
                        check_out_date = datetime.strptime(booking_data.get('check_out_date', ''), '%m/%d/%Y').date()
                    except (ValueError, TypeError):
                        # Keep existing dates if parsing fails
                        check_in_date = existing_booking.check_in_date
                        check_out_date = existing_booking.check_out_date

                # Try to parse booking date
                booking_date = None
                # Update booking date if provided
                if booking_data.get('booking_date'):
                    parsed_date = parse_date(booking_data.get('booking_date'))
                    if parsed_date:
                        existing_booking.booking_date = parsed_date

                # Only update fields if they exist in the CSV
                if booking_data.get('guest_name'):
                    existing_booking.guest_name = booking_data.get('guest_name')
                if booking_data.get('contact_number'):
                    existing_booking.contact_number = booking_data.get('contact_number')

                # Update dates only if valid
                if check_in_date and check_out_date and check_in_date < check_out_date:
                    existing_booking.check_in_date = check_in_date
                    existing_booking.check_out_date = check_out_date
                    # Calculate nights from the dates
                    existing_booking.number_of_nights = (check_out_date - check_in_date).days

                # Update booking_date if parsed successfully
                if booking_date:
                    existing_booking.booking_date = booking_date

                # Update other fields
                # Update other fields
                if booking_data.get('price'):
                    try:
                        # Handle price as string, removing any non-numeric characters except periods
                        price_str = str(booking_data.get('price'))
                        # Remove any remaining 'RM' if it wasn't caught by JavaScript
                        price_str = price_str.replace('RM', '').replace(',', '').strip()
                        price_value = float(price_str)

                        if price_value > 0:
                            existing_booking.price = price_value
                            print(f"Updated price to: {price_value}")
                    except (ValueError, TypeError) as e:
                        print(f"Failed to convert price: {booking_data.get('price')} - Error: {e}")

                if booking_data.get('payment_status'):
                    existing_booking.payment_status = booking_data.get('payment_status')

                # Update guest counts
                if 'adults' in booking_data and booking_data['adults'] > 0:
                    existing_booking.adults = booking_data['adults']
                if 'children' in booking_data and booking_data['children'] > 0:
                    existing_booking.children = booking_data['children']
                if 'infants' in booking_data and booking_data['infants'] > 0:
                    existing_booking.infants = booking_data['infants']

                # Update total number of guests
                existing_booking.number_of_guests = (
                        (existing_booking.adults or 0) +
                        (existing_booking.children or 0) +
                        (existing_booking.infants or 0)
                )

                updated_count += 1
            else:
                # This is a new booking - we would normally create it, but
                # in this case we'll skip it since we want to focus on updating existing bookings
                # If you decide you want to create new bookings too, uncomment this block
                """
                # New booking, but first we need to find the correct unit_id
                unit = None
                if booking_data.get('unit_number'):
                    unit = Unit.query.filter_by(
                        unit_number=booking_data.get('unit_number'),
                        company_id=company_id
                    ).first()

                if not unit:
                    # Skip if we can't find the unit
                    error_count += 1
                    continue

                # Convert date strings to date objects
                try:
                    check_in_date = datetime.strptime(booking_data.get('check_in_date', ''), '%Y-%m-%d').date()
                    check_out_date = datetime.strptime(booking_data.get('check_out_date', ''), '%Y-%m-%d').date()
                    nights = (check_out_date - check_in_date).days
                except (ValueError, TypeError):
                    # Try different date format
                    try:
                        check_in_date = datetime.strptime(booking_data.get('check_in_date', ''), '%m/%d/%Y').date()
                        check_out_date = datetime.strptime(booking_data.get('check_out_date', ''), '%m/%d/%Y').date()
                        nights = (check_out_date - check_in_date).days
                    except (ValueError, TypeError):
                        error_count += 1
                        continue

                # Parse booking date
                # Try to parse booking date - using the correct YYYY-MM-DD format
                booking_date = None
                if booking_data.get('booking_date'):
                    try:
                        # Parse in YYYY-MM-DD format
                        booking_date = datetime.strptime(booking_data.get('booking_date'), '%Y-%m-%d').date()
                    except (ValueError, TypeError) as e:
                        print(f"Error parsing booking date '{booking_data.get('booking_date')}': {e}")
                        # Keep the existing booking date if parsing fails
                        booking_date = existing_booking.booking_date

                # Create new booking
                new_booking = BookingForm(
                    guest_name=booking_data.get('guest_name', 'Airbnb Guest'),
                    contact_number=booking_data.get('contact_number', '-'),
                    check_in_date=check_in_date,
                    check_out_date=check_out_date,
                    property_name=unit.building or "Property",
                    unit_id=unit.id,
                    number_of_nights=nights,
                    number_of_guests=(
                        (booking_data.get('adults') or 0) + 
                        (booking_data.get('children') or 0) + 
                        (booking_data.get('infants') or 0)
                    ),
                    price=booking_data.get('price', '0.00'),
                    booking_source='Airbnb',
                    payment_status=booking_data.get('payment_status', 'Pending'),
                    notes=f"Imported from Airbnb CSV",
                    confirmation_code=confirmation_code,
                    booking_date=booking_date,
                    adults=booking_data.get('adults'),
                    children=booking_data.get('children'),
                    infants=booking_data.get('infants'),
                    company_id=company_id,
                    user_id=current_user.id
                )

                db.session.add(new_booking)
                created_count += 1
                """

                # Skip creating new bookings
                pass

        except Exception as e:
            error_count += 1
            print(f"Error processing booking: {e}")

    # Commit all changes
    db.session.commit()

    # Return the result
    return jsonify({
        'success': True,
        'message': f"Successfully processed {updated_count} bookings. Updated: {updated_count}, Errors: {error_count}",
        'updated': updated_count,
        'created': created_count,
        'errors': error_count
    })


# Update to the add_contact route to handle custom building
@app.route('/add_contact', methods=['POST'])
@login_required
def add_contact():
    if request.method == 'POST':
        try:
            full_name = request.form['full_name']
            role = request.form['role']
            phone = request.form.get('phone', '')

            # Handle custom building input
            building = request.form.get('building', '')
            custom_building = request.form.get('custom_building', '')

            if building == 'custom' and custom_building:
                building = custom_building

            favourite = 'favourite' in request.form
            notes = request.form.get('notes', '')

            # Create and add new contact
            new_contact = Contact(
                full_name=full_name,
                role=role,
                phone=phone,
                building=building,
                favourite=favourite,
                notes=notes,
                company_id=current_user.company_id,
                user_id=current_user.id
            )

            db.session.add(new_contact)
            db.session.commit()

            flash('Contact added successfully', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding contact: {str(e)}', 'danger')

        return redirect(url_for('contacts'))

    return redirect(url_for('contacts'))


# Update to the edit_contact route to handle custom building
@app.route('/edit_contact/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_contact(id):
    contact = Contact.query.get_or_404(id)

    # Ensure the contact belongs to the user's company
    if contact.company_id != current_user.company_id:
        flash('You do not have permission to edit this contact', 'danger')
        return redirect(url_for('contacts'))

    if request.method == 'POST':
        contact.full_name = request.form['full_name']
        contact.role = request.form['role']
        contact.phone = request.form.get('phone', '')

        # Handle custom building input
        building = request.form.get('building', '')
        custom_building = request.form.get('custom_building', '')

        if building == 'custom' and custom_building:
            contact.building = custom_building
        else:
            contact.building = building

        contact.favourite = 'favourite' in request.form
        contact.notes = request.form.get('notes', '')

        db.session.commit()
        flash('Contact updated successfully', 'success')
        return redirect(url_for('contacts'))

    # Get unique building names for the dropdown
    buildings_set = set()
    units = Unit.query.filter_by(company_id=current_user.company_id).all()

    # Extract unique building names
    buildings_list = []
    for unit in units:
        if unit.building and unit.building not in buildings_set:
            buildings_set.add(unit.building)
            buildings_list.append(unit.building)

    return render_template('edit_contact.html', contact=contact, buildings_list=buildings_list)


# Update to the contacts route to fix building dropdown
@app.route('/contacts')
@login_required
def contacts():
    # Get all contacts for the current user's company
    user_company_id = current_user.company_id
    contacts_list = Contact.query.filter_by(company_id=user_company_id).all()

    # Get units for filtering
    units = Unit.query.filter_by(company_id=user_company_id).all()

    # Extract unique building names
    # Use a set to ensure uniqueness
    buildings_set = set()
    for unit in units:
        if unit.building:
            buildings_set.add(unit.building)
    buildings_list = sorted(list(buildings_set))
    for unit in units:
        if unit.building and unit.building not in buildings_set:
            buildings_set.add(unit.building)
            buildings_list.append(unit.building)

    return render_template('contact.html', contacts=contacts_list, units=units, buildings_list=buildings_list)


@app.route('/delete_contact/<int:id>')
@login_required
def delete_contact(id):
    contact = Contact.query.get_or_404(id)

    # Ensure the contact belongs to the user's company
    if contact.company_id != current_user.company_id:
        flash('You do not have permission to delete this contact', 'danger')
        return redirect(url_for('contacts'))

    db.session.delete(contact)
    db.session.commit()

    flash('Contact deleted successfully', 'success')
    return redirect(url_for('contacts'))


# Create the database tables
with app.app_context():
    db.create_all()
    create_default_data()
    create_account_types()

if __name__ == '__main__':
    app.run(debug=True)


# Add to app.py - Expenses page route
@app.route('/expenses')
@login_required
def expenses():
    # Get current month and year for default filter
    current_date = datetime.now()
    current_month = f"{current_date.year}-{current_date.month:02d}"

    # Get unique buildings for filter
    user_company_id = current_user.company_id
    buildings = []
    units_with_buildings = Unit.query.filter_by(company_id=user_company_id).filter(Unit.building.isnot(None)).all()

    # Extract unique building names
    building_set = set()
    for unit in units_with_buildings:
        if unit.building and unit.building.strip() and unit.building not in building_set:
            building_set.add(unit.building)
            buildings.append(unit.building)

    # Sort buildings alphabetically
    buildings.sort()

    return render_template('expenses.html', current_month=current_month, buildings=buildings)


# API endpoint to get expense data
@app.route('/api/expenses', methods=['GET'])
@login_required
def get_expenses():
    # Get query parameters
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if not year or not month:
        return jsonify({'error': 'Year and month parameters are required'}), 400

    # Get all units for the current company
    company_id = current_user.company_id
    units = Unit.query.filter_by(company_id=company_id).all()

    # Format unit data for the response
    units_data = [{'id': unit.id, 'unit_number': unit.unit_number, 'building': unit.building} for unit in units]

    # Get expense data for the specified month and year
    expenses_data = {}

    # Query from database
    expenses = ExpenseData.query.filter_by(
        company_id=company_id,
        year=year,
        month=month
    ).all()

    # Format expense data
    for expense in expenses:
        expenses_data[expense.unit_id] = {
            'sales': expense.sales,
            'rental': expense.rental,
            'electricity': expense.electricity,
            'water': expense.water,
            'sewage': expense.sewage,
            'internet': expense.internet,
            'cleaner': expense.cleaner,
            'laundry': expense.laundry,
            'supplies': expense.supplies,
            'repair': expense.repair,
            'replace': expense.replace,
            'other': expense.other
        }

    return jsonify({
        'units': units_data,
        'expenses': expenses_data
    })


# API endpoint to save expense data
@app.route('/api/expenses', methods=['POST'])
@login_required
def save_expenses():
    # Get data from request
    data = request.json

    if not data or 'year' not in data or 'month' not in data or 'expenses' not in data:
        return jsonify({'error': 'Invalid data format'}), 400

    year = data['year']
    month = data['month']
    expenses_data = data['expenses']
    company_id = current_user.company_id

    # Process each unit's expense data
    for unit_id, expense in expenses_data.items():
        # Convert unit_id to integer (it might be a string in JSON)
        unit_id = int(unit_id)

        # Check if unit belongs to the company
        unit = Unit.query.filter_by(id=unit_id, company_id=company_id).first()
        if not unit:
            continue  # Skip if unit doesn't belong to the company

        # Check if expense record already exists
        existing_expense = ExpenseData.query.filter_by(
            company_id=company_id,
            unit_id=unit_id,
            year=year,
            month=month
        ).first()

        if existing_expense:
            # Update existing record
            existing_expense.sales = expense.get('sales', '')
            existing_expense.rental = expense.get('rental', '')
            existing_expense.electricity = expense.get('electricity', '')
            existing_expense.water = expense.get('water', '')
            existing_expense.sewage = expense.get('sewage', '')
            existing_expense.internet = expense.get('internet', '')
            existing_expense.cleaner = expense.get('cleaner', '')
            existing_expense.laundry = expense.get('laundry', '')
            existing_expense.supplies = expense.get('supplies', '')
            existing_expense.repair = expense.get('repair', '')
            existing_expense.replace = expense.get('replace', '')
            existing_expense.other = expense.get('other', '')
        else:
            # Create new record
            new_expense = ExpenseData(
                company_id=company_id,
                unit_id=unit_id,
                year=year,
                month=month,
                sales=expense.get('sales', ''),
                rental=expense.get('rental', ''),
                electricity=expense.get('electricity', ''),
                water=expense.get('water', ''),
                sewage=expense.get('sewage', ''),
                internet=expense.get('internet', ''),
                cleaner=expense.get('cleaner', ''),
                laundry=expense.get('laundry', ''),
                supplies=expense.get('supplies', ''),
                repair=expense.get('repair', ''),
                replace=expense.get('replace', ''),
                other=expense.get('other', '')
            )
            db.session.add(new_expense)

    # Commit all changes
    db.session.commit()

    return jsonify({'success': True, 'message': 'Expenses data saved successfully'})


@app.route('/api/bookings/monthly_revenue')
@login_required
def get_monthly_revenue():
    # Get query parameters
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)

    if not year or not month:
        return jsonify({'error': 'Year and month parameters are required'}), 400

    # Get the company ID for the current user
    company_id = current_user.company_id

    # Set date range for the specified month
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date()
    else:
        end_date = datetime(year, month + 1, 1).date()

    # Query bookings for the month that either:
    # 1. Have check-in date during the specified month
    # 2. Have check-out date during the specified month
    # 3. Span the entire month (check-in before the month, check-out after the month)
    bookings = BookingForm.query.filter(
        BookingForm.company_id == company_id,
        (
            # Check-in during the month
                (BookingForm.check_in_date >= start_date) & (BookingForm.check_in_date < end_date) |
                # Check-out during the month
                (BookingForm.check_out_date > start_date) & (BookingForm.check_out_date <= end_date) |
                # Spanning the entire month
                (BookingForm.check_in_date <= start_date) & (BookingForm.check_out_date >= end_date)
        )
    ).all()

    # Calculate revenue per unit
    revenues = {}
    for booking in bookings:
        unit_id = booking.unit_id
        if unit_id not in revenues:
            revenues[unit_id] = 0

        # Calculate the portion of booking revenue to attribute to this month
        total_nights = (booking.check_out_date - booking.check_in_date).days
        if total_nights <= 0:
            continue

        # Determine the nights that fall within the selected month
        night_start = max(booking.check_in_date, start_date)
        night_end = min(booking.check_out_date, end_date)
        nights_in_month = (night_end - night_start).days

        # Calculate prorated revenue for the month
        if total_nights > 0 and booking.price:
            try:
                daily_rate = float(booking.price) / total_nights
                month_revenue = daily_rate * nights_in_month
                revenues[unit_id] += month_revenue
            except (ValueError, TypeError):
                # Handle any conversion errors
                pass

    return jsonify({'revenues': revenues})


@app.route('/api/issues/monthly_costs')
@login_required
def get_monthly_issue_costs():
    # Get query parameters
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    issue_type = request.args.get('type')  # 'repair' or 'replace'

    if not year or not month:
        return jsonify({'error': 'Year and month parameters are required'}), 400

    # Get the company ID for the current user
    company_id = current_user.company_id

    # Set date range for the specified month
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    # Query to get issue costs for the month
    query = Issue.query.filter(
        Issue.company_id == company_id,
        Issue.date_added >= start_date,
        Issue.date_added < end_date,
        Issue.cost.isnot(None)  # Only include issues with non-null cost
    )

    # Filter by type if specified
    if issue_type == 'repair':
        # Join with Type model to filter for "Repair" type
        repair_type = Type.query.filter_by(name='Repair').first()
        if repair_type:
            query = query.filter(Issue.type_id == repair_type.id)
    elif issue_type == 'replace':
        # Join with Type model to filter for "Replace" type
        replace_type = Type.query.filter_by(name='Replace').first()
        if replace_type:
            query = query.filter(Issue.type_id == replace_type.id)

    # Get the issues
    issues = query.all()

    # Calculate costs per unit
    costs = {}
    for issue in issues:
        unit_id = issue.unit_id
        if unit_id not in costs:
            costs[unit_id] = 0

        try:
            if issue.cost:
                costs[unit_id] += float(issue.cost)
        except (ValueError, TypeError):
            # Handle any conversion errors
            pass

    return jsonify({'costs': costs})


@app.route('/api/expenses/yearly', methods=['GET'])
@login_required
def get_yearly_expenses():
    # Get query parameters
    year = request.args.get('year', type=int)
    building = request.args.get('building', 'all')

    if not year:
        return jsonify({'error': 'Year parameter is required'}), 400

    # Get the company ID for the current user
    company_id = current_user.company_id

    # Get all units for the company, filtered by building if specified
    if building == 'all':
        units = Unit.query.filter_by(company_id=company_id).all()
    else:
        units = Unit.query.filter_by(company_id=company_id, building=building).all()

    # Format unit data for the response
    units_data = [{'id': unit.id, 'unit_number': unit.unit_number, 'building': unit.building} for unit in units]

    # Get expense data for all months in the specified year
    yearly_expenses = {}

    # For each unit
    for unit in units:
        unit_id = unit.id
        yearly_expenses[unit_id] = {}

        # For each month
        for month in range(1, 13):
            # Check if we have data for this month
            expense_data = ExpenseData.query.filter_by(
                company_id=company_id,
                unit_id=unit_id,
                year=year,
                month=month
            ).first()

            if expense_data:
                # If we have data, format it
                yearly_expenses[unit_id][month] = {
                    'sales': float(expense_data.sales or 0),
                    'rental': float(expense_data.rental or 0),
                    'electricity': float(expense_data.electricity or 0),
                    'water': float(expense_data.water or 0),
                    'sewage': float(expense_data.sewage or 0),
                    'internet': float(expense_data.internet or 0),
                    'cleaner': float(expense_data.cleaner or 0),
                    'laundry': float(expense_data.laundry or 0),
                    'supplies': float(expense_data.supplies or 0),
                    'repair': float(expense_data.repair or 0),
                    'replace': float(expense_data.replace or 0),
                    'other': float(expense_data.other or 0)
                }
            else:
                # If we don't have data, use empty values
                yearly_expenses[unit_id][month] = {
                    'sales': 0,
                    'rental': 0,
                    'electricity': 0,
                    'water': 0,
                    'sewage': 0,
                    'internet': 0,
                    'cleaner': 0,
                    'laundry': 0,
                    'supplies': 0,
                    'repair': 0,
                    'replace': 0,
                    'other': 0
                }

    return jsonify({
        'units': units_data,
        'expenses': yearly_expenses
    })


@app.route('/api/expenses/years', methods=['GET'])
@login_required
def get_expense_years():
    # Get the company ID for the current user
    company_id = current_user.company_id

    # Get all years with expense data
    years = db.session.query(ExpenseData.year) \
        .filter_by(company_id=company_id) \
        .distinct() \
        .order_by(ExpenseData.year.desc()) \
        .all()

    # Extract years from query result
    years_list = [year[0] for year in years]

    # If no years found, add current year
    if not years_list:
        years_list = [datetime.now().year]

    return jsonify({
        'years': years_list
    })