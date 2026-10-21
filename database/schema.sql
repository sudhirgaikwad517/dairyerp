-- =====================================================================
-- COMPLETE DAIRY ERP DATABASE SCHEMA (PostgreSQL 14+)
-- Comprehensive B2B Dairy Distribution, Procurement, Production,
-- Route & Transport Costing (per Litre), Ledgers, and Profitability
-- =====================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =====================================================================
-- 1. ENUMS & DOMAINS
-- =====================================================================
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM (
        'super_admin', 'admin', 'sales_manager', 'accounts',
        'production_manager', 'warehouse_manager', 'delivery_manager',
        'driver', 'customer'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE customer_type AS ENUM (
        'hotel', 'restaurant', 'mess', 'cafe',
        'retailer', 'distributor', 'bakery', 'institution'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE order_status AS ENUM (
        'created', 'confirmed', 'processing', 'packed',
        'assigned', 'dispatched', 'out_for_delivery',
        'delivered', 'invoiced', 'paid', 'cancelled'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE delivery_status AS ENUM (
        'pending', 'in_transit', 'arrived', 'delivered',
        'partially_delivered', 'failed', 'returned'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE shortage_reason AS ENUM (
        'none', 'leakage', 'damage', 'customer_rejection',
        'stock_shortage', 'delivery_issue', 'other'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE transport_allocation_method AS ENUM (
        'equal_per_litre', 'distance_based', 'customer_specific'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE payment_method AS ENUM (
        'cash', 'upi', 'bank_transfer', 'cheque', 'credit'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE payment_status AS ENUM (
        'pending', 'partial', 'paid', 'overdue'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE milk_type AS ENUM (
        'cow', 'buffalo', 'mixed', 'standardized'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE quality_status AS ENUM (
        'accepted', 'rejected', 'conditionally_accepted'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE complaint_status AS ENUM (
        'open', 'in_progress', 'resolved', 'closed'
    );
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- =====================================================================
-- 2. CORE MASTER TABLES: BRANCHES & USERS
-- =====================================================================
CREATE TABLE IF NOT EXISTS branches (
    id SERIAL PRIMARY KEY,
    branch_code VARCHAR(20) UNIQUE NOT NULL,
    branch_name VARCHAR(100) NOT NULL,
    branch_type VARCHAR(50) DEFAULT 'Plant', -- Plant, Warehouse, Distribution Hub
    address TEXT,
    city VARCHAR(50),
    state VARCHAR(50),
    contact_phone VARCHAR(20),
    gstin VARCHAR(15),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    role user_role NOT NULL DEFAULT 'customer',
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 3. VEHICLE & FLEET MANAGEMENT
-- =====================================================================
CREATE TABLE IF NOT EXISTS vehicles (
    id SERIAL PRIMARY KEY,
    branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
    registration_number VARCHAR(30) UNIQUE NOT NULL, -- e.g. MH12AB1234
    vehicle_type VARCHAR(50) NOT NULL, -- Insulated Milk Van, Refrigerated Truck, Auto
    capacity_litres NUMERIC(10,2) NOT NULL,
    default_driver_id INT REFERENCES users(id) ON DELETE SET NULL,
    fuel_type VARCHAR(20) DEFAULT 'Diesel', -- Diesel, CNG, Electric
    average_mileage_kmpl NUMERIC(6,2) DEFAULT 8.0,
    insurance_expiry DATE,
    puc_expiry DATE,
    fitness_expiry DATE,
    current_odometer_km NUMERIC(10,2) DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 4. DELIVERY ROUTES & SCHEDULING
-- =====================================================================
CREATE TABLE IF NOT EXISTS delivery_routes (
    id SERIAL PRIMARY KEY,
    branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
    route_code VARCHAR(30) UNIQUE NOT NULL,
    route_name VARCHAR(100) NOT NULL,
    start_location VARCHAR(100) DEFAULT 'Dairy Processing Plant',
    end_location VARCHAR(100) DEFAULT 'Dairy Processing Plant',
    approx_distance_km NUMERIC(8,2) DEFAULT 0,
    estimated_duration_mins INT DEFAULT 180,
    default_vehicle_id INT REFERENCES vehicles(id) ON DELETE SET NULL,
    default_driver_id INT REFERENCES users(id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 5. CUSTOMER / B2B CLIENT MANAGEMENT
-- =====================================================================
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
    customer_code VARCHAR(30) UNIQUE NOT NULL, -- e.g. CUST-001
    business_name VARCHAR(150) NOT NULL,
    contact_person VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(100),
    customer_type customer_type NOT NULL DEFAULT 'hotel',
    gstin VARCHAR(15),
    pan VARCHAR(10),
    billing_address TEXT NOT NULL,
    delivery_address TEXT NOT NULL,
    latitude NUMERIC(10,7),
    longitude NUMERIC(10,7),
    assigned_route_id INT REFERENCES delivery_routes(id) ON DELETE SET NULL,
    assigned_driver_id INT REFERENCES users(id) ON DELETE SET NULL,
    route_stop_sequence INT DEFAULT 1,
    credit_limit NUMERIC(12,2) DEFAULT 50000.00,
    credit_days INT DEFAULT 7,
    current_outstanding NUMERIC(12,2) DEFAULT 0.00,
    transport_allocation_method transport_allocation_method DEFAULT 'equal_per_litre',
    negotiated_transport_rate_per_litre NUMERIC(8,2) DEFAULT 0.00,
    distance_from_plant_km NUMERIC(6,2) DEFAULT 5.0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_delivery_addresses (
    id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    location_title VARCHAR(100) NOT NULL, -- e.g. Main Kitchen, Branch 2
    address TEXT NOT NULL,
    latitude NUMERIC(10,7),
    longitude NUMERIC(10,7),
    contact_person VARCHAR(100),
    contact_phone VARCHAR(20),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 6. PRODUCT CATALOGUE & B2B/CUSTOMER-SPECIFIC PRICING
-- =====================================================================
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(50) UNIQUE NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL, -- Milk, Curd, Paneer, Ghee, Butter, Buttermilk, etc.
    unit VARCHAR(20) NOT NULL DEFAULT 'L', -- L, KG, Pcs, Pkt
    pack_size VARCHAR(50) DEFAULT '1 Litre Pouch',
    mrp NUMERIC(10,2) NOT NULL,
    standard_b2b_price NUMERIC(10,2) NOT NULL,
    cost_price NUMERIC(10,2) NOT NULL, -- Baseline production/procurement cost
    gst_rate NUMERIC(5,2) DEFAULT 0.00, -- 0% on fresh milk, 5% or 12% on dairy products
    hsn_code VARCHAR(20) DEFAULT '0401',
    min_order_quantity NUMERIC(10,2) DEFAULT 1.0,
    current_stock NUMERIC(10,2) DEFAULT 0.0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Customer-Specific Pricing (ABC Hotel @ ₹52/L vs Standard @ ₹55/L)
CREATE TABLE IF NOT EXISTS customer_pricing (
    id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    custom_price NUMERIC(10,2) NOT NULL,
    effective_from DATE DEFAULT CURRENT_DATE,
    effective_to DATE,
    discount_pct NUMERIC(5,2) DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customer_product_pricing UNIQUE (customer_id, product_id, effective_from)
);

-- =====================================================================
-- 7. STANDING / RECURRING DAILY ORDERS
-- =====================================================================
CREATE TABLE IF NOT EXISTS standing_orders (
    id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    day_of_week INT NOT NULL, -- 0=Sunday, 1=Monday, ..., 6=Saturday
    quantity NUMERIC(10,2) NOT NULL CHECK (quantity >= 0),
    is_active BOOLEAN DEFAULT TRUE,
    notes VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_customer_product_day UNIQUE (customer_id, product_id, day_of_week)
);

-- =====================================================================
-- 8. ORDER MANAGEMENT
-- =====================================================================
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_number VARCHAR(40) UNIQUE NOT NULL, -- e.g. ORD-20261015-001
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
    order_date DATE NOT NULL DEFAULT CURRENT_DATE,
    delivery_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status order_status NOT NULL DEFAULT 'created',
    is_standing_order BOOLEAN DEFAULT FALSE,
    subtotal NUMERIC(12,2) DEFAULT 0.00,
    tax_amount NUMERIC(12,2) DEFAULT 0.00,
    transport_charge NUMERIC(10,2) DEFAULT 0.00,
    total_amount NUMERIC(12,2) DEFAULT 0.00,
    total_litres NUMERIC(10,2) DEFAULT 0.00,
    payment_status payment_status DEFAULT 'pending',
    notes TEXT,
    created_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    ordered_quantity NUMERIC(10,2) NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL,
    gst_rate NUMERIC(5,2) DEFAULT 0.00,
    tax_amount NUMERIC(10,2) DEFAULT 0.00,
    total_amount NUMERIC(12,2) NOT NULL,
    product_cost_price NUMERIC(10,2) DEFAULT 0.00, -- Snapshot for profitability calculation
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 9. DELIVERY DISPATCH TRIPS & ADVANCED TRANSPORT COSTING
-- =====================================================================
CREATE TABLE IF NOT EXISTS delivery_trips (
    id SERIAL PRIMARY KEY,
    trip_number VARCHAR(40) UNIQUE NOT NULL, -- e.g. TRIP-20261015-01
    route_id INT NOT NULL REFERENCES delivery_routes(id) ON DELETE RESTRICT,
    vehicle_id INT NOT NULL REFERENCES vehicles(id) ON DELETE RESTRICT,
    driver_id INT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    trip_date DATE NOT NULL DEFAULT CURRENT_DATE,
    departure_time TIMESTAMP WITH TIME ZONE,
    return_time TIMESTAMP WITH TIME ZONE,
    opening_km NUMERIC(10,2) NOT NULL,
    closing_km NUMERIC(10,2),
    total_distance_km NUMERIC(8,2) GENERATED ALWAYS AS (CASE WHEN closing_km >= opening_km THEN closing_km - opening_km ELSE 0 END) STORED,
    diesel_litres NUMERIC(8,2) DEFAULT 0.00,
    diesel_price_per_litre NUMERIC(8,2) DEFAULT 95.00,
    diesel_cost NUMERIC(10,2) GENERATED ALWAYS AS (diesel_litres * diesel_price_per_litre) STORED,
    driver_cost NUMERIC(10,2) DEFAULT 800.00,
    toll_charges NUMERIC(10,2) DEFAULT 0.00,
    other_expenses NUMERIC(10,2) DEFAULT 0.00,
    total_transport_cost NUMERIC(12,2) DEFAULT 0.00,
    total_milk_litres_loaded NUMERIC(10,2) DEFAULT 0.00,
    total_milk_litres_delivered NUMERIC(10,2) DEFAULT 0.00,
    transport_cost_per_litre NUMERIC(8,3) DEFAULT 0.000, -- Total transport cost / Total litres delivered
    status VARCHAR(30) DEFAULT 'scheduled', -- scheduled, in_transit, completed, cancelled
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Individual Customer Stops on a Delivery Trip
CREATE TABLE IF NOT EXISTS deliveries (
    id SERIAL PRIMARY KEY,
    trip_id INT NOT NULL REFERENCES delivery_trips(id) ON DELETE CASCADE,
    order_id INT NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    delivery_sequence INT NOT NULL DEFAULT 1,
    status delivery_status NOT NULL DEFAULT 'pending',
    arrival_time TIMESTAMP WITH TIME ZONE,
    departure_time TIMESTAMP WITH TIME ZONE,
    total_ordered_litres NUMERIC(10,2) NOT NULL,
    total_delivered_litres NUMERIC(10,2) DEFAULT 0.00,
    total_shortage_litres NUMERIC(10,2) GENERATED ALWAYS AS (total_ordered_litres - total_delivered_litres) STORED,
    shortage_reason shortage_reason DEFAULT 'none',
    shortage_notes TEXT,
    customer_signature_url TEXT,
    proof_image_url TEXT,
    delivered_to_person VARCHAR(100),
    collected_amount NUMERIC(10,2) DEFAULT 0.00,
    collected_payment_method payment_method,
    payment_reference VARCHAR(100),
    latitude NUMERIC(10,7),
    longitude NUMERIC(10,7),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Granular Delivery Item Verification (Ordered vs Delivered vs Shortage per SKU)
CREATE TABLE IF NOT EXISTS delivery_items (
    id SERIAL PRIMARY KEY,
    delivery_id INT NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
    order_item_id INT NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    ordered_qty NUMERIC(10,2) NOT NULL,
    delivered_qty NUMERIC(10,2) NOT NULL,
    shortage_qty NUMERIC(10,2) GENERATED ALWAYS AS (ordered_qty - delivered_qty) STORED,
    shortage_reason shortage_reason DEFAULT 'none',
    remarks VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Transport Cost Allocation per Customer / Order
CREATE TABLE IF NOT EXISTS transport_cost_allocations (
    id SERIAL PRIMARY KEY,
    trip_id INT NOT NULL REFERENCES delivery_trips(id) ON DELETE CASCADE,
    delivery_id INT NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    delivered_litres NUMERIC(10,2) NOT NULL,
    allocation_method transport_allocation_method NOT NULL DEFAULT 'equal_per_litre',
    cost_per_litre_applied NUMERIC(8,3) NOT NULL,
    distance_km NUMERIC(6,2) DEFAULT 0.0,
    allocated_transport_cost NUMERIC(10,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 10. FUEL & VEHICLE EXPENSES LOGGING
-- =====================================================================
CREATE TABLE IF NOT EXISTS vehicle_fuel_logs (
    id SERIAL PRIMARY KEY,
    vehicle_id INT NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
    trip_id INT REFERENCES delivery_trips(id) ON DELETE SET NULL,
    driver_id INT REFERENCES users(id) ON DELETE SET NULL,
    fuel_date DATE NOT NULL DEFAULT CURRENT_DATE,
    odometer_reading NUMERIC(10,2) NOT NULL,
    litres_filled NUMERIC(8,2) NOT NULL,
    rate_per_litre NUMERIC(8,2) NOT NULL,
    total_cost NUMERIC(10,2) NOT NULL,
    gas_station_name VARCHAR(150),
    receipt_number VARCHAR(50),
    receipt_photo_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 11. MILK PROCUREMENT & QUALITY TESTING (FARMER / VENDOR LEVEL)
-- =====================================================================
CREATE TABLE IF NOT EXISTS procurement_vendors (
    id SERIAL PRIMARY KEY,
    vendor_code VARCHAR(30) UNIQUE NOT NULL, -- e.g. VEND-001
    full_name VARCHAR(120) NOT NULL,
    village VARCHAR(100),
    phone VARCHAR(20) NOT NULL,
    bank_account_number VARCHAR(30),
    ifsc_code VARCHAR(20),
    milk_type milk_type DEFAULT 'cow',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS milk_procurement (
    id SERIAL PRIMARY KEY,
    procurement_batch_no VARCHAR(40) UNIQUE NOT NULL, -- e.g. PROC-20261015-001
    vendor_id INT NOT NULL REFERENCES procurement_vendors(id) ON DELETE RESTRICT,
    branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
    collection_date DATE NOT NULL DEFAULT CURRENT_DATE,
    collection_shift VARCHAR(10) NOT NULL DEFAULT 'Morning', -- Morning / Evening
    milk_type milk_type NOT NULL DEFAULT 'cow',
    quantity_litres NUMERIC(10,2) NOT NULL CHECK (quantity_litres > 0),
    fat_pct NUMERIC(4,2) NOT NULL, -- e.g. 4.5%
    snf_pct NUMERIC(4,2) NOT NULL, -- e.g. 8.5%
    clr_reading NUMERIC(5,2),      -- Corrected Lactometer Reading
    temperature_c NUMERIC(4,1) DEFAULT 4.0,
    rate_per_litre NUMERIC(8,2) NOT NULL,
    total_amount NUMERIC(12,2) GENERATED ALWAYS AS (quantity_litres * rate_per_litre) STORED,
    quality_status quality_status DEFAULT 'accepted',
    rejected_litres NUMERIC(10,2) DEFAULT 0.00,
    rejection_reason VARCHAR(255),
    received_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS milk_quality_tests (
    id SERIAL PRIMARY KEY,
    procurement_id INT REFERENCES milk_procurement(id) ON DELETE CASCADE,
    sample_code VARCHAR(40) NOT NULL,
    tested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    fat_pct NUMERIC(4,2) NOT NULL,
    snf_pct NUMERIC(4,2) NOT NULL,
    acidity_pct NUMERIC(4,2) DEFAULT 0.14, -- Normal fresh milk ~0.13 - 0.16%
    clot_on_boiling_cob BOOLEAN DEFAULT FALSE, -- Must be false
    water_adulteration_pct NUMERIC(4,2) DEFAULT 0.00,
    temperature_c NUMERIC(4,1) DEFAULT 4.0,
    result quality_status NOT NULL DEFAULT 'accepted',
    tested_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    remarks TEXT
);

-- =====================================================================
-- 12. PRODUCTION MANAGEMENT & BATCH CONVERSION
-- =====================================================================
CREATE TABLE IF NOT EXISTS production_batches (
    id SERIAL PRIMARY KEY,
    batch_number VARCHAR(40) UNIQUE NOT NULL, -- e.g. PROD-20261015-B1
    branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
    production_date DATE NOT NULL DEFAULT CURRENT_DATE,
    raw_milk_input_litres NUMERIC(10,2) NOT NULL,
    process_type VARCHAR(50) NOT NULL, -- Pasteurization, Curd Making, Paneer Production, Ghee, Butter
    output_product_id INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    output_quantity NUMERIC(10,2) NOT NULL,
    output_unit VARCHAR(20) NOT NULL DEFAULT 'L',
    wastage_litres NUMERIC(10,2) DEFAULT 0.00,
    yield_percentage NUMERIC(5,2) GENERATED ALWAYS AS (
        CASE WHEN raw_milk_input_litres > 0 THEN ((output_quantity / raw_milk_input_litres) * 100.0) ELSE 0 END
    ) STORED,
    manufacturing_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expiry_date DATE NOT NULL,
    operator_name VARCHAR(100),
    status VARCHAR(30) DEFAULT 'completed', -- in_process, completed, quality_hold
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Product Finished Batches (FEFO: First Expiry First Out)
CREATE TABLE IF NOT EXISTS product_batches (
    id SERIAL PRIMARY KEY,
    batch_number VARCHAR(50) UNIQUE NOT NULL,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    production_batch_id INT REFERENCES production_batches(id) ON DELETE SET NULL,
    manufacturing_date DATE NOT NULL DEFAULT CURRENT_DATE,
    expiry_date DATE NOT NULL,
    initial_quantity NUMERIC(10,2) NOT NULL,
    remaining_quantity NUMERIC(10,2) NOT NULL,
    is_expired BOOLEAN GENERATED ALWAYS AS (CURRENT_DATE > expiry_date) STORED,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Inventory Movement Ledger
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id SERIAL PRIMARY KEY,
    branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    batch_id INT REFERENCES product_batches(id) ON DELETE SET NULL,
    transaction_type VARCHAR(40) NOT NULL, -- procurement_in, production_in, dispatch_out, return_in, wastage_out
    quantity NUMERIC(10,2) NOT NULL,
    reference_type VARCHAR(50), -- order, delivery, production_batch, return
    reference_id INT,
    balance_after NUMERIC(10,2) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 13. BILLING, GST INVOICES, CREDIT/DEBIT NOTES
-- =====================================================================
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(40) UNIQUE NOT NULL, -- e.g. INV-20261015-001
    order_id INT REFERENCES orders(id) ON DELETE SET NULL,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    branch_id INT REFERENCES branches(id) ON DELETE SET NULL,
    invoice_date DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date DATE NOT NULL,
    total_litres NUMERIC(10,2) DEFAULT 0.00,
    subtotal NUMERIC(12,2) NOT NULL,
    cgst_amount NUMERIC(10,2) DEFAULT 0.00,
    sgst_amount NUMERIC(10,2) DEFAULT 0.00,
    igst_amount NUMERIC(10,2) DEFAULT 0.00,
    total_tax NUMERIC(10,2) GENERATED ALWAYS AS (cgst_amount + sgst_amount + igst_amount) STORED,
    transport_charge NUMERIC(10,2) DEFAULT 0.00,
    total_amount NUMERIC(12,2) NOT NULL,
    paid_amount NUMERIC(12,2) DEFAULT 0.00,
    balance_due NUMERIC(12,2) GENERATED ALWAYS AS (total_amount - paid_amount) STORED,
    payment_status payment_status DEFAULT 'pending',
    pdf_path VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    payment_number VARCHAR(40) UNIQUE NOT NULL, -- e.g. PAY-20261015-001
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    invoice_id INT REFERENCES invoices(id) ON DELETE SET NULL,
    delivery_id INT REFERENCES deliveries(id) ON DELETE SET NULL,
    payment_date DATE NOT NULL DEFAULT CURRENT_DATE,
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0),
    payment_method payment_method NOT NULL DEFAULT 'upi',
    reference_number VARCHAR(100), -- UPI txn ID, Cheque No, Bank Ref
    received_by_driver_id INT REFERENCES users(id) ON DELETE SET NULL,
    remarks TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Customer Ledger (Account Statement)
CREATE TABLE IF NOT EXISTS customer_ledger (
    id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
    transaction_type VARCHAR(40) NOT NULL, -- opening_balance, sales_invoice, payment, sales_return, credit_note, debit_note
    reference_id INT, -- invoice_id or payment_id or return_id
    reference_number VARCHAR(50),
    debit_amount NUMERIC(12,2) DEFAULT 0.00,  -- Increases customer outstanding
    credit_amount NUMERIC(12,2) DEFAULT 0.00, -- Decreases customer outstanding
    running_balance NUMERIC(12,2) NOT NULL,
    narration TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Returns and Credit Notes
CREATE TABLE IF NOT EXISTS customer_returns (
    id SERIAL PRIMARY KEY,
    return_number VARCHAR(40) UNIQUE NOT NULL,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    order_id INT REFERENCES orders(id) ON DELETE SET NULL,
    delivery_id INT REFERENCES deliveries(id) ON DELETE SET NULL,
    product_id INT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity NUMERIC(10,2) NOT NULL,
    reason shortage_reason NOT NULL,
    action_taken VARCHAR(50) DEFAULT 'credit_note', -- credit_note, replacement, discarded
    credit_note_amount NUMERIC(10,2) DEFAULT 0.00,
    status VARCHAR(30) DEFAULT 'approved',
    inspected_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 14. CUSTOMER COMPLAINTS / TICKETS
-- =====================================================================
CREATE TABLE IF NOT EXISTS customer_complaints (
    id SERIAL PRIMARY KEY,
    ticket_number VARCHAR(40) UNIQUE NOT NULL,
    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    order_id INT REFERENCES orders(id) ON DELETE SET NULL,
    category VARCHAR(50) NOT NULL, -- product_quality, short_quantity, late_delivery, wrong_product, billing_issue, other
    subject VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    status complaint_status DEFAULT 'open',
    resolution_notes TEXT,
    resolved_by_user_id INT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- =====================================================================
-- 15. AUDIT LOGS (ENTERPRISE AUDIT TRAIL)
-- =====================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) ON DELETE SET NULL,
    username VARCHAR(100),
    action VARCHAR(50) NOT NULL, -- CREATE, UPDATE, DELETE, PRICE_CHANGE, CREDIT_OVERRIDE
    entity_name VARCHAR(50) NOT NULL, -- customer_pricing, customer, order, trip
    entity_id VARCHAR(50),
    old_values JSONB,
    new_values JSONB,
    ip_address VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================================
-- 16. INDEXES FOR HIGH-PERFORMANCE QUERYING
-- =====================================================================
CREATE INDEX IF NOT EXISTS idx_customers_route ON customers(assigned_route_id);
CREATE INDEX IF NOT EXISTS idx_customers_code ON customers(customer_code);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_delivery_date ON orders(delivery_date);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_deliveries_trip ON deliveries(trip_id);
CREATE INDEX IF NOT EXISTS idx_deliveries_customer ON deliveries(customer_id);
CREATE INDEX IF NOT EXISTS idx_standing_orders_customer ON standing_orders(customer_id, day_of_week);
CREATE INDEX IF NOT EXISTS idx_cust_pricing ON customer_pricing(customer_id, product_id);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_ledger_customer ON customer_ledger(customer_id, transaction_date);
CREATE INDEX IF NOT EXISTS idx_procurement_date ON milk_procurement(collection_date);
CREATE INDEX IF NOT EXISTS idx_production_batch ON production_batches(production_date);
CREATE INDEX IF NOT EXISTS idx_product_batches_fefo ON product_batches(product_id, expiry_date);

-- =====================================================================
-- 17. ANALYTICAL VIEWS
-- =====================================================================

-- VIEW 1: CUSTOMER PROFITABILITY VIEW
-- Calculates: Revenue - Raw Product Cost - Transport Cost - Other Costs = Contribution Margin & Margin %
CREATE OR REPLACE VIEW view_customer_profitability AS
SELECT 
    c.id AS customer_id,
    c.customer_code,
    c.business_name,
    c.customer_type,
    COALESCE(SUM(o.total_litres), 0) AS total_litres_delivered,
    COALESCE(SUM(o.subtotal), 0) AS gross_revenue,
    COALESCE(SUM(item_costs.total_product_cost), 0) AS total_product_cost,
    COALESCE(SUM(tca.allocated_transport_cost), 0) AS allocated_transport_cost,
    COALESCE(SUM(o.subtotal) - SUM(item_costs.total_product_cost) - SUM(COALESCE(tca.allocated_transport_cost, 0)), 0) AS contribution_margin,
    CASE 
        WHEN COALESCE(SUM(o.subtotal), 0) > 0 
        THEN ROUND(
            ((COALESCE(SUM(o.subtotal), 0) - COALESCE(SUM(item_costs.total_product_cost), 0) - COALESCE(SUM(tca.allocated_transport_cost), 0)) 
            / SUM(o.subtotal) * 100.0), 2
        )
        ELSE 0.00 
    END AS margin_percentage
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id AND o.status IN ('delivered', 'invoiced', 'paid')
LEFT JOIN (
    SELECT 
        oi.order_id,
        SUM(oi.ordered_quantity * p.cost_price) AS total_product_cost
    FROM order_items oi
    JOIN products p ON p.id = oi.product_id
    GROUP BY oi.order_id
) item_costs ON item_costs.order_id = o.id
LEFT JOIN (
    SELECT 
        order_id,
        SUM(allocated_transport_cost) AS allocated_transport_cost
    FROM transport_cost_allocations
    GROUP BY order_id
) tca ON tca.order_id = o.id
GROUP BY c.id, c.customer_code, c.business_name, c.customer_type;

-- VIEW 2: DAILY MILK BALANCE SHEET
CREATE OR REPLACE VIEW view_daily_milk_balance AS
SELECT
    proc.report_date,
    COALESCE(proc.total_procured_litres, 0) AS total_procured_litres,
    COALESCE(prod.total_production_litres, 0) AS total_production_litres,
    COALESCE(sales.total_dispatched_litres, 0) AS total_dispatched_litres,
    COALESCE(prod.total_wastage_litres, 0) AS total_wastage_litres,
    COALESCE(ret.total_returned_litres, 0) AS total_returned_litres,
    (COALESCE(proc.total_procured_litres, 0) - COALESCE(sales.total_dispatched_litres, 0) - COALESCE(prod.total_wastage_litres, 0) + COALESCE(ret.total_returned_litres, 0)) AS net_closing_stock_change
FROM (
    SELECT collection_date AS report_date, SUM(quantity_litres) AS total_procured_litres
    FROM milk_procurement WHERE quality_status = 'accepted'
    GROUP BY collection_date
) proc
FULL OUTER JOIN (
    SELECT production_date AS report_date, SUM(output_quantity) AS total_production_litres, SUM(wastage_litres) AS total_wastage_litres
    FROM production_batches
    GROUP BY production_date
) prod ON prod.report_date = proc.report_date
FULL OUTER JOIN (
    SELECT trip_date AS report_date, SUM(total_milk_litres_delivered) AS total_dispatched_litres
    FROM delivery_trips
    GROUP BY trip_date
) sales ON sales.report_date = COALESCE(proc.report_date, prod.report_date)
FULL OUTER JOIN (
    SELECT DATE(created_at) AS report_date, SUM(quantity) AS total_returned_litres
    FROM customer_returns
    GROUP BY DATE(created_at)
) ret ON ret.report_date = COALESCE(proc.report_date, prod.report_date, sales.report_date);

-- VIEW 3: ROUTE & TRANSPORT COST EFFICIENCY
CREATE OR REPLACE VIEW view_route_transport_efficiency AS
SELECT
    dt.id AS trip_id,
    dt.trip_number,
    dt.trip_date,
    dr.route_code,
    dr.route_name,
    v.registration_number AS vehicle_number,
    u.full_name AS driver_name,
    dt.total_distance_km,
    dt.diesel_litres,
    dt.diesel_cost,
    dt.driver_cost,
    dt.toll_charges,
    dt.total_transport_cost,
    dt.total_milk_litres_delivered,
    dt.transport_cost_per_litre,
    CASE WHEN dt.total_distance_km > 0 THEN ROUND(dt.total_transport_cost / dt.total_distance_km, 2) ELSE 0 END AS cost_per_km
FROM delivery_trips dt
JOIN delivery_routes dr ON dr.id = dt.route_id
JOIN vehicles v ON v.id = dt.vehicle_id
JOIN users u ON u.id = dt.driver_id;
