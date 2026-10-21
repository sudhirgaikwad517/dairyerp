# Dairy ERP — Database Schema & Data Dictionary

Comprehensive PostgreSQL schema structure covering all operational and analytical tables.

---

## 1. Core Architecture Tables

### `branches`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | SERIAL | PRIMARY KEY | Unique branch identifier |
| `branch_code` | VARCHAR(20) | UNIQUE, NOT NULL | Code (e.g. `BR-PUNE-01`) |
| `branch_name` | VARCHAR(100) | NOT NULL | Processing Plant / Distribution Center name |
| `branch_type` | VARCHAR(50) | DEFAULT 'Plant' | Plant, Warehouse, Distribution Hub |
| `gstin` | VARCHAR(15) | NULLABLE | State GSTIN number |

### `users`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | SERIAL | PRIMARY KEY | User ID |
| `username` | VARCHAR(50) | UNIQUE, NOT NULL | Login username |
| `role` | user_role | NOT NULL | super_admin, admin, driver, customer, sales_manager, etc. |
| `phone` | VARCHAR(20) | UNIQUE, NOT NULL | Mobile number |
| `password_hash` | VARCHAR(255) | NOT NULL | Secure salted bcrypt hash |

---

## 2. Logistics & Fleet Tables

### `vehicles`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | SERIAL | PRIMARY KEY | Vehicle ID |
| `registration_number` | VARCHAR(30) | UNIQUE, NOT NULL | Number plate (e.g. `MH12AB1234`) |
| `vehicle_type` | VARCHAR(50) | NOT NULL | Insulated Milk Van, Refrigerated Truck |
| `capacity_litres` | NUMERIC(10,2)| NOT NULL | Maximum tank/crate capacity in Litres |
| `average_mileage_kmpl`| NUMERIC(6,2) | DEFAULT 8.0 | Standard fuel efficiency |

### `delivery_routes`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | SERIAL | PRIMARY KEY | Route ID |
| `route_code` | VARCHAR(30) | UNIQUE, NOT NULL | Route code (e.g. `RT-01`) |
| `route_name` | VARCHAR(100) | NOT NULL | Full route description |
| `approx_distance_km` | NUMERIC(8,2) | DEFAULT 0.0 | Estimated round-trip distance |

### `delivery_trips`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | SERIAL | PRIMARY KEY | Trip ID |
| `trip_number` | VARCHAR(40) | UNIQUE, NOT NULL | Trip number (e.g. `TRIP-20261015-01`) |
| `opening_km` | NUMERIC(10,2)| NOT NULL | Starting odometer reading |
| `closing_km` | NUMERIC(10,2)| NULLABLE | Ending odometer reading |
| `diesel_litres`| NUMERIC(8,2) | DEFAULT 0.0 | Fuel consumed during trip |
| `driver_cost` | NUMERIC(10,2)| DEFAULT 800.0 | Driver trip allowance |
| `toll_charges`| NUMERIC(10,2)| DEFAULT 0.0 | Toll booth expenses |
| `total_transport_cost`| NUMERIC(12,2) | COMPUTED | Total transport cost |
| `transport_cost_per_litre`| NUMERIC(8,3) | COMPUTED | Total Cost ÷ Delivered Litres |

---

## 3. Customer & Commercial Tables

### `customers`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | SERIAL | PRIMARY KEY | Customer ID |
| `customer_code` | VARCHAR(30) | UNIQUE, NOT NULL | Code (e.g. `CUST-001`) |
| `business_name` | VARCHAR(150)| NOT NULL | Business / Trading name |
| `customer_type` | customer_type| DEFAULT 'hotel' | hotel, restaurant, mess, cafe, retailer, distributor |
| `credit_limit` | NUMERIC(12,2)| DEFAULT 50000.0 | Maximum allowed credit exposure |
| `credit_days` | INT | DEFAULT 7 | Payment grace days |
| `current_outstanding`| NUMERIC(12,2)| DEFAULT 0.0 | Real-time pending balance |
| `transport_allocation_method`| ENUM | DEFAULT 'equal_per_litre' | equal_per_litre, distance_based, customer_specific |
| `negotiated_transport_rate_per_litre`| NUMERIC(8,2)| DEFAULT 0.0 | Specific negotiated ₹/L rate |

### `customer_pricing`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `customer_id` | INT | FOREIGN KEY | Customer reference |
| `product_id` | INT | FOREIGN KEY | Product reference |
| `custom_price`| NUMERIC(10,2)| NOT NULL | Special negotiated selling price |
| `effective_from`| DATE | DEFAULT CURRENT_DATE | Pricing activation date |

### `standing_orders`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `customer_id` | INT | FOREIGN KEY | Customer reference |
| `product_id` | INT | FOREIGN KEY | Product reference |
| `day_of_week` | INT | NOT NULL (0-6) | 0=Sun, 1=Mon, ..., 6=Sat |
| `quantity` | NUMERIC(10,2)| NOT NULL | Daily recurring quantity in Units/Litres |

---

## 4. Deliveries, Shortages & Ledgers

### `deliveries`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `trip_id` | INT | FOREIGN KEY | Delivery trip |
| `order_id` | INT | FOREIGN KEY | Order reference |
| `customer_id` | INT | FOREIGN KEY | Customer reference |
| `total_ordered_litres` | NUMERIC(10,2)| NOT NULL | Quantity planned for delivery |
| `total_delivered_litres`| NUMERIC(10,2)| DEFAULT 0.0 | Actual received quantity |
| `total_shortage_litres` | NUMERIC(10,2)| STORED | Ordered − Delivered |
| `shortage_reason` | shortage_reason| DEFAULT 'none' | leakage, damage, rejection, shortage, delivery_issue |
| `customer_signature_url`| TEXT | NULLABLE | Base64 PNG signature captured on driver screen |
| `collected_amount` | NUMERIC(10,2)| DEFAULT 0.0 | Cash or UPI collected on delivery |

### `customer_ledger`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `customer_id` | INT | FOREIGN KEY | Customer reference |
| `transaction_date` | DATE | NOT NULL | Transaction posting date |
| `transaction_type` | VARCHAR(40) | NOT NULL | opening_balance, sales_invoice, payment, credit_note |
| `reference_number` | VARCHAR(50) | NULLABLE | Invoice/Payment/Credit Note reference |
| `debit_amount` | NUMERIC(12,2)| DEFAULT 0.0 | Debit (increases customer balance) |
| `credit_amount`| NUMERIC(12,2)| DEFAULT 0.0 | Credit (decreases customer balance) |
| `running_balance` | NUMERIC(12,2)| NOT NULL | Balance after transaction |

---

## 5. Analytical Views & Reports

### `view_customer_profitability`
$$\text{Revenue} - \text{Raw Product Cost} - \text{Allocated Transport} - \text{Overhead} = \text{Net Contribution Margin}$$

### `view_daily_milk_balance`
$$\text{Procured} - \text{Dispatched} - \text{Wastage} = \text{Closing Stock}$$
