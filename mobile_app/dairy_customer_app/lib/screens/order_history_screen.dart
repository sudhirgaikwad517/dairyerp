import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/order_details.dart';
import '../widgets/ui.dart';
import 'daily_orders_screen.dart';
import 'error_view.dart';

/// Past and upcoming orders, newest first. Tap an order for its product-wise details.
class OrderHistoryScreen extends StatefulWidget {
  const OrderHistoryScreen({super.key});

  @override
  State<OrderHistoryScreen> createState() => _OrderHistoryScreenState();
}

class _OrderHistoryScreenState extends State<OrderHistoryScreen> {
  List<OrderSummary>? _orders;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final orders = await ApiService.getOrders(limit: 90);
      setState(() {
        _orders = orders;
        _error = null;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    }
  }

  (String, Color) _status(OrderSummary o) {
    switch (o.status) {
      case 'delivered':
      case 'invoiced':
      case 'paid':
        return ('Delivered', AppTheme.freshGreen);
      case 'out_for_delivery':
        return ('On the way', AppTheme.warmAmber);
      case 'cancelled':
        return ('Cancelled', AppTheme.textMuted);
      default:
        return ('Ordered', AppTheme.primaryBlue);
    }
  }

  /// Upcoming orders open the day (to change it while still open); others show their details.
  Future<void> _open(OrderSummary o) async {
    final day = DateTime.parse(o.deliveryDate);
    if (o.status == 'confirmed' || o.status == 'created') {
      try {
        final plan = (await ApiService.getDays(start: day, days: 1)).first;
        if (!mounted) return;
        if (plan.editable) {
          final updated = await showDayOrderSheet(context, plan);
          if (updated != null) _load();
          return;
        }
      } on ApiException catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message), backgroundColor: AppTheme.alertRose));
        }
        return;
      }
    }
    if (!mounted) return;
    final (label, color) = _status(o);
    final delivered = o.isDelivered;
    await showOrderDetailsSheet<void>(
      context,
      title: DateFormat('EEEE, dd MMM yyyy').format(day),
      subtitle: o.orderNumber,
      statusText: label,
      statusColor: color,
      lines: o.items
          .map(
            (i) => OrderLineView(
              name: i.productName,
              unit: i.unit,
              qty: i.quantity,
              rate: i.unitPrice,
              amount: i.totalAmount,
              delivered: delivered ? i.deliveredQuantity : null,
            ),
          )
          .toList(),
      total: o.totalAmount,
      totalLabel: 'Order total',
      note: o.status == 'cancelled'
          ? const SheetNote('This order was cancelled.', icon: Icons.cancel_outlined)
          : delivered && o.items.any((i) => i.deliveredQuantity != null && i.deliveredQuantity! < i.quantity)
          ? const SheetNote(
              'Less was delivered than ordered. You are billed only for what was delivered.',
              icon: Icons.info_outline,
              color: AppTheme.warmAmber,
            )
          : (o.status == 'confirmed' || o.status == 'created')
          ? const SheetNote(
              'Locked: the cut-off time has passed. Please call the dairy for any change.',
              icon: Icons.lock_outline,
            )
          : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    final orders = _orders;
    return Scaffold(
      appBar: AppBar(title: const Text('Order History')),
      body: orders == null
          ? (_error != null ? ErrorView(message: _error!, onRetry: _load) : const Center(child: CircularProgressIndicator()))
          : RefreshIndicator(
              onRefresh: _load,
              child: orders.isEmpty
                  ? ListView(
                      children: const [
                        Padding(
                          padding: EdgeInsets.all(32),
                          child: Center(child: Text('No orders yet.')),
                        ),
                      ],
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.all(16),
                      itemCount: orders.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 10),
                      itemBuilder: (_, i) => _orderCard(orders[i]),
                    ),
            ),
    );
  }

  Widget _orderCard(OrderSummary o) {
    final (label, color) = _status(o);
    final day = DateTime.parse(o.deliveryDate);
    final cancelled = o.status == 'cancelled';
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => _open(o),
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppTheme.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          DateFormat('EEE, dd MMM yyyy').format(day),
                          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
                        ),
                        Text(o.orderNumber, style: const TextStyle(fontSize: 11.5, color: AppTheme.textMuted)),
                      ],
                    ),
                  ),
                  StatusChip(label, color: color),
                ],
              ),
              if (!cancelled && o.items.isNotEmpty) ...[
                const Divider(height: 20),
                for (final i in o.items)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(
                            '${qtyUnit(i.quantity, i.unit)}  ${i.productName}',
                            style: const TextStyle(fontSize: 13.5, height: 1.3),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(rupees(i.totalAmount), style: const TextStyle(fontSize: 13.5, color: AppTheme.textMuted)),
                      ],
                    ),
                  ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    const Expanded(
                      child: Text(
                        'Total',
                        style: TextStyle(fontWeight: FontWeight.w700, color: AppTheme.navy),
                      ),
                    ),
                    Text(
                      rupees(o.totalAmount),
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: AppTheme.navy),
                    ),
                    const SizedBox(width: 4),
                    const Icon(Icons.chevron_right, size: 20, color: AppTheme.textMuted),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
