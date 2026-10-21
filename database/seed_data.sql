-- =====================================================================
-- REALISTIC SEED DATA FOR DAIRY ERP
-- Matches Exact Examples from Requirements Specification
-- =====================================================================

-- 1. Branches
INSERT INTO branches (id, branch_code, branch_name, branch_type, address, city, state, contact_phone, gstin)
VALUES
(1, 'BR-PUNE-01', 'Pune Central Dairy Plant & Hub', 'Plant', 'Plot 42, Hadapsar Industrial Estate', 'Pune', 'Maharashtra', '+91 98220 11223', '27AABCA1234F1Z5'),
(2, 'BR-MUM-01', 'Mumbai Distribution Center', 'Distribution Hub', 'Sector 19, Vashi APMC', 'Navi Mumbai', 'Maharashtra', '+91 98220 44556', '27AABCA1234F1Z6')
ON CONFLICT (id) DO NOTHING;

-- 2. Users (Super Admin, Admins, Drivers, Customers)
-- Password for all demo accounts: 'Dairy@123'
INSERT INTO users (id, branch_id, username, email, password_hash, full_name, phone, role)
VALUES
(1, 1, 'admin', 'admin@dairyerp.com', '$2b$12$e8YfGqG4tWkS9j7P8.FvOu4MhXz9I2kZ3Tz1y6R3E4W5Q8Y7U9I2K', 'Vikram Deshmukh (Dairy Owner)', '+91 98900 11111', 'super_admin'),
(2, 1, 'sales_manager', 'sales@dairyerp.com', '$2b$12$e8YfGqG4tWkS9j7P8.FvOu4MhXz9I2kZ3Tz1y6R3E4W5Q8Y7U9I2K', 'Amit Verma', '+91 98900 22222', 'sales_manager'),
(3, 1, 'driver_rahul', 'rahul@dairyerp.com', '$2b$12$e8YfGqG4tWkS9j7P8.FvOu4MhXz9I2kZ3Tz1y6R3E4W5Q8Y7U9I2K', 'Rahul Patil (Driver)', '+91 98900 33333', 'driver'),
(4, 1, 'driver_suresh', 'suresh@dairyerp.com', '$2b$12$e8YfGqG4tWkS9j7P8.FvOu4MhXz9I2kZ3Tz1y6R3E4W5Q8Y7U9I2K', 'Suresh Shinde (Driver)', '+91 98900 44444', 'driver'),
(5, 1, 'cust_abchotel', 'manager@abchotel.com', '$2b$12$e8YfGqG4tWkS9j7P8.FvOu4MhXz9I2kZ3Tz1y6R3E4W5Q8Y7U9I2K', 'Ramesh Sharma (ABC Hotel)', '+91 98900 55555', 'customer'),
(6, 1, 'cust_xyzrest', 'owner@xyzrest.com', '$2b$12$e8YfGqG4tWkS9j7P8.FvOu4MhXz9I2kZ3Tz1y6R3E4W5Q8Y7U9I2K', 'Sunil Jadhav (XYZ Restaurant)', '+91 98900 66666', 'customer')
ON CONFLICT (id) DO NOTHING;

-- 3. Vehicles
INSERT INTO vehicles (id, branch_id, registration_number, vehicle_type, capacity_litres, default_driver_id, fuel_type, average_mileage_kmpl, current_odometer_km)
VALUES
(1, 1, 'MH12AB1234', 'Insulated Milk Van (Tata 407)', 1200.00, 3, 'Diesel', 8.5, 45280.00),
(2, 1, 'MH12CD5678', 'Refrigerated Eicher Pro', 2500.00, 4, 'Diesel', 6.5, 78120.00),
(3, 1, 'MH12EF9012', 'Mahindra Bolero Maxi Truck', 800.00, NULL, 'Diesel', 11.0, 32400.00)
ON CONFLICT (id) DO NOTHING;

-- 4. Delivery Routes
INSERT INTO delivery_routes (id, branch_id, route_code, route_name, start_location, end_location, approx_distance_km, default_vehicle_id, default_driver_id)
VALUES
(1, 1, 'RT-01', 'Route 01 - Pune City Central & Deccan', 'Hadapsar Plant', 'Hadapsar Plant', 145.0, 1, 3),
(2, 1, 'RT-02', 'Route 02 - Hinjewadi IT Park & Wakad', 'Hadapsar Plant', 'Hadapsar Plant', 110.0, 2, 4)
ON CONFLICT (id) DO NOTHING;

-- 5. Products Catalogue (Milk, Curd, Paneer, Buttermilk, Ghee, Butter)
INSERT INTO products (id, sku, product_name, category, unit, pack_size, mrp, standard_b2b_price, cost_price, gst_rate, hsn_code, min_order_quantity, current_stock)
VALUES
(1, 'MLK-COW-1L', 'Fresh Cow Milk Premium', 'Milk', 'L', '1 Litre Pouch', 60.00, 55.00, 42.00, 0.0, '04012000', 10.0, 2450.0),
(2, 'MLK-BUF-1L', 'Full Cream Buffalo Milk', 'Milk', 'L', '1 Litre Pouch', 72.00, 66.00, 52.00, 0.0, '04012000', 10.0, 1800.0),
(3, 'MLK-TON-1L', 'Toned Cow Milk (3.0% Fat)', 'Milk', 'L', '1 Litre Pouch', 54.00, 50.00, 38.00, 0.0, '04012000', 10.0, 1200.0),
(4, 'CRD-STD-500G', 'Farm Fresh Curd (Dahi)', 'Curd', 'KG', '500g Tub', 45.00, 70.00, 48.00, 5.0, '04031000', 5.0, 650.0),
(5, 'PNR-MAL-1KG', 'Fresh Malai Paneer (Vacuum Pack)', 'Paneer', 'KG', '1 Kg Block', 380.00, 320.00, 240.00, 5.0, '04061000', 2.0, 320.0),
(6, 'BTM-MAS-200ML', 'Spiced Masala Buttermilk (Taas)', 'Buttermilk', 'L', '200ml Pouch', 15.00, 35.00, 20.00, 12.0, '04039010', 20.0, 800.0),
(7, 'GHE-PUR-1L', 'Pure Desi Cow Ghee (Bilona)', 'Ghee', 'KG', '1 Litre Tin', 750.00, 620.00, 480.00, 12.0, '04059020', 1.0, 150.0)
ON CONFLICT (id) DO NOTHING;

-- 6. Customers (Hotels, Restaurants, Mess, Distributors)
INSERT INTO customers (id, user_id, branch_id, customer_code, business_name, contact_person, phone, email, customer_type, gstin, billing_address, delivery_address, assigned_route_id, assigned_driver_id, route_stop_sequence, credit_limit, credit_days, current_outstanding, transport_allocation_method, negotiated_transport_rate_per_litre, distance_from_plant_km)
VALUES
(1, 5, 1, 'CUST-001', 'ABC Grand Luxury Hotel', 'Ramesh Sharma', '+91 98900 55555', 'manager@abchotel.com', 'hotel', '27AABCH1234C1Z1', 'FC Road, Shivaji Nagar, Pune 411005', 'Central Receiving Gate, FC Road, Pune', 1, 3, 1, 200000.00, 15, 58000.00, 'customer_specific', 3.00, 12.5),
(2, 6, 1, 'CUST-002', 'XYZ Fine Dine Restaurant', 'Sunil Jadhav', '+91 98900 66666', 'owner@xyzrest.com', 'restaurant', '27AABCR9876D1Z2', 'JM Road, Deccan Gymkhana, Pune 411004', 'Rear Kitchen Entrance, JM Road, Pune', 1, 3, 2, 80000.00, 7, 24500.00, 'distance_based', 4.00, 14.0),
(3, NULL, 1, 'CUST-003', 'PQR Cafe & Bakers', 'Priya Kulkarni', '+91 98900 77777', 'priya@pqrcafe.com', 'cafe', '27AABCP5555E1Z3', 'Koregaon Park North Main Rd, Pune', 'Bakery Unit 3, Koregaon Park', 1, 3, 3, 50000.00, 7, 12800.00, 'equal_per_litre', 5.00, 18.0),
(4, NULL, 1, 'CUST-004', 'City Mess & Canteen Services', 'Ganesh Pawar', '+91 98900 88888', 'ganesh@citymess.com', 'mess', '27AABCM2222F1Z4', 'Sadashiv Peth, Near Tilak Smarak, Pune', 'Mess Kitchen, Sadashiv Peth', 1, 3, 4, 60000.00, 10, 19400.00, 'equal_per_litre', 5.00, 10.5),
(5, NULL, 1, 'CUST-005', 'Maharashtra Mega Dairy Distributor', 'Kailash Oswal', '+91 98900 99999', 'oswal@megadist.com', 'distributor', '27AABCD3333G1Z5', 'Marketyard Gate 2, Pune 411037', 'Warehouse 14, Marketyard, Pune', 2, 4, 1, 500000.00, 30, 185000.00, 'equal_per_litre', 2.50, 8.0)
ON CONFLICT (id) DO NOTHING;

-- 7. Customer Specific Pricing (Exact Prompt Examples)
-- ABC Hotel => ₹52/L (Standard ₹55/L)
-- XYZ Restaurant => ₹53/L
-- Big Distributor => ₹50/L
-- Small Customer => ₹55/L
INSERT INTO customer_pricing (customer_id, product_id, custom_price, effective_from)
VALUES
(1, 1, 52.00, '2026-01-01'), -- ABC Hotel Cow Milk
(1, 4, 68.00, '2026-01-01'), -- ABC Hotel Curd
(1, 5, 305.00, '2026-01-01'),-- ABC Hotel Paneer
(2, 1, 53.00, '2026-01-01'), -- XYZ Restaurant Cow Milk
(2, 5, 310.00, '2026-01-01'),-- XYZ Restaurant Paneer
(5, 1, 50.00, '2026-01-01'), -- Big Distributor Cow Milk
(5, 2, 62.00, '2026-01-01'), -- Big Distributor Buffalo Milk
(3, 1, 55.00, '2026-01-01')  -- PQR Cafe Standard Price
ON CONFLICT DO NOTHING;

-- 8. Standing Orders (Customer Day-of-Week Schedule)
-- ABC Hotel: Mon 100L, Tue 100L, Wed 120L, Thu 100L, Fri 100L, Sat 150L, Sun 80L
INSERT INTO standing_orders (customer_id, product_id, day_of_week, quantity, notes)
VALUES
(1, 1, 1, 100.0, 'Monday Standard Order'),
(1, 1, 2, 100.0, 'Tuesday Standard Order'),
(1, 1, 3, 120.0, 'Wednesday Midweek Surge'),
(1, 1, 4, 100.0, 'Thursday Standard Order'),
(1, 1, 5, 100.0, 'Friday Weekend Prep'),
(1, 1, 6, 150.0, 'Saturday Peak Buffet Requirement'),
(1, 1, 0, 80.0, 'Sunday Normal Order'),
(1, 4, 1, 20.0, 'Daily Curd 20KG'),
(1, 5, 1, 5.0, 'Daily Paneer 5KG'),
(2, 1, 1, 80.0, 'XYZ Daily Milk'),
(2, 5, 1, 8.0, 'XYZ Daily Paneer'),
(3, 1, 1, 40.0, 'PQR Cafe Daily Milk'),
(4, 1, 1, 60.0, 'City Mess Daily Milk'),
(5, 1, 1, 400.0, 'Distributor Daily Milk')
ON CONFLICT DO NOTHING;

-- 9. Farmers / Procurement Vendors
INSERT INTO procurement_vendors (id, vendor_code, full_name, village, phone, milk_type)
VALUES
(1, 'VEND-001', 'Raj Dairy Farm (Rajesh Patil)', 'Saswad', '+91 97650 11001', 'cow'),
(2, 'VEND-002', 'Mauli Dudh Utpadak (Sanjay Shinde)', 'Shirur', '+91 97650 22002', 'buffalo'),
(3, 'VEND-003', 'Kisan Seva Kendra (Datta More)', 'Manchar', '+91 97650 33003', 'mixed')
ON CONFLICT (id) DO NOTHING;

-- 10. Milk Procurement Today (Exact requirement: 8,500 L procured)
INSERT INTO milk_procurement (id, procurement_batch_no, vendor_id, branch_id, collection_date, collection_shift, milk_type, quantity_litres, fat_pct, snf_pct, clr_reading, rate_per_litre, quality_status)
VALUES
(1, 'PROC-20261015-01', 1, 1, CURRENT_DATE, 'Morning', 'cow', 4200.0, 4.2, 8.6, 28.5, 41.50, 'accepted'),
(2, 'PROC-20261015-02', 2, 1, CURRENT_DATE, 'Morning', 'buffalo', 2500.0, 6.2, 9.0, 30.0, 52.00, 'accepted'),
(3, 'PROC-20261015-03', 3, 1, CURRENT_DATE, 'Morning', 'mixed', 1800.0, 4.5, 8.7, 29.0, 42.50, 'accepted')
ON CONFLICT (id) DO NOTHING;

-- 11. Production Batches Today (Exact requirement: 8,200 L processed, 120 L wastage)
INSERT INTO production_batches (id, batch_number, branch_id, production_date, raw_milk_input_litres, process_type, output_product_id, output_quantity, output_unit, wastage_litres, expiry_date, operator_name, status)
VALUES
(1, 'PB-20261015-01', 1, CURRENT_DATE, 6000.0, 'Pasteurization & Pouch Packing', 1, 5920.0, 'L', 80.0, CURRENT_DATE + INTERVAL '2 days', 'Santosh Pawar', 'completed'),
(2, 'PB-20261015-02', 1, CURRENT_DATE, 1500.0, 'Curd Processing', 4, 1470.0, 'KG', 30.0, CURRENT_DATE + INTERVAL '5 days', 'Mahesh Kale', 'completed'),
(3, 'PB-20261015-03', 1, CURRENT_DATE, 700.0, 'Paneer Processing', 5, 140.0, 'KG', 10.0, CURRENT_DATE + INTERVAL '4 days', 'Gopal Rathi', 'completed')
ON CONFLICT (id) DO NOTHING;

-- 12. Delivery Trip Today (Trip with exact requirement: Distance 145km, Diesel 18L, ₹1,710 + ₹800 + ₹250 + ₹100 = ₹2,860)
INSERT INTO delivery_trips (id, trip_number, route_id, vehicle_id, driver_id, trip_date, departure_time, return_time, opening_km, closing_km, diesel_litres, diesel_price_per_litre, driver_cost, toll_charges, other_expenses, total_transport_cost, total_milk_litres_loaded, total_milk_litres_delivered, transport_cost_per_litre, status)
VALUES
(1, 'TRIP-20261015-01', 1, 1, 3, CURRENT_DATE, CURRENT_TIMESTAMP - INTERVAL '4 hours', CURRENT_TIMESTAMP - INTERVAL '30 minutes', 45135.0, 45280.0, 18.0, 95.0, 800.0, 250.0, 100.0, 2860.00, 500.0, 495.0, 5.777, 'completed')
ON CONFLICT (id) DO NOTHING;

-- 13. Orders & Deliveries
INSERT INTO orders (id, order_number, customer_id, branch_id, order_date, delivery_date, status, is_standing_order, subtotal, tax_amount, transport_charge, total_amount, total_litres, payment_status)
VALUES
(1, 'ORD-20261015-001', 1, 1, CURRENT_DATE, CURRENT_DATE, 'delivered', true, 12850.00, 250.00, 300.00, 13400.00, 100.0, 'partial'),
(2, 'ORD-20261015-002', 2, 1, CURRENT_DATE, CURRENT_DATE, 'delivered', true, 6720.00, 140.00, 320.00, 7180.00, 80.0, 'paid'),
(3, 'ORD-20261015-003', 3, 1, CURRENT_DATE, CURRENT_DATE, 'out_for_delivery', false, 2200.00, 0.00, 200.00, 2400.00, 40.0, 'pending')
ON CONFLICT (id) DO NOTHING;

INSERT INTO order_items (order_id, product_id, ordered_quantity, unit_price, gst_rate, tax_amount, total_amount, product_cost_price)
VALUES
(1, 1, 100.0, 52.00, 0.0, 0.0, 5200.00, 42.00), -- ABC Hotel 100L Cow Milk @ ₹52
(1, 4, 20.0, 68.00, 5.0, 68.0, 1428.00, 48.00),   -- Curd 20KG
(1, 5, 5.0, 305.00, 5.0, 76.25, 1601.25, 240.00), -- Paneer 5KG
(2, 1, 80.0, 53.00, 0.0, 0.0, 4240.00, 42.00),   -- XYZ Restaurant 80L Cow Milk @ ₹53
(2, 5, 8.0, 310.00, 5.0, 124.0, 2604.00, 240.00),
(3, 1, 40.0, 55.00, 0.0, 0.0, 2200.00, 42.00)
ON CONFLICT DO NOTHING;

-- Deliveries (ABC Hotel: Ordered 100L, Delivered 95L, Shortage 5L due to Leakage - Exact prompt example!)
INSERT INTO deliveries (id, trip_id, order_id, customer_id, delivery_sequence, status, arrival_time, departure_time, total_ordered_litres, total_delivered_litres, shortage_reason, shortage_notes, delivered_to_person, collected_amount, collected_payment_method)
VALUES
(1, 1, 1, 1, 1, 'partially_delivered', CURRENT_TIMESTAMP - INTERVAL '3 hours', CURRENT_TIMESTAMP - INTERVAL '2 hours 30 minutes', 100.0, 95.0, 'leakage', '5 pouches punctured during transit in crate #4', 'Chef Arvind', 5000.0, 'upi'),
(2, 1, 2, 2, 2, 'delivered', CURRENT_TIMESTAMP - INTERVAL '2 hours', CURRENT_TIMESTAMP - INTERVAL '1 hour 40 minutes', 80.0, 80.0, 'none', 'Received in good chilled condition', 'Sunil (Owner)', 7180.0, 'bank_transfer')
ON CONFLICT (id) DO NOTHING;

-- Transport Cost Allocations (Customer ABC Hotel allocated transport cost)
INSERT INTO transport_cost_allocations (trip_id, delivery_id, customer_id, order_id, delivered_litres, allocation_method, cost_per_litre_applied, distance_km, allocated_transport_cost)
VALUES
(1, 1, 1, 1, 95.0, 'customer_specific', 3.00, 12.5, 285.00),
(1, 2, 2, 1, 80.0, 'distance_based', 4.00, 14.0, 320.00)
ON CONFLICT DO NOTHING;

-- Customer Ledger Entries (ABC Hotel Exact Ledger from requirement: Opening 25000 + Sales 85000 - Payments 50000 - Returns 2000 = 58000)
INSERT INTO customer_ledger (customer_id, transaction_date, transaction_type, reference_number, debit_amount, credit_amount, running_balance, narration)
VALUES
(1, '2026-10-01', 'opening_balance', 'OB-OCT-26', 25000.00, 0.00, 25000.00, 'Opening Balance for October 2026'),
(1, '2026-10-08', 'sales_invoice', 'INV-20261008-01', 85000.00, 0.00, 110000.00, 'Weekly Milk & Dairy Products Delivery'),
(1, '2026-10-10', 'payment', 'PAY-UPI-98124', 0.00, 50000.00, 60000.00, 'Part payment received via UPI'),
(1, '2026-10-12', 'sales_return', 'CRN-20261012-01', 0.00, 2000.00, 58000.00, 'Credit Note for 38L damaged milk crates')
ON CONFLICT DO NOTHING;

-- Invoices
INSERT INTO invoices (id, invoice_number, order_id, customer_id, branch_id, invoice_date, due_date, total_litres, subtotal, cgst_amount, sgst_amount, igst_amount, transport_charge, total_amount, paid_amount, payment_status)
VALUES
(1, 'INV-20261015-001', 1, 1, 1, CURRENT_DATE, CURRENT_DATE + INTERVAL '15 days', 95.0, 12850.0, 125.0, 125.0, 0.0, 285.0, 13385.0, 5000.0, 'partial'),
(2, 'INV-20261015-002', 2, 2, 1, CURRENT_DATE, CURRENT_DATE + INTERVAL '7 days', 80.0, 6720.0, 70.0, 70.0, 0.0, 320.0, 7180.0, 7180.0, 'paid')
ON CONFLICT (id) DO NOTHING;
