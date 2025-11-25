import os
import sqlite3
import logging
import datetime
import json

import requests
import stripe
from flask import Flask, g, render_template, request, redirect, url_for, session, flash

# -----------------------
# App & Logging Setup
# -----------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = 'change-me-in-production'  # TODO: override in production
app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), 'tenantlandlord.db')

logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
)
logger = logging.getLogger(__name__)

# -----------------------
# Stripe Configuration
# -----------------------

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

if not STRIPE_SECRET_KEY:
    logger.warning("STRIPE_SECRET_KEY is not set. Stripe functionality will be disabled.")
else:
    stripe.api_key = STRIPE_SECRET_KEY
    logger.info("Stripe API key configured.")

@app.context_processor
def inject_stripe_publishable_key():
    """Expose Stripe publishable key to all templates as {{ stripe_publishable_key }}."""
    return {"stripe_publishable_key": STRIPE_PUBLISHABLE_KEY}

# -----------------------
# Language / i18n config
# -----------------------

SUPPORTED_LANGS = ["en", "es"]
DEFAULT_LANG = "en"

TRANSLATIONS = {
    # Navigation
    "nav_home": {
        "en": "Home",
        "es": "Inicio",
    },
    "nav_login": {
        "en": "Log in",
        "es": "Iniciar sesión",
    },
    "nav_logout": {
        "en": "Log out",
        "es": "Cerrar sesión",
    },

    # Tenant dashboard
    "tenant_dashboard_title": {
        "en": "Tenant dashboard",
        "es": "Panel de inquilino",
    },
    "tenant_rent_for_month": {
        "en": "Rent for",
        "es": "Renta de",
    },
    "tenant_monthly_rent": {
        "en": "Monthly rent",
        "es": "Renta mensual",
    },
    "tenant_this_month_paid": {
        "en": "This month paid",
        "es": "Pagado este mes",
    },
    "tenant_status": {
        "en": "Status",
        "es": "Estado",
    },
    "tenant_record_payment": {
        "en": "Record a rent payment",
        "es": "Registrar un pago de renta",
    },
    "tenant_pay_online_heading": {
        "en": "Pay rent online (card)",
        "es": "Pagar renta en línea (tarjeta)",
    },
    "tenant_pay_online_button": {
        "en": "Pay with card (Stripe)",
        "es": "Pagar con tarjeta (Stripe)",
    },

    # Landlord dashboard
    "landlord_dashboard_title": {
        "en": "Landlord dashboard",
        "es": "Panel de propietario",
    },
    "landlord_open_requests": {
        "en": "Open maintenance requests",
        "es": "Solicitudes de mantenimiento abiertas",
    },
    "landlord_unpaid_rent": {
        "en": "Unpaid/partial rent this month",
        "es": "Renta sin pagar/parcial este mes",
    },
    TRANSLATIONS = {
    # ...existing keys...

    "hello": {"en": "Hello", "es": "Hola"},

    "landlord_manage_tenants": {
        "en": "Manage tenants",
        "es": "Gestionar inquilinos",
    },
    "landlord_manage_leases": {
        "en": "Manage leases",
        "es": "Gestionar contratos",
    },
    "landlord_all_requests": {
        "en": "All maintenance requests",
        "es": "Todas las solicitudes de mantenimiento",
    },
    "landlord_rent_status_for": {
        "en": "Rent status for",
        "es": "Estado de la renta de",
    },
    "landlord_recent_requests": {
        "en": "Recent maintenance requests",
        "es": "Solicitudes de mantenimiento recientes",
    },
    "landlord_no_leases": {
        "en": "No active leases found.",
        "es": "No se encontraron contratos activos.",
    },
    "landlord_no_requests": {
        "en": "No maintenance requests yet.",
        "es": "Aún no hay solicitudes de mantenimiento.",
    },

    # Column/header labels
    "col_tenant": {"en": "Tenant", "es": "Inquilino"},
    "col_monthly_rent": {"en": "Monthly rent", "es": "Renta mensual"},
    "col_due_day": {"en": "Due day", "es": "Día de vencimiento"},
    "col_paid_this_month": {"en": "Paid this month", "es": "Pagado este mes"},
    "col_status": {"en": "Status", "es": "Estado"},
    "col_created": {"en": "Created", "es": "Creado"},
    "col_title": {"en": "Title", "es": "Título"},
    "col_description": {"en": "Description", "es": "Descripción"},
    "col_update": {"en": "Update", "es": "Actualizar"},
    "btn_save": {"en": "Save", "es": "Guardar"},
}

}

def get_lang():
    lang = session.get("lang") or DEFAULT_LANG
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    return lang

def translate_ui(key):
    """Return translated UI string for current language."""
    lang = get_lang()
    value = TRANSLATIONS.get(key, {})
    translated = value.get(lang) or value.get(DEFAULT_LANG) or key
    return translated

# DeepL configuration
DEEPL_API_KEY = os.environ.get("DEEPL_API_KEY")
DEEPL_API_URL = os.environ.get("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate")

def translate_text_deepl(text, target_lang):
    """
    Translate arbitrary text using DeepL.
    target_lang: "en" or "es", etc.
    """
    if not text:
        return text
    if not DEEPL_API_KEY:
        logger.warning("DeepL API key not configured, skipping translation.")
        return None

    # Map to DeepL language codes
    deepl_lang = target_lang.upper()
    if deepl_lang == "EN":
        deepl_lang = "EN"  # or EN-US
    elif deepl_lang == "ES":
        deepl_lang = "ES"

    logger.debug("DeepL translation requested to %s for text=%r", deepl_lang, text[:80])
    try:
        resp = requests.post(
            DEEPL_API_URL,
            data={
                "auth_key": DEEPL_API_KEY,
                "text": text,
                "target_lang": deepl_lang,
            },
            timeout=10,
        )
        logger.debug("DeepL response status=%s", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        translations = data.get("translations")
        if translations:
            translated_text = translations[0].get("text")
            logger.debug(
                "DeepL translation successful: %r -> %r",
                text[:60],
                translated_text[:60] if translated_text else None
            )
            return translated_text
        logger.error("DeepL response missing 'translations': %s", data)
    except Exception:
        logger.exception("DeepL translation failed.")
    return None

@app.context_processor
def inject_i18n():
    """Make translation helper and language info available in all templates."""
    return {
        "t": translate_ui,
        "current_lang": get_lang(),
        "supported_langs": SUPPORTED_LANGS,
    }

@app.route("/set-language/<lang>")
def set_language(lang):
    logger.debug("set_language called with lang=%s", lang)
    if lang not in SUPPORTED_LANGS:
        logger.warning("Unsupported language requested: %s", lang)
        flash("Language not supported.", "warning")
        return redirect(url_for("dashboard") if session.get("user_id") else url_for("index"))

    session["lang"] = lang
    logger.info("Language set to %s for current session.", lang)
    ref = request.referrer
    if ref:
        logger.debug("Redirecting back to referrer: %s", ref)
        return redirect(ref)
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("index"))

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
    logger.info("Initializing database schema if not present.")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('tenant', 'landlord')),
            full_name TEXT,
            email TEXT
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

        CREATE TABLE IF NOT EXISTS maintenance_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES users(id)
        );
        """
    )
    db.commit()
    logger.info("Database schema ensured (tables created if they did not exist).")

# -----------------------
# Utility Helpers
# -----------------------

def get_user(user_id):
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    logger.debug("Fetched user for user_id %s: %s", user_id, dict(user) if user else None)
    return user

def get_user_by_username(username):
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    logger.debug("Fetched user for username %s: %s", username, dict(user) if user else None)
    return user

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
    if user_id is None:
        logger.debug("No current user in session.")
        return None
    user = get_user(user_id)
    if not user:
        logger.warning("User id %s from session not found in DB; clearing session.", user_id)
        session.clear()
        return None
    return user

def login_user(user):
    session.clear()
    session['user_id'] = user['id']
    session['role'] = user['role']
    logger.info("User %s (id=%s, role=%s) logged in.", user['username'], user['id'], user['role'])

def logout_user():
    user = get_current_user()
    if user:
        logger.info("User %s (id=%s) logging out.", user['username'], user['id'])
    session.clear()

def login_required(role=None):
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
    logger.warning("init-db route called; reinitializing DB schema.")
    init_db()
    flash("Database initialized.", "success")
    return redirect(url_for('index'))

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    """Initial setup route to create a landlord and a tenant."""
    db = get_db()
    logger.debug("Setup route accessed with method=%s", request.method)
    existing_users = db.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    if existing_users > 0:
        logger.info("Setup attempted but users already exist; redirecting to index.")
        flash("Setup has already been completed.", "info")
        return redirect(url_for('index'))

    if request.method == 'POST':
        landlord_username = request.form.get('landlord_username', '').strip()
        landlord_password = request.form.get('landlord_password', '').strip()
        landlord_full_name = request.form.get('landlord_full_name', '').strip()
        landlord_email = request.form.get('landlord_email', '').strip()

        tenant_username = request.form.get('tenant_username', '').strip()
        tenant_password = request.form.get('tenant_password', '').strip()
        tenant_full_name = request.form.get('tenant_full_name', '').strip()
        tenant_email = request.form.get('tenant_email', '').strip()

        monthly_rent_raw = request.form.get('monthly_rent', '').strip()
        due_day_raw = request.form.get('due_day', '').strip()

        logger.debug(
            "Setup form submitted with landlord_username=%s, tenant_username=%s, monthly_rent_raw=%s, due_day_raw=%s",
            landlord_username, tenant_username, monthly_rent_raw, due_day_raw
        )

        if not all([landlord_username, landlord_password, tenant_username, tenant_password, monthly_rent_raw, due_day_raw]):
            flash("Please fill in all required fields.", "warning")
            return render_template('setup.html')

        try:
            monthly_rent = float(monthly_rent_raw)
            due_day = int(due_day_raw)
        except ValueError:
            logger.warning("Invalid monthly_rent or due_day entered during setup.")
            flash("Monthly rent must be a number and due day must be an integer.", "warning")
            return render_template('setup.html')

        try:
            db.execute(
                "INSERT INTO users (username, password, role, full_name, email) VALUES (?, ?, 'landlord', ?, ?)",
                (landlord_username, landlord_password, landlord_full_name, landlord_email)
            )
            landlord_id = db.execute("SELECT last_insert_rowid() as id").fetchone()['id']

            db.execute(
                "INSERT INTO users (username, password, role, full_name, email) VALUES (?, ?, 'tenant', ?, ?)",
                (tenant_username, tenant_password, tenant_full_name, tenant_email)
            )
            tenant_id = db.execute("SELECT last_insert_rowid() as id").fetchone()['id']

            db.execute(
                """
                INSERT INTO leases (tenant_id, landlord_id, monthly_rent, due_day, start_date, is_active)
                VALUES (?, ?, ?, ?, DATE('now'), 1)
                """,
                (tenant_id, landlord_id, monthly_rent, due_day)
            )
            db.commit()
            logger.info("Setup completed with landlord id=%s and tenant id=%s", landlord_id, tenant_id)
            flash("Setup completed. You can now log in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            logger.exception("IntegrityError during setup.")
            flash("Error during setup: usernames might already exist.", "danger")
            return render_template('setup.html')

    return render_template('setup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    logger.debug("Login route accessed with method=%s", request.method)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        logger.debug("Login attempt for username=%s", username)
        user = get_user_by_username(username)
        if user and user['password'] == password:
            login_user(user)
            next_page = request.args.get('next')
            logger.info(
                "Login successful for username=%s; redirecting to %s",
                username,
                next_page or 'dashboard'
            )
            return redirect(next_page or url_for('dashboard'))
        else:
            logger.warning("Login failed for username=%s", username)
            flash("Invalid username or password.", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    logger.debug("Logout route called.")
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required()
def dashboard():
    user = get_current_user()
    logger.debug("Dashboard requested by user id=%s role=%s", user['id'], user['role'])
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
    requests_rows = db.execute(
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
        requests=requests_rows,
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
                "INSERT INTO maintenance_requests (tenant_id, title, description, status) "
                "VALUES (?, ?, ?, ?)",
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

@app.route('/tenant/rent/stripe-checkout', methods=['POST'])
@login_required(role='tenant')
def tenant_stripe_checkout():
    """
    Start a Stripe Checkout session for the tenant's current month's rent.
    The amount charged is the remaining balance for the current month.
    """
    user = get_current_user()
    db = get_db()
    logger.debug("Tenant id=%s requested Stripe rent checkout", user['id'])

    if not STRIPE_SECRET_KEY or not STRIPE_PUBLISHABLE_KEY:
        logger.error(
            "Stripe keys not configured when tenant id=%s attempted Stripe payment",
            user['id']
        )
        flash("Online payments are not configured. Please contact your landlord.", "danger")
        return redirect(url_for('tenant_dashboard'))

    lease = get_active_lease_for_tenant(user['id'])
    if not lease:
        logger.warning("Tenant id=%s attempted Stripe payment but has no active lease", user['id'])
        flash("No active lease found. Please contact your landlord.", "danger")
        return redirect(url_for('tenant_dashboard'))

    month, year, month_label = get_current_month_year()
    rent_paid, rent_status = get_rent_status_for_lease(
        lease['id'], lease['monthly_rent'], month, year
    )
    amount_due = (lease['monthly_rent'] or 0) - (rent_paid or 0)
    logger.debug(
        "Stripe checkout calculation for tenant id=%s lease_id=%s month=%s year=%s: "
        "monthly_rent=%.2f rent_paid=%.2f amount_due=%.2f status=%s",
        user['id'], lease['id'], month, year,
        lease['monthly_rent'] or 0, rent_paid or 0, amount_due, rent_status
    )

    if amount_due <= 0:
        flash("No outstanding rent balance for this month.", "info")
        return redirect(url_for('tenant_dashboard'))

    try:
        amount_cents = int(round(amount_due * 100))
        logger.debug(
            "Creating Stripe Checkout Session for tenant id=%s lease_id=%s amount_due=%.2f "
            "(amount_cents=%s)",
            user['id'], lease['id'], amount_due, amount_cents
        )

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"Rent for {month_label} (Lease #{lease['id']})"
                        },
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "tenant_id": str(user['id']),
                "lease_id": str(lease['id']),
                "month": str(month),
                "year": str(year),
            },
            success_url=url_for("tenant_stripe_success", _external=True),
            cancel_url=url_for("tenant_stripe_cancel", _external=True),
        )

        logger.info(
            "Created Stripe Checkout Session id=%s for tenant id=%s lease_id=%s amount_cents=%s",
            checkout_session.id, user['id'], lease['id'], amount_cents
        )
        # Redirect directly to the hosted checkout page
        return redirect(checkout_session.url, code=303)

    except Exception:
        logger.exception("Failed to create Stripe Checkout Session for tenant id=%s", user['id'])
        flash("Could not start payment. Please try again later.", "danger")
        return redirect(url_for('tenant_dashboard'))

@app.route('/tenant/rent/stripe-success')
@login_required(role='tenant')
def tenant_stripe_success():
    """
    Landing page when Stripe Checkout reports success in the browser.
    The authoritative record is still the Stripe webhook; this route is only UX.
    """
    user = get_current_user()
    logger.info("Tenant id=%s returned from Stripe success URL", user['id'])
    flash("Payment completed. Your rent status will update shortly.", "success")
    return redirect(url_for('tenant_dashboard'))

@app.route('/tenant/rent/stripe-cancel')
@login_required(role='tenant')
def tenant_stripe_cancel():
    """
    Landing page when the tenant cancels the Stripe Checkout flow.
    """
    user = get_current_user()
    logger.info("Tenant id=%s returned from Stripe cancel URL", user['id'])
    flash("Payment was cancelled. No charges were made.", "warning")
    return redirect(url_for('tenant_dashboard'))

@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    """
    Stripe webhook endpoint to record successful card payments into rent_payments.
    Configure this in your Stripe dashboard with STRIPE_WEBHOOK_SECRET.
    """
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    logger.debug("Stripe webhook received. Signature header=%s", sig_header)

    if not STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured; cannot verify Stripe webhook.")
        return "Webhook secret not configured", 500

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
        logger.debug("Stripe webhook event constructed successfully: type=%s", event["type"])
    except ValueError:
        logger.exception("Invalid payload in Stripe webhook.")
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        logger.exception("Invalid signature in Stripe webhook.")
        return "Invalid signature", 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        logger.debug("Processing checkout.session.completed: %s", json.dumps(session_obj, indent=2))

        metadata = session_obj.get("metadata") or {}
        tenant_id = metadata.get("tenant_id")
        lease_id = metadata.get("lease_id")
        month = metadata.get("month")
        year = metadata.get("year")
        amount_total = session_obj.get("amount_total")  # in cents

        logger.info(
            "checkout.session.completed for tenant_id=%s lease_id=%s month=%s year=%s amount_total=%s",
            tenant_id, lease_id, month, year, amount_total
        )

        try:
            if not (tenant_id and lease_id and month and year and amount_total is not None):
                logger.error(
                    "Missing required metadata in Stripe webhook for rent payment: %s",
                    metadata
                )
            else:
                db = get_db()
                amount = float(amount_total) / 100.0
                month_int = int(month)
                year_int = int(year)

                db.execute(
                    """
                    INSERT INTO rent_payments (lease_id, amount, month, year, status, method, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(lease_id),
                        amount,
                        month_int,
                        year_int,
                        "Paid",
                        "Stripe",
                        f"Stripe Checkout session {session_obj.get('id')}",
                    )
                )
                db.commit()
                logger.info(
                    "Rent payment recorded from Stripe webhook: lease_id=%s amount=%.2f "
                    "month=%s year=%s",
                    lease_id, amount, month_int, year_int
                )
        except Exception:
            logger.exception("Failed to record rent payment from Stripe webhook.")
    else:
        logger.debug("Unhandled Stripe event type: %s", event["type"])

    return "OK", 200

# -----------------------
# Landlord Views
# -----------------------

def _apply_deepl_to_requests(rows):
    """If current language is Spanish, add translated_description to each maintenance row."""
    lang = get_lang()
    if lang != "es":
        return rows

    processed = []
    for r in rows:
        r_dict = dict(r)
        desc = r_dict.get("description")
        if desc:
            translated = translate_text_deepl(desc, target_lang="es")
            if translated:
                r_dict["translated_description"] = translated
        processed.append(r_dict)
    logger.debug(
        "Applied DeepL translation to %d maintenance requests (lang=%s).",
        len(processed),
        lang
    )
    return processed

@app.route('/landlord')
@login_required(role='landlord')
def landlord_dashboard():
    user = get_current_user()
    db = get_db()
    logger.debug("Loading landlord dashboard for landlord id=%s", user['id'])

    # Maintenance overview scoped to this landlord's tenants
    requests_rows = db.execute(
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
    requests_for_view = _apply_deepl_to_requests(requests_rows)

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
    logger.debug(
        "Calculating rent overview for landlord id=%s month=%s year=%s",
        user['id'], month, year
    )

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
          ON rp.lease_id = l.id AND rp.month = ? AND rp.year = ?
        WHERE l.landlord_id = ? AND l.is_active = 1
        GROUP BY l.id, t.full_name, t.username, l.monthly_rent, l.due_day
        ORDER BY t.full_name, t.username
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
        "Rent overview for landlord id=%s: %d leases, %d unpaid/partial",
        user['id'], len(rent_overview), unpaid_count
    )

    return render_template(
        'landlord_dashboard.html',
        user=user,
        requests=requests_for_view,
        open_count=open_count,
        rent_month_label=month_label,
        rent_overview=rent_overview,
        unpaid_count=unpaid_count
    )

@app.route('/landlord/leases')
@login_required(role='landlord')
def landlord_leases():
    user = get_current_user()
    db = get_db()
    logger.debug("Landlord leases view for landlord id=%s", user['id'])

    leases = db.execute(
        """
        SELECT l.*, t.full_name as tenant_name, t.username as tenant_username
        FROM leases l
        JOIN users t ON t.id = l.tenant_id
        WHERE l.landlord_id = ?
        ORDER BY l.is_active DESC, t.full_name, t.username
        """,
        (user['id'],)
    ).fetchall()

    return render_template('landlord_leases.html', user=user, leases=leases)

@app.route('/landlord/leases/new', methods=['GET', 'POST'])
@login_required(role='landlord')
def landlord_new_lease():
    user = get_current_user()
    db = get_db()
    logger.debug("New lease route accessed by landlord id=%s method=%s", user['id'], request.method)

    tenants = db.execute(
        "SELECT * FROM users WHERE role = 'tenant' ORDER BY full_name, username"
    ).fetchall()

    if request.method == 'POST':
        tenant_id_raw = request.form.get('tenant_id')
        monthly_rent_raw = request.form.get('monthly_rent')
        due_day_raw = request.form.get('due_day')
        start_date = request.form.get('start_date') or None
        end_date = request.form.get('end_date') or None

        logger.debug(
            "New lease submission: tenant_id_raw=%s, monthly_rent_raw=%s, due_day_raw=%s, "
            "start_date=%s, end_date=%s",
            tenant_id_raw, monthly_rent_raw, due_day_raw, start_date, end_date
        )

        try:
            tenant_id = int(tenant_id_raw)
            monthly_rent = float(monthly_rent_raw)
            due_day = int(due_day_raw)
        except (TypeError, ValueError):
            logger.warning("Invalid lease form input.")
            flash("Please provide valid values for tenant, monthly rent, and due day.", "warning")
            return render_template('landlord_lease_form.html', user=user, tenants=tenants)

        db.execute(
            """
            INSERT INTO leases (tenant_id, landlord_id, monthly_rent, due_day, start_date, end_date, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (tenant_id, user['id'], monthly_rent, due_day, start_date, end_date)
        )
        db.commit()
        logger.info("New lease created by landlord id=%s for tenant_id=%s", user['id'], tenant_id)
        flash("Lease created.", "success")
        return redirect(url_for('landlord_leases'))

    return render_template('landlord_lease_form.html', user=user, tenants=tenants)

@app.route('/landlord/leases/<int:lease_id>/toggle', methods=['POST'])
@login_required(role='landlord')
def landlord_toggle_lease(lease_id):
    user = get_current_user()
    db = get_db()
    logger.debug("Toggle lease id=%s requested by landlord id=%s", lease_id, user['id'])

    lease = db.execute(
        "SELECT * FROM leases WHERE id = ? AND landlord_id = ?",
        (lease_id, user['id'])
    ).fetchone()
    if not lease:
        logger.warning("Lease id=%s not found or not owned by landlord id=%s", lease_id, user['id'])
        flash("Lease not found.", "danger")
        return redirect(url_for('landlord_leases'))

    new_status = 0 if lease['is_active'] else 1
    db.execute(
        "UPDATE leases SET is_active = ? WHERE id = ?",
        (new_status, lease_id)
    )
    db.commit()
    logger.info(
        "Lease id=%s toggled by landlord id=%s to is_active=%s",
        lease_id, user['id'], new_status
    )
    flash("Lease status updated.", "success")
    return redirect(url_for('landlord_leases'))

@app.route('/landlord/tenants')
@login_required(role='landlord')
def landlord_tenants():
    user = get_current_user()
    db = get_db()
    logger.debug("Landlord tenants view for landlord id=%s", user['id'])

    tenants = db.execute(
        "SELECT * FROM users WHERE role = 'tenant' ORDER BY full_name, username"
    ).fetchall()
    return render_template('landlord_tenants.html', user=user, tenants=tenants)

@app.route('/landlord/tenants/new', methods=['GET', 'POST'])
@login_required(role='landlord')
def landlord_new_tenant():
    user = get_current_user()
    db = get_db()
    logger.debug("New tenant route accessed by landlord id=%s method=%s", user['id'], request.method)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()

        logger.debug(
            "New tenant submission: username=%s, full_name=%s, email=%s",
            username, full_name, email
        )

        if not username or not password:
            flash("Username and password are required.", "warning")
            return render_template('landlord_tenant_form.html', user=user)

        try:
            db.execute(
                "INSERT INTO users (username, password, role, full_name, email) "
                "VALUES (?, ?, 'tenant', ?, ?)",
                (username, password, full_name, email)
            )
            db.commit()
            logger.info("New tenant %s created by landlord id=%s", username, user['id'])
            flash("Tenant created.", "success")
            return redirect(url_for('landlord_tenants'))
        except sqlite3.IntegrityError:
            logger.exception("IntegrityError creating new tenant username=%s", username)
            flash("A tenant with that username already exists.", "danger")

    return render_template('landlord_tenant_form.html', user=user)

@app.route('/landlord/requests')
@login_required(role='landlord')
def landlord_requests():
    user = get_current_user()
    db = get_db()
    logger.debug("Landlord requests view for landlord id=%s", user['id'])

    requests_rows = db.execute(
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

    requests_for_view = _apply_deepl_to_requests(requests_rows)

    return render_template('landlord_requests.html', user=user, requests=requests_for_view)

@app.route('/landlord/requests/<int:request_id>/status', methods=['POST'])
@login_required(role='landlord')
def landlord_update_request_status(request_id):
    user = get_current_user()
    db = get_db()
    new_status = request.form.get('status', '').strip()
    logger.debug(
        "Landlord id=%s updating maintenance request id=%s to status=%s",
        user['id'], request_id, new_status
    )

    if new_status not in ['Open', 'In progress', 'Completed']:
        logger.warning("Invalid status %s provided for request id=%s", new_status, request_id)
        flash("Invalid status.", "warning")
        return redirect(url_for('landlord_requests'))

    db.execute(
        "UPDATE maintenance_requests SET status = ? WHERE id = ?",
        (new_status, request_id)
    )
    db.commit()
    logger.info(
        "Maintenance request id=%s updated to status=%s by landlord id=%s",
        request_id, new_status, user['id']
    )
    flash("Request status updated.", "success")
    return redirect(url_for('landlord_requests'))

# -----------------------
# App Entry
# -----------------------

if __name__ == '__main__':
    logger.debug("Starting app in debug mode on localhost.")
    app.run(debug=True)
