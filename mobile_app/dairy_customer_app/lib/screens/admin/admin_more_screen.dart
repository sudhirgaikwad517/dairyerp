import 'package:flutter/material.dart';

import '../../widgets/dev_credit.dart';
import '../../main.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/change_password_dialog.dart';
import '../../widgets/ui.dart';
import 'admin_claims_screen.dart';
import 'admin_customers_screen.dart';
import '../../widgets/floating_nav_bar.dart';
import '../../widgets/legal_links.dart';

class AdminMoreScreen extends StatefulWidget {
  const AdminMoreScreen({super.key});

  @override
  State<AdminMoreScreen> createState() => _AdminMoreScreenState();
}

class _AdminMoreScreenState extends State<AdminMoreScreen> {
  int _pendingClaims = 0;

  @override
  void initState() {
    super.initState();
    _refreshBadge();
  }

  void _refreshBadge() {
    ApiService.adminPendingClaims().then((n) {
      if (mounted) setState(() => _pendingClaims = n);
    }).catchError((_) {});
  }

  Future<void> _push(Widget screen) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
    _refreshBadge();
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
    if (ok == true) await AppSession.logout();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: ListView(
        padding: EdgeInsets.fromLTRB(16, 8, 16, navBarListPadding(context)),
        children: [
          Card(
            child: ListTile(
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              leading: const CircleAvatar(
                radius: 26,
                backgroundColor: AppTheme.navy,
                child: Icon(Icons.admin_panel_settings_outlined, color: Colors.white, size: 28),
              ),
              title: Text(ApiService.userName ?? 'Admin', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
              subtitle: const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Align(alignment: Alignment.centerLeft, child: StatusChip('Dairy admin', color: AppTheme.primaryBlue)),
              ),
            ),
          ),
          const SectionHeader('Manage'),
          TileGrid(children: [
            ActionTile(
              icon: Icons.report_gmailerrorred,
              label: 'Claims',
              badge: _pendingClaims > 0 ? '$_pendingClaims' : null,
              onTap: () => _push(const AdminClaimsScreen()),
            ),
            ActionTile(icon: Icons.people_alt_outlined, label: 'Customers', onTap: () => _push(const AdminCustomersScreen())),
            ActionTile(icon: Icons.account_balance_wallet_outlined, label: 'Dues', onTap: () => _push(const AdminCustomersScreen(sortByDues: true))),
          ]),
          const SectionHeader('Account'),
          TileGrid(children: [
            ActionTile(icon: Icons.lock_reset, label: 'Change Password', onTap: _changePassword),
            ActionTile(icon: Icons.logout, label: 'Log Out', iconColor: AppTheme.alertRose, onTap: _logout),
          ]),
          const SectionHeader('Legal'),
          TileGrid(children: [
            ActionTile(icon: Icons.privacy_tip_outlined, label: 'Privacy Policy', onTap: () => openLegalPage(context, '/privacy')),
            ActionTile(icon: Icons.gavel_outlined, label: 'Terms & Conditions', onTap: () => openLegalPage(context, '/terms')),
          ]),
          const SizedBox(height: 20),
          const Text(
            'Making bills, prices, routes and dispatch are done on the web admin panel.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 12.5, color: AppTheme.textMuted),
          ),
          const SizedBox(height: 16),
          const DevCredit(),
        ],
      ),
    );
  }
}
