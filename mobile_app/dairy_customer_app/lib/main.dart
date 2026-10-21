import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'screens/admin/admin_shell.dart';
import 'screens/bills_screen.dart';
import 'screens/claims_screen.dart';
import 'screens/daily_orders_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/login_screen.dart';
import 'services/api_service.dart';
import 'theme/app_theme.dart';
import 'widgets/floating_nav_bar.dart';

void main() {
  runApp(const DairyCustomerApp());
}

/// App-wide login state: screens call [AppSession.logout] and the app returns to the login screen.
class AppSession {
  static final loggedIn = ValueNotifier<bool?>(null); // null = still checking saved login
  static String? message;

  static Future<void> logout({String? reason}) async {
    await ApiService.logout();
    message = reason;
    loggedIn.value = false;
  }
}

class DairyCustomerApp extends StatelessWidget {
  const DairyCustomerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Akash Dairy Farm',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      home: const AuthGate(),
    );
  }
}

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  @override
  void initState() {
    super.initState();
    ApiService.onSessionExpired = () {
      AppSession.message = 'Your session has ended. Please log in again.';
      AppSession.loggedIn.value = false;
    };
    ApiService.restoreSession().then((hasToken) => AppSession.loggedIn.value = hasToken);
  }

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<bool?>(
      valueListenable: AppSession.loggedIn,
      builder: (context, loggedIn, _) {
        if (loggedIn == null) {
          return const Scaffold(body: Center(child: CircularProgressIndicator(color: AppTheme.primaryBlue)));
        }
        if (!loggedIn) {
          final message = AppSession.message;
          AppSession.message = null;
          return LoginScreen(
            message: message,
            onLoggedIn: () => AppSession.loggedIn.value = true,
          );
        }
        return ApiService.isAdmin ? const AdminShell() : const MainNavigationShell();
      },
    );
  }
}

class MainNavigationShell extends StatefulWidget {
  const MainNavigationShell({super.key});

  @override
  State<MainNavigationShell> createState() => _MainNavigationShellState();
}

class _MainNavigationShellState extends State<MainNavigationShell> {
  static const _navItems = [
    (Icons.home_outlined, Icons.home_rounded, 'Home'),
    (Icons.calendar_month_outlined, Icons.calendar_month, 'Orders'),
    (Icons.report_gmailerrorred, Icons.report, 'Problems'),
    (Icons.receipt_long_outlined, Icons.receipt_long, 'Bills'),
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
      CustomerDashboardScreen(onOpenTab: _openTab),
      const DailyOrdersScreen(),
      const ClaimsScreen(),
      const BillsScreen(),
    ];

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _handleBack();
      },
      child: Scaffold(
        extendBody: true, // content scrolls behind the floating bar
        // Rebuilt on every tab switch so each tab shows fresh data (e.g. Home after placing an order)
        body: screens[_currentIndex],
        bottomNavigationBar: FloatingNavBar(items: _navItems, currentIndex: _currentIndex, onTap: _openTab),
      ),
    );
  }
}

