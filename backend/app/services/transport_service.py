from typing import List, Dict, Any

def calculate_trip_transport_cost(
    distance_km: float,
    diesel_litres: float,
    diesel_price: float = 95.0,
    driver_cost: float = 800.0,
    toll_charges: float = 0.0,
    other_expenses: float = 0.0
) -> Dict[str, float]:
    """
    Calculates total transport cost of a trip:
    Total = Diesel Cost + Driver Cost + Toll Charges + Other Expenses
    """
    diesel_cost = round(diesel_litres * diesel_price, 2)
    total_transport_cost = round(diesel_cost + driver_cost + toll_charges + other_expenses, 2)
    return {
        "diesel_cost": diesel_cost,
        "driver_cost": driver_cost,
        "toll_charges": toll_charges,
        "other_expenses": other_expenses,
        "total_transport_cost": total_transport_cost,
    }

def allocate_transport_cost_to_customers(
    trip_total_cost: float,
    total_delivered_litres: float,
    customers_delivered: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Supports 3 Allocation Methods as defined in dairy specification:
    1. Equal per litre: rate = trip_total_cost / total_delivered_litres
    2. Distance based: base_charge + (distance_km * rate_km)
    3. Customer specific: custom negotiated ₹/L rate (e.g. ABC Hotel ₹3/L, Remote ₹7/L)
    """
    equal_rate_per_litre = round(trip_total_cost / max(total_delivered_litres, 1.0), 3)

    allocations = []
    for item in customers_delivered:
        cust_id = item["customer_id"]
        litres = item.get("delivered_litres", 0.0)
        method = item.get("allocation_method", "equal_per_litre")
        distance = item.get("distance_km", 10.0)
        negotiated_rate = item.get("negotiated_rate", 0.0)

        applied_rate = equal_rate_per_litre
        allocated_amount = 0.0

        if method == "customer_specific" and negotiated_rate > 0:
            applied_rate = negotiated_rate
            allocated_amount = round(litres * applied_rate, 2)
        elif method == "distance_based":
            # Example formula: ₹100 base + ₹12/km, weighted by volume proportion
            base_fee = 100.0 + (distance * 12.0)
            applied_rate = round(base_fee / max(litres, 1.0), 3)
            allocated_amount = round(base_fee, 2)
        else:
            # Default: Equal per litre
            applied_rate = equal_rate_per_litre
            allocated_amount = round(litres * equal_rate_per_litre, 2)

        allocations.append({
            "customer_id": cust_id,
            "order_id": item.get("order_id"),
            "delivery_id": item.get("delivery_id"),
            "delivered_litres": litres,
            "allocation_method": method,
            "cost_per_litre_applied": applied_rate,
            "distance_km": distance,
            "allocated_transport_cost": allocated_amount
        })

    return allocations
