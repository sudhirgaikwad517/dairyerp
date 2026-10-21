import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../widgets/dev_credit.dart';
import '../widgets/legal_links.dart';
import '../main.dart';
import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/change_password_dialog.dart';
import '../widgets/ui.dart';
import 'bills_screen.dart';
import 'claims_screen.dart';
import 'daily_orders_screen.dart';
import 'ledger_screen.dart';
import 'order_history_screen.dart';

/// Everything in one place, grouped like the dairy's paper processes.
class MenuScreen extends StatefulWidget {
  final void Function(int tab) onOpenTab;

  const MenuScreen({super.key, required this.onOpenTab});

  @override
  State<MenuScreen> createState() => _MenuScreenState();
}

class _MenuScreenState extends State<MenuScreen> {
  CustomerProfile? _profile;

  @override
  void initState() {
    super.initState();
    ApiService.getProfile().then((p) {
      if (mounted) setState(() => _profile = p);
    }).catchError((_) {});
  }

  void _push(Widget screen) => Navigator.push(context, MaterialPageRoute(builder: (_) => screen));

  Future<void> _callDairy() async {
    final numbers = (_profile?.dairyContact ?? '').split(RegExp(r'[/,]')).map((n) => n.replaceAll(RegExp(r'[^0-9+]'), '')).where((n) => n.length >= 10);
    if (numbers.isEmpty) return;
    await launchUrl(Uri(scheme: 'tel', path: numbers.first));
  }

  Future<void> _changePassword() async {
    final changed = await showDialog<bool>(context: context, builder: (_) => const ChangePasswordDialog());
    if (changed == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Password changed'), backgroundColor: AppTheme.freshGreen),
      );
    }
  }

  Future<void> _logout() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Log out?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Log out')),
        ],
      ),
    );
    if (ok == true) {
      if (mounted) Navigator.of(context).popUntil((r) => r.isFirst);
      await AppSession.logout();
    }
  }

  Future<void> _deleteAccount() async {
    final reason = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete my account?'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'The dairy will contact you, settle any unpaid dues or advance, and close your account within 30 days. '
                'Your login and personal details are then deleted. Bills and payments are kept as required by tax law.',
                style: TextStyle(fontSize: 13.5, height: 1.4),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: reason,
                maxLines: 2,
                maxLength: 300,
                decoration: const InputDecoration(labelText: 'Reason (optional)', border: OutlineInputBorder()),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: TextButton.styleFrom(foregroundColor: AppTheme.alertRose),
            child: const Text('Send request'),
          ),
        ],
      ),
    );
    final text = reason.text.trim();
    reason.dispose();
    if (ok != true || !mounted) return;
    try {
      final message = await ApiService.requestAccountDeletion(text);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Request sent'),
          content: Text(message),
          actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK'))],
        ),
      );
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message), backgroundColor: AppTheme.alertRose));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = _profile;
    return Scaffold(
      appBar: AppBar(title: const Text('Menu')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          Card(
            child: ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              leading: const CircleAvatar(
                radius: 26,
                backgroundColor: AppTheme.navy,
                child: Icon(Icons.person, color: Colors.white, size: 30),
              ),
              title: Text(p?.businessName ?? '', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
              subtitle: Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Wrap(
                  spacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    StatusChip(p?.customerCode ?? '', color: AppTheme.primaryBlue),
                    if (p != null && p.milkRate != null) Text('${rupees(p.milkRate!)}/${p.mainProductUnit}'),
                  ],
                ),
              ),
            ),
          ),
          const SectionHeader('Orders'),
          TileGrid(children: [
            ActionTile(icon: Icons.add_shopping_cart_outlined, label: 'Order Milk', onTap: () => _push(const DailyOrdersScreen())),
            ActionTile(icon: Icons.event_note_outlined, label: 'Upcoming Orders', onTap: () => _push(const DailyOrdersScreen())),
            ActionTile(icon: Icons.history, label: 'Order History', onTap: () => _push(const OrderHistoryScreen())),
          ]),
          const SectionHeader('Billing & Invoices'),
          TileGrid(children: [
            ActionTile(icon: Icons.receipt_long_outlined, label: 'Bills', onTap: () => _push(const BillsScreen())),
            ActionTile(icon: Icons.picture_as_pdf_outlined, label: 'Download Statement', onTap: () => _push(const BillsScreen())),
            ActionTile(icon: Icons.account_balance_wallet_outlined, label: 'Ledger', onTap: () => _push(const LedgerStatementScreen())),
          ]),
          const SectionHeader('Help'),
          TileGrid(children: [
            ActionTile(icon: Icons.report_gmailerrorred, label: 'Report Problem', onTap: () => _push(const ClaimsScreen())),
            ActionTile(icon: Icons.fact_check_outlined, label: 'My Claims', onTap: () => _push(const ClaimsScreen())),
            ActionTile(icon: Icons.call_outlined, label: 'Call Dairy', onTap: _callDairy),
          ]),
          const SectionHeader('Account'),
          TileGrid(children: [
            ActionTile(icon: Icons.lock_reset, label: 'Change Password', onTap: _changePassword),
            ActionTile(icon: Icons.logout, label: 'Log Out', iconColor: AppTheme.alertRose, onTap: _logout),
            ActionTile(icon: Icons.no_accounts_outlined, label: 'Delete my account', iconColor: AppTheme.alertRose, onTap: _deleteAccount),
          ]),
          const SectionHeader('Legal'),
          TileGrid(children: [
            ActionTile(icon: Icons.privacy_tip_outlined, label: 'Privacy Policy', onTap: () => openLegalPage(context, '/privacy')),
            ActionTile(icon: Icons.gavel_outlined, label: 'Terms & Conditions', onTap: () => openLegalPage(context, '/terms')),
          ]),
          if (p != null && p.dairyName.isNotEmpty) ...[
            const SizedBox(height: 24),
            Center(
              child: Text([p.dairyName, p.dairyContact, p.dairyEmail].where((x) => x.isNotEmpty).join('\n'),
                  textAlign: TextAlign.center, style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
            ),
          ],
          const SizedBox(height: 16),
          const DevCredit(),
        ],
      ),
    );
  }
}
