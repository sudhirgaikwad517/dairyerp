import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../widgets/floating_nav_bar.dart';
import 'admin_bills_screen.dart';
import 'admin_delivery_screen.dart';
import 'admin_home_screen.dart';
import 'admin_more_screen.dart';
import 'admin_orders_screen.dart';

/// The dairy admin's part of the app: today's orders, deliveries, bills and claims.
class AdminShell extends StatefulWidget {
  const AdminShell({super.key});

  @override
  State<AdminShell> createState() => _AdminShellState();
}

class _AdminShellState extends State<AdminShell> {
  static const _navItems = [
    (Icons.dashboard_outlined, Icons.dashboard_rounded, 'Home'),
    (Icons.list_alt_outlined, Icons.list_alt_rounded, 'Orders'),
    (Icons.local_shipping_outlined, Icons.local_shipping, 'Delivery'),
    (Icons.receipt_long_outlined, Icons.receipt_long, 'Bills'),
    (Icons.grid_view_outlined, Icons.grid_view_rounded, 'More'),
  ];

  int _currentIndex = 0;
  DateTime? _lastBackOnHome;

  void _openTab(int index) => setState(() => _currentIndex = index);

  /// Android back: other tabs go to Home; on Home, press back twice to close the app.
  void _handleBack() {
    if (_currentIndex != 0) {
      setState(() => _currentIndex = 0);
      return;
    }
    final now = DateTime.now();
    if (_lastBackOnHome != null && now.difference(_lastBackOnHome!) < const Duration(seconds: 2)) {
      SystemNavigator.pop();
      return;
    }
    _lastBackOnHome = now;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Press back again to exit'), duration: Duration(seconds: 2)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      AdminHomeScreen(onOpenTab: _openTab),
      const AdminOrdersScreen(),
      const AdminDeliveryScreen(),
      const AdminBillsScreen(),
      const AdminMoreScreen(),
    ];
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _handleBack();
      },
      child: Scaffold(
        extendBody: true,
        body: screens[_currentIndex],
        bottomNavigationBar: FloatingNavBar(items: _navItems, currentIndex: _currentIndex, onTap: _openTab),
      ),
    );
  }
}
