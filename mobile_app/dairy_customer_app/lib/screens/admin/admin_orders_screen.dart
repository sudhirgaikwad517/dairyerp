import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/admin_models.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../utils/format.dart';
import '../../widgets/ui.dart';
import '../error_view.dart';
import 'admin_widgets.dart';
import '../../widgets/floating_nav_bar.dart';

/// One day's orders, customer-wise: quantity x rate = amount, and the day's total.
class AdminOrdersScreen extends StatefulWidget {
  const AdminOrdersScreen({super.key});

  @override
  State<AdminOrdersScreen> createState() => _AdminOrdersScreenState();
}

class _AdminOrdersScreenState extends State<AdminOrdersScreen> {
  DateTime _day = dateOnly(DateTime.now());
  DaySummary? _summary;
  List<AdminOrder> _orders = [];
  String? _error;
  bool _loading = true;
  String _search = '';

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
      final r = await Future.wait([ApiService.adminDaySummary(day), ApiService.adminOrders(day)]);
      if (day != _day) return; // moved to another day meanwhile
      setState(() {
        _summary = r[0] as DaySummary;
        _orders = (r[1] as List<AdminOrder>)..sort((a, b) => a.customerName.compareTo(b.customerName));
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
    final visible = _orders
        .where((o) => _search.isEmpty || o.customerName.toLowerCase().contains(_search) || o.customerCode.toLowerCase().contains(_search))
        .toList();
    final active = visible.where((o) => !o.isCancelled).toList();
    final totalL = active.fold<double>(0, (s, o) => s + o.totalLitres);
    final totalAmt = active.fold<double>(0, (s, o) => s + o.totalAmount);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Orders'),
        actions: [
          if (_day != dateOnly(DateTime.now()).add(const Duration(days: 1)))
            TextButton(
              onPressed: () => _setDay(dateOnly(DateTime.now()).add(const Duration(days: 1))),
              child: const Text('Tomorrow'),
            ),
          IconButton(
            tooltip: 'Download Excel',
            icon: const Icon(Icons.table_view_outlined, color: AppTheme.freshGreen),
            onPressed: _downloadExcel,
          ),
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
            if (_loading && _summary == null)
              const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator(color: AppTheme.navy)))
            else if (_error != null && _summary == null)
              ErrorView(message: _error!, onRetry: _load)
            else ...[
              _summaryBar(),
              if (_summary!.productsText.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(_summary!.productsText, style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted)),
              ],
              if (_summary!.dispatch != null) ...[
                const SizedBox(height: 12),
                _dispatchCard(_summary!.dispatch!),
              ],
              const SizedBox(height: 12),
              TextField(
                decoration: const InputDecoration(
                  hintText: 'Search customer',
                  prefixIcon: Icon(Icons.search),
                  isDense: true,
                ),
                onChanged: (v) => setState(() => _search = v.trim().toLowerCase()),
              ),
              const SizedBox(height: 12),
              if (visible.isEmpty)
                EmptyNote(_orders.isEmpty ? 'No orders for this day.' : 'No customer matches.')
              else ...[
                for (final o in visible) ...[_orderCard(o), const SizedBox(height: 10)],
                _totalCard(active.length, totalL, totalAmt),
              ],
              if (_summary!.notOrdered.isNotEmpty) ...[
                const SectionHeader('No order from'),
                Text(_summary!.notOrdered.join(', '), style: const TextStyle(color: AppTheme.textMuted, height: 1.4)),
              ],
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _downloadExcel() async {
    final ok = await launchUrl(ApiService.adminOrdersExcelUrl(_day), mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open the download')));
    }
  }

  Widget _dispatchCard(DispatchInfo d) {
    final at = d.dispatchAt == null ? '' : DateFormat('h:mm a, dd MMM').format(d.dispatchAt!);
    final (IconData icon, Color color, String title, String sub) = d.onHold
        ? (Icons.pause_circle_outline_rounded, AppTheme.warmAmber, 'Dispatch on hold', d.holdNote ?? '')
        : d.dispatchedOrders > 0 && d.waitingOrders == 0
            ? (Icons.check_circle_outline_rounded, AppTheme.freshGreen, '${d.dispatchedOrders} order(s) sent to delivery boys',
                d.autoDispatchedAt != null ? 'Automatically at ${DateFormat('h:mm a').format(d.autoDispatchedAt!)}' : '')
            : d.timePassed && d.waitingOrders > 0
                ? (Icons.hourglass_top_rounded, AppTheme.warmAmber, '${d.waitingOrders} order(s) waiting',
                    'They go out within a minute. If not, check the customer\'s route.')
                : (Icons.schedule_rounded, AppTheme.primaryBlue, 'Automatic dispatch at $at',
                    d.waitingOrders > 0 ? '${d.waitingOrders} order(s) will go to the delivery boys' : 'No orders yet');
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, color: color),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14.5)),
                    if (sub.isNotEmpty) Text(sub, style: const TextStyle(color: AppTheme.textMain, fontSize: 13, height: 1.35)),
                    if (d.onHold)
                      Text(d.customersTold ? 'Customers with orders have been told.' : 'Customers are told at $at if the hold is still on.',
                          style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                  ],
                ),
              ),
            ],
          ),
          if (d.canHold) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                OutlinedButton.icon(
                  onPressed: () => _editHold(d),
                  icon: Icon(d.onHold ? Icons.edit_note_rounded : Icons.pause_rounded, size: 18),
                  label: Text(d.onHold ? 'Change note' : 'Hold dispatch'),
                ),
                if (d.onHold)
                  ElevatedButton.icon(
                    onPressed: () => _releaseHold(d),
                    icon: const Icon(Icons.play_arrow_rounded, size: 18),
                    label: Text(d.timePassed ? 'Remove hold & send now' : 'Remove hold'),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _editHold(DispatchInfo d) async {
    final controller = TextEditingController(text: d.holdNote ?? '');
    final note = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(d.onHold ? 'Change hold note' : 'Hold the dispatch'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Delivery boys will not get this day\'s orders until you remove the hold. '
                'Customers with orders see this note at dispatch time.',
                style: TextStyle(fontSize: 13, color: AppTheme.textMuted)),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              autofocus: true,
              maxLines: 3,
              maxLength: 300,
              decoration: const InputDecoration(
                labelText: 'Reason',
                hintText: 'e.g. Milk tanker late, delivery after 8 AM',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, controller.text.trim()), child: const Text('Save')),
        ],
      ),
    );
    controller.dispose();
    if (note == null || !mounted) return;
    if (note.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Write why the milk cannot be dispatched')));
      return;
    }
    try {
      await ApiService.holdDispatch(_day, note);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Dispatch is on hold')));
      _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message), backgroundColor: AppTheme.alertRose));
      }
    }
  }

  Future<void> _releaseHold(DispatchInfo d) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remove the hold?'),
        content: Text(d.timePassed
            ? 'The dispatch time has passed, so the orders go to the delivery boys right now.'
            : 'Orders will go out automatically at the dispatch time.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Remove hold')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await ApiService.releaseDispatchHold(_day);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Hold removed')));
      _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message), backgroundColor: AppTheme.alertRose));
      }
    }
  }

  Widget _summaryBar() {
    final s = _summary!;
    Widget cell(String value, String label) => Expanded(
          child: Column(
            children: [
              FittedBox(
                fit: BoxFit.scaleDown,
                child: Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: Colors.white)),
              ),
              const SizedBox(height: 2),
              Text(label, style: const TextStyle(fontSize: 11.5, color: Colors.white70)),
            ],
          ),
        );
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
      decoration: BoxDecoration(color: AppTheme.navy, borderRadius: BorderRadius.circular(16)),
      child: Row(
        children: [
          cell('${s.customersOrdered}/${s.activeCustomers}', 'Customers'),
          cell('${qty(s.totalLitres)} L', s.productsText.isEmpty ? 'Milk' : 'Milk (all types)'),
          cell(rupees(s.totalAmount), 'Amount'),
        ],
      ),
    );
  }

  Widget _orderCard(AdminOrder o) {
    final (statusText, statusColor) = adminOrderStatus(o);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(o.customerName, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                      const SizedBox(height: 2),
                      Text([o.routeName, o.driverName].whereType<String>().join(' • '),
                          style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                    ],
                  ),
                ),
                StatusChip(statusText, color: statusColor),
              ],
            ),
            if (!o.isCancelled) ...[
              const Divider(height: 20),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      o.multiProduct ? o.what : '${o.what} × ${o.rate != null ? rupees(o.rate!) : 'mixed'}',
                      style: const TextStyle(fontSize: 14, color: AppTheme.textMain),
                    ),
                  ),
                  Text(rupees(o.totalAmount), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: AppTheme.navy)),
                ],
              ),
              if (o.isShort || o.notDelivered)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    o.notDelivered
                        ? 'Not delivered • billed ₹0'
                        : 'Delivered ${o.deliveredWhat} • billed ${rupees(o.amount)}'
                            '${o.shortageReason != null ? ' (${o.shortageReason!.replaceAll('_', ' ')})' : ''}',
                    style: TextStyle(fontSize: 12.5, color: o.notDelivered ? AppTheme.alertRose : AppTheme.warmAmber, fontWeight: FontWeight.w600),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _totalCard(int count, double litres, double amount) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.infoBanner,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('TOTAL', style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 1, color: AppTheme.navy)),
                Text('$count orders • ${qty(litres)} L milk', style: const TextStyle(color: AppTheme.textMain)),
              ],
            ),
          ),
          Text(rupees(amount), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppTheme.navy)),
        ],
      ),
    );
  }
}
