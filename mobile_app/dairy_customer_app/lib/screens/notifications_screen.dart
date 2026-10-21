import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import 'error_view.dart';

/// Opens the app screen a notice points to (orders, bills, claims, statement, delivery).
typedef NoticeLinkHandler = void Function(String link);

/// Bell icon with an unread badge. Checks for new notices every minute while visible.
class NotificationBell extends StatefulWidget {
  final Color color;
  final NoticeLinkHandler onOpenLink;

  const NotificationBell({super.key, this.color = Colors.white, required this.onOpenLink});

  @override
  State<NotificationBell> createState() => _NotificationBellState();
}

class _NotificationBellState extends State<NotificationBell> {
  int _unread = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _refresh();
    _timer = Timer.periodic(const Duration(minutes: 1), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final n = await ApiService.unreadNotifications();
      if (mounted && n != _unread) setState(() => _unread = n);
    } catch (_) {
      // No server right now: keep the last count; the screen itself shows connection errors
    }
  }

  Future<void> _open() async {
    final link = await Navigator.push<String>(context, MaterialPageRoute(builder: (_) => const NotificationsScreen()));
    if (!mounted) return;
    _refresh();
    if (link != null) widget.onOpenLink(link);
  }

  @override
  Widget build(BuildContext context) {
    final badge = _unread > 99 ? '99+' : '$_unread';
    return IconButton(
      tooltip: _unread > 0 ? 'Notifications ($_unread new)' : 'Notifications',
      onPressed: _open,
      icon: Stack(
        clipBehavior: Clip.none,
        children: [
          Icon(_unread > 0 ? Icons.notifications_active_outlined : Icons.notifications_none_rounded, size: 27, color: widget.color),
          if (_unread > 0)
            Positioned(
              right: -5,
              top: -4,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                constraints: const BoxConstraints(minWidth: 18),
                decoration: BoxDecoration(
                  color: AppTheme.alertRose,
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: Colors.white, width: 1.5),
                ),
                child: Text(badge,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Colors.white, fontSize: 10.5, fontWeight: FontWeight.w800, height: 1.2)),
              ),
            ),
        ],
      ),
    );
  }
}

/// List of notices, newest first. Tapping one marks it read and closes with its link.
class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  List<AppNotice>? _items;
  int _unread = 0;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final r = await ApiService.getNotifications();
      if (!mounted) return;
      setState(() {
        _items = r.items;
        _unread = r.unread;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _markAll() async {
    try {
      await ApiService.markAllNotificationsRead();
      if (!mounted) return;
      setState(() {
        _items = _items?.map((n) => n.markedRead()).toList();
        _unread = 0;
      });
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _tap(AppNotice n) async {
    if (!n.read) {
      setState(() {
        _items = _items?.map((x) => x.id == n.id ? x.markedRead() : x).toList();
        _unread = _unread > 0 ? _unread - 1 : 0;
      });
      try {
        await ApiService.markNotificationRead(n.id);
      } catch (_) {
        // Stays unread on the server; it will show again next time
      }
    }
    if (mounted && n.link != null) Navigator.pop(context, n.link);
  }

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          if (_unread > 0)
            TextButton.icon(
              onPressed: _markAll,
              icon: const Icon(Icons.done_all_rounded, size: 19),
              label: const Text('Mark all read'),
            ),
        ],
      ),
      body: _error != null && items == null
          ? ErrorView(message: _error!, onRetry: _load)
          : items == null
              ? const Center(child: CircularProgressIndicator())
              : RefreshIndicator(
                  onRefresh: _load,
                  child: items.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          children: const [
                            SizedBox(height: 120),
                            Icon(Icons.notifications_none_rounded, size: 56, color: AppTheme.textMuted),
                            SizedBox(height: 12),
                            Text('No notifications yet', textAlign: TextAlign.center,
                                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                            SizedBox(height: 4),
                            Padding(
                              padding: EdgeInsets.symmetric(horizontal: 32),
                              child: Text('Deliveries, bills, payments and claim updates will show here.',
                                  textAlign: TextAlign.center, style: TextStyle(color: AppTheme.textMuted)),
                            ),
                          ],
                        )
                      : ListView.separated(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: EdgeInsets.fromLTRB(12, 12, 12, 24 + MediaQuery.paddingOf(context).bottom),
                          itemCount: items.length,
                          separatorBuilder: (_, _) => const SizedBox(height: 8),
                          itemBuilder: (_, i) => _tile(items[i]),
                        ),
                ),
    );
  }

  Widget _tile(AppNotice n) {
    final (icon, color) = noticeStyle(n.kind);
    return Material(
      color: n.read ? Colors.white : const Color(0xFFF1F7FD),
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => _tap(n),
        child: Container(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: n.read ? AppTheme.border : AppTheme.primaryBlue.withValues(alpha: 0.25)),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(12)),
                child: Icon(icon, color: color, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(
                          child: Text(n.title,
                              style: TextStyle(
                                  fontSize: 14.5, fontWeight: n.read ? FontWeight.w600 : FontWeight.w800, color: AppTheme.textMain)),
                        ),
                        if (!n.read)
                          Container(
                            margin: const EdgeInsets.only(left: 6, top: 5),
                            width: 9,
                            height: 9,
                            decoration: const BoxDecoration(color: AppTheme.alertRose, shape: BoxShape.circle),
                          ),
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(n.body, style: const TextStyle(fontSize: 13, color: Color(0xFF334155), height: 1.35)),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Text(noticeTime(n.createdAt), style: const TextStyle(fontSize: 11.5, color: AppTheme.textMuted)),
                        const Spacer(),
                        if (n.link != null)
                          const Row(
                            children: [
                              Text('Open', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: AppTheme.primaryBlue)),
                              Icon(Icons.chevron_right_rounded, size: 18, color: AppTheme.primaryBlue),
                            ],
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
    );
  }
}

(IconData, Color) noticeStyle(String kind) => switch (kind) {
      'delivered' => (Icons.check_circle_outline_rounded, AppTheme.freshGreen),
      'delivered_short' => (Icons.error_outline_rounded, AppTheme.warmAmber),
      'not_delivered' => (Icons.cancel_outlined, AppTheme.alertRose),
      'dispatched' => (Icons.local_shipping_outlined, AppTheme.accentCyan),
      'order_confirmed' => (Icons.event_available_outlined, AppTheme.freshGreen),
      'order_placed' || 'order_changed' => (Icons.edit_calendar_outlined, AppTheme.primaryBlue),
      'order_cancelled' => (Icons.event_busy_outlined, AppTheme.alertRose),
      'bill_created' => (Icons.receipt_long_outlined, AppTheme.primaryBlue),
      'bill_cancelled' => (Icons.receipt_long_outlined, AppTheme.alertRose),
      'payment' || 'payment_collected' => (Icons.payments_outlined, AppTheme.freshGreen),
      'claim_approved' => (Icons.verified_outlined, AppTheme.freshGreen),
      'claim_rejected' => (Icons.block_rounded, AppTheme.alertRose),
      'claim_reopened' => (Icons.history_rounded, AppTheme.warmAmber),
      'claim_new' => (Icons.report_problem_outlined, AppTheme.alertRose),
      'account_deletion' => (Icons.no_accounts_outlined, AppTheme.alertRose),
      'dispatch_held' || 'dispatch_skipped' => (Icons.pause_circle_outline_rounded, AppTheme.warmAmber),
      'delivery_delayed' || 'delivery_issue' => (Icons.running_with_errors_rounded, AppTheme.warmAmber),
      _ => (Icons.notifications_none_rounded, AppTheme.primaryBlue),
    };

String noticeTime(DateTime? t, {DateTime? now}) {
  if (t == null) return '';
  now ??= DateTime.now();
  final diff = now.difference(t);
  if (diff.inMinutes < 1) return 'Just now';
  if (diff.inMinutes < 60) return '${diff.inMinutes} min ago';
  final today = DateTime(now.year, now.month, now.day);
  final day = DateTime(t.year, t.month, t.day);
  final clock = DateFormat('h:mm a').format(t);
  if (day == today) return 'Today, $clock';
  if (day == today.subtract(const Duration(days: 1))) return 'Yesterday, $clock';
  return DateFormat('d MMM, h:mm a').format(t);
}
