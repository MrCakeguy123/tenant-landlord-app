import os
import uuid
import logging
import datetime
import json

import requests
import stripe
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from supabase_client import get_supabase, get_supabase_url, STORAGE_BUCKET


# -----------------------
# App & Logging Setup
# -----------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
)
logger = logging.getLogger(__name__)


# -----------------------
# Stripe Configuration
# -----------------------

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

if not STRIPE_SECRET_KEY:
    logger.warning(
        "STRIPE_SECRET_KEY is not set. Stripe functionality will be disabled."
    )
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
    # ----------------------
    # Navigation
    # ----------------------
    "nav_home": {"en": "Home", "es": "Inicio"},
    "nav_login": {"en": "Log in", "es": "Iniciar sesión"},
    "nav_logout": {"en": "Log out", "es": "Cerrar sesión"},
    "nav_dashboard": {"en": "Dashboard", "es": "Panel"},
    # ----------------------
    # Generic
    # ----------------------
    "hello": {"en": "Hello", "es": "Hola"},
    # ----------------------
    # Tenant dashboard
    # ----------------------
    "tenant_dashboard_title": {
        "en": "Tenant dashboard",
        "es": "Panel de inquilino",
    },
    "tenant_rent_for_month": {"en": "Rent for", "es": "Renta de"},
    "tenant_monthly_rent": {"en": "Monthly rent", "es": "Renta mensual"},
    "tenant_this_month_paid": {"en": "This month paid", "es": "Pagado este mes"},
    "tenant_status": {"en": "Status", "es": "Estado"},
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
    # ----------------------
    # Landlord dashboard
    # ----------------------
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
    # ----------------------
    # Table / column labels
    # ----------------------
    "col_tenant": {"en": "Tenant", "es": "Inquilino"},
    "col_monthly_rent": {"en": "Monthly rent", "es": "Renta mensual"},
    "col_due_day": {"en": "Due day", "es": "Día de vencimiento"},
    "col_paid_this_month": {"en": "Paid this month", "es": "Pagado este mes"},
    "col_status": {"en": "Status", "es": "Estado"},
    "col_created": {"en": "Created", "es": "Creado"},
    "col_title": {"en": "Title", "es": "Título"},
    "col_description": {"en": "Description", "es": "Descripción"},
    "col_update": {"en": "Update", "es": "Actualizar"},
    "col_priority": {"en": "Priority", "es": "Prioridad"},
    # ----------------------
    # Priority labels
    # ----------------------
    "priority_low": {"en": "Low", "es": "Baja"},
    "priority_normal": {"en": "Normal", "es": "Normal"},
    "priority_high": {"en": "High", "es": "Alta"},
    "priority_emergency": {"en": "Emergency", "es": "Emergencia"},
    "label_overdue": {"en": "Overdue", "es": "Atrasado"},
    # ----------------------
    # Buttons
    # ----------------------
    "btn_save": {"en": "Save", "es": "Guardar"},
    "btn_submit_request": {"en": "Submit request", "es": "Enviar solicitud"},
    # ----------------------
    # Settings
    # ----------------------
    "nav_settings": {"en": "Settings", "es": "Configuración"},
    "settings_title": {"en": "Settings", "es": "Configuración"},
    "settings_subtitle": {"en": "Manage your account", "es": "Administra tu cuenta"},
    "settings_profile": {"en": "Profile Information", "es": "Información del perfil"},
    "settings_password": {"en": "Change Password", "es": "Cambiar contraseña"},
    "settings_username": {"en": "Username", "es": "Nombre de usuario"},
    "settings_username_hint": {"en": "Username cannot be changed", "es": "El nombre de usuario no se puede cambiar"},
    "settings_full_name": {"en": "Full Name", "es": "Nombre completo"},
    "settings_email": {"en": "Email", "es": "Correo electrónico"},
    "settings_role": {"en": "Role", "es": "Rol"},
    "settings_update_profile": {"en": "Update Profile", "es": "Actualizar perfil"},
    "settings_current_password": {"en": "Current Password", "es": "Contraseña actual"},
    "settings_new_password": {"en": "New Password", "es": "Nueva contraseña"},
    "settings_confirm_password": {"en": "Confirm New Password", "es": "Confirmar nueva contraseña"},
    "settings_change_password": {"en": "Change Password", "es": "Cambiar contraseña"},
    "back_to_dashboard": {"en": "← Back to Dashboard", "es": "← Volver al panel"},
    # ----------------------
    # Calendar
    # ----------------------
    "calendar_title": {"en": "Calendar", "es": "Calendario"},
    "calendar_subtitle": {"en": "View rent due dates, lease dates, and maintenance requests", "es": "Ver fechas de vencimiento de renta, fechas de contrato y solicitudes de mantenimiento"},
    "calendar_rent_due": {"en": "Rent Due", "es": "Renta vence"},
    "calendar_lease_start": {"en": "Lease Start", "es": "Inicio de contrato"},
    "calendar_lease_end": {"en": "Lease End", "es": "Fin de contrato"},
    "calendar_maintenance_open": {"en": "Maintenance (Open)", "es": "Mantenimiento (Abierto)"},
    "calendar_maintenance_closed": {"en": "Maintenance (Closed)", "es": "Mantenimiento (Cerrado)"},
    "calendar_announcement": {"en": "Announcement", "es": "Anuncio"},
    # ----------------------
    # Announcements
    # ----------------------
    "announcements_title": {"en": "Announcements", "es": "Anuncios"},
    "announcements_subtitle": {"en": "Post notices for your tenants", "es": "Publica avisos para tus inquilinos"},
    "announcements_new": {"en": "+ New Announcement", "es": "+ Nuevo anuncio"},
    "announcements_new_title": {"en": "New Announcement", "es": "Nuevo anuncio"},
    "announcements_new_subtitle": {"en": "Post a notice to all your tenants", "es": "Publica un aviso para todos tus inquilinos"},
    "announcements_posted": {"en": "Posted", "es": "Publicado"},
    "announcements_expires": {"en": "Expires", "es": "Expira"},
    "announcements_never": {"en": "Never", "es": "Nunca"},
    "announcements_active": {"en": "Active", "es": "Activo"},
    "announcements_inactive": {"en": "Inactive", "es": "Inactivo"},
    "announcements_activate": {"en": "Activate", "es": "Activar"},
    "announcements_deactivate": {"en": "Deactivate", "es": "Desactivar"},
    "announcements_delete": {"en": "Delete", "es": "Eliminar"},
    "announcements_delete_confirm": {"en": "Delete this announcement?", "es": "¿Eliminar este anuncio?"},
    "announcements_none": {"en": "No announcements yet. Create one to notify your tenants!", "es": "No hay anuncios todavía. ¡Crea uno para notificar a tus inquilinos!"},
    "announcements_content": {"en": "Content", "es": "Contenido"},
    "announcements_expires_optional": {"en": "Expires (optional)", "es": "Expira (opcional)"},
    "announcements_expires_hint": {"en": "Leave empty for no expiration", "es": "Deja vacío para que no expire"},
    "announcements_post": {"en": "Post Announcement", "es": "Publicar anuncio"},
    "cancel": {"en": "Cancel", "es": "Cancelar"},
    "actions": {"en": "Actions", "es": "Acciones"},
    # ----------------------
    # Login / Setup / Index
    # ----------------------
    "login_title": {"en": "Log in", "es": "Iniciar sesión"},
    "password": {"en": "Password", "es": "Contraseña"},
    "username": {"en": "Username", "es": "Nombre de usuario"},
    "welcome_title": {"en": "Welcome", "es": "Bienvenido"},
    "welcome_subtitle": {"en": "This is a simple tenant/landlord app.", "es": "Esta es una aplicación simple para inquilinos y propietarios."},
    "welcome_setup_hint": {"en": "If you haven't set things up yet, go to", "es": "Si aún no has configurado, ve a"},
    "setup_title": {"en": "Initial setup", "es": "Configuración inicial"},
    "setup_subtitle": {"en": "Create a landlord, a tenant, and the first lease.", "es": "Crea un propietario, un inquilino y el primer contrato."},
    "setup_landlord": {"en": "Landlord", "es": "Propietario"},
    "setup_tenant": {"en": "Tenant", "es": "Inquilino"},
    "setup_lease": {"en": "Lease", "es": "Contrato"},
    "setup_full_name": {"en": "Full name", "es": "Nombre completo"},
    "setup_monthly_rent": {"en": "Monthly rent", "es": "Renta mensual"},
    "setup_due_day": {"en": "Due day of month", "es": "Día de vencimiento del mes"},
    "setup_complete": {"en": "Complete setup", "es": "Completar configuración"},
    "setup": {"en": "setup", "es": "configuración"},
    # ----------------------
    # Maintenance Requests
    # ----------------------
    "maintenance_requests": {"en": "Maintenance requests", "es": "Solicitudes de mantenimiento"},
    "maintenance_new": {"en": "New maintenance request", "es": "Nueva solicitud de mantenimiento"},
    "maintenance_submit_new": {"en": "Submit a new request", "es": "Enviar una nueva solicitud"},
    "maintenance_none": {"en": "You have no maintenance requests yet.", "es": "Aún no tienes solicitudes de mantenimiento."},
    "maintenance_image": {"en": "Image", "es": "Imagen"},
    "maintenance_image_optional": {"en": "Image (optional)", "es": "Imagen (opcional)"},
    "maintenance_no_image": {"en": "No image", "es": "Sin imagen"},
    "maintenance_view": {"en": "View", "es": "Ver"},
    # ----------------------
    # Rent / Payments
    # ----------------------
    "rent_due_on_day": {"en": "due on day", "es": "vence el día"},
    "rent_each_month": {"en": "each month", "es": "de cada mes"},
    "rent_record_payment": {"en": "Record payment", "es": "Registrar pago"},
    "rent_amount": {"en": "Amount", "es": "Monto"},
    "rent_method": {"en": "Method", "es": "Método"},
    "rent_note_optional": {"en": "Note (optional)", "es": "Nota (opcional)"},
    "rent_cash": {"en": "Cash", "es": "Efectivo"},
    "rent_check": {"en": "Check", "es": "Cheque"},
    "rent_bank_transfer": {"en": "Bank transfer", "es": "Transferencia bancaria"},
    "rent_other": {"en": "Other", "es": "Otro"},
    "rent_stripe_redirect": {"en": "You will be redirected to a secure payment page to pay the remaining balance for this month.", "es": "Serás redirigido a una página de pago segura para pagar el saldo restante de este mes."},
    "rent_recent_payments": {"en": "Recent rent payments", "es": "Pagos de renta recientes"},
    "rent_no_payments": {"en": "No rent payments recorded yet.", "es": "No hay pagos de renta registrados todavía."},
    "rent_no_lease": {"en": "You do not have an active lease. Please contact your landlord.", "es": "No tienes un contrato activo. Por favor contacta a tu propietario."},
    "rent_paid_at": {"en": "Paid at", "es": "Pagado el"},
    "rent_month": {"en": "Month", "es": "Mes"},
    "rent_year": {"en": "Year", "es": "Año"},
    "rent_note": {"en": "Note", "es": "Nota"},
    # ----------------------
    # Status labels
    # ----------------------
    "status_paid": {"en": "Paid", "es": "Pagado"},
    "status_partial": {"en": "Partial", "es": "Parcial"},
    "status_unpaid": {"en": "Unpaid", "es": "Sin pagar"},
    "status_open": {"en": "Open", "es": "Abierto"},
    "status_in_progress": {"en": "In progress", "es": "En progreso"},
    "status_completed": {"en": "Completed", "es": "Completado"},
    # ----------------------
    # Roles
    # ----------------------
    "role_tenant": {"en": "Tenant", "es": "Inquilino"},
    "role_landlord": {"en": "Landlord", "es": "Propietario"},
    # ----------------------
    # Landlord pages
    # ----------------------
    "leases_title": {"en": "Leases", "es": "Contratos"},
    "leases_new": {"en": "New lease", "es": "Nuevo contrato"},
    "leases_start_date": {"en": "Start date", "es": "Fecha de inicio"},
    "leases_end_date": {"en": "End date", "es": "Fecha de fin"},
    "leases_active": {"en": "Active", "es": "Activo"},
    "leases_toggle": {"en": "Toggle", "es": "Cambiar"},
    "leases_none": {"en": "No leases yet.", "es": "No hay contratos todavía."},
    "yes": {"en": "Yes", "es": "Sí"},
    "no": {"en": "No", "es": "No"},
    "tenants_title": {"en": "Tenants", "es": "Inquilinos"},
    "tenants_new": {"en": "New tenant", "es": "Nuevo inquilino"},
    "tenants_none": {"en": "No tenants yet.", "es": "No hay inquilinos todavía."},
    "tenants_back": {"en": "Back to tenants", "es": "Volver a inquilinos"},
    "tenants_create": {"en": "Create tenant", "es": "Crear inquilino"},
    "leases_back": {"en": "Back to leases", "es": "Volver a contratos"},
    "leases_select_tenant": {"en": "Select tenant...", "es": "Seleccionar inquilino..."},
    "leases_start_optional": {"en": "Start date (optional)", "es": "Fecha de inicio (opcional)"},
    "leases_end_optional": {"en": "End date (optional)", "es": "Fecha de fin (opcional)"},
    "leases_save": {"en": "Save lease", "es": "Guardar contrato"},
    "last_updated": {"en": "Last updated", "es": "Última actualización"},
    "maintenance_delete": {"en": "Delete", "es": "Eliminar"},
    "maintenance_delete_confirm": {"en": "Delete this maintenance request?", "es": "¿Eliminar esta solicitud de mantenimiento?"},
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
DEEPL_API_URL = os.environ.get(
    "DEEPL_API_URL", "https://api-free.deepl.com/v2/translate"
)


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

    deepl_lang = target_lang.upper()
    if deepl_lang == "EN":
        deepl_lang = "EN"
    elif deepl_lang == "ES":
        deepl_lang = "ES"

    logger.debug(
        "DeepL translation requested to %s for text=%r", deepl_lang, text[:80]
    )
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
                translated_text[:60] if translated_text else None,
            )
            return translated_text
        logger.error("DeepL response missing 'translations': %s", data)
    except Exception:
        logger.exception("DeepL translation failed.")
    return None


@app.context_processor
def inject_i18n():
    """Make translation helper and language info available in all templates."""
    return {"t": translate_ui, "current_lang": get_lang(), "supported_langs": SUPPORTED_LANGS}


@app.route("/set-language/<lang>")
def set_language(lang):
    logger.debug("set_language called with lang=%s", lang)
    if lang not in SUPPORTED_LANGS:
        logger.warning("Unsupported language requested: %s", lang)
        flash("Language not supported.", "warning")
        return redirect(
            url_for("dashboard") if session.get("user_id") else url_for("index")
        )

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
# Supabase Database Helpers
# -----------------------

def require_supabase():
    """Get Supabase client or raise an error."""
    supabase = get_supabase()
    if supabase is None:
        raise RuntimeError("Supabase is not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
    return supabase


def upload_image_to_storage(file, filename):
    """
    Upload an image file to Supabase Storage.
    Returns the public URL of the uploaded image, or None on failure.
    """
    try:
        supabase = require_supabase()
        supabase_url = get_supabase_url()
        
        # Read file content
        file_content = file.read()
        
        # Determine content type
        ext = filename.rsplit(".", 1)[-1].lower()
        content_types = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
        }
        content_type = content_types.get(ext, "application/octet-stream")
        
        # Upload to Supabase Storage
        response = supabase.storage.from_(STORAGE_BUCKET).upload(
            path=filename,
            file=file_content,
            file_options={"content-type": content_type}
        )
        
        # Construct public URL
        public_url = f"{supabase_url}/storage/v1/object/public/{STORAGE_BUCKET}/{filename}"
        logger.info("Uploaded image to Supabase Storage: %s", public_url)
        return public_url
        
    except Exception as e:
        logger.exception("Failed to upload image to Supabase Storage: %s", e)
        return None


# -----------------------
# Utility Helpers
# -----------------------

def get_user(user_id):
    """Fetch a single user by id from Supabase."""
    try:
        supabase = require_supabase()
        logger.debug("Fetching user by id=%s", user_id)
        resp = (
            supabase.table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        user = rows[0] if rows else None
        logger.debug("Fetched user id=%s -> %s", user_id, user)
        return user
    except Exception as e:
        logger.exception("Error fetching user id=%s: %s", user_id, e)
        return None


def get_user_by_username(username):
    """Fetch a single user by username from Supabase."""
    try:
        supabase = require_supabase()
        logger.debug("Fetching user with username=%s", username)
        resp = (
            supabase.table("users")
            .select("*")
            .eq("username", username)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        user = rows[0] if rows else None
        logger.debug("Fetched user username=%s -> %s", username, user)
        return user
    except Exception as e:
        logger.exception("Error fetching user by username=%s: %s", username, e)
        return None


def get_current_month_year():
    today = datetime.date.today()
    month_label = today.strftime("%B %Y")
    return today.month, today.year, month_label


def get_active_lease_for_tenant(tenant_id):
    """Get the active lease for a tenant, including landlord/tenant names."""
    try:
        supabase = require_supabase()
        # First get the lease
        resp = (
            supabase.table("leases")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("is_active", True)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            logger.debug("No active lease found for tenant_id=%s", tenant_id)
            return None
        
        lease = rows[0]
        
        # Get tenant name
        tenant_resp = supabase.table("users").select("full_name").eq("id", tenant_id).limit(1).execute()
        if tenant_resp.data:
            lease["tenant_name"] = tenant_resp.data[0].get("full_name")
        
        # Get landlord name
        landlord_resp = supabase.table("users").select("full_name").eq("id", lease["landlord_id"]).limit(1).execute()
        if landlord_resp.data:
            lease["landlord_name"] = landlord_resp.data[0].get("full_name")
        
        logger.debug("Active lease for tenant_id %s: %s", tenant_id, lease)
        return lease
    except Exception as e:
        logger.exception("Error fetching active lease for tenant_id=%s: %s", tenant_id, e)
        return None


def allowed_image_file(filename):
    """Return True if the provided filename has an allowed image extension."""
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext in ALLOWED_IMAGE_EXTENSIONS


def get_rent_status_for_lease(lease_id, monthly_rent, month, year):
    """Calculate rent payment status for a specific lease and month."""
    try:
        supabase = require_supabase()
        resp = (
            supabase.table("rent_payments")
            .select("amount, status")
            .eq("lease_id", lease_id)
            .eq("month", month)
            .eq("year", year)
            .execute()
        )
        rows = resp.data or []
        paid = sum(row["amount"] for row in rows if row.get("status") == "Paid")
        
        if paid >= monthly_rent:
            status = "Paid"
        elif paid > 0:
            status = "Partial"
        else:
            status = "Unpaid"
        
        logger.debug(
            "Rent status for lease_id=%s month=%s year=%s: paid=%.2f status=%s (monthly_rent=%.2f)",
            lease_id, month, year, paid, status, monthly_rent,
        )
        return paid, status
    except Exception as e:
        logger.exception("Error getting rent status for lease_id=%s: %s", lease_id, e)
        return 0, "Unknown"


def get_recent_rent_payments_for_tenant(tenant_id, limit=5):
    """Get recent rent payments for a tenant."""
    try:
        supabase = require_supabase()
        # First get tenant's leases
        leases_resp = supabase.table("leases").select("id, monthly_rent").eq("tenant_id", tenant_id).execute()
        leases = leases_resp.data or []
        
        if not leases:
            return []
        
        lease_ids = [l["id"] for l in leases]
        lease_rent_map = {l["id"]: l["monthly_rent"] for l in leases}
        
        # Get payments for those leases
        payments_resp = (
            supabase.table("rent_payments")
            .select("*")
            .in_("lease_id", lease_ids)
            .order("paid_at", desc=True)
            .limit(limit)
            .execute()
        )
        payments = payments_resp.data or []
        
        # Add monthly_rent to each payment
        for p in payments:
            p["monthly_rent"] = lease_rent_map.get(p["lease_id"], 0)
        
        logger.debug("Loaded %d recent rent payments for tenant_id=%s", len(payments), tenant_id)
        return payments
    except Exception as e:
        logger.exception("Error fetching recent payments for tenant_id=%s: %s", tenant_id, e)
        return []


# -----------------------
# Auth Helpers
# -----------------------

def get_current_user():
    user_id = session.get("user_id")
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
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    logger.info(
        "User %s (id=%s, role=%s) logged in.",
        user["username"],
        user["id"],
        user["role"],
    )


def logout_user():
    user = get_current_user()
    if user:
        logger.info("User %s (id=%s) logging out.", user["username"], user["id"])
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
                return redirect(url_for("login", next=request.path))
            if role is not None and user["role"] != role:
                flash("You do not have access to that page.", "danger")
                logger.warning(
                    "User %s with role %s tried to access %s-only page %s",
                    user["username"],
                    user["role"],
                    role,
                    request.path,
                )
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


# -----------------------
# Routes: Core / Auth
# -----------------------

@app.route("/")
def index():
    logger.debug("Index page requested.")
    user = get_current_user()
    if user:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """Initial setup route to create a landlord and a tenant."""
    logger.debug("Setup route accessed with method=%s", request.method)
    
    try:
        supabase = require_supabase()
        
        # Check if users already exist
        existing = supabase.table("users").select("id").limit(1).execute()
        if existing.data:
            logger.info("Setup attempted but users already exist; redirecting to index.")
            flash("Setup has already been completed.", "info")
            return redirect(url_for("index"))
        
        if request.method == "POST":
            landlord_username = request.form.get("landlord_username", "").strip()
            landlord_password = request.form.get("landlord_password", "").strip()
            landlord_full_name = request.form.get("landlord_full_name", "").strip()
            landlord_email = request.form.get("landlord_email", "").strip()

            tenant_username = request.form.get("tenant_username", "").strip()
            tenant_password = request.form.get("tenant_password", "").strip()
            tenant_full_name = request.form.get("tenant_full_name", "").strip()
            tenant_email = request.form.get("tenant_email", "").strip()

            monthly_rent_raw = request.form.get("monthly_rent", "").strip()
            due_day_raw = request.form.get("due_day", "").strip()

            logger.debug(
                "Setup form submitted with landlord_username=%s, tenant_username=%s",
                landlord_username, tenant_username,
            )

            if not all([
                landlord_username, landlord_password,
                tenant_username, tenant_password,
                monthly_rent_raw, due_day_raw,
            ]):
                flash("Please fill in all required fields.", "warning")
                return render_template("setup.html")

            try:
                monthly_rent = float(monthly_rent_raw)
                due_day = int(due_day_raw)
            except ValueError:
                logger.warning("Invalid monthly_rent or due_day entered during setup.")
                flash("Monthly rent must be a number and due day must be an integer.", "warning")
                return render_template("setup.html")

            try:
                # Create landlord
                landlord_resp = supabase.table("users").insert({
                    "username": landlord_username,
                    "password": generate_password_hash(landlord_password),
                    "role": "landlord",
                    "full_name": landlord_full_name or None,
                    "email": landlord_email or None,
                }).execute()
                landlord_id = landlord_resp.data[0]["id"]

                # Create tenant
                tenant_resp = supabase.table("users").insert({
                    "username": tenant_username,
                    "password": generate_password_hash(tenant_password),
                    "role": "tenant",
                    "full_name": tenant_full_name or None,
                    "email": tenant_email or None,
                }).execute()
                tenant_id = tenant_resp.data[0]["id"]

                # Create lease
                today = datetime.date.today().isoformat()
                supabase.table("leases").insert({
                    "tenant_id": tenant_id,
                    "landlord_id": landlord_id,
                    "monthly_rent": monthly_rent,
                    "due_day": due_day,
                    "start_date": today,
                    "is_active": True,
                }).execute()

                logger.info("Setup completed with landlord id=%s and tenant id=%s", landlord_id, tenant_id)
                flash("Setup completed. You can now log in.", "success")
                return redirect(url_for("login"))
            except Exception as e:
                logger.exception("Error during setup: %s", e)
                flash("Error during setup: usernames might already exist.", "danger")
                return render_template("setup.html")

    except RuntimeError as e:
        flash(str(e), "danger")
        return render_template("setup.html")
    
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    logger.debug("Login route accessed with method=%s", request.method)
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        logger.debug("Login attempt for username=%s", username)
        user = get_user_by_username(username)
        
        if user:
            stored_password = user["password"]
            password_valid = False
            needs_upgrade = False
            
            # Check if password is hashed (starts with hash algorithm identifier)
            if stored_password.startswith(("scrypt:", "pbkdf2:", "sha256:")):
                # Verify hashed password
                password_valid = check_password_hash(stored_password, password)
            else:
                # Legacy plaintext password check
                password_valid = (stored_password == password)
                needs_upgrade = password_valid  # Upgrade if correct
            
            if password_valid:
                # Upgrade plaintext password to hashed (one-time migration)
                if needs_upgrade:
                    try:
                        supabase = require_supabase()
                        new_hash = generate_password_hash(password)
                        supabase.table("users").update({"password": new_hash}).eq("id", user["id"]).execute()
                        logger.info("Upgraded password to hashed for user id=%s", user["id"])
                    except Exception as e:
                        logger.warning("Failed to upgrade password for user id=%s: %s", user["id"], e)
                
                login_user(user)
                next_page = request.args.get("next")
                logger.info(
                    "Login successful for username=%s; redirecting to %s",
                    username,
                    next_page or "dashboard",
                )
                return redirect(next_page or url_for("dashboard"))
        
        logger.warning("Login failed for username=%s", username)
        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    logger.debug("Logout route called.")
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required()
def dashboard():
    user = get_current_user()
    logger.debug("Dashboard requested by user id=%s role=%s", user["id"], user["role"])
    if user["role"] == "landlord":
        return redirect(url_for("landlord_dashboard"))
    return redirect(url_for("tenant_dashboard"))


# -----------------------
# Settings / Profile
# -----------------------

@app.route("/settings")
@login_required()
def settings():
    """Display user settings page."""
    user = get_current_user()
    logger.debug("Settings page requested by user id=%s", user["id"])
    return render_template("settings.html", user=user)


@app.route("/settings/profile", methods=["POST"])
@login_required()
def update_profile():
    """Update user profile information."""
    user = get_current_user()
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    
    logger.debug("Profile update for user id=%s: full_name=%s, email=%s", user["id"], full_name, email)
    
    try:
        supabase = require_supabase()
        supabase.table("users").update({
            "full_name": full_name or None,
            "email": email or None,
        }).eq("id", user["id"]).execute()
        
        logger.info("Profile updated for user id=%s", user["id"])
        flash("Profile updated successfully.", "success")
    except Exception as e:
        logger.exception("Error updating profile for user id=%s: %s", user["id"], e)
        flash("Error updating profile. Please try again.", "danger")
    
    return redirect(url_for("settings"))


@app.route("/settings/password", methods=["POST"])
@login_required()
def change_password():
    """Change user password."""
    user = get_current_user()
    current_password = request.form.get("current_password", "").strip()
    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()
    
    logger.debug("Password change attempt for user id=%s", user["id"])
    
    # Validation
    if not current_password or not new_password or not confirm_password:
        flash("Please fill in all password fields.", "warning")
        return redirect(url_for("settings"))
    
    if new_password != confirm_password:
        flash("New passwords do not match.", "warning")
        return redirect(url_for("settings"))
    
    if len(new_password) < 6:
        flash("New password must be at least 6 characters.", "warning")
        return redirect(url_for("settings"))
    
    # Verify current password
    stored_password = user["password"]
    password_valid = False
    
    if stored_password.startswith(("scrypt:", "pbkdf2:", "sha256:")):
        password_valid = check_password_hash(stored_password, current_password)
    else:
        password_valid = (stored_password == current_password)
    
    if not password_valid:
        logger.warning("Password change failed for user id=%s: incorrect current password", user["id"])
        flash("Current password is incorrect.", "danger")
        return redirect(url_for("settings"))
    
    # Update password
    try:
        supabase = require_supabase()
        new_hash = generate_password_hash(new_password)
        supabase.table("users").update({"password": new_hash}).eq("id", user["id"]).execute()
        
        logger.info("Password changed for user id=%s", user["id"])
        flash("Password changed successfully.", "success")
    except Exception as e:
        logger.exception("Error changing password for user id=%s: %s", user["id"], e)
        flash("Error changing password. Please try again.", "danger")
    
    return redirect(url_for("settings"))


# -----------------------
# Maintenance helpers (priority + overdue)
# -----------------------

def _apply_deepl_and_overdue(rows):
    """
    Process maintenance request rows, attach translated_description (for ES)
    and is_overdue flag based on age + status.
    """
    lang = get_lang()
    now = datetime.datetime.utcnow()
    processed = []

    for r in rows:
        r_dict = dict(r) if hasattr(r, "keys") else r

        # DeepL translation only when viewing in Spanish
        if lang == "es":
            desc = r_dict.get("description")
            if desc:
                translated = translate_text_deepl(desc, target_lang="es")
                if translated:
                    r_dict["translated_description"] = translated

        # Overdue logic: Open/In progress older than 7 days
        r_dict["is_overdue"] = False
        created_at_str = r_dict.get("created_at")
        status = r_dict.get("status")
        if created_at_str and status in ("Open", "In progress"):
            try:
                # Handle ISO format from Supabase
                if isinstance(created_at_str, str):
                    created_at_str = created_at_str.replace("Z", "+00:00")
                    created_dt = datetime.datetime.fromisoformat(created_at_str.replace(" ", "T"))
                    if created_dt.tzinfo:
                        created_dt = created_dt.replace(tzinfo=None)
                    age_days = (now - created_dt).days
                    if age_days >= 7:
                        r_dict["is_overdue"] = True
            except Exception:
                logger.exception(
                    "Failed to parse created_at for maintenance request id=%s value=%r",
                    r_dict.get("id"), created_at_str,
                )

        processed.append(r_dict)

    logger.debug("Processed %d maintenance requests for DeepL/overdue (lang=%s).", len(processed), lang)
    return processed


# -----------------------
# Tenant Views
# -----------------------

@app.route("/tenant")
@login_required(role="tenant")
def tenant_dashboard():
    user = get_current_user()
    logger.debug("Loading tenant dashboard for tenant id=%s", user["id"])

    try:
        supabase = require_supabase()
        
        # Maintenance requests
        requests_resp = (
            supabase.table("maintenance_requests")
            .select("*")
            .eq("tenant_id", user["id"])
            .order("created_at", desc=True)
            .execute()
        )
        requests_rows = requests_resp.data or []
        requests_for_view = _apply_deepl_and_overdue(requests_rows)

        # Rent info
        month, year, month_label = get_current_month_year()
        lease = get_active_lease_for_tenant(user["id"])
        rent_paid = 0
        rent_status = None
        recent_payments = []
        if lease:
            rent_paid, rent_status = get_rent_status_for_lease(
                lease["id"], lease["monthly_rent"], month, year
            )
            recent_payments = get_recent_rent_payments_for_tenant(user["id"], limit=5)
        else:
            logger.warning("No active lease found for tenant id=%s", user["id"])

        # Get announcements from landlord
        announcements = get_announcements_for_tenant(user["id"])

        return render_template(
            "tenant_dashboard.html",
            user=user,
            requests=requests_for_view,
            lease=lease,
            rent_month_label=month_label,
            rent_paid=rent_paid,
            rent_status=rent_status,
            recent_payments=recent_payments,
            announcements=announcements,
        )
    except Exception as e:
        logger.exception("Error loading tenant dashboard: %s", e)
        flash("Error loading dashboard. Please try again.", "danger")
        return redirect(url_for("index"))


@app.route("/tenant/request/new", methods=["GET", "POST"])
@login_required(role="tenant")
def new_request():
    user = get_current_user()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        priority = request.form.get("priority", "Normal").strip() or "Normal"
        image_file = request.files.get("image")
        image_filename = None
        logger.debug(
            "New maintenance request submission by tenant id=%s, title='%s', priority='%s'",
            user["id"], title, priority,
        )

        allowed_priorities = {"Low", "Normal", "High", "Emergency"}
        if priority not in allowed_priorities:
            logger.warning("Invalid priority '%s' supplied, defaulting to 'Normal'.", priority)
            priority = "Normal"

        if not title or not description:
            flash("Please fill in both title and description.", "warning")
        elif image_file and image_file.filename and not allowed_image_file(image_file.filename):
            flash("Image must be a PNG, JPG, JPEG, GIF, or WEBP file.", "warning")
            logger.warning(
                "Rejected maintenance request image with invalid extension for tenant id=%s",
                user["id"],
            )
        else:
            image_url = None
            if image_file and image_file.filename:
                safe_name = secure_filename(image_file.filename)
                storage_filename = f"{uuid.uuid4().hex}_{safe_name}"
                image_url = upload_image_to_storage(image_file, storage_filename)
                if image_url:
                    logger.debug(
                        "Uploaded maintenance request image for tenant id=%s to %s",
                        user["id"], image_url,
                    )
                else:
                    logger.warning(
                        "Failed to upload image for tenant id=%s, continuing without image",
                        user["id"],
                    )

            try:
                supabase = require_supabase()
                supabase.table("maintenance_requests").insert({
                    "tenant_id": user["id"],
                    "title": title,
                    "description": description,
                    "status": "Open",
                    "priority": priority,
                    "image_filename": image_url,  # Now stores the full URL
                }).execute()
                
                logger.info(
                    "Maintenance request created for tenant id=%s with title='%s' priority='%s'",
                    user["id"], title, priority,
                )
                flash("Request submitted!", "success")
                return redirect(url_for("tenant_dashboard"))
            except Exception as e:
                logger.exception("Error creating maintenance request: %s", e)
                flash("Error submitting request. Please try again.", "danger")
    
    return render_template("new_request.html", user=user)


@app.route("/tenant/rent/pay", methods=["POST"])
@login_required(role="tenant")
def tenant_pay_rent():
    user = get_current_user()
    amount_raw = request.form.get("amount", "").strip()
    method = request.form.get("method", "").strip() or "Recorded in app"
    note = request.form.get("note", "").strip()
    logger.debug(
        "Tenant id=%s attempting to record rent payment amount_raw='%s', method='%s'",
        user["id"], amount_raw, method,
    )

    try:
        amount = float(amount_raw)
    except ValueError:
        logger.warning("Invalid payment amount entered by tenant id=%s: '%s'", user["id"], amount_raw)
        flash("Please enter a valid numeric amount.", "warning")
        return redirect(url_for("tenant_dashboard"))

    if amount <= 0:
        logger.warning("Non-positive payment amount entered by tenant id=%s: %s", user["id"], amount)
        flash("Payment amount must be greater than zero.", "warning")
        return redirect(url_for("tenant_dashboard"))

    lease = get_active_lease_for_tenant(user["id"])
    if not lease:
        logger.warning("Tenant id=%s tried to pay rent but has no active lease.", user["id"])
        flash("No active lease found. Please contact your landlord.", "danger")
        return redirect(url_for("tenant_dashboard"))

    month, year, _ = get_current_month_year()

    try:
        supabase = require_supabase()
        supabase.table("rent_payments").insert({
            "lease_id": lease["id"],
            "amount": amount,
            "month": month,
            "year": year,
            "status": "Paid",
            "method": method,
            "note": note or None,
        }).execute()
        
        logger.info(
            "Recorded rent payment for tenant id=%s, lease_id=%s, amount=%.2f, month=%s, year=%s",
            user["id"], lease["id"], amount, month, year,
        )
        flash("Rent payment recorded for this month (this does not actually charge a card).", "success")
    except Exception as e:
        logger.exception("Error recording rent payment: %s", e)
        flash("Error recording payment. Please try again.", "danger")
    
    return redirect(url_for("tenant_dashboard"))


# -----------------------
# Stripe tenant flows
# -----------------------

@app.route("/tenant/rent/stripe-checkout", methods=["POST"])
@login_required(role="tenant")
def tenant_stripe_checkout():
    """
    Start a Stripe Checkout session for the tenant's current month's rent.
    The amount charged is the remaining balance for the current month.
    """
    user = get_current_user()
    logger.debug("Tenant id=%s requested Stripe rent checkout", user["id"])

    if not STRIPE_SECRET_KEY or not STRIPE_PUBLISHABLE_KEY:
        logger.error(
            "Stripe keys not configured when tenant id=%s attempted Stripe payment",
            user["id"],
        )
        flash("Online payments are not configured. Please contact your landlord.", "danger")
        return redirect(url_for("tenant_dashboard"))

    lease = get_active_lease_for_tenant(user["id"])
    if not lease:
        logger.warning(
            "Tenant id=%s attempted Stripe payment but has no active lease", user["id"]
        )
        flash("No active lease found. Please contact your landlord.", "danger")
        return redirect(url_for("tenant_dashboard"))

    month, year, month_label = get_current_month_year()
    rent_paid, rent_status = get_rent_status_for_lease(
        lease["id"], lease["monthly_rent"], month, year
    )
    amount_due = (lease["monthly_rent"] or 0) - (rent_paid or 0)
    logger.debug(
        "Stripe checkout calculation for tenant id=%s lease_id=%s month=%s year=%s: "
        "monthly_rent=%.2f rent_paid=%.2f amount_due=%.2f status=%s",
        user["id"], lease["id"], month, year,
        lease["monthly_rent"] or 0, rent_paid or 0, amount_due, rent_status,
    )

    if amount_due <= 0:
        flash("No outstanding rent balance for this month.", "info")
        return redirect(url_for("tenant_dashboard"))

    try:
        amount_cents = int(round(amount_due * 100))
        logger.debug(
            "Creating Stripe Checkout Session for tenant id=%s lease_id=%s amount_due=%.2f (amount_cents=%s)",
            user["id"], lease["id"], amount_due, amount_cents,
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
                "tenant_id": str(user["id"]),
                "lease_id": str(lease["id"]),
                "month": str(month),
                "year": str(year),
            },
            success_url=url_for("tenant_stripe_success", _external=True),
            cancel_url=url_for("tenant_stripe_cancel", _external=True),
        )

        logger.info(
            "Created Stripe Checkout Session id=%s for tenant id=%s lease_id=%s amount_cents=%s",
            checkout_session.id, user["id"], lease["id"], amount_cents,
        )
        return redirect(checkout_session.url, code=303)

    except Exception:
        logger.exception("Failed to create Stripe Checkout Session for tenant id=%s", user["id"])
        flash("Could not start payment. Please try again later.", "danger")
        return redirect(url_for("tenant_dashboard"))


@app.route("/tenant/rent/stripe-success")
@login_required(role="tenant")
def tenant_stripe_success():
    """
    Landing page when Stripe Checkout reports success in the browser.
    The authoritative record is still the Stripe webhook; this route is only UX.
    """
    user = get_current_user()
    logger.info("Tenant id=%s returned from Stripe success URL", user["id"])
    flash("Payment completed. Your rent status will update shortly.", "success")
    return redirect(url_for("tenant_dashboard"))


@app.route("/tenant/rent/stripe-cancel")
@login_required(role="tenant")
def tenant_stripe_cancel():
    """
    Landing page when the tenant cancels the Stripe Checkout flow.
    """
    user = get_current_user()
    logger.info("Tenant id=%s returned from Stripe cancel URL", user["id"])
    flash("Payment was cancelled. No charges were made.", "warning")
    return redirect(url_for("tenant_dashboard"))


@app.route("/stripe/webhook", methods=["POST"])
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
        logger.debug(
            "Processing checkout.session.completed: %s",
            json.dumps(session_obj, indent=2),
        )

        metadata = session_obj.get("metadata") or {}
        tenant_id = metadata.get("tenant_id")
        lease_id = metadata.get("lease_id")
        month = metadata.get("month")
        year = metadata.get("year")
        amount_total = session_obj.get("amount_total")  # in cents

        logger.info(
            "checkout.session.completed for tenant_id=%s lease_id=%s month=%s year=%s amount_total=%s",
            tenant_id, lease_id, month, year, amount_total,
        )

        try:
            if not (tenant_id and lease_id and month and year and amount_total is not None):
                logger.error(
                    "Missing required metadata in Stripe webhook for rent payment: %s",
                    metadata,
                )
            else:
                supabase = require_supabase()
                amount = float(amount_total) / 100.0
                month_int = int(month)
                year_int = int(year)

                supabase.table("rent_payments").insert({
                    "lease_id": int(lease_id),
                    "amount": amount,
                    "month": month_int,
                    "year": year_int,
                    "status": "Paid",
                    "method": "Stripe",
                    "note": f"Stripe Checkout session {session_obj.get('id')}",
                }).execute()
                
                logger.info(
                    "Rent payment recorded from Stripe webhook: lease_id=%s amount=%.2f month=%s year=%s",
                    lease_id, amount, month_int, year_int,
                )
        except Exception:
            logger.exception("Failed to record rent payment from Stripe webhook.")
    else:
        logger.debug("Unhandled Stripe event type: %s", event["type"])

    return "OK", 200


# -----------------------
# Landlord Views
# -----------------------

@app.route("/landlord")
@login_required(role="landlord")
def landlord_dashboard():
    user = get_current_user()
    logger.debug("Loading landlord dashboard for landlord id=%s", user["id"])

    try:
        supabase = require_supabase()
        
        # Get all tenant IDs for this landlord's active leases
        leases_resp = (
            supabase.table("leases")
            .select("tenant_id")
            .eq("landlord_id", user["id"])
            .eq("is_active", True)
            .execute()
        )
        tenant_ids = [l["tenant_id"] for l in (leases_resp.data or [])]
        
        # Maintenance requests for landlord's tenants
        requests_for_view = []
        open_count = 0
        
        if tenant_ids:
            requests_resp = (
                supabase.table("maintenance_requests")
                .select("*")
                .in_("tenant_id", tenant_ids)
                .order("created_at", desc=True)
                .execute()
            )
            requests_rows = requests_resp.data or []
            
            # Add tenant names
            users_resp = supabase.table("users").select("id, full_name, username").in_("id", tenant_ids).execute()
            user_map = {u["id"]: u for u in (users_resp.data or [])}
            
            for r in requests_rows:
                tenant = user_map.get(r["tenant_id"], {})
                r["tenant_name"] = tenant.get("full_name")
                r["tenant_username"] = tenant.get("username")
            
            requests_for_view = _apply_deepl_and_overdue(requests_rows)
            open_count = sum(1 for r in requests_rows if r.get("status") == "Open")

        # Rent overview for current month
        month, year, month_label = get_current_month_year()
        logger.debug("Calculating rent overview for landlord id=%s month=%s year=%s", user["id"], month, year)

        rent_overview = []
        unpaid_count = 0
        
        # Get all active leases with tenant info
        leases_full_resp = (
            supabase.table("leases")
            .select("id, tenant_id, monthly_rent, due_day")
            .eq("landlord_id", user["id"])
            .eq("is_active", True)
            .execute()
        )
        leases_full = leases_full_resp.data or []
        
        if leases_full:
            lease_ids = [l["id"] for l in leases_full]
            tenant_ids_full = list(set(l["tenant_id"] for l in leases_full))
            
            # Get tenant names
            tenants_resp = supabase.table("users").select("id, full_name, username").in_("id", tenant_ids_full).execute()
            tenant_map = {t["id"]: t for t in (tenants_resp.data or [])}
            
            # Get payments for this month
            payments_resp = (
                supabase.table("rent_payments")
                .select("lease_id, amount, status")
                .in_("lease_id", lease_ids)
                .eq("month", month)
                .eq("year", year)
                .execute()
            )
            payments = payments_resp.data or []
            
            # Sum payments by lease
            paid_by_lease = {}
            for p in payments:
                if p.get("status") == "Paid":
                    paid_by_lease[p["lease_id"]] = paid_by_lease.get(p["lease_id"], 0) + p["amount"]
            
            for lease in leases_full:
                tenant = tenant_map.get(lease["tenant_id"], {})
                monthly_rent = lease["monthly_rent"]
                paid_amount = paid_by_lease.get(lease["id"], 0)
                
                if paid_amount >= monthly_rent:
                    status = "Paid"
                elif paid_amount > 0:
                    status = "Partial"
                else:
                    status = "Unpaid"
                
                if status != "Paid":
                    unpaid_count += 1
                
                rent_overview.append({
                    "tenant_name": tenant.get("full_name") or tenant.get("username"),
                    "monthly_rent": monthly_rent,
                    "due_day": lease["due_day"],
                    "paid_amount": paid_amount,
                    "status": status,
                })

        rent_last_updated = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        logger.debug(
            "Rent overview for landlord id=%s: %d leases, %d unpaid/partial (generated %s)",
            user["id"], len(rent_overview), unpaid_count, rent_last_updated,
        )

        return render_template(
            "landlord_dashboard.html",
            user=user,
            requests=requests_for_view,
            open_count=open_count,
            rent_month_label=month_label,
            rent_overview=rent_overview,
            unpaid_count=unpaid_count,
            rent_last_updated=rent_last_updated,
        )
    except Exception as e:
        logger.exception("Error loading landlord dashboard: %s", e)
        flash("Error loading dashboard. Please try again.", "danger")
        return redirect(url_for("index"))


@app.route("/landlord/leases")
@login_required(role="landlord")
def landlord_leases():
    user = get_current_user()
    logger.debug("Landlord leases view for landlord id=%s", user["id"])

    try:
        supabase = require_supabase()
        
        # Get leases
        leases_resp = (
            supabase.table("leases")
            .select("*")
            .eq("landlord_id", user["id"])
            .order("is_active", desc=True)
            .execute()
        )
        leases = leases_resp.data or []
        
        # Get tenant names
        if leases:
            tenant_ids = list(set(l["tenant_id"] for l in leases))
            tenants_resp = supabase.table("users").select("id, full_name, username").in_("id", tenant_ids).execute()
            tenant_map = {t["id"]: t for t in (tenants_resp.data or [])}
            
            for lease in leases:
                tenant = tenant_map.get(lease["tenant_id"], {})
                lease["tenant_name"] = tenant.get("full_name")
                lease["tenant_username"] = tenant.get("username")

        return render_template("landlord_leases.html", user=user, leases=leases)
    except Exception as e:
        logger.exception("Error loading leases: %s", e)
        flash("Error loading leases. Please try again.", "danger")
        return redirect(url_for("landlord_dashboard"))


@app.route("/landlord/leases/new", methods=["GET", "POST"])
@login_required(role="landlord")
def landlord_new_lease():
    user = get_current_user()
    logger.debug("New lease route accessed by landlord id=%s method=%s", user["id"], request.method)

    try:
        supabase = require_supabase()
        
        # Get all tenants
        tenants_resp = (
            supabase.table("users")
            .select("*")
            .eq("role", "tenant")
            .order("full_name")
            .execute()
        )
        tenants = tenants_resp.data or []

        if request.method == "POST":
            tenant_id_raw = request.form.get("tenant_id")
            monthly_rent_raw = request.form.get("monthly_rent")
            due_day_raw = request.form.get("due_day")
            start_date = request.form.get("start_date") or None
            end_date = request.form.get("end_date") or None

            logger.debug(
                "New lease submission: tenant_id_raw=%s, monthly_rent_raw=%s, due_day_raw=%s",
                tenant_id_raw, monthly_rent_raw, due_day_raw,
            )

            try:
                tenant_id = int(tenant_id_raw)
                monthly_rent = float(monthly_rent_raw)
                due_day = int(due_day_raw)
            except (TypeError, ValueError):
                logger.warning("Invalid lease form input.")
                flash("Please provide valid values for tenant, monthly rent, and due day.", "warning")
                return render_template("landlord_lease_form.html", user=user, tenants=tenants)

            supabase.table("leases").insert({
                "tenant_id": tenant_id,
                "landlord_id": user["id"],
                "monthly_rent": monthly_rent,
                "due_day": due_day,
                "start_date": start_date,
                "end_date": end_date,
                "is_active": True,
            }).execute()
            
            logger.info("New lease created by landlord id=%s for tenant_id=%s", user["id"], tenant_id)
            flash("Lease created.", "success")
            return redirect(url_for("landlord_leases"))

        return render_template("landlord_lease_form.html", user=user, tenants=tenants)
    except Exception as e:
        logger.exception("Error in new lease: %s", e)
        flash("Error creating lease. Please try again.", "danger")
        return redirect(url_for("landlord_leases"))


@app.route("/landlord/leases/<int:lease_id>/toggle", methods=["POST"])
@login_required(role="landlord")
def landlord_toggle_lease(lease_id):
    user = get_current_user()
    logger.debug("Toggle lease id=%s requested by landlord id=%s", lease_id, user["id"])

    try:
        supabase = require_supabase()
        
        # Get the lease
        lease_resp = (
            supabase.table("leases")
            .select("*")
            .eq("id", lease_id)
            .eq("landlord_id", user["id"])
            .limit(1)
            .execute()
        )
        leases = lease_resp.data or []
        
        if not leases:
            logger.warning("Lease id=%s not found or not owned by landlord id=%s", lease_id, user["id"])
            flash("Lease not found.", "danger")
            return redirect(url_for("landlord_leases"))

        lease = leases[0]
        new_status = not lease["is_active"]
        
        supabase.table("leases").update({"is_active": new_status}).eq("id", lease_id).execute()
        
        logger.info("Lease id=%s toggled by landlord id=%s to is_active=%s", lease_id, user["id"], new_status)
        flash("Lease status updated.", "success")
    except Exception as e:
        logger.exception("Error toggling lease: %s", e)
        flash("Error updating lease. Please try again.", "danger")
    
    return redirect(url_for("landlord_leases"))


@app.route("/landlord/tenants")
@login_required(role="landlord")
def landlord_tenants():
    user = get_current_user()
    logger.debug("Landlord tenants view for landlord id=%s", user["id"])

    try:
        supabase = require_supabase()
        tenants_resp = (
            supabase.table("users")
            .select("*")
            .eq("role", "tenant")
            .order("full_name")
            .execute()
        )
        tenants = tenants_resp.data or []
        return render_template("landlord_tenants.html", user=user, tenants=tenants)
    except Exception as e:
        logger.exception("Error loading tenants: %s", e)
        flash("Error loading tenants. Please try again.", "danger")
        return redirect(url_for("landlord_dashboard"))


@app.route("/landlord/tenants/new", methods=["GET", "POST"])
@login_required(role="landlord")
def landlord_new_tenant():
    user = get_current_user()
    logger.debug("New tenant route accessed by landlord id=%s method=%s", user["id"], request.method)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()

        logger.debug("New tenant submission: username=%s, full_name=%s, email=%s", username, full_name, email)

        if not username or not password:
            flash("Username and password are required.", "warning")
            return render_template("landlord_tenant_form.html", user=user)

        try:
            supabase = require_supabase()
            supabase.table("users").insert({
                "username": username,
                "password": generate_password_hash(password),
                "role": "tenant",
                "full_name": full_name or None,
                "email": email or None,
            }).execute()
            
            logger.info("New tenant %s created by landlord id=%s", username, user["id"])
            flash("Tenant created.", "success")
            return redirect(url_for("landlord_tenants"))
        except Exception as e:
            logger.exception("Error creating tenant: %s", e)
            flash("A tenant with that username already exists.", "danger")

    return render_template("landlord_tenant_form.html", user=user)


@app.route("/landlord/requests")
@login_required(role="landlord")
def landlord_requests():
    user = get_current_user()
    logger.debug("Landlord requests view for landlord id=%s", user["id"])

    try:
        supabase = require_supabase()
        
        # Get tenant IDs for this landlord
        leases_resp = (
            supabase.table("leases")
            .select("tenant_id")
            .eq("landlord_id", user["id"])
            .eq("is_active", True)
            .execute()
        )
        tenant_ids = list(set(l["tenant_id"] for l in (leases_resp.data or [])))
        
        requests_for_view = []
        
        if tenant_ids:
            # Get maintenance requests
            requests_resp = (
                supabase.table("maintenance_requests")
                .select("*")
                .in_("tenant_id", tenant_ids)
                .order("created_at", desc=True)
                .execute()
            )
            requests_rows = requests_resp.data or []
            
            # Get tenant names
            tenants_resp = supabase.table("users").select("id, full_name, username").in_("id", tenant_ids).execute()
            tenant_map = {t["id"]: t for t in (tenants_resp.data or [])}
            
            for r in requests_rows:
                tenant = tenant_map.get(r["tenant_id"], {})
                r["tenant_name"] = tenant.get("full_name")
                r["tenant_username"] = tenant.get("username")
            
            requests_for_view = _apply_deepl_and_overdue(requests_rows)

        return render_template("landlord_requests.html", user=user, requests=requests_for_view)
    except Exception as e:
        logger.exception("Error loading requests: %s", e)
        flash("Error loading requests. Please try again.", "danger")
        return redirect(url_for("landlord_dashboard"))


@app.route("/landlord/requests/<int:request_id>/status", methods=["POST"])
@login_required(role="landlord")
def landlord_update_request_status(request_id):
    user = get_current_user()
    new_status = request.form.get("status", "").strip()
    logger.debug(
        "Landlord id=%s updating maintenance request id=%s to status=%s",
        user["id"], request_id, new_status,
    )

    if new_status not in ["Open", "In progress", "Completed"]:
        logger.warning("Invalid status %s provided for request id=%s", new_status, request_id)
        flash("Invalid status.", "warning")
        return redirect(url_for("landlord_requests"))

    try:
        supabase = require_supabase()
        supabase.table("maintenance_requests").update({"status": new_status}).eq("id", request_id).execute()
        
        logger.info(
            "Maintenance request id=%s updated to status=%s by landlord id=%s",
            request_id, new_status, user["id"],
        )
        flash("Request status updated.", "success")
    except Exception as e:
        logger.exception("Error updating request status: %s", e)
        flash("Error updating status. Please try again.", "danger")
    
    return redirect(url_for("landlord_requests"))


@app.route("/landlord/requests/<int:request_id>/delete", methods=["POST"])
@login_required(role="landlord")
def landlord_delete_request(request_id):
    """Delete a maintenance request."""
    user = get_current_user()
    logger.debug("Landlord id=%s deleting maintenance request id=%s", user["id"], request_id)

    try:
        supabase = require_supabase()
        
        # Verify the request belongs to one of this landlord's tenants
        leases_resp = (
            supabase.table("leases")
            .select("tenant_id")
            .eq("landlord_id", user["id"])
            .execute()
        )
        tenant_ids = [l["tenant_id"] for l in (leases_resp.data or [])]
        
        if tenant_ids:
            # Delete the request if it belongs to one of the landlord's tenants
            supabase.table("maintenance_requests").delete().eq("id", request_id).in_("tenant_id", tenant_ids).execute()
            logger.info("Maintenance request id=%s deleted by landlord id=%s", request_id, user["id"])
            flash("Maintenance request deleted.", "success")
        else:
            flash("Request not found.", "danger")
    except Exception as e:
        logger.exception("Error deleting maintenance request: %s", e)
        flash("Error deleting request. Please try again.", "danger")
    
    return redirect(url_for("landlord_requests"))


# -----------------------
# Announcements
# -----------------------

@app.route("/landlord/announcements")
@login_required(role="landlord")
def landlord_announcements():
    """View and manage announcements."""
    user = get_current_user()
    logger.debug("Announcements page for landlord id=%s", user["id"])
    
    try:
        supabase = require_supabase()
        resp = (
            supabase.table("announcements")
            .select("*")
            .eq("landlord_id", user["id"])
            .order("created_at", desc=True)
            .execute()
        )
        announcements = resp.data or []
        return render_template("landlord_announcements.html", user=user, announcements=announcements)
    except Exception as e:
        logger.exception("Error loading announcements: %s", e)
        flash("Error loading announcements.", "danger")
        return redirect(url_for("landlord_dashboard"))


@app.route("/landlord/announcements/new", methods=["GET", "POST"])
@login_required(role="landlord")
def landlord_new_announcement():
    """Create a new announcement."""
    user = get_current_user()
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        expires_at = request.form.get("expires_at", "").strip() or None
        
        if not title or not content:
            flash("Please fill in both title and content.", "warning")
            return render_template("landlord_announcement_form.html", user=user)
        
        try:
            supabase = require_supabase()
            supabase.table("announcements").insert({
                "landlord_id": user["id"],
                "title": title,
                "content": content,
                "is_active": True,
                "expires_at": expires_at,
            }).execute()
            
            logger.info("Announcement created by landlord id=%s: %s", user["id"], title)
            flash("Announcement posted!", "success")
            return redirect(url_for("landlord_announcements"))
        except Exception as e:
            logger.exception("Error creating announcement: %s", e)
            flash("Error creating announcement.", "danger")
    
    return render_template("landlord_announcement_form.html", user=user)


@app.route("/landlord/announcements/<int:announcement_id>/toggle", methods=["POST"])
@login_required(role="landlord")
def landlord_toggle_announcement(announcement_id):
    """Toggle announcement active status."""
    user = get_current_user()
    
    try:
        supabase = require_supabase()
        
        # Get current status
        resp = (
            supabase.table("announcements")
            .select("is_active")
            .eq("id", announcement_id)
            .eq("landlord_id", user["id"])
            .limit(1)
            .execute()
        )
        
        if not resp.data:
            flash("Announcement not found.", "danger")
            return redirect(url_for("landlord_announcements"))
        
        new_status = not resp.data[0]["is_active"]
        supabase.table("announcements").update({"is_active": new_status}).eq("id", announcement_id).execute()
        
        logger.info("Announcement id=%s toggled to is_active=%s", announcement_id, new_status)
        flash("Announcement updated.", "success")
    except Exception as e:
        logger.exception("Error toggling announcement: %s", e)
        flash("Error updating announcement.", "danger")
    
    return redirect(url_for("landlord_announcements"))


@app.route("/landlord/announcements/<int:announcement_id>/delete", methods=["POST"])
@login_required(role="landlord")
def landlord_delete_announcement(announcement_id):
    """Delete an announcement."""
    user = get_current_user()
    
    try:
        supabase = require_supabase()
        supabase.table("announcements").delete().eq("id", announcement_id).eq("landlord_id", user["id"]).execute()
        
        logger.info("Announcement id=%s deleted by landlord id=%s", announcement_id, user["id"])
        flash("Announcement deleted.", "success")
    except Exception as e:
        logger.exception("Error deleting announcement: %s", e)
        flash("Error deleting announcement.", "danger")
    
    return redirect(url_for("landlord_announcements"))


def get_announcements_for_tenant(tenant_id):
    """Get active announcements for a tenant from their landlord(s)."""
    try:
        supabase = require_supabase()
        
        # Get landlord IDs from tenant's active leases
        leases_resp = (
            supabase.table("leases")
            .select("landlord_id")
            .eq("tenant_id", tenant_id)
            .eq("is_active", True)
            .execute()
        )
        landlord_ids = list(set(l["landlord_id"] for l in (leases_resp.data or [])))
        
        if not landlord_ids:
            return []
        
        # Get active announcements from those landlords
        now = datetime.datetime.utcnow().isoformat()
        resp = (
            supabase.table("announcements")
            .select("*")
            .in_("landlord_id", landlord_ids)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .execute()
        )
        
        # Filter out expired announcements
        announcements = []
        for a in (resp.data or []):
            if a.get("expires_at"):
                if a["expires_at"] > now:
                    announcements.append(a)
            else:
                announcements.append(a)
        
        return announcements
    except Exception as e:
        logger.exception("Error fetching announcements for tenant id=%s: %s", tenant_id, e)
        return []


# -----------------------
# Calendar View
# -----------------------

@app.route("/calendar")
@login_required()
def calendar_view():
    """Display calendar view with events."""
    user = get_current_user()
    logger.debug("Calendar view for user id=%s role=%s", user["id"], user["role"])
    return render_template("calendar.html", user=user)


@app.route("/api/calendar-events")
@login_required()
def calendar_events():
    """API endpoint returning calendar events as JSON."""
    user = get_current_user()
    events = []
    
    try:
        supabase = require_supabase()
        
        if user["role"] == "tenant":
            # Get tenant's lease info
            lease = get_active_lease_for_tenant(user["id"])
            if lease:
                # Rent due dates (for next 12 months)
                today = datetime.date.today()
                for i in range(12):
                    month = (today.month + i - 1) % 12 + 1
                    year = today.year + ((today.month + i - 1) // 12)
                    due_day = min(lease["due_day"], 28)  # Handle short months
                    due_date = datetime.date(year, month, due_day)
                    
                    events.append({
                        "title": f"Rent Due (${lease['monthly_rent']:.0f})",
                        "start": due_date.isoformat(),
                        "color": "#e74c3c",
                        "type": "rent_due"
                    })
                
                # Lease dates
                if lease.get("start_date"):
                    events.append({
                        "title": "Lease Start",
                        "start": lease["start_date"],
                        "color": "#27ae60",
                        "type": "lease"
                    })
                if lease.get("end_date"):
                    events.append({
                        "title": "Lease End",
                        "start": lease["end_date"],
                        "color": "#e67e22",
                        "type": "lease"
                    })
            
            # Maintenance requests
            requests_resp = (
                supabase.table("maintenance_requests")
                .select("id, title, created_at, status")
                .eq("tenant_id", user["id"])
                .execute()
            )
            for r in (requests_resp.data or []):
                created = r["created_at"][:10] if r.get("created_at") else None
                if created:
                    color = "#3498db" if r["status"] == "Open" else "#95a5a6"
                    events.append({
                        "title": f"🔧 {r['title']}",
                        "start": created,
                        "color": color,
                        "type": "maintenance"
                    })
        
        else:  # Landlord
            # Get all active leases
            leases_resp = (
                supabase.table("leases")
                .select("id, tenant_id, monthly_rent, due_day, start_date, end_date")
                .eq("landlord_id", user["id"])
                .eq("is_active", True)
                .execute()
            )
            leases = leases_resp.data or []
            
            # Get tenant names
            tenant_ids = list(set(l["tenant_id"] for l in leases))
            if tenant_ids:
                tenants_resp = supabase.table("users").select("id, full_name, username").in_("id", tenant_ids).execute()
                tenant_map = {t["id"]: t.get("full_name") or t.get("username") for t in (tenants_resp.data or [])}
            else:
                tenant_map = {}
            
            today = datetime.date.today()
            for lease in leases:
                tenant_name = tenant_map.get(lease["tenant_id"], "Tenant")
                
                # Rent due dates (next 12 months)
                for i in range(12):
                    month = (today.month + i - 1) % 12 + 1
                    year = today.year + ((today.month + i - 1) // 12)
                    due_day = min(lease["due_day"], 28)
                    due_date = datetime.date(year, month, due_day)
                    
                    events.append({
                        "title": f"💰 {tenant_name} (${lease['monthly_rent']:.0f})",
                        "start": due_date.isoformat(),
                        "color": "#e74c3c",
                        "type": "rent_due"
                    })
                
                # Lease dates
                if lease.get("end_date"):
                    events.append({
                        "title": f"📋 {tenant_name} Lease Ends",
                        "start": lease["end_date"],
                        "color": "#e67e22",
                        "type": "lease"
                    })
            
            # Maintenance requests from tenants
            if tenant_ids:
                requests_resp = (
                    supabase.table("maintenance_requests")
                    .select("id, tenant_id, title, created_at, status")
                    .in_("tenant_id", tenant_ids)
                    .execute()
                )
                for r in (requests_resp.data or []):
                    created = r["created_at"][:10] if r.get("created_at") else None
                    if created:
                        tenant_name = tenant_map.get(r["tenant_id"], "Tenant")
                        color = "#3498db" if r["status"] == "Open" else "#95a5a6"
                        events.append({
                            "title": f"🔧 {tenant_name}: {r['title']}",
                            "start": created,
                            "color": color,
                            "type": "maintenance"
                        })
            
            # Announcements
            announcements_resp = (
                supabase.table("announcements")
                .select("id, title, created_at")
                .eq("landlord_id", user["id"])
                .execute()
            )
            for a in (announcements_resp.data or []):
                created = a["created_at"][:10] if a.get("created_at") else None
                if created:
                    events.append({
                        "title": f"📢 {a['title']}",
                        "start": created,
                        "color": "#9b59b6",
                        "type": "announcement"
                    })
        
        return {"events": events}
    
    except Exception as e:
        logger.exception("Error fetching calendar events: %s", e)
        return {"events": [], "error": str(e)}


# -----------------------
# App Entry
# -----------------------

if __name__ == "__main__":
    logger.debug("Starting app in debug mode on localhost.")
    app.run(debug=True)
