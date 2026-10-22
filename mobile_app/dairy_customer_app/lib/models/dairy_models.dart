import '../utils/format.dart';
double _num(dynamic v) => (v as num?)?.toDouble() ?? 0.0;

class CustomerProfile {
  final int id;
  final String customerCode;
  final String businessName;
  final String contactPerson;
  final String phone;
  final String customerType;
  final double creditLimit;
  final int creditDays;
  final double currentOutstanding;
  final String deliveryAddress;
  final double? milkRate;
  final String mainProductName; // the customer's usual product (whose rate is milkRate)
  final String mainProductUnit;
  final String dairyName;
  final String dairyContact;
  final String dairyEmail;
  final String upiNumber;
  final String orderCutoffTime; // "HH:MM", last time to place / change an order
  final String orderCutoffText; // '1:00 AM on the delivery day'
  final String bankAccountName;
  final String bankName;
  final String bankAccountNumber;
  final String bankIfsc;
  final String bankBranch;

  CustomerProfile({
    required this.id,
    required this.customerCode,
    required this.businessName,
    required this.contactPerson,
    required this.phone,
    required this.customerType,
    required this.creditLimit,
    required this.creditDays,
    required this.currentOutstanding,
    required this.deliveryAddress,
    required this.milkRate,
    required this.dairyName,
    required this.dairyContact,
    this.mainProductName = '',
    this.mainProductUnit = 'L',
    this.dairyEmail = '',
    required this.upiNumber,
    required this.orderCutoffTime,
    this.orderCutoffText = '',
    required this.bankAccountName,
    required this.bankName,
    required this.bankAccountNumber,
    required this.bankIfsc,
    required this.bankBranch,
  });

  bool get hasBankDetails => bankAccountNumber.isNotEmpty;

  factory CustomerProfile.fromJson(Map<String, dynamic> json) {
    return CustomerProfile(
      id: json['id'],
      customerCode: json['customer_code'] ?? '',
      businessName: json['business_name'] ?? '',
      contactPerson: json['contact_person'] ?? '',
      phone: json['phone'] ?? '',
      customerType: json['customer_type'] ?? '',
      creditLimit: _num(json['credit_limit']),
      creditDays: json['credit_days'] ?? 0,
      currentOutstanding: _num(json['current_outstanding']),
      deliveryAddress: json['delivery_address'] ?? '',
      milkRate: (json['milk_rate'] as num?)?.toDouble(),
      dairyName: json['dairy_name'] ?? '',
      dairyContact: json['dairy_contact'] ?? '',
      mainProductName: (json['main_product'] as Map?)?['name'] ?? '',
      mainProductUnit: (json['main_product'] as Map?)?['unit'] ?? 'L',
      dairyEmail: json['dairy_email'] ?? '',
      upiNumber: json['upi_number'] ?? '',
      orderCutoffTime: json['order_cutoff_time'] ?? '21:00',
      orderCutoffText: json['order_cutoff_text'] ?? '',
      bankAccountName: json['bank_account_name'] ?? '',
      bankName: json['bank_name'] ?? '',
      bankAccountNumber: json['bank_account_number'] ?? '',
      bankIfsc: json['bank_ifsc'] ?? '',
      bankBranch: json['bank_branch'] ?? '',
    );
  }
}

class ProductItem {
  final int id;
  final String sku;
  final String name;
  final String category;
  final String unit;
  final String packSize;
  final double b2bPrice;
  final double price; // this customer's rate (GST included)
  final String description;
  final String groupName; // sizes of one product share it ('Cow Milk Brand Pouch')
  final String variantName; // the size, e.g. '500 ML'; empty for a product without sizes

  ProductItem({
    required this.id,
    required this.sku,
    required this.name,
    required this.category,
    required this.unit,
    required this.packSize,
    required this.b2bPrice,
    required this.price,
    this.description = '',
    this.groupName = '',
    this.variantName = '',
  });

  bool get isSpecialPrice => price < b2bPrice;

  /// Group heading in the order form (the product's own name when it has no sizes)
  String get group => groupName.isNotEmpty ? groupName : name;
  bool get whole => wholeUnit(unit);

  factory ProductItem.fromJson(Map<String, dynamic> json) {
    return ProductItem(
      id: json['id'],
      sku: json['sku'] ?? '',
      name: json['product_name'] ?? '',
      category: json['category'] ?? '',
      unit: json['unit'] ?? 'L',
      packSize: json['pack_size'] ?? '',
      b2bPrice: _num(json['standard_b2b_price']),
      price: _num(json['custom_price']),
      description: json['description'] ?? '',
      groupName: json['group_name'] ?? '',
      variantName: json['variant_name'] ?? '',
    );
  }
}

class OrderLine {
  final int productId;
  final String productName;
  final String unit;
  final double quantity;
  final double unitPrice;
  final double totalAmount;
  final double? deliveredQuantity; // set once delivered

  OrderLine({
    required this.productId,
    required this.productName,
    required this.unit,
    required this.quantity,
    required this.unitPrice,
    required this.totalAmount,
    this.deliveredQuantity,
  });

  factory OrderLine.fromJson(Map<String, dynamic> json) {
    return OrderLine(
      productId: json['product_id'],
      productName: json['product_name'] ?? '',
      unit: json['unit'] ?? 'L',
      quantity: _num(json['quantity']),
      unitPrice: _num(json['unit_price']),
      totalAmount: _num(json['total_amount']),
      deliveredQuantity: json['delivered_quantity'] == null ? null : _num(json['delivered_quantity']),
    );
  }
}

class OrderSummary {
  final int id;
  final String orderNumber;
  final String deliveryDate;
  final String status;
  final double totalLitres;
  final double totalAmount;
  final List<OrderLine> items;

  OrderSummary({
    required this.id,
    required this.orderNumber,
    required this.deliveryDate,
    required this.status,
    required this.totalLitres,
    required this.totalAmount,
    required this.items,
  });

  bool get isDelivered => const ['delivered', 'invoiced', 'paid'].contains(status);

  String get statusLabel => status.replaceAll('_', ' ').toUpperCase();

  String get what => itemsText(items.map((i) => (name: i.productName, unit: i.unit, qty: i.quantity)), names: items.length > 1);

  factory OrderSummary.fromJson(Map<String, dynamic> json) {
    return OrderSummary(
      id: json['id'],
      orderNumber: json['order_number'] ?? '',
      deliveryDate: json['delivery_date'] ?? '',
      status: json['status'] ?? '',
      totalLitres: _num(json['total_litres']),
      totalAmount: _num(json['total_amount']),
      items: ((json['items'] as List?) ?? []).map((i) => OrderLine.fromJson(i)).toList(),
    );
  }
}

class OrderResult {
  final OrderSummary order;
  final String? creditWarning;
  OrderResult(this.order, this.creditWarning);
}

class LedgerTransaction {
  final int id;
  final String date;
  final String type;
  final String refNo;
  final String narration;
  final double debit;
  final double credit;
  final double balance;

  LedgerTransaction({
    required this.id,
    required this.date,
    required this.type,
    required this.refNo,
    required this.narration,
    required this.debit,
    required this.credit,
    required this.balance,
  });

  factory LedgerTransaction.fromJson(Map<String, dynamic> json) {
    return LedgerTransaction(
      id: json['id'] ?? 0,
      date: json['date'] ?? '',
      type: json['type'] ?? '',
      refNo: json['ref_no'] ?? '',
      narration: json['narration'] ?? '',
      debit: _num(json['debit']),
      credit: _num(json['credit']),
      balance: _num(json['balance']),
    );
  }
}

class LedgerStatement {
  final double currentOutstanding;
  final double creditLimit;
  final List<LedgerTransaction> transactions;

  LedgerStatement({required this.currentOutstanding, required this.creditLimit, required this.transactions});

  factory LedgerStatement.fromJson(Map<String, dynamic> json) {
    return LedgerStatement(
      currentOutstanding: _num(json['current_outstanding']),
      creditLimit: _num(json['credit_limit']),
      transactions: ((json['ledger'] as List?) ?? []).map((t) => LedgerTransaction.fromJson(t)).toList(),
    );
  }
}

class DayItem {
  final int productId;
  final String productName;
  final String unit;
  final double quantity;
  final double rate;
  final double amount;
  final double? deliveredQuantity;
  final double litres; // milk in this line (500 pouches of 500 ML = 250 L); 0 for non-milk

  DayItem({required this.productId, required this.productName, required this.unit, required this.quantity, required this.rate,
      double? amount, this.deliveredQuantity, this.litres = 0})
      : amount = amount ?? quantity * rate;

  factory DayItem.fromJson(Map<String, dynamic> json) => DayItem(
        productId: json['product_id'],
        productName: json['product_name'] ?? '',
        unit: json['unit'] ?? 'L',
        quantity: _num(json['quantity']),
        rate: _num(json['rate']),
        amount: json['amount'] == null ? null : _num(json['amount']),
        deliveredQuantity: json['delivered_quantity'] == null ? null : _num(json['delivered_quantity']),
        litres: _num(json['litres']),
      );
}

/// '10 L Cow Milk, 1.5 kg Paneer' (one product: just '10 L')
String itemsText(Iterable<({String name, String unit, double qty})> items, {bool names = true}) {
  final list = items.where((i) => i.qty > 0).toList();
  if (list.isEmpty) return '-';
  if (list.length == 1 && !names) return qtyUnit(list.first.qty, list.first.unit);
  return list.map((i) => '${qtyUnit(i.qty, i.unit)} ${i.name}').join(', ');
}

/// One day's milk: the customer's own order, a skipped day, or the fixed schedule.
class DayPlan {
  final String date;
  final String dayName;
  final List<DayItem> items;
  final double totalQty;
  final double totalAmount;
  final double totalLitres;
  final String source; // order | none
  final String status;
  final bool editable; // the customer can still place / change / cancel (till the cut-off)
  final bool canCancel;
  final bool ordersClosed;
  final DateTime orderDeadline; // last time the customer can place / change this day's order
  final double? deliveredLitres;

  DayPlan({
    required this.date,
    required this.dayName,
    required this.items,
    required this.totalQty,
    required this.totalAmount,
    this.totalLitres = 0,
    required this.source,
    required this.status,
    required this.editable,
    this.canCancel = false,
    required this.ordersClosed,
    required this.orderDeadline,
    required this.deliveredLitres,
  });

  bool get hasOrder => items.isNotEmpty;

  /// What was ordered ('10 L' for one product, '10 L Cow Milk, 1 kg Paneer' for more)
  String get what => itemsText(items.map((i) => (name: i.productName, unit: i.unit, qty: i.quantity)), names: items.length > 1);

  /// What reached the customer, once delivered
  String get deliveredWhat =>
      itemsText(items.map((i) => (name: i.productName, unit: i.unit, qty: i.deliveredQuantity ?? 0)), names: items.length > 1);

  bool get deliveredShort => items.any((i) => i.deliveredQuantity != null && i.deliveredQuantity! < i.quantity);

  DateTime get day => DateTime.parse(date);

  String get statusLabel {
    switch (status) {
      case 'no_order':
        return 'No order';
      case 'cancelled':
        return 'Cancelled by dairy';
      case 'confirmed':
      case 'created':
        return 'Ordered';
      case 'out_for_delivery':
        return 'Out for delivery';
      case 'delivered':
      case 'invoiced':
      case 'paid':
        return 'Delivered';
      default:
        return status.replaceAll('_', ' ');
    }
  }

  factory DayPlan.fromJson(Map<String, dynamic> json) => DayPlan(
        date: json['date'],
        dayName: json['day_name'] ?? '',
        items: ((json['items'] as List?) ?? []).map((i) => DayItem.fromJson(i)).toList(),
        totalQty: _num(json['total_qty']),
        totalAmount: _num(json['total_amount']),
        totalLitres: _num(json['total_litres']),
        source: json['source'] ?? 'none',
        status: json['status'] ?? '',
        editable: json['editable'] == true,
        canCancel: json['can_cancel'] == true,
        ordersClosed: json['orders_closed'] == true,
        orderDeadline: DateTime.parse(json['order_deadline']),
        deliveredLitres: json['delivery'] == null ? null : _num(json['delivery']['delivered_litres']),
      );
}

/// A product delivered on a day that a problem can be reported for.
class ClaimProduct {
  final int productId;
  final String name;
  final String unit;
  final double deliveredQty;
  final double availableQty;
  final double rate;

  ClaimProduct({required this.productId, required this.name, required this.unit, required this.deliveredQty,
      required this.availableQty, required this.rate});

  bool get whole => wholeUnit(unit);

  factory ClaimProduct.fromJson(Map<String, dynamic> json) => ClaimProduct(
        productId: json['product_id'],
        name: json['product_name'] ?? '',
        unit: json['unit'] ?? 'L',
        deliveredQty: _num(json['delivered']),
        availableQty: _num(json['available_qty']),
        rate: _num(json['rate']),
      );
}

class ClaimableDay {
  final String date;
  final double deliveredQty;
  final double availableQty;
  final double rate;
  final List<ClaimProduct> products;

  ClaimableDay({required this.date, required this.deliveredQty, required this.availableQty, required this.rate,
      this.products = const []});

  factory ClaimableDay.fromJson(Map<String, dynamic> json) => ClaimableDay(
        date: json['date'],
        deliveredQty: _num(json['delivered_qty']),
        availableQty: _num(json['available_qty']),
        rate: _num(json['rate']),
        products: ((json['products'] as List?) ?? []).map((p) => ClaimProduct.fromJson(p)).toList(),
      );

  String get deliveredText => products.isEmpty
      ? qtyUnit(deliveredQty, 'L')
      : itemsText(products.map((p) => (name: p.name, unit: p.unit, qty: p.deliveredQty)), names: products.length > 1);
}

class ClaimOptions {
  final Map<String, String> reasons;
  final List<ClaimableDay> days;

  ClaimOptions({required this.reasons, required this.days});

  factory ClaimOptions.fromJson(Map<String, dynamic> json) => ClaimOptions(
        reasons: Map<String, String>.from(json['reasons'] ?? {}),
        days: ((json['days'] as List?) ?? []).map((d) => ClaimableDay.fromJson(d)).toList(),
      );
}

class ClaimItem {
  final int id;
  final String claimNumber;
  final String issueDate;
  final String reasonLabel;
  final double claimedQty;
  final String description;
  final String status; // pending | approved | rejected
  final double approvedQty;
  final double creditAmount;
  final String? adminNote;
  final String settlementText;
  final List<int> photoIds;
  final String productName;
  final String unit;

  ClaimItem({
    required this.id,
    required this.claimNumber,
    required this.issueDate,
    required this.reasonLabel,
    required this.claimedQty,
    required this.description,
    required this.status,
    required this.approvedQty,
    required this.creditAmount,
    required this.adminNote,
    required this.settlementText,
    required this.photoIds,
    this.productName = '',
    this.unit = 'L',
  });

  factory ClaimItem.fromJson(Map<String, dynamic> json) => ClaimItem(
        id: json['id'],
        claimNumber: json['claim_number'] ?? '',
        issueDate: json['issue_date'] ?? '',
        reasonLabel: json['reason_label'] ?? '',
        claimedQty: _num(json['claimed_qty']),
        description: json['description'] ?? '',
        status: json['status'] ?? 'pending',
        approvedQty: _num(json['approved_qty']),
        creditAmount: _num(json['credit_amount']),
        adminNote: json['admin_note'],
        settlementText: json['settlement_text'] ?? '',
        photoIds: ((json['photo_ids'] as List?) ?? []).cast<int>(),
        productName: json['product_name'] ?? '',
        unit: json['unit'] ?? 'L',
      );
}

/// A bill's quantity of one product.
class BillProduct {
  final String product;
  final String unit;
  final double qty;

  BillProduct(this.product, this.unit, this.qty);

  factory BillProduct.fromJson(Map<String, dynamic> j) => BillProduct(j['product'] ?? '', j['unit'] ?? 'L', _num(j['qty']));
}

/// A claim listed on a bill: deducted in it, or refunded separately.
class BillAdjustment {
  final String product;
  final String unit;
  final double claimQty;
  final double amount;
  final bool refunded;

  BillAdjustment(this.product, this.unit, this.claimQty, this.amount, this.refunded);

  factory BillAdjustment.fromJson(Map<String, dynamic> j) =>
      BillAdjustment(j['product'] ?? '', j['unit'] ?? 'L', _num(j['claim_qty']), _num(j['amount']), j['mode'] == 'refunded');

  String get text => '${qtyUnit(claimQty, unit)}${product.isNotEmpty ? ' $product' : ''}';
}

class BillItem {
  final int id;
  final String invoiceNumber;
  final String periodLabel;
  final double totalQty;
  final double amount;
  final double balanceDue;
  final String paymentStatus;
  final double originalQty;
  final double claimsQty;
  final double claimsAmount;
  final double advance;
  final double paidAmount;
  final double excessPaid;
  final double refundedQty; // claims paid back separately: listed on the bill, not deducted
  final double refundedAmount;
  final List<BillProduct> products;
  final List<BillAdjustment> adjustments;

  BillItem({
    required this.id,
    required this.invoiceNumber,
    required this.periodLabel,
    required this.totalQty,
    required this.amount,
    required this.balanceDue,
    required this.paymentStatus,
    this.originalQty = 0,
    this.claimsQty = 0,
    this.claimsAmount = 0,
    this.advance = 0,
    this.paidAmount = 0,
    this.excessPaid = 0,
    this.refundedQty = 0,
    this.refundedAmount = 0,
    this.products = const [],
    this.adjustments = const [],
  });

  /// '816 L' for one product, '300 L Cow Milk, 12 kg Paneer' for several
  String get what => products.isEmpty
      ? qtyUnit(totalQty, 'L')
      : itemsText(products.map((p) => (name: p.product, unit: p.unit, qty: p.qty)), names: products.length > 1);

  bool get isPaid => balanceDue <= 0;
  bool get isPartPaid => !isPaid && paidAmount + advance > 0;

  factory BillItem.fromJson(Map<String, dynamic> json) => BillItem(
        id: json['id'],
        invoiceNumber: json['invoice_number'] ?? '',
        periodLabel: json['period_label'] ?? '',
        totalQty: _num(json['total_qty']),
        amount: _num(json['amount']),
        balanceDue: _num(json['balance_due']),
        paymentStatus: json['payment_status'] ?? '',
        originalQty: _num(json['original_qty']),
        claimsQty: _num(json['claims_qty']),
        claimsAmount: _num(json['claims_amount']),
        advance: _num(json['advance']),
        paidAmount: _num(json['paid_amount']),
        excessPaid: _num(json['excess_paid']),
        refundedQty: _refunded(json, 'claim_qty'),
        refundedAmount: _refunded(json, 'amount'),
        products: ((json['products'] as List?) ?? []).map((p) => BillProduct.fromJson(p)).toList(),
        adjustments: ((json['adjustments'] as List?) ?? []).map((a) => BillAdjustment.fromJson(a)).toList(),
      );

  static double _refunded(Map<String, dynamic> json, String field) => ((json['adjustments'] as List?) ?? [])
      .where((a) => a['mode'] == 'refunded')
      .fold(0.0, (s, a) => s + _num(a[field]));
}


/// One bell notification.
class AppNotice {
  final int id;
  final String kind;
  final String title;
  final String body;
  final String? link; // orders, bills, claims, statement, delivery
  final DateTime? createdAt; // local time
  final bool read;

  AppNotice({required this.id, required this.kind, required this.title, required this.body,
      this.link, this.createdAt, required this.read});

  factory AppNotice.fromJson(Map<String, dynamic> j) => AppNotice(
        id: (j['id'] as num).toInt(),
        kind: j['kind'] as String? ?? '',
        title: j['title'] as String? ?? '',
        body: j['body'] as String? ?? '',
        link: j['link'] as String?,
        createdAt: j['created_at'] == null ? null : DateTime.tryParse(j['created_at'] as String)?.toLocal(),
        read: j['read'] == true,
      );

  AppNotice markedRead() => AppNotice(id: id, kind: kind, title: title, body: body, link: link, createdAt: createdAt, read: true);
}

class NoticeList {
  final int unread;
  final List<AppNotice> items;

  NoticeList(this.unread, this.items);

  factory NoticeList.fromJson(Map<String, dynamic> j) => NoticeList(
        (j['unread'] as num? ?? 0).toInt(),
        ((j['items'] as List?) ?? []).map((e) => AppNotice.fromJson(e as Map<String, dynamic>)).toList(),
      );
}
