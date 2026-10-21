-- =====================================================================
-- ADVANCED ANALYTICAL SQL QUERIES & STORED VIEWS FOR DAIRY ERP
-- Includes Litre-wise Costing, Transport Cost Allocation & Customer Profitability
-- =====================================================================

-- 1. Customer Monthly Milk Delivered & Daily Average
-- (Directly implements Module 8: har customer ke liye total milk & average L/day)
CREATE OR REPLACE VIEW view_customer_monthly_milk_summary AS
SELECT
    c.id AS customer_id,
    c.customer_code,
    c.business_name,
    TO_CHAR(d.arrival_time, 'YYYY-MM') AS month_year,
    SUM(d.total_delivered_litres) AS total_milk_delivered_litres,
    COUNT(DISTINCT DATE(d.arrival_time)) AS active_delivery_days,
    ROUND(SUM(d.total_delivered_litres) / NULLIF(COUNT(DISTINCT DATE(d.arrival_time)), 0), 2) AS average_litres_per_day
FROM customers c
JOIN deliveries d ON d.customer_id = c.id
WHERE d.status IN ('delivered', 'partially_delivered')
GROUP BY c.id, c.customer_code, c.business_name, TO_CHAR(d.arrival_time, 'YYYY-MM');

-- 2. Delivery Shortage & Leakage Analysis
-- (Implements Module 9: Ordered vs Dispatched vs Delivered vs Shortage with Reason)
CREATE OR REPLACE VIEW view_delivery_shortage_analysis AS
SELECT
    d.id AS delivery_id,
    o.order_number,
    c.business_name,
    dt.trip_number,
    u.full_name AS driver_name,
    v.registration_number AS vehicle_number,
    d.total_ordered_litres,
    d.total_delivered_litres,
    (d.total_ordered_litres - d.total_delivered_litres) AS shortage_litres,
    CASE 
        WHEN d.total_ordered_litres > 0 
        THEN ROUND(((d.total_ordered_litres - d.total_delivered_litres) / d.total_ordered_litres * 100.0), 2)
        ELSE 0.00 
    END AS shortage_percentage,
    d.shortage_reason,
    d.shortage_notes,
    d.created_at AS delivery_timestamp
FROM deliveries d
JOIN orders o ON o.id = d.order_id
JOIN customers c ON c.id = d.customer_id
JOIN delivery_trips dt ON dt.id = d.trip_id
JOIN users u ON u.id = dt.driver_id
JOIN vehicles v ON v.id = dt.vehicle_id;

-- 3. Vehicle Fuel & Running Cost Analytics
-- (Implements Module 15 & 16: KM, Fuel, Mileage, Cost/KM, Cost/Litre)
CREATE OR REPLACE VIEW view_vehicle_performance AS
SELECT
    v.id AS vehicle_id,
    v.registration_number,
    v.vehicle_type,
    COUNT(dt.id) AS total_trips,
    COALESCE(SUM(dt.total_distance_km), 0) AS total_km_run,
    COALESCE(SUM(dt.diesel_litres), 0) AS total_diesel_litres,
    COALESCE(SUM(dt.diesel_cost), 0) AS total_diesel_cost,
    COALESCE(SUM(dt.total_transport_cost), 0) AS total_running_cost,
    COALESCE(SUM(dt.total_milk_litres_delivered), 0) AS total_litres_transported,
    CASE 
        WHEN SUM(dt.diesel_litres) > 0 THEN ROUND(SUM(dt.total_distance_km) / SUM(dt.diesel_litres), 2)
        ELSE 0.00 
    END AS actual_mileage_kmpl,
    CASE 
        WHEN SUM(dt.total_distance_km) > 0 THEN ROUND(SUM(dt.total_transport_cost) / SUM(dt.total_distance_km), 2)
        ELSE 0.00 
    END AS cost_per_km,
    CASE 
        WHEN SUM(dt.total_milk_litres_delivered) > 0 THEN ROUND(SUM(dt.total_transport_cost) / SUM(dt.total_milk_litres_delivered), 3)
        ELSE 0.000 
    END AS average_transport_cost_per_litre
FROM vehicles v
LEFT JOIN delivery_trips dt ON dt.vehicle_id = v.id
GROUP BY v.id, v.registration_number, v.vehicle_type;
