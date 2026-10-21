import 'package:flutter/material.dart';

import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/ui.dart';
import 'error_view.dart';

/// Past and upcoming orders, newest first.
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
                  ? ListView(children: const [
                      Padding(padding: EdgeInsets.all(32), child: Center(child: Text('No orders yet.'))),
                    ])
                  : ListView.separated(
                      padding: const EdgeInsets.all(16),
                      itemCount: orders.length,
                      separatorBuilder: (_, _) => const SizedBox(height: 10),
                      itemBuilder: (_, i) {
                        final o = orders[i];
                        final (label, color) = _status(o);
                        return Card(
                          child: ListTile(
                            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                            title: Text(niceDate(o.deliveryDate), style: const TextStyle(fontWeight: FontWeight.w600)),
                            subtitle: Text(o.orderNumber, style: const TextStyle(fontSize: 12)),
                            trailing: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(o.status == 'cancelled' ? '—' : '${o.what} • ${rupees(o.totalAmount)}',
                                    style: const TextStyle(fontWeight: FontWeight.w700, color: AppTheme.navy)),
                                const SizedBox(height: 4),
                                StatusChip(label, color: color),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
            ),
    );
  }
}
