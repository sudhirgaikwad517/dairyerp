import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/dairy_logo.dart';
import '../widgets/ui.dart';
import 'bills_screen.dart';
import 'claims_screen.dart';
import 'daily_orders_screen.dart';
import 'error_view.dart';
import 'ledger_screen.dart';
import 'menu_screen.dart';
import 'notifications_screen.dart';
import 'order_history_screen.dart';
import '../widgets/floating_nav_bar.dart';

class CustomerDashboardScreen extends StatefulWidget {
  final void Function(int tab) onOpenTab;

  const CustomerDashboardScreen({super.key, required this.onOpenTab});

  @override
  State<CustomerDashboardScreen> createState() => _CustomerDashboardScreenState();
}

class _CustomerDashboardScreenState extends State<CustomerDashboardScreen> {
  CustomerProfile? _profile;
  List<DayPlan> _days = [];
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
    try {
      final results = await Future.wait([ApiService.getProfile(), ApiService.getDays(days: 7)]);
      setState(() {
        _profile = results[0] as CustomerProfile;
        _days = results[1] as List<DayPlan>;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _push(Widget screen) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
    if (mounted) _load(); // orders / claims may have changed
  }

  void _openNoticeLink(String link) {
    switch (link) {
      case 'orders':
        widget.onOpenTab(1);
      case 'claims':
        widget.onOpenTab(2);
      case 'bills':
        widget.onOpenTab(3);
      case 'statement':
        _push(const LedgerStatementScreen());
    }
  }

  /// Order form for a day straight from Home.
  Future<void> _orderDay(DayPlan day) async {
    final updated = await showDayOrderSheet(context, day);
    if (updated != null) _load();
  }

  /// Tomorrow's order: the order form while it is open, otherwise its details.
  Future<void> _orderNext() async {
    if (_days.isEmpty) return;
    await _orderDay(_days.length > 1 ? _days[1] : _days.first);
  }

  String _cutoffText(CustomerProfile p) {
    if (p.orderCutoffText.isNotEmpty) return 'Order, change or cancel till ${p.orderCutoffText}.';
    final parts = p.orderCutoffTime.split(':');
    final t = DateTime(2000, 1, 1, int.tryParse(parts[0]) ?? 21, int.tryParse(parts.length > 1 ? parts[1] : '0') ?? 0);
    return 'Order, change or cancel till ${DateFormat('h:mm a').format(t)}.';
  }

  @override
  Widget build(BuildContext context) {
    final p = _profile;
    final statusBar = MediaQuery.paddingOf(context).top;
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: p == null ? SystemUiOverlayStyle.dark : SystemUiOverlayStyle.light,
      child: Scaffold(
        body: SafeArea(
          top: p == null,
          bottom: false,
          child: _loading && p == null
              ? const Center(child: CircularProgressIndicator(color: AppTheme.navy))
              : _error != null && p == null
              ? ErrorView(message: _error!, onRetry: _load)
              : Column(
                  children: [
                    // Fixed navy strip behind the status bar: scrolled content never shows under the clock
                    Container(height: statusBar, color: _headerTop),
                    Expanded(
                      child: RefreshIndicator(
                        onRefresh: _load,
                        child: ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: EdgeInsets.zero,
                          children: [
                            _topBar(p!),
                            Padding(
                              padding: EdgeInsets.fromLTRB(16, 16, 16, navBarListPadding(context)),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  InfoBanner(_cutoffText(p), icon: Icons.schedule_rounded),
                                  const SizedBox(height: 16),
                                  _todayCard(),
                                  SectionHeader('Upcoming', onViewAll: () => widget.onOpenTab(1)),
                                  _upcomingStrip(),
                                  const SectionHeader('Quick Actions'),
                                  TileGrid(
                                    children: [
                                      ActionTile(
                                        icon: Icons.add_shopping_cart_outlined,
                                        label: 'Order Milk',
                                        onTap: () => _push(const DailyOrdersScreen()),
                                      ),
                                      ActionTile(
                                        icon: Icons.history,
                                        label: 'Order History',
                                        onTap: () => _push(const OrderHistoryScreen()),
                                      ),
                                      ActionTile(
                                        icon: Icons.report_gmailerrorred,
                                        label: 'Report Problem',
                                        onTap: () => _push(const ClaimsScreen()),
                                      ),
                                      ActionTile(
                                        icon: Icons.receipt_long_outlined,
                                        label: 'Bills',
                                        onTap: () => _push(const BillsScreen()),
                                      ),
                                      ActionTile(
                                        icon: Icons.account_balance_wallet_outlined,
                                        label: 'Ledger',
                                        onTap: () => _push(const LedgerStatementScreen()),
                                      ),
                                      ActionTile(
                                        icon: Icons.grid_view_outlined,
                                        label: 'More',
                                        onTap: () => _push(MenuScreen(onOpenTab: widget.onOpenTab)),
                                      ),
                                    ],
                                  ),
                                  const SectionHeader('My Account'),
                                  _accountCard(p),
                                  if (p.hasBankDetails || p.upiNumber.isNotEmpty) ...[
                                    const SectionHeader('Pay to Dairy'),
                                    _paymentCard(p),
                                  ],
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  static const _headerTop = Color(0xFF0B2545);

  Widget _topBar(CustomerProfile p) {
    final hour = DateTime.now().hour;
    final greet = hour < 12 ? 'Good morning' : (hour < 17 ? 'Good afternoon' : 'Good evening');
    final out = p.currentOutstanding;
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 8, 20),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0B2545), Color(0xFF13406B), Color(0xFF0E7FB5)],
          stops: [0, 0.6, 1],
        ),
        borderRadius: BorderRadius.vertical(bottom: Radius.circular(24)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const DairyLogo(size: 44),
              const SizedBox(width: 10),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Akash Dairy Farm',
                      style: TextStyle(color: Colors.white, fontSize: 15.5, fontWeight: FontWeight.w800),
                    ),
                    Text(
                      'CUSTOMER',
                      style: TextStyle(color: Colors.white70, fontSize: 10.5, fontWeight: FontWeight.w700, letterSpacing: 1),
                    ),
                  ],
                ),
              ),
              NotificationBell(onOpenLink: _openNoticeLink),
              IconButton(
                tooltip: 'Menu',
                icon: const Icon(Icons.menu_rounded, size: 28, color: Colors.white),
                onPressed: () => _push(MenuScreen(onOpenTab: widget.onOpenTab)),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(greet, style: const TextStyle(color: Colors.white70, fontSize: 13)),
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Text(
              p.businessName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w800),
            ),
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _headerChip(Icons.badge_outlined, p.customerCode),
              Material(
                color: Colors.white,
                borderRadius: BorderRadius.circular(20),
                child: InkWell(
                  borderRadius: BorderRadius.circular(20),
                  onTap: () => _push(const LedgerStatementScreen()),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.account_balance_wallet_outlined,
                          size: 16,
                          color: out > 0 ? AppTheme.alertRose : AppTheme.freshGreen,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          out > 0 ? 'Due ${rupees(out)}' : (out < 0 ? 'Advance ${rupees(-out)}' : 'No dues'),
                          style: TextStyle(
                            fontWeight: FontWeight.w700,
                            fontSize: 13,
                            color: out > 0 ? AppTheme.alertRose : AppTheme.freshGreen,
                          ),
                        ),
                        const Icon(Icons.chevron_right, size: 18, color: AppTheme.textMuted),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _headerChip(IconData icon, String text) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(20)),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 15, color: Colors.white),
        const SizedBox(width: 5),
        Text(
          text,
          style: const TextStyle(color: Colors.white, fontSize: 12.5, fontWeight: FontWeight.w600),
        ),
      ],
    ),
  );

  Widget _todayCard() {
    final d = _days.isEmpty ? null : _days.first;
    final delivered = d != null && d.status == 'delivered';
    final hasOrder = d != null && d.hasOrder;
    final (statusText, statusColor) = d == null ? ('No order', AppTheme.textMuted) : dayStatus(d);
    final tomorrow = _days.length > 1 ? _days[1] : null;
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: d == null ? null : () => _orderDay(d),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    "Today's Delivery • ${DateFormat('dd MMM').format(DateTime.now())}",
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                  ),
                  StatusChip(statusText, color: statusColor),
                ],
              ),
              const SizedBox(height: 14),
              if (hasOrder) ...[
                FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerLeft,
                  child: Text(
                    rupees(d.totalAmount),
                    style: const TextStyle(fontSize: 30, fontWeight: FontWeight.w800, color: AppTheme.navy, height: 1),
                  ),
                ),
                const SizedBox(height: 8),
                for (final i in d.items)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Text(
                      '${qtyUnit(i.quantity, i.unit)}  ${i.productName}',
                      style: const TextStyle(color: AppTheme.textMain, fontSize: 13.5, height: 1.3),
                    ),
                  ),
              ] else
                const Text(
                  'No delivery today',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: AppTheme.textMuted),
                ),
              if (delivered && d.deliveredShort)
                Padding(
                  padding: const EdgeInsets.only(top: 6),
                  child: Text(
                    'Delivered ${d.deliveredWhat} (less than ordered)',
                    style: const TextStyle(color: AppTheme.warmAmber, fontSize: 13),
                  ),
                ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: _orderNext,
                      icon: Icon(
                        tomorrow != null && tomorrow.hasOrder ? Icons.receipt_long_outlined : Icons.add_shopping_cart_outlined,
                        size: 18,
                      ),
                      label: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          tomorrow != null && tomorrow.hasOrder
                              ? 'Tomorrow ${rupees(tomorrow.totalAmount)} • ${tomorrow.editable ? 'Change' : 'View'}'
                              : 'Order for Tomorrow',
                        ),
                      ),
                    ),
                  ),
                  if (delivered) ...[
                    const SizedBox(width: 10),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => _push(const ClaimsScreen()),
                        icon: const Icon(Icons.report_gmailerrorred, size: 18),
                        label: const Text('Report Issue'),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _upcomingStrip() {
    final upcoming = _days.skip(1).toList();
    return SizedBox(
      height: 118,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.zero,
        itemCount: upcoming.length,
        separatorBuilder: (_, _) => const SizedBox(width: 10),
        itemBuilder: (_, i) {
          final d = upcoming[i];
          return Material(
            color: Colors.white,
            borderRadius: BorderRadius.circular(14),
            child: InkWell(
              borderRadius: BorderRadius.circular(14),
              onTap: () => _orderDay(d),
              child: Container(
                width: 116,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: d.hasOrder ? AppTheme.primaryBlue.withValues(alpha: 0.4) : AppTheme.border),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      DateFormat('EEE').format(d.day).toUpperCase(),
                      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: AppTheme.textMuted),
                    ),
                    Text(DateFormat('dd MMM').format(d.day), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                    d.hasOrder
                        ? Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              FittedBox(
                                fit: BoxFit.scaleDown,
                                alignment: Alignment.centerLeft,
                                child: Text(
                                  rupees(d.totalAmount),
                                  maxLines: 1,
                                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: AppTheme.navy),
                                ),
                              ),
                              Row(
                                children: [
                                  Icon(
                                    d.editable ? Icons.edit_outlined : Icons.lock_outline,
                                    size: 13,
                                    color: d.editable ? AppTheme.primaryBlue : AppTheme.textMuted,
                                  ),
                                  const SizedBox(width: 3),
                                  Text(
                                    d.editable ? 'Change' : 'Locked',
                                    style: TextStyle(
                                      fontSize: 11.5,
                                      fontWeight: FontWeight.w600,
                                      color: d.editable ? AppTheme.primaryBlue : AppTheme.textMuted,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          )
                        : Row(
                            children: [
                              Icon(
                                d.editable ? Icons.add_circle_outline : Icons.lock_outline,
                                size: 16,
                                color: d.editable ? AppTheme.primaryBlue : AppTheme.textMuted,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                d.editable ? 'Order' : 'Closed',
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: d.editable ? AppTheme.primaryBlue : AppTheme.textMuted,
                                ),
                              ),
                            ],
                          ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _paymentCard(CustomerProfile p) {
    Widget row(IconData icon, String label, String value, {bool copy = true}) {
      if (value.isEmpty) return const SizedBox.shrink();
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          children: [
            Icon(icon, size: 20, color: AppTheme.textMuted),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                  Text(value, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                ],
              ),
            ),
            if (copy)
              IconButton(
                tooltip: 'Copy $label',
                icon: const Icon(Icons.copy_rounded, size: 18, color: AppTheme.primaryBlue),
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: value));
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$label copied')));
                },
              ),
          ],
        ),
      );
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 12, 8, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (p.upiNumber.isNotEmpty) ...[
              row(Icons.qr_code_2, 'Google Pay / PhonePe', p.upiNumber),
              if (p.hasBankDetails) const Divider(height: 16),
            ],
            if (p.hasBankDetails) ...[
              row(Icons.account_balance_outlined, 'Account Name', p.bankAccountName, copy: false),
              row(
                Icons.account_balance_outlined,
                'Bank',
                [p.bankName, p.bankBranch].where((x) => x.isNotEmpty).join(', '),
                copy: false,
              ),
              row(Icons.numbers, 'Account Number', p.bankAccountNumber),
              row(Icons.qr_code, 'IFSC', p.bankIfsc),
            ],
          ],
        ),
      ),
    );
  }

  Widget _accountCard(CustomerProfile p) {
    final out = p.currentOutstanding;
    final hasLimit = p.creditLimit > 0;
    final available = p.creditLimit - out;
    Widget figure(String label, String value, {Color color = AppTheme.textMain}) => Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
          const SizedBox(height: 4),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(
              value,
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: color),
            ),
          ),
        ],
      ),
    );
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => _push(const LedgerStatementScreen()),
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              figure(
                out < 0 ? 'Advance' : 'Outstanding',
                rupees(out.abs()),
                color: out > 0 ? AppTheme.alertRose : AppTheme.freshGreen,
              ),
              figure('Credit Limit', hasLimit ? rupees(p.creditLimit) : 'No limit'),
              if (hasLimit) figure('Available', rupees(available < 0 ? 0 : available)),
            ],
          ),
        ),
      ),
    );
  }
}
