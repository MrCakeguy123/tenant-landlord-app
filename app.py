import os
import sqlite3
import logging
import datetime
from flask import Flask, g, render_template, request, redirect, url_for, session, flash

# -----------------------
# App & Logging Setup
# -----------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-in-production'  # TODO: override in production
app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), 'tenantlandlord.db')

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
logger = logging.getLogger(__name__)

# -----------------------
# Database Helpers
# -----------------------

def get_db():
    if 'db' not in g:
        logger.debug("Opening new database connection.")
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        logger.debug("Closing database connection.")
        db.close()

def init_db():
    """Initialize or migrate the database with required tables."""
    db = get_db()
    logger.debug("Initializing database schema (creating tables if needed).")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('tenant', 'landlord')),
            full_name TEXT
        );

        CREATE TABLE IF NOT EXISTS maintenance_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS leases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            landlord_id INTEGER NOT NULL,
            monthly_rent REAL NOT NULL,
            due_day INTEGER NOT NULL DEFAULT 1,
            start_date DATE,
            end_date DATE,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (tenant_id) REFERENCES users(id),
            FOREIGN KEY (landlord_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS rent_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lease_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Paid',
            paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            method TEXT,
            note TEXT,
            FOREIGN KEY (lease_id) REFERENCES leases(id)
        );
        """
    )
    db.commit()
    logger.info("Database schema ensured (tables created if they did not exist).")

# -----------------------
# Helper functions for rent
# -----------------------

def get_current_month_year():
    today = datetime.date.today()
    month_label = today.strftime("%B %Y")
    return today.month, today.year, month_label

def get_active_lease_for_tenant(tenant_id):
    db = get_db()
    lease = db.execute(
        """
        SELECT l.*, t.full_name as tenant_name, ll.full_name as landlord_name
        FROM leases l
        JOIN users t ON t.id = l.tenant_id
        JOIN users ll ON ll.id = l.landlord_id
        WHERE l.tenant_id = ? AND l.is_active = 1
        ORDER BY l.id DESC
        LIMIT 1
        """,
        (tenant_id,)
    ).fetchone()
    logger.debug("Active lease for tenant_id %s: %s", tenant_id, dict(lease) if lease else None)
    return lease

def get_rent_status_for_lease(lease_id, monthly_rent, month, year):
    db = get_db()
    row = db.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN status = 'Paid' THEN amount ELSE 0 END), 0) as paid
        FROM rent_payments
        WHERE lease_id = ? AND month = ? AND year = ?
        """,
        (lease_id, month, year)
    ).fetchone()
    paid = row['paid'] if row else 0
    if paid >= monthly_rent:
        status = 'Paid'
    elif paid > 0:
        status = 'Partial'
    else:
        status = 'Unpaid'
    logger.debug(
        "Rent status for lease_id=%s month=%s year=%s: paid=%.2f status=%s (monthly_rent=%.2f)",
        lease_id, month, year, paid, status, monthly_rent
    )
    return paid, status

def get_recent_rent_payments_for_tenant(tenant_id, limit=5):
    db = get_db()
    rows = db.execute(
        """
        SELECT rp.*, l.monthly_rent
        FROM rent_payments rp
        JOIN leases l ON l.id = rp.lease_id
        WHERE l.tenant_id = ?
        ORDER BY rp.paid_at DESC
        LIMIT ?
        """,
        (tenant_id, limit)
    ).fetchall()
    logger.debug("Loaded %d recent rent payments for tenant_id=%s", len(rows), tenant_id)
    return rows

# -----------------------
# Auth Helpers
# -----------------------

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        logger.debug("No user_id in session.")
        return None
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    logger.debug("Loaded current user from DB: %s", dict(user) if user else None)
    return user

@app.context_processor
def inject_current_user():
    """Make the current user available in all templates as current_user."""
    try:
        user = get_current_user()
    except Exception as exc:  # pragma: no cover - very defensive
        logger.error("Error injecting current_user: %s", exc)
        user = None
    return {"current_user": user}

def login_required(role=None):
    """Decorator to require login (and optional role) for a view."""
    from functools import wraps

    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            user = get_current_user()
            if user is None:
                flash("Please log in first.", "warning")
                logger.warning("Unauthorized access attempt to %s", request.path)
                return redirect(url_for('login', next=request.path))
            if role is not None and user['role'] != role:
                flash("You do not have access to that page.", "danger")
                logger.warning(
                    "User %s with role %s tried to access %s-only page %s",
                    user['username'], user['role'], role, request.path
                )
                return redirect(url_for('dashboard'))
            return view(*args, **kwargs)
        return wrapped_view
    return decorator

# -----------------------
# Routes: Core / Auth
# -----------------------

@app.route('/')
def index():
    logger.debug("Index page requested.")
    user = get_current_user()
    if user:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/init-db')
def init_db_route():
    """Manual route to (re)initialize DB tables (no demo data)."""
    logger.info("Init DB route called.")
    init_db()
    flash("Database tables checked/initialized.", "success")
    return redirect(url_for('index'))

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """
    One-time setup route to create the first landlord account.
    If any users already exist, this route just redirects to login.
    """
    db = get_db()
    count = db.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    if count > 0:
        logger.info("Setup route accessed but users already exist; redirecting.")
        flash("Setup has already been completed.", "info")
        return redirect(url_for('login'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        logger.debug("Initial setup: attempting to create landlord username='%s'", username)

        if not username or not password:
            flash("Username and password are required.", "warning")
        else:
            try:
                db.execute(
                    "INSERT INTO users (username, password, role, full_name) VALUES (?, ?, 'landlord', ?)",
                    (username, password, full_name)
                )
                db.commit()
                logger.info("Initial landlord account '%s' created via setup.", username)
                flash("Landlord account created. You can now log in.", "success")
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                logger.warning("IntegrityError creating initial landlord with username='%s'", username)
                flash("That username is already taken.", "danger")

    return render_template('setup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    logger.debug("Login route hit with method %s", request.method)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        logger.debug("Login attempt for username='%s'", username)
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? AND password = ?",
            (username, password)
        ).fetchone()
        if user:
            session['user_id'] = user['id']
            logger.info("User '%s' logged in successfully.", username)
            flash("Welcome back!", "success")
            next_url = request.args.get('next')
            return redirect(next_url or url_for('dashboard'))
        else:
            logger.warning("Failed login attempt for username='%s'", username)
            flash("Invalid username or password.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    logger.info("Logout requested.")
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    user = get_current_user()
    if not user:
        logger.debug("Dashboard requested without user; redirecting to login.")
        return redirect(url_for('login'))
    logger.debug("Dashboard for user '%s' (role=%s)", user['username'], user['role'])
    if user['role'] == 'landlord':
        return redirect(url_for('landlord_dashboard'))
    return redirect(url_for('tenant_dashboard'))

# -----------------------
# Tenant Views
# -----------------------

@app.route('/tenant')
@login_required(role='tenant')
def tenant_dashboard():
    user = get_current_user()
    db = get_db()
    logger.debug("Loading tenant dashboard for tenant id=%s", user['id'])

    # Maintenance requests
    requests = db.execute(
        "SELECT * FROM maintenance_requests WHERE tenant_id = ? ORDER BY created_at DESC",
        (user['id'],)
    ).fetchall()

    # Rent info
    month, year, month_label = get_current_month_year()
    lease = get_active_lease_for_tenant(user['id'])
    rent_paid = 0
    rent_status = None
    recent_payments = []
    if lease:
        rent_paid, rent_status = get_rent_status_for_lease(
            lease['id'], lease['monthly_rent'], month, year
        )
        recent_payments = get_recent_rent_payments_for_tenant(user['id'], limit=5)
    else:
        logger.warning("No active lease found for tenant id=%s", user['id'])

    return render_template(
        'tenant_dashboard.html',
        user=user,
        requests=requests,
        lease=lease,
        rent_month_label=month_label,
        rent_paid=rent_paid,
        rent_status=rent_status,
        recent_payments=recent_payments
    )

@app.route('/tenant/request/new', methods=['GET', 'POST'])
@login_required(role='tenant')
def new_request():
    user = get_current_user()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        logger.debug(
            "New maintenance request submission by tenant id=%s, title='%s'",
            user['id'], title
        )
        if not title or not description:
            flash("Please fill in both title and description.", "warning")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO maintenance_requests (tenant_id, title, description, status) VALUES (?, ?, ?, ?)",
                (user['id'], title, description, 'Open')
            )
            db.commit()
            logger.info(
                "Maintenance request created for tenant id=%s with title='%s'",
                user['id'], title
            )
            flash("Request submitted!", "success")
            return redirect(url_for('tenant_dashboard'))
    return render_template('new_request.html', user=user)

@app.route('/tenant/rent/pay', methods=['POST'])
@login_required(role='tenant')
def tenant_pay_rent():
    user = get_current_user()
    db = get_db()
    amount_raw = request.form.get('amount', '').strip()
    method = request.form.get('method', '').strip() or 'Recorded in app'
    note = request.form.get('note', '').strip()
    logger.debug(
        "Tenant id=%s attempting to record rent payment amount_raw='%s', method='%s'",
        user['id'], amount_raw, method
    )

    try:
        amount = float(amount_raw)
    except ValueError:
        logger.warning("Invalid payment amount entered by tenant id=%s: '%s'", user['id'], amount_raw)
        flash("Please enter a valid numeric amount.", "warning")
        return redirect(url_for('tenant_dashboard'))

    if amount <= 0:
        logger.warning("Non-positive payment amount entered by tenant id=%s: %s", user['id'], amount)
        flash("Payment amount must be greater than zero.", "warning")
        return redirect(url_for('tenant_dashboard'))

    lease = get_active_lease_for_tenant(user['id'])
    if not lease:
        logger.warning("Tenant id=%s tried to pay rent but has no active lease.", user['id'])
        flash("No active lease found. Please contact your landlord.", "danger")
        return redirect(url_for('tenant_dashboard'))

    month, year, _ = get_current_month_year()

    db.execute(
        """
        INSERT INTO rent_payments (lease_id, amount, month, year, status, method, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (lease['id'], amount, month, year, 'Paid', method, note)
    )
    db.commit()
    logger.info(
        "Recorded rent payment for tenant id=%s, lease_id=%s, amount=%.2f, month=%s, year=%s",
        user['id'], lease['id'], amount, month, year
    )
    flash("Rent payment recorded for this month (this does not actually charge a card).", "success")
    return redirect(url_for('tenant_dashboard'))

# -----------------------
# Landlord Views
# -----------------------

@app.route('/landlord')
@login_required(role='landlord')
def landlord_dashboard():
    user = get_current_user()
    db = get_db()
    logger.debug("Loading landlord dashboard for landlord id=%s", user['id'])

    # Maintenance overview scoped to this landlord's tenants
    requests = db.execute(
        """
        SELECT mr.*, u.full_name as tenant_name, u.username as tenant_username
        FROM maintenance_requests mr
        JOIN users u ON u.id = mr.tenant_id
        LEFT JOIN leases l ON l.tenant_id = u.id AND l.is_active = 1
        WHERE l.landlord_id = ?
        ORDER BY mr.created_at DESC
        """,
        (user['id'],)
    ).fetchall()

    open_count = db.execute(
        """
        SELECT COUNT(*) as c
        FROM maintenance_requests mr
        JOIN users u ON u.id = mr.tenant_id
        LEFT JOIN leases l ON l.tenant_id = u.id AND l.is_active = 1
        WHERE mr.status = 'Open'
          AND l.landlord_id = ?
        """,
        (user['id'],)
    ).fetchone()['c']

    # Rent overview for current month
    month, year, month_label = get_current_month_year()
    logger.debug("Calculating rent overview for landlord id=%s month=%s year=%s", user['id'], month, year)

    rent_rows = db.execute(
        """
        SELECT l.id as lease_id,
               t.full_name as tenant_name,
               t.username as tenant_username,
               l.monthly_rent,
               l.due_day,
               COALESCE(SUM(CASE WHEN rp.status = 'Paid' THEN rp.amount ELSE 0 END), 0) as paid_amount
        FROM leases l
        JOIN users t ON t.id = l.tenant_id
        LEFT JOIN rent_payments rp
          ON rp.lease_id = l.id
         AND rp.month = ?
         AND rp.year = ?
        WHERE l.is_active = 1
          AND l.landlord_id = ?
        GROUP BY l.id, tenant_name, tenant_username, l.monthly_rent, l.due_day
        ORDER BY tenant_name
        """,
        (month, year, user['id'])
    ).fetchall()

    rent_overview = []
    unpaid_count = 0
    for row in rent_rows:
        monthly_rent = row['monthly_rent']
        paid_amount = row['paid_amount']
        if paid_amount >= monthly_rent:
            status = 'Paid'
        elif paid_amount > 0:
            status = 'Partial'
        else:
            status = 'Unpaid'
        if status != 'Paid':
            unpaid_count += 1
        rent_overview.append({
            'tenant_name': row['tenant_name'] or row['tenant_username'],
            'monthly_rent': monthly_rent,
            'due_day': row['due_day'],
            'paid_amount': paid_amount,
            'status': status,
        })
    logger.debug(
        "Rent overview generated for %d leases for landlord id=%s, unpaid_count=%d",
        len(rent_overview), user['id'], unpaid_count
    )

    recent_payments = db.execute(
        """
        SELECT rp.*, t.full_name as tenant_name, t.username as tenant_username
        FROM rent_payments rp
        JOIN leases l ON l.id = rp.lease_id
        JOIN users t ON t.id = l.tenant_id
        WHERE l.landlord_id = ?
        ORDER BY rp.paid_at DESC
        LIMIT 10
        """,
        (user['id'],)
    ).fetchall()
    logger.debug("Loaded %d recent rent payments for landlord view.", len(recent_payments))

    return render_template(
        'landlord_dashboard.html',
        user=user,
        requests=requests,
        open_count=open_count,
        rent_month_label=month_label,
        rent_overview=rent_overview,
        unpaid_count=unpaid_count,
        recent_payments=recent_payments
    )

@app.route('/landlord/tenants')
@login_required(role='landlord')
def landlord_tenants():
    user = get_current_user()
    db = get_db()
    tenants = db.execute(
        "SELECT * FROM users WHERE role = 'tenant' ORDER BY full_name, username"
    ).fetchall()
    logger.debug("Loaded %d tenants for landlord id=%s", len(tenants), user['id'])
    return render_template('landlord_tenants.html', user=user, tenants=tenants)

@app.route('/landlord/tenant/new', methods=['GET', 'POST'])
@login_required(role='landlord')
def landlord_new_tenant():
    user = get_current_user()
    db = get_db()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        logger.debug(
            "Landlord id=%s creating tenant username='%s'",
            user['id'], username
        )
        if not username or not password:
            flash("Username and password are required.", "warning")
        else:
            try:
                db.execute(
                    "INSERT INTO users (username, password, role, full_name) VALUES (?, ?, 'tenant', ?)",
                    (username, password, full_name)
                )
                db.commit()
                flash("Tenant account created.", "success")
                logger.info("Landlord '%s' created tenant '%s'", user['username'], username)
                return redirect(url_for('landlord_tenants'))
            except sqlite3.IntegrityError:
                logger.warning("Landlord '%s' tried to create duplicate username '%s'", user['username'], username)
                flash("That username is already taken.", "danger")
    return render_template('landlord_tenant_form.html', user=user)

@app.route('/landlord/leases')
@login_required(role='landlord')
def landlord_leases():
    user = get_current_user()
    db = get_db()
    leases = db.execute(
        """
        SELECT l.*,
               t.full_name as tenant_name,
               t.username as tenant_username
        FROM leases l
        JOIN users t ON t.id = l.tenant_id
        WHERE l.landlord_id = ?
        ORDER BY t.full_name, t.username
        """,
        (user['id'],)
    ).fetchall()
    logger.debug("Loaded %d leases for landlord id=%s", len(leases), user['id'])
    return render_template('landlord_leases.html', user=user, leases=leases)

@app.route('/landlord/lease/new', methods=['GET', 'POST'])
@login_required(role='landlord')
def landlord_new_lease():
    user = get_current_user()
    db = get_db()
    tenants = db.execute(
        "SELECT id, full_name, username FROM users WHERE role = 'tenant' ORDER BY full_name, username"
    ).fetchall()
    if not tenants:
        flash("You need to create a tenant before you can create a lease.", "warning")

    if request.method == 'POST':
        tenant_id_raw = request.form.get('tenant_id', '').strip()
        monthly_rent_raw = request.form.get('monthly_rent', '').strip()
        due_day_raw = request.form.get('due_day', '').strip()
        start_date = request.form.get('start_date', '').strip() or None
        end_date = request.form.get('end_date', '').strip() or None
        is_active = 1 if request.form.get('is_active') == 'on' else 0
        logger.debug(
            "Landlord id=%s creating lease for tenant_id_raw='%s', rent_raw='%s'",
            user['id'], tenant_id_raw, monthly_rent_raw
        )

        try:
            tenant_id = int(tenant_id_raw)
        except ValueError:
            flash("Please select a tenant.", "warning")
            return render_template('landlord_lease_form.html', user=user, tenants=tenants, lease=None)

        try:
            monthly_rent = float(monthly_rent_raw)
        except ValueError:
            flash("Please enter a valid monthly rent.", "warning")
            return render_template('landlord_lease_form.html', user=user, tenants=tenants, lease=None)

        try:
            due_day = int(due_day_raw)
        except ValueError:
            flash("Please enter a valid due day (1-28).", "warning")
            return render_template('landlord_lease_form.html', user=user, tenants=tenants, lease=None)

        if due_day < 1 or due_day > 28:
            flash("Due day should be between 1 and 28.", "warning")
            return render_template('landlord_lease_form.html', user=user, tenants=tenants, lease=None)

        db.execute(
            """
            INSERT INTO leases (tenant_id, landlord_id, monthly_rent, due_day, start_date, end_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tenant_id, user['id'], monthly_rent, due_day, start_date, end_date, is_active)
        )
        db.commit()
        logger.info(
            "Landlord '%s' created lease for tenant_id=%s with rent=%.2f",
            user['username'], tenant_id, monthly_rent
        )
        flash("Lease created.", "success")
        return redirect(url_for('landlord_leases'))

    return render_template('landlord_lease_form.html', user=user, tenants=tenants, lease=None)

@app.route('/landlord/lease/<int:lease_id>/edit', methods=['GET', 'POST'])
@login_required(role='landlord')
def landlord_edit_lease(lease_id):
    user = get_current_user()
    db = get_db()
    lease = db.execute(
        """
        SELECT l.*,
               t.full_name as tenant_name,
               t.username as tenant_username
        FROM leases l
        JOIN users t ON t.id = l.tenant_id
        WHERE l.id = ? AND l.landlord_id = ?
        """,
        (lease_id, user['id'])
    ).fetchone()
    if not lease:
        flash("Lease not found.", "danger")
        logger.warning("Landlord '%s' tried to edit missing lease id=%s", user['username'], lease_id)
        return redirect(url_for('landlord_leases'))

    if request.method == 'POST':
        monthly_rent_raw = request.form.get('monthly_rent', '').strip()
        due_day_raw = request.form.get('due_day', '').strip()
        start_date = request.form.get('start_date', '').strip() or None
        end_date = request.form.get('end_date', '').strip() or None
        is_active = 1 if request.form.get('is_active') == 'on' else 0

        logger.debug(
            "Landlord '%s' updating lease id=%s, rent_raw='%s', due_day_raw='%s'",
            user['username'], lease_id, monthly_rent_raw, due_day_raw
        )

        try:
            monthly_rent = float(monthly_rent_raw)
        except ValueError:
            flash("Please enter a valid monthly rent.", "warning")
            return render_template('landlord_lease_form.html', user=user, lease=lease, tenants=None)

        try:
            due_day = int(due_day_raw)
        except ValueError:
            flash("Please enter a valid due day (1-28).", "warning")
            return render_template('landlord_lease_form.html', user=user, lease=lease, tenants=None)

        if due_day < 1 or due_day > 28:
            flash("Due day should be between 1 and 28.", "warning")
            return render_template('landlord_lease_form.html', user=user, lease=lease, tenants=None)

        db.execute(
            """
            UPDATE leases
               SET monthly_rent = ?,
                   due_day = ?,
                   start_date = ?,
                   end_date = ?,
                   is_active = ?
             WHERE id = ? AND landlord_id = ?
            """,
            (monthly_rent, due_day, start_date, end_date, is_active, lease_id, user['id'])
        )
        db.commit()
        logger.info(
            "Lease id=%s updated by landlord '%s' (new rent=%.2f, due_day=%s, is_active=%s)",
            lease_id, user['username'], monthly_rent, due_day, is_active
        )
        flash("Lease updated.", "success")
        return redirect(url_for('landlord_leases'))

    return render_template('landlord_lease_form.html', user=user, lease=lease, tenants=None)

@app.route('/landlord/request/<int:req_id>/update', methods=['POST'])
@login_required(role='landlord')
def update_request_status(req_id):
    user = get_current_user()
    new_status = request.form.get('status')
    logger.debug("Landlord '%s' updating request id=%s to status='%s'", user['username'], req_id, new_status)
    if new_status not in ('Open', 'In Progress', 'Completed'):
        logger.warning("Invalid status '%s' submitted for request id=%s", new_status, req_id)
        flash("Invalid status.", "danger")
        return redirect(url_for('landlord_dashboard'))

    db = get_db()
    req = db.execute(
        """
        SELECT mr.*
        FROM maintenance_requests mr
        JOIN users u ON u.id = mr.tenant_id
        LEFT JOIN leases l ON l.tenant_id = u.id AND l.is_active = 1
        WHERE mr.id = ? AND l.landlord_id = ?
        """,
        (req_id, user['id'])
    ).fetchone()
    if not req:
        logger.warning(
            "Maintenance request id=%s not found or not owned by landlord '%s'.",
            req_id, user['username']
        )
        flash("Request not found.", "danger")
        return redirect(url_for('landlord_dashboard'))

    db.execute(
        "UPDATE maintenance_requests SET status = ? WHERE id = ?",
        (new_status, req_id)
    )
    db.commit()
    logger.info("Request id=%s status updated to '%s' by landlord '%s'", req_id, new_status, user['username'])
    flash("Request updated.", "success")
    return redirect(url_for('landlord_dashboard'))

# -----------------------
# Main entrypoint
# -----------------------

if __name__ == '__main__':
    with app.app_context():
        logger.info("Ensuring database schema is initialized on startup.")
        init_db()
    app.run(debug=True)
