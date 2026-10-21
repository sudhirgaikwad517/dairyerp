/// Data shown in the admin section of the app (same figures as the web admin panel).
library;

double _d(dynamic v) => (v as num?)?.toDouble() ?? 0.0;
double? _dn(dynamic v) => (v as num?)?.toDouble();
List<int> _ids(dynamic v) => ((v as List?) ?? const []).map((e) => (e as num).toInt()).toList();

/// One delivery day at a glance.
class DaySummary {
  final String date;
  final int activeCustomers;
  final int customersOrdered;
  final List<String> notOrdered;
  final int cancelled;
  final double totalLitres;
  final double totalAmount;
  final Map<String, int> statusCounts;
  final int waitingDispatch;
  final DateTime? orderDeadline;
  final bool customersCanOrder;
  final DispatchInfo? dispatch;
  final String productsText; // 'Cow Milk 120 L • Paneer 3.5 kg' when more than one product

  DaySummary.fromJson(Map<String, dynamic> j)
      : date = j['date'] as String,
        activeCustomers = (j['active_customers'] as num).toInt(),
        customersOrdered = (j['customers_ordered'] as num).toInt(),
        notOrdered = ((j['not_ordered'] as List?) ?? const []).map((x) => (x as Map)['name'] as String).toList(),
        cancelled = (j['cancelled'] as num? ?? 0).toInt(),
        totalLitres = _d(j['total_litres']),
        totalAmount = _d(j['total_amount']),
        statusCounts = ((j['status_counts'] as Map?) ?? const {}).map((k, v) => MapEntry(k as String, (v as num).toInt())),
        waitingDispatch = (j['waiting_dispatch'] as num? ?? 0).toInt(),
        orderDeadline = DateTime.tryParse(j['order_deadline'] as String? ?? ''),
        customersCanOrder = j['customers_can_order'] as bool? ?? false,
        dispatch = j['dispatch'] == null ? null : DispatchInfo.fromJson(j['dispatch'] as Map<String, dynamic>),
        productsText = ((j['products'] as List?) ?? const []).length > 1
            ? (j['products'] as List).map((p) => '${p['product_name']} ${_fmt(p['quantity'])} ${p['unit']}').join(' • ')
            : '';

  int get delivered => statusCounts['delivered'] ?? 0;
  int get outForDelivery => statusCounts['out_for_delivery'] ?? 0;
}

/// A delivery day's automatic dispatch: when it runs, and the admin's hold (with the note customers see).
class DispatchInfo {
  final DateTime? dispatchAt;
  final bool timePassed;
  final bool onHold;
  final String? holdNote;
  final bool customersTold;
  final int waitingOrders;
  final int dispatchedOrders;
  final DateTime? autoDispatchedAt;
  final bool canHold;

  DispatchInfo.fromJson(Map<String, dynamic> j)
      : dispatchAt = DateTime.tryParse(j['dispatch_at'] as String? ?? ''),
        timePassed = j['time_passed'] == true,
        onHold = j['on_hold'] == true,
        holdNote = j['hold_note'] as String?,
        customersTold = j['customers_told'] == true,
        waitingOrders = (j['waiting_orders'] as num? ?? 0).toInt(),
        dispatchedOrders = (j['dispatched_orders'] as num? ?? 0).toInt(),
        autoDispatchedAt = DateTime.tryParse(j['auto_dispatched_at'] as String? ?? ''),
        canHold = j['can_hold'] == true;
}

/// A customer's order for one day, with its delivery.
class AdminOrder {
  final int id;
  final String orderNumber;
  final int customerId;
  final String customerName;
  final String customerCode;
  final String? routeName;
  final String? driverName;
  final String deliveryDate;
  final String status;
  final double totalLitres;
  final double? deliveredLitres;
  final String? deliveryStatus;
  final String? shortageReason;
  final double? rate;
  final double totalAmount;
  final double? billedAmount;
  final String? billNumber;
  final DateTime? deliveredAt;
  final String? deliveredTo;
  final List<int> photoIds;
  final bool hasSignature;
  final String what; // '10 L Cow Milk, 1 kg Paneer'
  final String? deliveredWhat; // set once delivered
  final String? shortWhat;
  final bool shortFlag;
  final bool multiProduct;

  AdminOrder.fromJson(Map<String, dynamic> j)
      : id = (j['id'] as num).toInt(),
        orderNumber = j['order_number'] as String? ?? '',
        customerId = (j['customer_id'] as num).toInt(),
        customerName = j['customer_name'] as String? ?? '',
        customerCode = j['customer_code'] as String? ?? '',
        routeName = j['route_name'] as String?,
        driverName = j['driver_name'] as String?,
        deliveryDate = j['delivery_date'] as String? ?? '',
        status = j['status'] as String? ?? '',
        totalLitres = _d(j['total_litres']),
        deliveredLitres = _dn(j['delivered_litres']),
        deliveryStatus = j['delivery_status'] as String?,
        shortageReason = j['shortage_reason'] as String?,
        rate = _dn(j['rate']),
        totalAmount = _d(j['total_amount']),
        billedAmount = _dn(j['billed_amount']),
        billNumber = j['bill_number'] as String?,
        deliveredAt = DateTime.tryParse(j['delivered_at'] as String? ?? ''),
        deliveredTo = j['delivered_to'] as String?,
        photoIds = _ids(j['photo_ids']),
        hasSignature = j['has_signature'] as bool? ?? false,
        what = j['what'] as String? ?? '',
        deliveredWhat = j['delivered_what'] as String?,
        shortWhat = j['short_what'] as String?,
        shortFlag = j['is_short'] as bool? ?? false,
        multiProduct = j['multi_product'] as bool? ?? false;

  bool get isCancelled => status == 'cancelled';
  // Per product: an order of paneer only has no litres, so litres cannot tell if it was delivered
  bool get isDelivered => deliveredWhat != null;
  bool get notDelivered => isDelivered && (billedAmount ?? 0) <= 0;
  bool get isShort => isDelivered && !notDelivered && shortFlag;
  bool get waitingDispatch => status == 'confirmed' || status == 'created';

  /// What this day adds to the bill (delivered milk), or the order value if not delivered yet.
  double get amount => billedAmount ?? totalAmount;
}

class AdminBill {
  final int id;
  final String invoiceNumber;
  final String billType;
  final String periodLabel;
  final String periodStart;
  final int customerId;
  final String customerName;
  final String customerPhone;
  final double totalQty;
  final double originalQty;
  final double claimsQty;
  final double originalAmount;
  final double claimsAmount;
  final double amount;
  final double advance;
  final double paidAmount;
  final double balanceDue;
  final double excessPaid;
  final String paymentStatus;
  final double currentOutstanding;
  final String invoiceDate;
  final String what;
  final bool multiProduct;

  AdminBill.fromJson(Map<String, dynamic> j)
      : id = (j['id'] as num).toInt(),
        invoiceNumber = j['invoice_number'] as String? ?? '',
        billType = j['bill_type'] as String? ?? '',
        periodLabel = j['period_label'] as String? ?? '',
        periodStart = j['period_start'] as String? ?? '',
        customerId = (j['customer_id'] as num).toInt(),
        customerName = j['customer_name'] as String? ?? '',
        customerPhone = j['customer_phone'] as String? ?? '',
        totalQty = _d(j['total_qty']),
        originalQty = _d(j['original_qty']),
        claimsQty = _d(j['claims_qty']),
        originalAmount = _d(j['original_amount']),
        claimsAmount = _d(j['claims_amount']),
        amount = _d(j['amount']),
        advance = _d(j['advance']),
        paidAmount = _d(j['paid_amount']),
        balanceDue = _d(j['balance_due']),
        excessPaid = _d(j['excess_paid']),
        paymentStatus = j['payment_status'] as String? ?? 'pending',
        currentOutstanding = _d(j['current_outstanding']),
        invoiceDate = j['invoice_date'] as String? ?? '',
        what = j['what'] as String? ?? '${_d(j['total_qty'])} L',
        multiProduct = j['multi_product'] as bool? ?? false;

  String get typeLabel => const {'monthly': 'Monthly', 'fortnightly': '15 Days', 'daily': 'Daily', 'custom': 'Custom'}[billType] ?? billType;
}

class AdminCustomer {
  final int id;
  final String code;
  final String name;
  final String contactPerson;
  final String phone;
  final String address;
  final String routeName;
  final String? driverName;
  final double outstanding;
  final double creditLimit;
  final double? milkRate;
  final String? rateProduct; // 'Cow Milk (/L)'
  final bool isActive;

  AdminCustomer.fromJson(Map<String, dynamic> j)
      : id = (j['id'] as num).toInt(),
        code = j['customer_code'] as String? ?? '',
        name = j['business_name'] as String? ?? '',
        contactPerson = j['contact_person'] as String? ?? '',
        phone = j['phone'] as String? ?? '',
        address = j['delivery_address'] as String? ?? '',
        routeName = j['route_name'] as String? ?? 'Unassigned',
        driverName = j['driver_name'] as String?,
        outstanding = _d(j['current_outstanding']),
        creditLimit = _d(j['credit_limit']),
        milkRate = _dn(j['milk_rate']),
        rateProduct = j['rate_product'] as String?,
        isActive = j['is_active'] as bool? ?? true;

  bool get overLimit => creditLimit > 0 && outstanding > creditLimit;
}

class ClaimDelivery {
  final String? driverName;
  final DateTime? deliveredAt;
  final String status;
  final double orderedLitres;
  final double deliveredLitres;
  final String? deliveredTo;
  final List<int> photoIds;
  final String? signature; // PNG data URL

  ClaimDelivery.fromJson(Map<String, dynamic> j)
      : driverName = j['driver_name'] as String?,
        deliveredAt = DateTime.tryParse(j['delivered_at'] as String? ?? ''),
        status = j['status'] as String? ?? '',
        orderedLitres = _d(j['ordered_litres']),
        deliveredLitres = _d(j['delivered_litres']),
        deliveredTo = j['delivered_to'] as String?,
        photoIds = _ids(j['photo_ids']),
        signature = j['signature'] as String?;
}

class AdminClaim {
  final int id;
  final String claimNumber;
  final String customerName;
  final String customerCode;
  final String issueDate;
  final String reasonLabel;
  final double claimedQty;
  final String productName;
  final String unit;
  final String description;
  final String status;
  final double approvedQty;
  final double rate;
  final double creditAmount;
  final String? adminNote;
  final String? settlement;
  final String? refundMethod;
  final DateTime? createdAt;
  final List<int> photoIds;
  // Only in the detail view
  final String? billedIn;
  final double? billedBalanceDue;
  final double orderedQty;
  final double deliveredQty;
  final double otherClaimsQty;
  final List<ClaimDelivery> deliveries;

  AdminClaim.fromJson(Map<String, dynamic> j)
      : id = (j['id'] as num).toInt(),
        claimNumber = j['claim_number'] as String? ?? '',
        customerName = j['customer_name'] as String? ?? '',
        customerCode = j['customer_code'] as String? ?? '',
        issueDate = j['issue_date'] as String? ?? '',
        reasonLabel = j['reason_label'] as String? ?? '',
        claimedQty = _d(j['claimed_qty']),
        productName = j['product_name'] as String? ?? '',
        unit = j['unit'] as String? ?? 'L',
        description = j['description'] as String? ?? '',
        status = j['status'] as String? ?? 'pending',
        approvedQty = _d(j['approved_qty']),
        rate = _d(j['rate']),
        creditAmount = _d(j['credit_amount']),
        adminNote = j['admin_note'] as String?,
        settlement = j['settlement'] as String?,
        refundMethod = j['refund_method'] as String?,
        createdAt = DateTime.tryParse(j['created_at'] as String? ?? '')?.toLocal(),
        photoIds = _ids(j['photo_ids']),
        billedIn = j['billed_in'] as String?,
        billedBalanceDue = _dn(j['billed_balance_due']),
        orderedQty = _d(j['ordered_qty']),
        deliveredQty = _d(j['delivered_qty']),
        otherClaimsQty = _d(j['other_claims_qty']),
        deliveries = ((j['deliveries'] as List?) ?? const []).map((d) => ClaimDelivery.fromJson(d as Map<String, dynamic>)).toList();

  /// Most that can still be approved for that day.
  double get maxApprovable {
    final left = deliveredQty - otherClaimsQty;
    return left < claimedQty ? (left < 0 ? 0 : left) : claimedQty;
  }

  /// How an approved claim was settled, in the admin's words.
  String get settlementLabel {
    if (status != 'approved') return '';
    if (settlement == 'refund') {
      final how = const {'cash': 'cash', 'upi': 'UPI', 'bank_transfer': 'bank transfer'}[refundMethod] ?? '';
      return how.isEmpty ? 'Refunded' : 'Refunded by $how';
    }
    if (settlement == 'credit_note' || settlement == 'bill') return 'Deducted from bill';
    return 'To be deducted in next bill';
  }
}


String _fmt(dynamic v) {
  final d = (v as num?)?.toDouble() ?? 0.0;
  return d == d.roundToDouble() ? d.toStringAsFixed(0) : d.toStringAsFixed(2).replaceAll(RegExp(r'0+$'), '');
}
