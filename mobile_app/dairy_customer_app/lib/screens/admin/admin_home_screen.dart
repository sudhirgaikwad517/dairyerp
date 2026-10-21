import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../models/admin_models.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../utils/format.dart';
import '../../widgets/ui.dart';
import '../error_view.dart';
import 'admin_claims_screen.dart';
import 'admin_customers_screen.dart';
import 'admin_widgets.dart';
import '../../widgets/floating_nav_bar.dart';
import '../notifications_screen.dart';

class AdminHomeScreen extends StatefulWidget {
  final void Function(int tab) onOpenTab;

  const AdminHomeScreen({super.key, required this.onOpenTab});

  @override
  State<AdminHomeScreen> createState() => _AdminHomeScreenState();
}

class _AdminHomeScreenState extends State<AdminHomeScreen> {
  DaySummary? _today;
  DaySummary? _tomorrow;
  List<AdminOrder> _orders = [];
  List<AdminCustomer> _customers = [];
  int _pendingClaims = 0;
  String? _error;
  bool _loading = true;

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
    final today = dateOnly(DateTime.now());
    try {
      final r = await Future.wait([
        ApiService.adminDaySummary(today),
        ApiService.adminDaySummary(today.add(const Duration(days: 1))),
        ApiService.adminOrders(today),
        ApiService.adminCustomers(),
        ApiService.adminPendingClaims(),
      ]);
      setState(() {
        _today = r[0] as DaySummary;
        _tomorrow = r[1] as DaySummary;
        _orders = r[2] as List<AdminOrder>;
        _customers = r[3] as List<AdminCustomer>;
        _pendingClaims = r[4] as int;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _openNoticeLink(String link) {
    switch (link) {
      case 'orders':
        widget.onOpenTab(1);
      case 'delivery':
        widget.onOpenTab(2);
      case 'bills':
        widget.onOpenTab(3);
      case 'claims':
        _push(const AdminClaimsScreen());
      case 'customers':
        _push(const AdminCustomersScreen());
    }
  }

  Future<void> _push(Widget screen) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
    if (mounted) _load();
  }

  @override
  Widget build(BuildContext context) {
    final t = _today;
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: _loading && t == null
            ? const Center(child: CircularProgressIndicator(color: AppTheme.navy))
            : _error != null && t == null
                ? ErrorView(message: _error!, onRetry: _load)
                : RefreshIndicator(
                    onRefresh: _load,
                    child: ListView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: EdgeInsets.zero,
                      children: [
                        _header(),
                        Padding(
                          padding: EdgeInsets.fromLTRB(16, 16, 16, navBarListPadding(context)),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              _todayHero(t!),
                              const SizedBox(height: 12),
                              _kpis(t),
                              if (t.notOrdered.isNotEmpty) ...[
                                const SectionHeader('No order today'),
                                _chips(t.notOrdered),
                              ],
                              const SectionHeader('Tomorrow'),
                              _tomorrowCard(),
                              const SectionHeader('Quick Actions'),
                              TileGrid(children: [
                                ActionTile(icon: Icons.list_alt_outlined, label: "Today's Orders", onTap: () => widget.onOpenTab(1)),
                                ActionTile(icon: Icons.local_shipping_outlined, label: 'Delivery Status', onTap: () => widget.onOpenTab(2)),
                                ActionTile(icon: Icons.receipt_long_outlined, label: 'Bills', onTap: () => widget.onOpenTab(3)),
                                ActionTile(
                                    icon: Icons.report_gmailerrorred,
                                    label: 'Claims',
                                    badge: _pendingClaims > 0 ? '$_pendingClaims' : null,
                                    onTap: () => _push(const AdminClaimsScreen())),
                                ActionTile(icon: Icons.people_alt_outlined, label: 'Customers', onTap: () => _push(const AdminCustomersScreen())),
                                ActionTile(icon: Icons.account_balance_wallet_outlined, label: 'Dues', onTap: () => _push(const AdminCustomersScreen(sortByDues: true))),
                              ]),
                              const SectionHeader('Top Dues'),
                              _topDues(),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
      ),
    );
  }

  Widget _header() {
    final hour = DateTime.now().hour;
    final greet = hour < 12 ? 'Good morning' : (hour < 17 ? 'Good afternoon' : 'Good evening');
    return Container(
      color: Colors.white,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      child: Row(
        children: [
          Container(
            width: 46,
            height: 46,
            decoration: BoxDecoration(color: AppTheme.navy, borderRadius: BorderRadius.circular(10)),
            alignment: Alignment.center,
            child: const Icon(Icons.admin_panel_settings_outlined, color: Colors.white),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('$greet, ${ApiService.userName ?? 'Admin'}',
                    maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                Text('Akash Dairy Farm • ${DateFormat('EEE, dd MMM yyyy').format(DateTime.now())}',
                    style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
              ],
            ),
          ),
          if (_loading) const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
          NotificationBell(color: AppTheme.navy, onOpenLink: _openNoticeLink),
        ],
      ),
    );
  }

  /// Navy card: today's milk, amount and delivery progress.
  Widget _todayHero(DaySummary t) {
    final active = t.customersOrdered;
    final done = t.delivered;
    final progress = active == 0 ? 0.0 : done / active;
    return Material(
      color: AppTheme.navy,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () => widget.onOpenTab(1),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text("TODAY'S MILK", style: TextStyle(color: Colors.white70, fontSize: 12, letterSpacing: 1, fontWeight: FontWeight.w600)),
              const SizedBox(height: 8),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text('${qty(t.totalLitres)} L',
                      style: const TextStyle(color: Colors.white, fontSize: 34, fontWeight: FontWeight.w800, height: 1)),
                  const SizedBox(width: 10),
                  Flexible(
                    child: Text(rupees(t.totalAmount),
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(color: Colors.white70, fontSize: 16, fontWeight: FontWeight.w600)),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text('$active of ${t.activeCustomers} customers ordered',
                  style: const TextStyle(color: Colors.white70, fontSize: 13)),
              const SizedBox(height: 14),
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: progress,
                  minHeight: 8,
                  backgroundColor: Colors.white24,
                  color: AppTheme.freshGreen,
                ),
              ),
              const SizedBox(height: 6),
              Text('$done delivered • ${t.outForDelivery} on the way • ${t.waitingDispatch} not dispatched',
                  style: const TextStyle(color: Colors.white, fontSize: 12.5)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _kpis(DaySummary t) {
    final short = _orders.where((o) => o.isShort || o.notDelivered).length;
    final dues = _customers.fold<double>(0, (s, c) => s + (c.outstanding > 0 ? c.outstanding : 0));
    return Column(
      children: [
        KpiRow(
          KpiCard(
            icon: Icons.local_shipping_outlined,
            label: 'Delivery issues',
            value: '$short',
            sub: short == 0 ? 'No short / missed delivery' : 'short or not delivered',
            color: short == 0 ? AppTheme.freshGreen : AppTheme.alertRose,
            onTap: () => widget.onOpenTab(2),
          ),
          KpiCard(
            icon: Icons.report_gmailerrorred,
            label: 'Claims pending',
            value: '$_pendingClaims',
            sub: _pendingClaims == 0 ? 'Nothing to review' : 'waiting for your decision',
            color: _pendingClaims == 0 ? AppTheme.freshGreen : AppTheme.warmAmber,
            onTap: () => _push(const AdminClaimsScreen()),
          ),
        ),
        const SizedBox(height: 10),
        KpiRow(
          KpiCard(
            icon: Icons.account_balance_wallet_outlined,
            label: 'Total outstanding',
            value: rupees(dues),
            sub: '${_customers.where((c) => c.outstanding > 0).length} customers',
            color: AppTheme.alertRose,
            onTap: () => _push(const AdminCustomersScreen(sortByDues: true)),
          ),
          KpiCard(
            icon: Icons.schedule,
            label: 'Ordering for tomorrow',
            value: (_tomorrow?.customersCanOrder ?? false) ? 'Open' : 'Closed',
            sub: _tomorrow?.orderDeadline == null
                ? null
                : '${(_tomorrow!.customersCanOrder) ? 'until' : 'closed at'} ${DateFormat('h:mm a').format(_tomorrow!.orderDeadline!)}',
            color: (_tomorrow?.customersCanOrder ?? false) ? AppTheme.freshGreen : AppTheme.textMuted,
          ),
        ),
      ],
    );
  }

  Widget _tomorrowCard() {
    final t = _tomorrow;
    if (t == null) return const SizedBox.shrink();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${qty(t.totalLitres)} L ordered',
                      style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppTheme.navy)),
                  if (t.productsText.isNotEmpty)
                    Text(t.productsText, style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                  const SizedBox(height: 2),
                  Text('${t.customersOrdered} of ${t.activeCustomers} customers • ${rupees(t.totalAmount)}',
                      style: const TextStyle(fontSize: 13, color: AppTheme.textMuted)),
                ],
              ),
            ),
            StatusChip(t.customersCanOrder ? 'Still open' : 'Final', color: t.customersCanOrder ? AppTheme.warmAmber : AppTheme.freshGreen),
          ],
        ),
      ),
    );
  }

  Widget _chips(List<String> names) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final n in names)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20), border: Border.all(color: AppTheme.border)),
            child: Text(n, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
          ),
      ],
    );
  }

  Widget _topDues() {
    final list = _customers.where((c) => c.outstanding > 0).toList()..sort((a, b) => b.outstanding.compareTo(a.outstanding));
    if (list.isEmpty) return const Card(child: Padding(padding: EdgeInsets.all(16), child: Text('No dues. Everyone has paid.')));
    return Card(
      child: Column(
        children: [
          for (final c in list.take(5))
            ListTile(
              dense: true,
              title: Text(c.name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
              subtitle: Text(c.routeName, style: const TextStyle(fontSize: 12)),
              trailing: Text(rupees(c.outstanding),
                  style: TextStyle(fontWeight: FontWeight.w700, color: c.overLimit ? AppTheme.alertRose : AppTheme.textMain)),
            ),
        ],
      ),
    );
  }
}
