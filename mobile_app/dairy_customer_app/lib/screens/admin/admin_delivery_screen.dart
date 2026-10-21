import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../models/admin_models.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../utils/format.dart';
import '../../widgets/ui.dart';
import '../error_view.dart';
import 'admin_widgets.dart';
import '../../widgets/floating_nav_bar.dart';

/// Route-wise delivery progress for a day: delivered, short, not delivered or still on the way.
class AdminDeliveryScreen extends StatefulWidget {
  const AdminDeliveryScreen({super.key});

  @override
  State<AdminDeliveryScreen> createState() => _AdminDeliveryScreenState();
}

class _AdminDeliveryScreenState extends State<AdminDeliveryScreen> {
  DateTime _day = dateOnly(DateTime.now());
  List<AdminOrder> _orders = [];
  String? _error;
  bool _loading = true;
  DateTime? _updatedAt;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final day = _day;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await ApiService.adminOrders(day);
      if (day != _day) return;
      setState(() {
        _orders = list.where((o) => !o.isCancelled).toList();
        _updatedAt = DateTime.now();
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _setDay(DateTime d) {
    setState(() => _day = d);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final byRoute = <String, List<AdminOrder>>{};
    for (final o in _orders) {
      byRoute.putIfAbsent(o.routeName ?? 'No route', () => []).add(o);
    }
    final delivered = _orders.where((o) => o.isDelivered).length;
    final issues = _orders.where((o) => o.isShort || o.notDelivered).length;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Delivery'),
        actions: [
          IconButton(tooltip: 'Refresh', onPressed: _load, icon: const Icon(Icons.refresh_rounded)),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.fromLTRB(16, 12, 16, navBarListPadding(context)),
          children: [
            DateSwitcher(day: _day, onChanged: _setDay),
            const SizedBox(height: 12),
            if (_loading && _orders.isEmpty && _error == null)
              const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator(color: AppTheme.navy)))
            else if (_error != null && _orders.isEmpty)
              ErrorView(message: _error!, onRetry: _load)
            else if (_orders.isEmpty)
              const EmptyNote('No deliveries for this day.', icon: Icons.local_shipping_outlined)
            else ...[
              KpiRow(
                KpiCard(
                  icon: Icons.check_circle_outline,
                  label: 'Delivered',
                  value: '$delivered / ${_orders.length}',
                  sub: delivered == _orders.length ? 'All stops done' : '${_orders.length - delivered} pending',
                  color: delivered == _orders.length ? AppTheme.freshGreen : AppTheme.primaryBlue,
                ),
                KpiCard(
                  icon: Icons.warning_amber_rounded,
                  label: 'Short / missed',
                  value: '$issues',
                  sub: issues == 0 ? 'No problems' : 'check below',
                  color: issues == 0 ? AppTheme.freshGreen : AppTheme.alertRose,
                ),
              ),
              if (_updatedAt != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text('Updated ${DateFormat('h:mm a').format(_updatedAt!)} • pull down to refresh',
                      style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                ),
              for (final entry in byRoute.entries) _routeSection(entry.key, entry.value),
            ],
          ],
        ),
      ),
    );
  }

  Widget _routeSection(String route, List<AdminOrder> stops) {
    final done = stops.where((o) => o.isDelivered).length;
    final loaded = stops.fold<double>(0, (s, o) => s + o.totalLitres);
    final deliveredL = stops.fold<double>(0, (s, o) => s + (o.deliveredLitres ?? 0));
    final amount = stops.fold<double>(0, (s, o) => s + o.amount);
    final drivers = stops.map((o) => o.driverName).whereType<String>().toSet().join(', ');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SectionHeader(route),
        Card(
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.person_pin_circle_outlined, size: 18, color: AppTheme.textMuted),
                        const SizedBox(width: 6),
                        Expanded(child: Text(drivers.isEmpty ? 'No delivery boy' : drivers, style: const TextStyle(fontWeight: FontWeight.w600))),
                        Text('$done/${stops.length} stops', style: const TextStyle(fontWeight: FontWeight.w700, color: AppTheme.navy)),
                      ],
                    ),
                    const SizedBox(height: 10),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: LinearProgressIndicator(
                        value: stops.isEmpty ? 0 : done / stops.length,
                        minHeight: 7,
                        backgroundColor: AppTheme.border,
                        color: AppTheme.freshGreen,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text('Milk ${qty(deliveredL)} of ${qty(loaded)} L delivered • ${rupees(amount)}',
                        style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted)),
                  ],
                ),
              ),
              const Divider(height: 1),
              for (final o in stops) _stopTile(o),
            ],
          ),
        ),
      ],
    );
  }

  Widget _stopTile(AdminOrder o) {
    final (text, color) = adminOrderStatus(o);
    return ListTile(
      onTap: () => _showStop(o),
      title: Text(o.customerName, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14.5)),
      subtitle: Text(
        o.isDelivered
            ? '${o.deliveredWhat}${o.deliveredAt != null ? ' • ${DateFormat('h:mm a').format(o.deliveredAt!)}' : ''}'
            : '${o.what} ordered',
        style: const TextStyle(fontSize: 12.5),
      ),
      trailing: StatusChip(text, color: color),
    );
  }

  void _showStop(AdminOrder o) {
    final (text, color) = adminOrderStatus(o);
    Widget row(String label, String value) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 5),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(width: 120, child: Text(label, style: const TextStyle(color: AppTheme.textMuted))),
              Expanded(child: Text(value, style: const TextStyle(fontWeight: FontWeight.w600))),
            ],
          ),
        );
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: Colors.white,
      builder: (ctx) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(o.customerName, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800))),
                  StatusChip(text, color: color),
                ],
              ),
              const SizedBox(height: 10),
              row('Ordered', o.what),
              row('Delivered', o.isDelivered ? o.deliveredWhat! : 'Not yet'),
              if (o.isShort) row('Less than ordered', o.shortWhat ?? ''),
              if (o.shortageReason != null) row('Reason', o.shortageReason!.replaceAll('_', ' ')),
              row('Delivery boy', o.driverName ?? '-'),
              if (o.deliveredAt != null) row('Time', DateFormat('dd MMM, h:mm a').format(o.deliveredAt!)),
              if (o.deliveredTo != null && o.deliveredTo!.isNotEmpty) row('Received by', o.deliveredTo!),
              row('Signature', o.hasSignature ? 'Taken' : (o.isDelivered ? 'Not taken' : '-')),
              row('Amount', o.isDelivered ? '${rupees(o.amount)} (billed)' : rupees(o.totalAmount)),
              if (o.billNumber != null) row('Bill', o.billNumber!),
              if (o.photoIds.isNotEmpty) ...[
                const SizedBox(height: 12),
                const Text('Delivery photo', style: TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                PhotoStrip(o.photoIds, size: 110),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
