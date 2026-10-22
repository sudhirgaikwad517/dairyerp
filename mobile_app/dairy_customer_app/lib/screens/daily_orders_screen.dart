import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/order_details.dart';
import '../widgets/ui.dart';
import 'error_view.dart';
import '../widgets/floating_nav_bar.dart';

/// Next 14 days of milk. A day's order can be placed, changed or cancelled till its cut-off time;
/// after that it is locked and only shown.
class DailyOrdersScreen extends StatefulWidget {
  const DailyOrdersScreen({super.key});

  @override
  State<DailyOrdersScreen> createState() => _DailyOrdersScreenState();
}

class _DailyOrdersScreenState extends State<DailyOrdersScreen> {
  List<DayPlan> _days = [];
  List<ProductItem> _products = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([ApiService.getDays(days: 14), ApiService.getProducts()]);
      setState(() {
        _days = results[0] as List<DayPlan>;
        _products = results[1] as List<ProductItem>;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _open(DayPlan day) async {
    final updated = await showDayOrderSheet(context, day, products: _products);
    if (updated != null) {
      setState(() => _days = _days.map((d) => d.date == updated.date ? updated : d).toList());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My Daily Milk')),
      body: _loading && _days.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : _error != null && _days.isEmpty
          ? ErrorView(message: _error!, onRetry: _load)
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                // Room for the floating bottom bar
                padding: EdgeInsets.fromLTRB(16, 16, 16, navBarListPadding(context)),
                children: [
                  const InfoBanner(
                    'Tap a day to order. You can change or cancel an order till its cut-off time. '
                    'After that it is locked and you can only view it.',
                    icon: Icons.schedule_rounded,
                  ),
                  const SizedBox(height: 12),
                  ..._days.map(_dayTile),
                ],
              ),
            ),
    );
  }

  Widget _dayTile(DayPlan d) {
    final isToday = d.date == ApiService.isoDate(DateTime.now());
    final (label, color) = dayStatus(d);
    final deadline = DateFormat('h:mm a, dd MMM').format(d.orderDeadline);
    final sub = d.status == 'delivered' && d.items.any((i) => i.deliveredQuantity != null)
        ? 'Delivered ${d.deliveredWhat}'
        : d.editable
        ? (d.hasOrder ? 'Change or cancel till $deadline' : 'Order till $deadline')
        : (d.hasOrder ? (d.status == 'out_for_delivery' ? 'On the way' : 'Locked • view only') : 'Orders closed');
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Material(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: () => _open(d),
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: isToday ? AppTheme.primaryBlue : AppTheme.border, width: isToday ? 1.5 : 1),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 46,
                  child: Column(
                    children: [
                      Text(
                        DateFormat('EEE').format(d.day).toUpperCase(),
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: isToday ? AppTheme.primaryBlue : AppTheme.textMuted,
                        ),
                      ),
                      Text(DateFormat('dd').format(d.day), style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
                      Text(DateFormat('MMM').format(d.day), style: const TextStyle(fontSize: 11, color: AppTheme.textMuted)),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: d.hasOrder
                                ? Text(
                                    rupees(d.totalAmount),
                                    style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: AppTheme.navy),
                                  )
                                : Text(
                                    isToday ? 'Today' : 'No order',
                                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: AppTheme.textMuted),
                                  ),
                          ),
                          StatusChip(label, color: color),
                        ],
                      ),
                      if (d.hasOrder) ...[
                        const SizedBox(height: 6),
                        for (final i in d.items)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 2),
                            child: Text(
                              '${qtyUnit(i.quantity, i.unit)}  ${i.productName}',
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 13, color: AppTheme.textMain, height: 1.3),
                            ),
                          ),
                      ],
                      const SizedBox(height: 6),
                      Row(
                        children: [
                          Icon(
                            d.editable ? Icons.edit_calendar_outlined : Icons.lock_outline,
                            size: 15,
                            color: d.editable ? AppTheme.primaryBlue : AppTheme.textMuted,
                          ),
                          const SizedBox(width: 5),
                          Expanded(
                            child: Text(
                              sub,
                              style: TextStyle(fontSize: 12, color: d.editable ? AppTheme.primaryBlue : AppTheme.textMuted),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Status label and colour of a day.
(String, Color) dayStatus(DayPlan d) {
  if (!d.hasOrder) return (d.status == 'cancelled' ? 'Cancelled' : 'No order', AppTheme.textMuted);
  switch (d.status) {
    case 'delivered':
    case 'invoiced':
    case 'paid':
      return ('Delivered', AppTheme.freshGreen);
    case 'out_for_delivery':
      return ('On the way', AppTheme.warmAmber);
    default:
      return d.editable ? ('Ordered', AppTheme.primaryBlue) : ('Locked', AppTheme.navy);
  }
}

List<OrderLineView> dayLines(DayPlan d) => d.items
    .map(
      (i) => OrderLineView(
        name: i.productName,
        unit: i.unit,
        qty: i.quantity,
        rate: i.rate,
        amount: i.amount,
        delivered: i.deliveredQuantity,
      ),
    )
    .toList();

/// Opens a day: the order form while it can still be changed, otherwise its details (read only).
/// Returns the updated day after a save or cancel, or null.
Future<DayPlan?> showDayOrderSheet(BuildContext context, DayPlan day, {List<ProductItem>? products}) async {
  final messenger = ScaffoldMessenger.of(context);
  final when = DateFormat('EEEE, dd MMM').format(day.day);
  if (!day.editable) {
    if (!day.hasOrder) {
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            day.ordersClosed
                ? 'Orders for ${DateFormat('dd MMM').format(day.day)} closed at '
                      '${DateFormat('h:mm a, dd MMM').format(day.orderDeadline)}. Please call the dairy.'
                : 'This day can no longer be ordered.',
          ),
        ),
      );
      return null;
    }
    final (label, color) = dayStatus(day);
    await showOrderDetailsSheet<void>(
      context,
      title: when,
      subtitle: 'Your order',
      statusText: label,
      statusColor: color,
      lines: dayLines(day),
      total: day.totalAmount,
      note: SheetNote(
        day.status == 'delivered'
            ? 'Delivered. You are billed only for what was delivered.'
            : day.status == 'out_for_delivery'
            ? 'Your order is on the way.'
            : 'Locked at ${DateFormat('h:mm a, dd MMM').format(day.orderDeadline)}. Please call the dairy for any change.',
        icon: day.status == 'delivered' ? Icons.check_circle_outline : Icons.lock_outline,
      ),
    );
    return null;
  }
  List<ProductItem> list = products ?? [];
  if (list.isEmpty) {
    try {
      list = await ApiService.getProducts();
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message), backgroundColor: AppTheme.alertRose));
      return null;
    }
  }
  if (!context.mounted) return null;
  final updated = await showModalBottomSheet<DayPlan>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: Colors.white,
    builder: (_) => _DayEditor(day: day, products: list),
  );
  if (updated != null) {
    messenger.showSnackBar(
      SnackBar(
        content: Text(
          updated.hasOrder
              ? '${DateFormat('EEE, dd MMM').format(updated.day)}: order saved, ${rupees(updated.totalAmount)}'
              : '${DateFormat('EEE, dd MMM').format(updated.day)}: order cancelled',
        ),
        backgroundColor: updated.hasOrder ? AppTheme.freshGreen : AppTheme.navy,
      ),
    );
  }
  return updated;
}

class _DayEditor extends StatefulWidget {
  final DayPlan day;
  final List<ProductItem> products;

  const _DayEditor({required this.day, required this.products});

  @override
  State<_DayEditor> createState() => _DayEditorState();
}

class _DayEditorState extends State<_DayEditor> {
  final Map<int, TextEditingController> _qty = {};
  late final List<ProductItem> _products;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    // Products on sale, plus any already on this day's order
    _products = [...widget.products];
    for (final i in widget.day.items) {
      if (!_products.any((p) => p.id == i.productId)) {
        _products.add(
          ProductItem(
            id: i.productId,
            sku: '',
            name: i.productName,
            category: '',
            unit: i.unit,
            packSize: '',
            b2bPrice: i.rate,
            price: i.rate,
          ),
        );
      }
    }
    for (final p in _products) {
      final current = widget.day.items.where((i) => i.productId == p.id).fold(0.0, (sum, i) => sum + i.quantity);
      _qty[p.id] = TextEditingController(text: current > 0 ? qty(current).replaceAll(',', '') : '')
        ..addListener(() => setState(() {}));
    }
  }

  @override
  void dispose() {
    for (final c in _qty.values) {
      c.dispose();
    }
    super.dispose();
  }

  double _value(ProductItem p) => double.tryParse(_qty[p.id]!.text) ?? 0.0;

  /// Rate for a product on this day: the order's own rate if already on it, else today's rate.
  double _rate(ProductItem p) {
    final onOrder = widget.day.items.where((i) => i.productId == p.id);
    return onOrder.isNotEmpty ? onOrder.first.rate : p.price;
  }

  List<OrderLineView> get _lines => _products
      .where((p) => _value(p) > 0)
      .map((p) => OrderLineView(name: p.name, unit: p.unit, qty: _value(p), rate: _rate(p), amount: _value(p) * _rate(p)))
      .toList();

  double get _total => _lines.fold(0.0, (sum, l) => sum + l.amount);

  bool get _isChange => widget.day.hasOrder;

  void _step(ProductItem p, int by) {
    final next = (_value(p) + by).clamp(0, 100000).toDouble();
    _qty[p.id]!.text = next > 0 ? qty(next).replaceAll(',', '') : '';
  }

  Future<void> _save({bool cancel = false}) async {
    final wanted = _products.where((p) => _value(p) > 0).toList();
    if (!cancel) {
      final bad = wanted.where((p) => p.whole && _value(p) != _value(p).roundToDouble()).toList();
      if (bad.isNotEmpty) {
        setState(() => _error = '${bad.first.name} is sold per ${bad.first.unit}; enter a whole number');
        return;
      }
      if (wanted.isEmpty) {
        setState(() => _error = 'Enter a quantity for at least one product');
        return;
      }
    }
    final deadline = DateFormat('h:mm a, dd MMM').format(widget.day.orderDeadline);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(cancel ? 'Cancel this order?' : (_isChange ? 'Save the changes?' : 'Place this order?')),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(DateFormat('EEEE, dd MMM').format(widget.day.day), style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              if (!cancel) OrderLinesTable(lines: _lines, total: _total),
              const SizedBox(height: 10),
              Text(
                cancel
                    ? 'No milk will come on this day. You can order again till $deadline.'
                    : 'You can change or cancel it till $deadline. After that it is locked.',
                style: const TextStyle(fontSize: 13, color: AppTheme.textMuted),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Go back')),
          ElevatedButton(
            style: cancel ? ElevatedButton.styleFrom(backgroundColor: AppTheme.alertRose) : null,
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(cancel ? 'Cancel Order' : (_isChange ? 'Save Changes' : 'Place Order')),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final items = _products.map((p) => {'product_id': p.id, 'quantity': cancel ? 0.0 : _value(p)}).toList();
      final updated = await ApiService.setDay(widget.day.day, items);
      if (mounted) Navigator.pop(context, updated);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // Sizes of one product (500 ML, 1 L) are shown together under the product's name
    final groups = <String, List<ProductItem>>{};
    for (final p in _products) {
      groups.putIfAbsent(p.group, () => []).add(p);
    }
    final lines = _lines;
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.9),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${_isChange ? 'Change order' : 'Order'} • ${DateFormat('EEE, dd MMM').format(widget.day.day)}',
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppTheme.navy),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    'Change or cancel till ${DateFormat('h:mm a, dd MMM').format(widget.day.orderDeadline)} • rates include GST',
                    style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted),
                  ),
                ],
              ),
            ),
            Flexible(
              child: ListView(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 8),
                children: [
                  for (final entry in groups.entries) _groupCard(entry.key, entry.value),
                  if (lines.isNotEmpty) ...[
                    const SizedBox(height: 6),
                    const Text(
                      'ORDER SUMMARY',
                      style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w800,
                        color: AppTheme.textMuted,
                        letterSpacing: 0.6,
                      ),
                    ),
                    const SizedBox(height: 8),
                    OrderLinesTable(lines: lines, total: _total),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 10),
                    Text(_error!, style: const TextStyle(color: AppTheme.alertRose)),
                  ],
                ],
              ),
            ),
            SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    ElevatedButton(
                      onPressed: _saving || lines.isEmpty ? null : () => _save(),
                      child: _saving
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : Text(
                              lines.isEmpty
                                  ? 'Enter a quantity'
                                  : '${_isChange ? 'Save Changes' : 'Place Order'} • ${rupees(_total)}',
                            ),
                    ),
                    if (widget.day.canCancel)
                      TextButton.icon(
                        onPressed: _saving ? null : () => _save(cancel: true),
                        icon: const Icon(Icons.cancel_outlined, size: 18, color: AppTheme.alertRose),
                        label: const Text('Cancel this order', style: TextStyle(color: AppTheme.alertRose)),
                      ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _groupCard(String name, List<ProductItem> items) {
    final hasSizes = items.length > 1 || items.first.variantName.isNotEmpty;
    final desc = items.first.description;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTheme.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 4),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                if (desc.isNotEmpty) Text(desc, style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
              ],
            ),
          ),
          for (final p in items) _sizeRow(p, hasSizes),
          const SizedBox(height: 6),
        ],
      ),
    );
  }

  Widget _sizeRow(ProductItem p, bool hasSizes) {
    final v = _value(p);
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 6, 8, 6),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (hasSizes)
                  Text(
                    p.variantName.isNotEmpty ? p.variantName : p.name,
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                  ),
                Text('${rupees(_rate(p))} / ${p.unit}', style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted)),
                if (v > 0)
                  Text(
                    rupees(v * _rate(p)),
                    style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700, color: AppTheme.primaryBlue),
                  ),
              ],
            ),
          ),
          _stepButton(Icons.remove, v > 0 ? () => _step(p, -1) : null),
          SizedBox(
            width: 72,
            child: TextField(
              controller: _qty[p.id],
              textAlign: TextAlign.center,
              keyboardType: p.whole ? TextInputType.number : const TextInputType.numberWithOptions(decimal: true),
              inputFormatters: [FilteringTextInputFormatter.allow(p.whole ? RegExp(r'^\d*') : RegExp(r'^\d*\.?\d{0,2}'))],
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
              decoration: InputDecoration(
                hintText: '0',
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
                helperText: p.unit,
                helperStyle: const TextStyle(fontSize: 10.5),
                border: const OutlineInputBorder(),
              ),
            ),
          ),
          _stepButton(Icons.add, () => _step(p, 1)),
        ],
      ),
    );
  }

  Widget _stepButton(IconData icon, VoidCallback? onTap) => IconButton(
    onPressed: onTap,
    icon: Icon(icon, size: 20),
    style: IconButton.styleFrom(
      backgroundColor: onTap == null ? null : AppTheme.primaryBlue.withValues(alpha: 0.08),
      foregroundColor: AppTheme.primaryBlue,
    ),
  );
}
