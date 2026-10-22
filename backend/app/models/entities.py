from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime,
    ForeignKey, Text, Numeric
)
from sqlalchemy.orm import relationship
from backend.app.database import Base

# 1. Branch
class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True, index=True)
    branch_code = Column(String(20), unique=True, nullable=False)
    branch_name = Column(String(100), nullable=False)
    branch_type = Column(String(50), default="Plant")
    address = Column(Text)
    city = Column(String(50))
    state = Column(String(50))
    contact_phone = Column(String(20))
    gstin = Column(String(15))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# 2. User
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    role = Column(String(30), default="customer") # super_admin, admin, driver, customer, sales_manager, etc.
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# 3. Vehicle
class Vehicle(Base):
    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    registration_number = Column(String(30), unique=True, nullable=False)
    vehicle_type = Column(String(50), nullable=False) # Milk Van, Refrigerated Truck
    capacity_litres = Column(Float, nullable=False)
    default_driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    fuel_type = Column(String(20), default="Diesel")
    average_mileage_kmpl = Column(Float, default=8.0)
    current_odometer_km = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)

# 4. Delivery Route
class DeliveryRoute(Base):
    __tablename__ = "delivery_routes"
    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    route_code = Column(String(30), unique=True, nullable=False)
    route_name = Column(String(100), nullable=False)
    start_location = Column(String(100), default="Dairy Plant")
    end_location = Column(String(100), default="Dairy Plant")
    approx_distance_km = Column(Float, default=0.0)
    default_vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    default_driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    fixed_daily_cost = Column(Float, default=0.0)  # transport cost for running this route one day (vehicle, driver, fuel)
    is_active = Column(Boolean, default=True)

# 5. Customer
class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    customer_code = Column(String(30), unique=True, nullable=False, index=True)
    business_name = Column(String(150), nullable=False)
    contact_person = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(100), nullable=True)
    customer_type = Column(String(30), default="hotel") # hotel, restaurant, mess, cafe, retailer, distributor
    gstin = Column(String(15), nullable=True)
    pan = Column(String(10), nullable=True)
    billing_address = Column(Text, nullable=False)
    delivery_address = Column(Text, nullable=False)
    latitude = Column(Float, default=18.5204)
    longitude = Column(Float, default=73.8567)
    assigned_route_id = Column(Integer, ForeignKey("delivery_routes.id"), nullable=True)
    assigned_driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    route_stop_sequence = Column(Integer, default=1)
    credit_limit = Column(Float, default=50000.0)
    credit_days = Column(Integer, default=7)
    current_outstanding = Column(Float, default=0.0)
    transport_allocation_method = Column(String(30), default="equal_per_litre") # equal_per_litre, distance_based, customer_specific
    negotiated_transport_rate_per_litre = Column(Float, default=0.0)
    distance_from_plant_km = Column(Float, default=5.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    orders = relationship("Order", back_populates="customer")
    pricing = relationship("CustomerPricing", back_populates="customer")

# 6. Product
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, nullable=False)
    product_name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False) # Milk, Curd, Paneer, Ghee, Butter
    unit = Column(String(20), default="L")
    pack_size = Column(String(50), default="1 Litre Pouch")
    mrp = Column(Float, nullable=False)
    standard_b2b_price = Column(Float, nullable=False)
    cost_price = Column(Float, default=42.0)
    gst_rate = Column(Float, default=0.0)
    hsn_code = Column(String(20), default="0401")
    min_order_quantity = Column(Float, default=1.0)
    current_stock = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)  # order in the customer's order form
    description = Column(String(200), nullable=True)
    # Pack sizes of one product: same group_name, own variant_name ("500 ML", "1 L"). product_name is
    # then "<group> - <variant>", so bills and reports show the full name.
    group_name = Column(String(100), nullable=True)
    variant_name = Column(String(50), nullable=True)
    # Litres of milk in one unit (0.5 for a 500 ML pouch). Empty: 1 for a product sold per litre, else 0.
    litres_per_unit = Column(Float, nullable=True)

# 7. Customer Specific Pricing
class CustomerPricing(Base):
    __tablename__ = "customer_pricing"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    custom_price = Column(Float, nullable=False)
    effective_from = Column(Date, default=date.today)
    effective_to = Column(Date, nullable=True)

    customer = relationship("Customer", back_populates="pricing")
    product = relationship("Product")

# 9. Order & Order Items
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(40), unique=True, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    order_date = Column(Date, default=date.today)
    delivery_date = Column(Date, default=date.today)
    status = Column(String(30), default="created") # created, confirmed, packed, assigned, dispatched, out_for_delivery, delivered, invoiced, paid, cancelled
    is_standing_order = Column(Boolean, default=False)
    subtotal = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    transport_charge = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0)
    total_litres = Column(Float, default=0.0)
    payment_status = Column(String(20), default="pending")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    ordered_quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=False)
    gst_rate = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    product_cost_price = Column(Float, default=0.0)
    # What the delivery boy handed over for this product (None = not delivered yet)
    delivered_quantity = Column(Float, nullable=True)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")

# Transport: one total cost per day for all deliveries (vehicles, drivers, fuel together).
# Cost per litre for a day = this amount / milk delivered to all customers that day.
class TransportDayCost(Base):
    __tablename__ = "transport_day_costs"
    id = Column(Integer, primary_key=True, index=True)
    cost_date = Column(Date, unique=True, index=True, nullable=False)
    amount = Column(Float, nullable=False, default=0.0)
    note = Column(String(200), nullable=True)
    updated_by = Column(String(50), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 10. Delivery Trips & Dispatch
class DeliveryTrip(Base):
    __tablename__ = "delivery_trips"
    id = Column(Integer, primary_key=True, index=True)
    trip_number = Column(String(40), unique=True, nullable=False)
    route_id = Column(Integer, ForeignKey("delivery_routes.id"), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    trip_date = Column(Date, default=date.today)
    departure_time = Column(DateTime, nullable=True)
    return_time = Column(DateTime, nullable=True)
    opening_km = Column(Float, nullable=False)
    closing_km = Column(Float, default=0.0)
    total_distance_km = Column(Float, default=0.0)
    diesel_litres = Column(Float, default=0.0)
    diesel_price_per_litre = Column(Float, default=95.0)
    diesel_cost = Column(Float, default=0.0)
    driver_cost = Column(Float, default=800.0)
    toll_charges = Column(Float, default=0.0)
    other_expenses = Column(Float, default=0.0)
    total_transport_cost = Column(Float, default=0.0)
    total_milk_litres_loaded = Column(Float, default=0.0)
    total_milk_litres_delivered = Column(Float, default=0.0)
    transport_cost_per_litre = Column(Float, default=0.0)
    status = Column(String(30), default="scheduled") # scheduled, in_transit, completed

    route = relationship("DeliveryRoute")
    vehicle = relationship("Vehicle")
    driver = relationship("User")
    deliveries = relationship("Delivery", back_populates="trip")

# 11. Deliveries (Stop-level execution)
class Delivery(Base):
    __tablename__ = "deliveries"
    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("delivery_trips.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    delivery_sequence = Column(Integer, default=1)
    status = Column(String(30), default="pending") # pending, in_transit, arrived, delivered, partially_delivered, failed
    arrival_time = Column(DateTime, nullable=True)
    departure_time = Column(DateTime, nullable=True)
    total_ordered_litres = Column(Float, nullable=False)
    total_delivered_litres = Column(Float, default=0.0)
    total_shortage_litres = Column(Float, default=0.0)
    shortage_reason = Column(String(50), default="none") # none, leakage, damage, customer_rejection, stock_shortage, delivery_issue
    shortage_notes = Column(Text, nullable=True)
    customer_signature_url = Column(Text, nullable=True)
    delivered_to_person = Column(String(100), nullable=True)
    collected_amount = Column(Float, default=0.0)
    collected_payment_method = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    trip = relationship("DeliveryTrip", back_populates="deliveries")
    order = relationship("Order")
    customer = relationship("Customer")

# 12. Transport Cost Allocation
class TransportCostAllocation(Base):
    __tablename__ = "transport_cost_allocations"
    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("delivery_trips.id"), nullable=False)
    delivery_id = Column(Integer, ForeignKey("deliveries.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    delivered_litres = Column(Float, nullable=False)
    allocation_method = Column(String(30), default="equal_per_litre") # equal_per_litre, distance_based, customer_specific
    cost_per_litre_applied = Column(Float, nullable=False)
    distance_km = Column(Float, default=0.0)
    allocated_transport_cost = Column(Float, nullable=False)

# 13. Procurement & Quality
class ProcurementVendor(Base):
    __tablename__ = "procurement_vendors"
    id = Column(Integer, primary_key=True, index=True)
    vendor_code = Column(String(30), unique=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    village = Column(String(100))
    phone = Column(String(20), nullable=False)
    milk_type = Column(String(20), default="cow")
    is_active = Column(Boolean, default=True)

class MilkProcurement(Base):
    __tablename__ = "milk_procurement"
    id = Column(Integer, primary_key=True, index=True)
    procurement_batch_no = Column(String(40), unique=True, nullable=False)
    vendor_id = Column(Integer, ForeignKey("procurement_vendors.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    collection_date = Column(Date, default=date.today)
    collection_shift = Column(String(10), default="Morning")
    milk_type = Column(String(20), default="cow")
    quantity_litres = Column(Float, nullable=False)
    fat_pct = Column(Float, nullable=False)
    snf_pct = Column(Float, nullable=False)
    clr_reading = Column(Float, default=28.0)
    temperature_c = Column(Float, default=4.0)
    rate_per_litre = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    quality_status = Column(String(30), default="accepted") # accepted, rejected, conditionally_accepted

    vendor = relationship("ProcurementVendor")

# 14. Production Batches
class ProductionBatch(Base):
    __tablename__ = "production_batches"
    id = Column(Integer, primary_key=True, index=True)
    batch_number = Column(String(40), unique=True, nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    production_date = Column(Date, default=date.today)
    raw_milk_input_litres = Column(Float, nullable=False)
    process_type = Column(String(50), nullable=False)
    output_product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    output_quantity = Column(Float, nullable=False)
    output_unit = Column(String(20), default="L")
    wastage_litres = Column(Float, default=0.0)
    expiry_date = Column(Date, nullable=False)
    operator_name = Column(String(100), default="Plant Operator")
    status = Column(String(30), default="completed")

    product = relationship("Product")

# 15. Invoices & Payments
class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(40), unique=True, nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    invoice_date = Column(Date, default=date.today)
    due_date = Column(Date, nullable=False)
    total_litres = Column(Float, default=0.0)
    subtotal = Column(Float, nullable=False)
    cgst_amount = Column(Float, default=0.0)
    sgst_amount = Column(Float, default=0.0)
    igst_amount = Column(Float, default=0.0)
    total_tax = Column(Float, default=0.0)
    transport_charge = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    paid_amount = Column(Float, default=0.0)
    balance_due = Column(Float, default=0.0)
    payment_status = Column(String(20), default="pending")
    # Period bills (daily / fortnightly / monthly / custom); order-level invoices leave these empty
    bill_type = Column(String(20), nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    previous_balance = Column(Float, default=0.0)  # dues (+) or advance (-) before this bill
    advance_applied = Column(Float, default=0.0)  # customer's advance used to pay this bill when it was made
    bill_lines = Column(Text, nullable=True)  # JSON snapshot of day-wise qty / rate / amount
    # "order": period and lines are order days (delivery - 1). Empty: older bills, in delivery days.
    day_basis = Column(String(10), nullable=True)

    customer = relationship("Customer")
    order = relationship("Order")

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    payment_number = Column(String(40), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    payment_date = Column(Date, default=date.today)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(30), default="upi")
    reference_number = Column(String(100), nullable=True)
    remarks = Column(Text, nullable=True)

# 16. Customer Ledger
class CustomerLedger(Base):
    __tablename__ = "customer_ledger"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    transaction_date = Column(Date, default=date.today)
    transaction_type = Column(String(40), nullable=False) # opening_balance, sales_invoice, payment, sales_return, credit_note
    reference_number = Column(String(50), nullable=True)
    debit_amount = Column(Float, default=0.0)
    credit_amount = Column(Float, default=0.0)
    running_balance = Column(Float, nullable=False)
    narration = Column(Text, nullable=True)

    customer = relationship("Customer")

# 17. Complaints
class CustomerComplaint(Base):
    __tablename__ = "customer_complaints"
    id = Column(Integer, primary_key=True, index=True)
    ticket_number = Column(String(40), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    order_id = Column(Integer, nullable=True)
    category = Column(String(50), nullable=False) # product_quality, short_quantity, late_delivery, wrong_product, billing_issue
    subject = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(30), default="open") # open, in_progress, resolved
    resolution_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer")

# 18. Audit Log
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(100), nullable=True)
    action = Column(String(50), nullable=False)
    entity_name = Column(String(50), nullable=False)
    entity_id = Column(String(50), nullable=True)
    old_values = Column(Text, nullable=True)
    new_values = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# 19. Business profile (printed on bills)
class BusinessProfile(Base):
    __tablename__ = "business_profile"
    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String(150), nullable=False)
    contact_numbers = Column(String(100), nullable=True)
    contact_email = Column(String(120), nullable=True)  # shown on the privacy policy / terms pages
    address = Column(Text, nullable=True)
    gstin = Column(String(15), nullable=True)
    bank_account_name = Column(String(150), nullable=True)
    bank_name = Column(String(100), nullable=True)
    bank_account_number = Column(String(40), nullable=True)
    bank_ifsc = Column(String(20), nullable=True)
    bank_branch = Column(String(100), nullable=True)
    upi_number = Column(String(40), nullable=True)
    # Customers can place / change an order for a day until this time on the day before ("HH:MM", 24h)
    order_cutoff_time = Column(String(5), default="21:00")
    # Each delivery day's confirmed orders go to the delivery boys automatically at this time ("HH:MM", 24h)
    dispatch_time = Column(String(5), default="04:00")
    updated_at = Column(DateTime, default=datetime.utcnow)


# 20. Customer claims: milk spoiled / short / not delivered, verified by the admin before billing
class DeliveryClaim(Base):
    __tablename__ = "delivery_claims"
    id = Column(Integer, primary_key=True, index=True)
    claim_number = Column(String(40), unique=True, nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    delivery_id = Column(Integer, ForeignKey("deliveries.id"), nullable=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)  # which product the problem is with
    issue_date = Column(Date, nullable=False)  # delivery date the problem relates to
    reason = Column(String(30), nullable=False)  # spoiled, short_delivered, not_delivered, leakage, other
    claimed_qty = Column(Float, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), default="pending")  # pending, approved, rejected
    approved_qty = Column(Float, default=0.0)
    rate = Column(Float, default=0.0)  # customer's rate on that day, fixed at approval
    credit_amount = Column(Float, default=0.0)
    admin_note = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    # How the approved amount reached the customer: deducted in a bill, or a ledger credit note
    # bill        = deducted when the period's bill was generated
    # credit_note = approved after the bill: that bill was reduced (ledger credit note)
    # refund      = paid back to the customer separately; bills are not changed
    settlement = Column(String(20), nullable=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    refund_method = Column(String(30), nullable=True)  # cash | upi | bank_transfer
    refund_reference = Column(String(100), nullable=True)
    refunded_on = Column(Date, nullable=True)
    # Credit on an already-paid bill that went to pay other bills: JSON {"advance": x, "<bill id>": amount}
    excess_moves = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer")
    order = relationship("Order")
    delivery = relationship("Delivery")


# 21. Uploaded photos (claim evidence, proof of delivery)
class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True, index=True)
    owner_type = Column(String(20), nullable=False, index=True)  # claim | delivery
    owner_id = Column(Integer, nullable=False, index=True)
    file_path = Column(String(255), nullable=False)  # relative to the uploads folder
    content_type = Column(String(50), default="image/jpeg")
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# 22. In-app notifications (bell icon in the app)
class AppNotification(Base):
    __tablename__ = "app_notifications"
    id = Column(Integer, primary_key=True, index=True)
    audience = Column(String(20), nullable=False, index=True)  # customer | admin
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)  # set for customer notices
    kind = Column(String(40), nullable=False)  # delivered, bill_created, claim_approved, ...
    title = Column(String(120), nullable=False)
    body = Column(Text, nullable=False)
    link = Column(String(30), nullable=True)  # app screen to open: orders, bills, claims, statement, delivery
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    read_at = Column(DateTime, nullable=True)


# 23. One row per delivery day: admin's hold on the automatic dispatch, and what the dispatcher did
class DispatchDay(Base):
    __tablename__ = "dispatch_days"
    id = Column(Integer, primary_key=True, index=True)
    day = Column(Date, unique=True, nullable=False, index=True)
    on_hold = Column(Boolean, default=False)
    hold_note = Column(Text, nullable=True)  # why the milk cannot go out; sent to the customers
    hold_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    hold_set_at = Column(DateTime, nullable=True)
    hold_notified_ids = Column(Text, nullable=True)  # JSON list of order ids already told about the hold
    skipped_notified_ids = Column(Text, nullable=True)  # JSON list of order ids the admin was told could not go
    auto_dispatched_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


# 24. Problems a delivery boy reports on the way (vehicle breakdown, delay...); customers waiting are told
class DeliveryIssue(Base):
    __tablename__ = "delivery_issues"
    id = Column(Integer, primary_key=True, index=True)
    day = Column(Date, nullable=False, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reason = Column(String(30), nullable=False)
    note = Column(Text, nullable=True)
    stops_affected = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# 25. Requests to delete a customer account (from the app or the public web page; Play Store rule)
class AccountDeletionRequest(Base):
    __tablename__ = "account_deletion_requests"
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)  # known when sent from the app
    name = Column(String(150), nullable=True)
    phone = Column(String(20), nullable=True)
    reason = Column(Text, nullable=True)
    source = Column(String(10), nullable=False)  # app | web
    status = Column(String(20), default="open")  # open | done
    created_at = Column(DateTime, default=datetime.utcnow)


# 26. Admin-edited text of the public legal pages (privacy, terms, delete_account); no row = default text
class LegalPage(Base):
    __tablename__ = "legal_pages"
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(30), unique=True, nullable=False)
    content = Column(Text, nullable=True)  # None = use the built-in default text
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)


# 27. Email (SMTP) settings, one row. The password is stored encrypted with the server's secret key.
class EmailSettings(Base):
    __tablename__ = "email_settings"
    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, default=False)
    smtp_host = Column(String(120), nullable=True)
    smtp_port = Column(Integer, default=465)
    smtp_security = Column(String(10), default="ssl")  # ssl (port 465) | starttls (port 587) | none
    smtp_username = Column(String(150), nullable=True)
    smtp_password_enc = Column(Text, nullable=True)
    from_email = Column(String(150), nullable=True)
    from_name = Column(String(150), nullable=True)
    reply_to = Column(String(150), nullable=True)
    site_url = Column(String(200), nullable=True)  # public address of the portal, used for links in emails
    admin_email = Column(String(150), nullable=True)  # where the dairy's own alerts go
    send_bills = Column(Boolean, default=True)
    send_payments = Column(Boolean, default=True)
    send_claims = Column(Boolean, default=True)
    send_orders = Column(Boolean, default=True)  # order confirmed, or placed / changed / cancelled by the dairy
    send_delays = Column(Boolean, default=True)  # dispatch on hold, delivery delayed on the way
    send_daily_delivery = Column(Boolean, default=True)  # delivery details: delivered / short / not delivered
    send_admin_alerts = Column(Boolean, default=True)
    updated_at = Column(DateTime, nullable=True)


# 28. Emails waiting to be sent / sent / failed (sent by a background worker, retried up to 3 times)
class EmailOutbox(Base):
    __tablename__ = "email_outbox"
    id = Column(Integer, primary_key=True, index=True)
    to_email = Column(String(150), nullable=False)
    customer_id = Column(Integer, nullable=True)  # no foreign key: deleting data never fails because of old emails
    kind = Column(String(40), nullable=False)
    subject = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    link = Column(String(30), nullable=True)
    invoice_id = Column(Integer, nullable=True)  # bill PDF attached when set (skipped if the bill was deleted)
    status = Column(String(10), default="pending", index=True)  # pending | sent | failed
    attempts = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
