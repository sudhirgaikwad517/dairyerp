import logging
import random
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from backend.app.models.entities import (
    Branch, User, Vehicle, DeliveryRoute, Customer, Product,
    CustomerPricing, Order, OrderItem,
    DeliveryTrip, Delivery, TransportCostAllocation,
    ProcurementVendor, MilkProcurement, ProductionBatch,
    Invoice, Payment, CustomerLedger, CustomerComplaint, BusinessProfile
)
from backend.app.services.billing_service import DEFAULT_PROFILE

logger = logging.getLogger("dairy_erp")

# Sample month: September 2026. Monthly rate & quantity per customer are taken from the
# monthly milk register (Excel); daily quantities are a realistic split of that monthly total.
SAMPLE_YEAR, SAMPLE_MONTH, SAMPLE_DAYS = 2026, 9, 30

# (code, name, contact, phone, type, area, route_id, stop, rate, monthly_qty, credit_days)
SAMPLE_CUSTOMERS = [
    ("CUST-001", "Siddharth Kharghar", "Siddharth Patil", "+91 98201 10001", "retailer", "Sector 12, Kharghar, Navi Mumbai", 1, 1, 57.0, 816.0, 7),
    ("CUST-002", "Pro Shakti Mumbai", "Prakash Shetty", "+91 98201 10002", "distributor", "Chembur, Mumbai", 2, 1, 57.0, 1055.0, 15),
    ("CUST-003", "Kadam", "Sunil Kadam", "+91 98201 10003", "retailer", "Sector 20, Kharghar, Navi Mumbai", 1, 2, 56.5, 5575.0, 15),
    ("CUST-004", "Nitin Prabhu", "Nitin Prabhu", "+91 98201 10004", "distributor", "CBD Belapur, Navi Mumbai", 1, 3, 56.5, 6030.0, 15),
    ("CUST-005", "Sham Bharwad", "Sham Bharwad", "+91 98201 10005", "distributor", "Ghatkopar East, Mumbai", 2, 2, 56.5, 16332.0, 30),
    ("CUST-006", "Rushi Meghraj", "Rushikesh Meghraj", "+91 98201 10006", "retailer", "Vashi, Navi Mumbai", 1, 4, 57.0, 1905.0, 7),
    ("CUST-007", "Nature Rich", "Anand Joshi", "+91 98201 10007", "retailer", "Sion, Mumbai", 2, 3, 58.0, 929.0, 7),
]

MILK_COST_PRICE = 47.0


def _round_half(x: float) -> float:
    return round(x * 2) / 2


def split_monthly_quantity(total: float, days: list, rng: random.Random) -> list:
    """Split a monthly quantity into daily quantities (0.5 L steps) that add up exactly to the total."""
    weights = []
    for d in days:
        w = 1.0 + rng.uniform(-0.06, 0.06)
        if d.weekday() == 6:
            w += 0.08   # Sunday peak
        elif d.weekday() == 5:
            w += 0.04   # Saturday
        weights.append(w)
    total_w = sum(weights)
    qty = [max(0.5, _round_half(total * w / total_w)) for w in weights]

    diff = _round_half(total - sum(qty))
    i = 0
    while abs(diff) >= 0.5:
        step = 0.5 if diff > 0 else -0.5
        idx = i % len(qty)
        if qty[idx] + step > 0:
            qty[idx] += step
            diff -= step
        i += 1
    return qty


def milk_rate(fat_pct: float, snf_pct: float) -> float:
    # Same cow-milk rate chart as the procurement API
    return round(max(32.0, min(fat_pct * 7.4 + snf_pct * 1.2, 75.0)), 2)


# The dairy does not record farmer collections or packing yet: keep those tabs empty.
# (Random numbers are still drawn so the rest of the sample data stays the same.)
SEED_PLANT_DATA = False


def seed_database_if_empty(db: Session):
    if db.query(Customer).first():
        logger.info("Database already seeded. Skipping initial seeding.")
        return

    logger.info("Seeding September 2026 sample dataset...")
    rng = random.Random(2026)
    days = [date(SAMPLE_YEAR, SAMPLE_MONTH, d) for d in range(1, SAMPLE_DAYS + 1)]

    # 1. Branch, users, vehicles, routes
    db.add(Branch(
        id=1, branch_code="BR-01", branch_name="Akash Dairy Farm",
        branch_type="Plant", address="Plot 42, Taloja MIDC, Navi Mumbai 410208", city="Navi Mumbai",
        state="Maharashtra", contact_phone="+91 98220 11223", gstin="27AABCA1234F1Z5"
    ))
    db.add_all([
        User(id=1, branch_id=1, username="admin", email="admin@dairyerp.com", password_hash="Dairy@123",
             full_name="Admin", phone="+91 98900 11111", role="super_admin"),
        User(id=3, branch_id=1, username="driver_rahul", email="rahul@dairyerp.com", password_hash="Driver@123",
             full_name="Rahul Patil", phone="+91 98900 33333", role="driver"),
        User(id=4, branch_id=1, username="driver_sachin", email="sachin@dairyerp.com", password_hash="Driver@123",
             full_name="Sachin More", phone="+91 98900 44444", role="driver"),
    ])
    db.flush()
    db.add_all([
        Vehicle(id=1, branch_id=1, registration_number="MH12AB1234", vehicle_type="Insulated Milk Van (Tata 407)",
                capacity_litres=1200.0, default_driver_id=3, average_mileage_kmpl=8.5, current_odometer_km=45000.0),
        Vehicle(id=2, branch_id=1, registration_number="MH12CD5678", vehicle_type="Refrigerated Eicher Pro",
                capacity_litres=2500.0, default_driver_id=4, average_mileage_kmpl=6.5, current_odometer_km=78000.0),
    ])
    db.flush()
    routes = {
        1: DeliveryRoute(id=1, branch_id=1, route_code="RT-01", route_name="Route 01 - Navi Mumbai",
                         start_location="Dairy Plant", end_location="Dairy Plant", approx_distance_km=70.0, fixed_daily_cost=1800.0,
                         default_vehicle_id=1, default_driver_id=3),
        2: DeliveryRoute(id=2, branch_id=1, route_code="RT-02", route_name="Route 02 - Mumbai City",
                         start_location="Dairy Plant", end_location="Dairy Plant", approx_distance_km=95.0, fixed_daily_cost=2400.0,
                         default_vehicle_id=2, default_driver_id=4),
    }
    db.add_all(routes.values())
    db.flush()

    # 2. Product (milk only, as in the monthly register)
    milk = Product(
        id=1, sku="MLK-COW-1L", product_name="Fresh Cow Milk", category="Milk", unit="L",
        pack_size="1 Litre Pouch", mrp=64.0, standard_b2b_price=57.0, cost_price=MILK_COST_PRICE,
        gst_rate=0.0, hsn_code="0401", min_order_quantity=10.0, current_stock=0.0
    )
    db.add(milk)
    db.flush()

    # 3. Customers and their rates
    customers = {}
    daily_qty = {}
    for code, name, contact, phone, ctype, area, route_id, stop, rate, monthly_qty, credit_days in SAMPLE_CUSTOMERS:
        monthly_amount = monthly_qty * rate
        c = Customer(
            customer_code=code, branch_id=1, business_name=name, contact_person=contact, phone=phone,
            customer_type=ctype, billing_address=area, delivery_address=area,
            assigned_route_id=route_id, assigned_driver_id=routes[route_id].default_driver_id,
            route_stop_sequence=stop, credit_limit=round(monthly_amount * 1.5, -3), credit_days=credit_days,
            transport_allocation_method="equal_per_litre", distance_from_plant_km=routes[route_id].approx_distance_km / 2
        )
        db.add(c)
        db.flush()
        customers[code] = c
        db.add(CustomerPricing(customer_id=c.id, product_id=milk.id, custom_price=rate,
                               effective_from=date(SAMPLE_YEAR, SAMPLE_MONTH, 1)))
        daily_qty[code] = split_monthly_quantity(monthly_qty, days, rng)

    # 4. Farmers / vendors
    vendors = [
        ProcurementVendor(vendor_code="VEND-001", full_name="Raj Dairy Farm (Rajesh Patil)", village="Karjat", phone="+91 97650 11001", milk_type="cow"),
        ProcurementVendor(vendor_code="VEND-002", full_name="Mauli Dudh Utpadak (Sanjay Shinde)", village="Pen", phone="+91 97650 22002", milk_type="cow"),
        ProcurementVendor(vendor_code="VEND-003", full_name="Kisan Seva Dairy (Datta More)", village="Murbad", phone="+91 97650 33003", milk_type="cow"),
    ]
    if SEED_PLANT_DATA:
        db.add_all(vendors)
        db.flush()

    # 5. Daily operations for every day of the month
    odometer = {1: 45000.0, 2: 78000.0}
    order_seq = 0
    for di, day in enumerate(days):
        ymd = day.strftime("%Y%m%d")
        demand = sum(daily_qty[code][di] for code in customers)

        # Production: pack today's demand plus a small buffer; ~0.8% process wastage
        output = demand + rng.choice([10.0, 15.0, 20.0])
        wastage = round(output * rng.uniform(0.006, 0.010), 1)
        raw_input = output + wastage

        # Procurement: accepted milk covers production with a small raw-milk balance left in the tank
        accepted_total = raw_input + rng.choice([20.0, 30.0, 40.0])
        shares = [0.48, 0.32, 0.20]
        collected = [round(accepted_total * s / 10) * 10 for s in shares]
        collected[0] += accepted_total - sum(collected)
        for vi, (vendor, qty) in enumerate(zip(vendors, collected)):
            fat = round(rng.uniform(3.8, 4.6), 1)
            snf = round(rng.uniform(8.3, 8.8), 1)
            r = milk_rate(fat, snf)
            clr = round(rng.uniform(27.5, 29.5), 1)
            temperature = round(rng.uniform(3.5, 4.5), 1)
            if SEED_PLANT_DATA:
                db.add(MilkProcurement(
                    procurement_batch_no=f"PROC-{ymd}-{vi + 1:02d}", vendor_id=vendor.id, branch_id=1,
                    collection_date=day, collection_shift="Morning", milk_type="cow",
                    quantity_litres=qty, fat_pct=fat, snf_pct=snf, clr_reading=clr,
                    temperature_c=temperature, rate_per_litre=r,
                    total_amount=round(qty * r, 2), quality_status="accepted"
                ))
        if day.day == 18 and SEED_PLANT_DATA:
            # One rejected batch (low fat) - not used in production
            db.add(MilkProcurement(
                procurement_batch_no=f"PROC-{ymd}-04", vendor_id=vendors[2].id, branch_id=1,
                collection_date=day, collection_shift="Evening", milk_type="cow",
                quantity_litres=120.0, fat_pct=2.9, snf_pct=7.8, clr_reading=26.0, temperature_c=6.5,
                rate_per_litre=milk_rate(2.9, 7.8), total_amount=round(120.0 * milk_rate(2.9, 7.8), 2),
                quality_status="rejected"
            ))

        if SEED_PLANT_DATA:
            db.add(ProductionBatch(
                batch_number=f"PB-{ymd}-01", branch_id=1, production_date=day,
                raw_milk_input_litres=raw_input, process_type="Pasteurization & 1L Pouch Packing",
                output_product_id=milk.id, output_quantity=output, output_unit="L", wastage_litres=wastage,
                expiry_date=day + timedelta(days=2), operator_name="Santosh Pawar", status="completed"
            ))

        # Orders + deliveries, one trip per route
        for route_id, route in routes.items():
            route_customers = sorted(
                [c for c in customers.values() if c.assigned_route_id == route_id],
                key=lambda c: c.route_stop_sequence
            )
            vehicle_id = route.default_vehicle_id
            km = round(route.approx_distance_km + rng.uniform(-4, 4), 1)
            mileage = 8.5 if vehicle_id == 1 else 6.5
            diesel_l = round(km / mileage, 1)
            diesel_cost = round(diesel_l * 94.5, 2)
            driver_cost, toll = 700.0, (150.0 if route_id == 1 else 200.0)
            other = 100.0
            total_cost = route.fixed_daily_cost  # fixed transport cost per route per day
            route_litres = sum(daily_qty[c.customer_code][di] for c in route_customers)
            departure = datetime(day.year, day.month, day.day, 4, 30)

            trip = DeliveryTrip(
                trip_number=f"TRIP-{ymd}-{route_id:02d}", route_id=route_id, vehicle_id=vehicle_id,
                driver_id=route.default_driver_id, trip_date=day, departure_time=departure,
                return_time=departure + timedelta(hours=6), opening_km=odometer[vehicle_id],
                closing_km=round(odometer[vehicle_id] + km, 1), total_distance_km=km, diesel_litres=diesel_l,
                diesel_price_per_litre=94.5, diesel_cost=diesel_cost, driver_cost=driver_cost,
                toll_charges=toll, other_expenses=other, total_transport_cost=total_cost,
                total_milk_litres_loaded=route_litres, total_milk_litres_delivered=route_litres,
                transport_cost_per_litre=round(total_cost / route_litres, 3), status="completed"
            )
            odometer[vehicle_id] = round(odometer[vehicle_id] + km, 1)
            db.add(trip)
            db.flush()

            per_litre = total_cost / route_litres
            for seq, c in enumerate(route_customers, start=1):
                qty = daily_qty[c.customer_code][di]
                rate = next(s[8] for s in SAMPLE_CUSTOMERS if s[0] == c.customer_code)
                amount = round(qty * rate, 2)
                order_seq += 1
                order = Order(
                    order_number=f"ORD-{ymd}-{c.customer_code[-3:]}", customer_id=c.id, branch_id=1,
                    order_date=day - timedelta(days=1), delivery_date=day, status="delivered",
                    is_standing_order=False, subtotal=amount, tax_amount=0.0, transport_charge=0.0,
                    total_amount=amount, total_litres=qty, payment_status="pending"
                )
                db.add(order)
                db.flush()
                db.add(OrderItem(order_id=order.id, product_id=milk.id, ordered_quantity=qty, unit_price=rate,
                                 gst_rate=0.0, tax_amount=0.0, total_amount=amount, product_cost_price=MILK_COST_PRICE))
                arrival = departure + timedelta(hours=1, minutes=45 * seq)
                delivery = Delivery(
                    trip_id=trip.id, order_id=order.id, customer_id=c.id, delivery_sequence=seq,
                    status="delivered", arrival_time=arrival, departure_time=arrival + timedelta(minutes=15),
                    total_ordered_litres=qty, total_delivered_litres=qty, total_shortage_litres=0.0,
                    shortage_reason="none", delivered_to_person=c.contact_person
                )
                db.add(delivery)
                db.flush()
                db.add(TransportCostAllocation(
                    trip_id=trip.id, delivery_id=delivery.id, customer_id=c.id, order_id=order.id,
                    delivered_litres=qty, allocation_method="equal_per_litre",
                    cost_per_litre_applied=round(per_litre, 3), distance_km=c.distance_from_plant_km,
                    allocated_transport_cost=round(qty * per_litre, 2)
                ))

    for v in db.query(Vehicle).all():
        v.current_odometer_km = round(odometer[v.id], 1)

    # 6. Accounts: August bill (opening balance) paid on 10 Sep. September is left unbilled so
    #    bills can be generated from the Billing screen (monthly / 15 days / daily).
    for n, (code, c) in enumerate(customers.items(), start=1):
        rate = next(s[8] for s in SAMPLE_CUSTOMERS if s[0] == code)
        august_amount = round(sum(daily_qty[code]) * rate * rng.uniform(0.92, 1.04), 0)
        pay_no = f"PAY-20260910-{n:04d}"
        db.add(Payment(payment_number=pay_no, customer_id=c.id, payment_date=date(2026, 9, 10),
                       amount=august_amount, payment_method="bank_transfer", reference_number=f"NEFT-AUG-{n:03d}",
                       remarks="August 2026 bill"))
        db.add_all([
            CustomerLedger(customer_id=c.id, transaction_date=date(2026, 9, 1), transaction_type="opening_balance",
                           reference_number="OB-SEP-26", debit_amount=august_amount, running_balance=august_amount,
                           narration="Opening balance (August 2026 bill)"),
            CustomerLedger(customer_id=c.id, transaction_date=date(2026, 9, 10), transaction_type="payment",
                           reference_number=pay_no, credit_amount=august_amount, running_balance=0.0,
                           narration="Payment received - August 2026 bill"),
        ])
        c.current_outstanding = 0.0

    db.add(BusinessProfile(**DEFAULT_PROFILE))

    # 7. One resolved complaint
    db.add(CustomerComplaint(
        ticket_number="TKT-20260912-001", customer_id=customers["CUST-003"].id, category="late_delivery",
        subject="Delivery arrived late", description="Milk delivery on 12 Sep arrived 45 minutes late.",
        status="resolved", resolution_notes="Route 01 was delayed by traffic on Sion-Panvel highway. Driver briefed.",
        created_at=datetime(2026, 9, 12, 10, 30)
    ))

    db.commit()
    logger.info("September 2026 sample dataset seeded successfully.")
