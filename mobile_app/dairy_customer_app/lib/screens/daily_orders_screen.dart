import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import 'error_view.dart';
import '../widgets/floating_nav_bar.dart';

/// Next 14 days of milk. The customer can change any day that is not yet out for delivery.
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

  Future<void> _edit(DayPlan day) async {
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
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: AppTheme.primaryBlue.withValues(alpha: 0.08),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Text(
                          'Tap a day to order milk. You can order for a day until the cut-off time the '
                          'evening before. Once placed, an order cannot be changed or cancelled; '
                          'please call the dairy if you need a change.',
                          style: TextStyle(fontSize: 12, color: Colors.black87),
                        ),
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
    final color = !d.hasOrder
        ? Colors.black45
        : (d.status == 'delivered' ? AppTheme.freshGreen : AppTheme.primaryBlue);
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      shape: isToday
          ? RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16), side: const BorderSide(color: AppTheme.primaryBlue, width: 1.5))
          : null,
      child: ListTile(
        onTap: d.editable ? () => _edit(d) : null,
        leading: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(DateFormat('EEE').format(d.day).toUpperCase(),
                style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: isToday ? AppTheme.primaryBlue : Colors.black54)),
            Text(DateFormat('dd').format(d.day), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          ],
        ),
        title: Text(isToday ? 'Today • ${DateFormat('dd MMM').format(d.day)}' : DateFormat('dd MMM yyyy').format(d.day),
            style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(
          d.status == 'delivered' && d.items.any((i) => i.deliveredQuantity != null)
              ? 'Delivered ${d.deliveredWhat}'
              : d.editable
                  ? '${d.statusLabel} • order by ${DateFormat('h:mm a, dd MMM').format(d.orderDeadline)}'
                  : (d.hasOrder ? d.statusLabel : (d.ordersClosed ? 'No order • orders closed' : d.statusLabel)),
          style: TextStyle(color: color, fontSize: 12),
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(d.hasOrder ? (d.items.length == 1 ? d.what : rupees(d.totalAmount)) : '-',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: color)),
            const SizedBox(width: 6),
            Icon(d.editable ? Icons.add_circle_outline : Icons.lock_outline, size: 18, color: d.editable ? AppTheme.primaryBlue : Colors.black26),
          ],
        ),
      ),
    );
  }
}

/// Opens the order form for one day (used by the Orders tab and the Home screen).
/// Returns the updated day after a successful save, or null if closed / not possible.
Future<DayPlan?> showDayOrderSheet(BuildContext context, DayPlan day, {List<ProductItem>? products}) async {
  final messenger = ScaffoldMessenger.of(context);
  if (!day.editable) {
    messenger.showSnackBar(SnackBar(
      content: Text(day.hasOrder
          ? 'You have ordered ${day.what} for ${DateFormat('dd MMM').format(day.day)}. '
              'An order cannot be changed once placed. Please call the dairy.'
          : day.ordersClosed
              ? 'Orders for ${DateFormat('dd MMM').format(day.day)} are closed. Please call the dairy.'
              : 'This day can no longer be ordered.'),
    ));
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
    builder: (_) => _DayEditor(day: day, products: list),
  );
  if (updated != null) {
    messenger.showSnackBar(SnackBar(
      content: Text('${DateFormat('EEE, dd MMM').format(updated.day)}: ${updated.what} ordered'),
      backgroundColor: AppTheme.freshGreen,
    ));
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
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    for (final p in widget.products) {
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

  double get _total => widget.products.fold(0.0, (sum, p) => sum + _value(p) * p.price);

  Future<void> _save() async {
    final wanted = widget.products.where((p) => _value(p) > 0).toList();
    final bad = wanted.where((p) => p.whole && _value(p) != _value(p).roundToDouble()).toList();
    if (bad.isNotEmpty) {
      setState(() => _error = '${bad.first.name} is sold per ${bad.first.unit}; enter a whole number');
      return;
    }
    final summary = wanted.map((p) => '${qtyUnit(_value(p), p.unit)} ${p.name}').join('\n');
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Place this order?'),
        content: Text('${DateFormat('EEEE, dd MMM').format(widget.day.day)}\n$summary\nTotal ${rupees(_total)}\n\n'
            'Once placed, the order cannot be changed or cancelled from the app. Please call the dairy if you need a change.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Go back')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Place Order')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final items = widget.products
          .map((p) => {'product_id': p.id, 'quantity': _value(p)})
          .toList();
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
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(context).viewInsets.bottom + 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Milk for ${DateFormat('EEEE, dd MMM').format(widget.day.day)}',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          ...widget.products.map((p) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: TextField(
                  controller: _qty[p.id],
                  autofocus: p == widget.products.first,
                  keyboardType: p.whole ? TextInputType.number : const TextInputType.numberWithOptions(decimal: true),
                  inputFormatters: [FilteringTextInputFormatter.allow(p.whole ? RegExp(r'^\d*') : RegExp(r'^\d*\.?\d{0,2}'))],
                  decoration: InputDecoration(
                    labelText: '${p.name} (${rupees(p.price)}/${p.unit})',
                    helperText: p.description.isNotEmpty ? p.description : null,
                    suffixText: p.unit,
                    border: const OutlineInputBorder(),
                  ),
                ),
              )),
          Text('Amount: ${rupees(_total)}', textAlign: TextAlign.right, style: const TextStyle(fontWeight: FontWeight.bold)),
          const Text('Rates include GST.', textAlign: TextAlign.right, style: TextStyle(fontSize: 11, color: Colors.black45)),
          if (_error != null) ...[
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: AppTheme.alertRose)),
          ],
          const SizedBox(height: 16),
          Text(
            'Order before ${DateFormat('h:mm a, dd MMM').format(widget.day.orderDeadline)}. '
            'Check the quantity: once placed, the order cannot be changed or cancelled.',
            style: const TextStyle(fontSize: 12, color: Colors.black54),
          ),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _saving || _total <= 0 ? null : () => _save(),
            child: _saving
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Text('Place Order'),
          ),
        ],
      ),
    );
  }
}
