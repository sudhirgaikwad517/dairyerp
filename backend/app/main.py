import os
import time

# All business times (order cut-off, 4 AM dispatch, bill dates) are Indian time, even on a UTC server (VPS)
os.environ["TZ"] = os.environ.get("APP_TIMEZONE", "Asia/Kolkata")
if hasattr(time, "tzset"):
    time.tzset()

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.database import engine, Base, SessionLocal, add_missing_columns
from backend.app.services.seed_service import seed_database_if_empty

# Routers
from backend.app.api.dashboard import router as dashboard_router
from backend.app.api.customers import router as customers_router
from backend.app.api.products import router as products_router
from backend.app.api.pricing import router as pricing_router
from backend.app.api.orders import router as orders_router
from backend.app.api.driver_api import router as driver_router
from backend.app.api.transport import router as transport_router
from backend.app.api.procurement import router as procurement_router
from backend.app.api.production import router as production_router
from backend.app.api.profitability import router as profitability_router
from backend.app.api.invoices import router as invoices_router
from backend.app.api.complaints import router as complaints_router
from backend.app.api.reports import router as reports_router
from backend.app.api.billing import router as billing_router
from backend.app.api.drivers import router as drivers_router
from backend.app.api.auth import router as auth_router
from backend.app.api.customer_app import router as customer_app_router
from backend.app.api.claims import router as claims_router
from backend.app.api.files import router as files_router
from backend.app.api.notifications import router as notifications_router
from backend.app.api.legal import admin_router as legal_admin_router, router as legal_router
from backend.app.api.email_settings import router as email_settings_router
from backend.app.core.security import require_admin, upgrade_plaintext_passwords

# Create DB tables (and add columns introduced after a database was created)
Base.metadata.create_all(bind=engine)
add_missing_columns()

# Auto-seed initial demo dataset
with SessionLocal() as db:
    seed_database_if_empty(db)
    upgrade_plaintext_passwords(db)
    # Older orders, claims and bills get their per-product details (safe to run every start)
    from backend.app.services.order_lines import backfill
    backfill(db)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Full-Featured Dairy ERP Backend covering Procurement, Processing, Route & Transport Costing (per Litre), B2B Customer Management, Daily Orders, Driver Portal, Invoicing & Profitability.",
    version="1.0.0",
    # API docs only when asked for (DAIRY_DOCS=1); a live server should not list every endpoint publicly
    docs_url="/docs" if os.environ.get("DAIRY_DOCS") == "1" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if os.environ.get("DAIRY_DOCS") == "1" else None,
)



@app.on_event("startup")
def start_background_jobs():
    # Each day's orders go to the delivery boys at the dispatch time set by the admin
    if os.environ.get("DAIRY_AUTO_DISPATCH", "1") != "0":
        from backend.app.services.dispatch_control import start_auto_dispatcher
        start_auto_dispatcher(SessionLocal)
    # Bills and notices by email (only sends when the admin has turned email on)
    if os.environ.get("DAIRY_EMAIL_WORKER", "1") != "0":
        from backend.app.services.email_service import start_email_worker
        start_email_worker(SessionLocal)


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
api_v1 = settings.API_V1_STR

# Public: login. Self-scoped: delivery boy app (/driver) and customer app (/me) check their own roles.
app.include_router(auth_router, prefix=api_v1)
app.include_router(driver_router, prefix=api_v1)
app.include_router(customer_app_router, prefix=api_v1)
app.include_router(files_router, prefix=api_v1)  # checks who may see each photo
app.include_router(notifications_router, prefix=api_v1)  # customer: own notices, admin: the dairy's
app.include_router(legal_router)  # public: /privacy, /terms, /delete-account (Play Store)

# Everything else is the admin panel and needs an admin login
admin_only = [Depends(require_admin)]
for admin_router in [
    dashboard_router, customers_router, products_router, pricing_router,
    orders_router, transport_router, procurement_router, production_router, profitability_router,
    invoices_router, complaints_router, reports_router, billing_router, drivers_router, claims_router,
    legal_admin_router, email_settings_router,
]:
    app.include_router(admin_router, prefix=api_v1, dependencies=admin_only)

# Frontend Static Mount
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

@app.get("/")
def serve_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "DairyERP Backend Running", "docs": "/docs"}

@app.get("/login")
def serve_login():
    return FileResponse(os.path.join(frontend_dir, "login.html"))

@app.get("/driver")
def serve_driver_portal():
    driver_path = os.path.join(frontend_dir, "driver.html")
    if os.path.exists(driver_path):
        return FileResponse(driver_path)
    return {"message": "Driver portal file not found"}

@app.get("/customer")
def serve_customer_portal():
    cust_path = os.path.join(frontend_dir, "customer_portal.html")
    if os.path.exists(cust_path):
        return FileResponse(cust_path)
    return {"message": "Customer portal file not found"}

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "system": settings.PROJECT_NAME,
        "database": engine.name
    }
