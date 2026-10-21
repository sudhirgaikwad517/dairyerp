import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:dairy_customer_app/models/admin_models.dart';
import 'package:dairy_customer_app/models/dairy_models.dart';
import 'package:dairy_customer_app/screens/admin/admin_widgets.dart';
import 'package:dairy_customer_app/screens/claims_screen.dart';
import 'package:dairy_customer_app/screens/notifications_screen.dart';
import 'package:dairy_customer_app/services/api_service.dart';
import 'package:dairy_customer_app/utils/format.dart';
import 'package:dairy_customer_app/widgets/floating_nav_bar.dart';
import 'package:dairy_customer_app/screens/login_screen.dart';
import 'package:dairy_customer_app/theme/app_theme.dart';
import 'package:dairy_customer_app/widgets/ui.dart';

void main() {
  Widget app({String? message}) => MaterialApp(home: LoginScreen(onLoggedIn: () {}, message: message));

  testWidgets('Login screen shows mobile and password fields', (tester) async {
    await tester.pumpWidget(app());

    expect(find.text('Akash Dairy Farm'), findsOneWidget);
    expect(find.widgetWithText(TextFormField, 'Mobile number'), findsOneWidget);
    expect(find.widgetWithText(TextFormField, 'Password'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'Log In'), findsOneWidget);
    expect(find.textContaining('Prowexa Technologies Pvt. Ltd', findRichText: true), findsOneWidget);
  });

  testWidgets('Login validates input before calling the server', (tester) async {
    await tester.pumpWidget(app());

    final logIn = find.widgetWithText(ElevatedButton, 'Log In');
    await tester.ensureVisible(logIn);
    await tester.tap(logIn);
    await tester.pump();
    expect(find.text('Enter your 10-digit mobile number'), findsOneWidget);
    expect(find.text('Enter your password'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextFormField, 'Mobile number'), '12345');
    await tester.ensureVisible(logIn);
    await tester.tap(logIn);
    await tester.pump();
    expect(find.text('Enter your 10-digit mobile number'), findsOneWidget);
  });

  testWidgets('Session-expired message is shown', (tester) async {
    await tester.pumpWidget(app(message: 'Your session has ended. Please log in again.'));
    expect(find.text('Your session has ended. Please log in again.'), findsOneWidget);
  });

  testWidgets('Action tiles fit two-line labels on a phone with large text', (tester) async {
    tester.view.physicalSize = const Size(1080, 2392);
    tester.view.devicePixelRatio = 2.625; // ~411 x 911 dp, like the test phone
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: MediaQuery(
        data: const MediaQueryData(size: Size(411, 911), textScaler: TextScaler.linear(1.3)),
        child: Scaffold(
          body: Padding(
            padding: const EdgeInsets.all(16),
            child: TileGrid(children: [
              for (final label in ['Upcoming Orders', 'Download Statement', 'Report Problem', 'Change Password', 'Order History', 'Log Out'])
                ActionTile(icon: Icons.history, label: label, onTap: () {}),
            ]),
          ),
        ),
      ),
    ));
    expect(tester.takeException(), isNull); // a RenderFlex overflow would be reported here
    expect(find.text('Download Statement'), findsOneWidget);
  });

  testWidgets('Login accepts a dairy staff username', (tester) async {
    await tester.pumpWidget(app());
    await tester.tap(find.text('Dairy Staff'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextFormField, 'Username'), 'admin');
    await tester.tap(find.widgetWithText(ElevatedButton, 'Log In'));
    await tester.pump();
    expect(find.text('Enter your 10-digit mobile number'), findsNothing);
    expect(find.text('Enter your username'), findsNothing);
  });

  testWidgets('Login screen fits a small phone with large text', (tester) async {
    tester.view.physicalSize = const Size(720, 1280);
    tester.view.devicePixelRatio = 2.0; // 360 x 640 dp
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => MediaQuery(
          data: MediaQuery.of(context).copyWith(textScaler: const TextScaler.linear(1.3)),
          child: LoginScreen(onLoggedIn: () {}, message: 'Wrong mobile number or password'),
        ),
      ),
    ));
    expect(tester.takeException(), isNull);
    expect(find.text('Customer'), findsOneWidget);
    expect(find.text('Dairy Staff'), findsOneWidget);
  });

  test('Admin order reads delivery figures', () {
    final o = AdminOrder.fromJson({
      'id': 1, 'order_number': 'ORD-1', 'customer_id': 3, 'customer_name': 'Kadam', 'customer_code': 'CUST-003',
      'route_name': 'Route 01', 'driver_name': 'Rahul', 'delivery_date': '2026-10-16', 'status': 'delivered',
      'total_litres': 186, 'delivered_litres': 180.5, 'rate': 56.5, 'total_amount': 10509, 'billed_amount': 10198.25,
      'photo_ids': [4, 5], 'has_signature': true, 'delivered_at': '2026-10-16T07:15:00',
      'what': '186 L', 'delivered_what': '180.5 L', 'is_short': true, 'short_what': '5.5 L Cow Milk',
    });
    expect(o.isShort, isTrue);
    expect(adminOrderStatus(o).$1, 'Short');
    expect(o.notDelivered, isFalse);
    expect(o.amount, 10198.25);
    expect(o.photoIds, [4, 5]);
    expect(orderStatus(o.status, delivered: o.deliveredLitres, ordered: o.totalLitres).$1, 'Short');
    expect(orderStatus('out_for_delivery').$1, 'On the way');
    expect(orderStatus('confirmed').$1, 'Not dispatched');
    expect(orderStatus('delivered', delivered: 0, ordered: 30).$1, 'Not delivered');
  });

  test('Admin claim: most that can be approved and settlement wording', () {
    final c = AdminClaim.fromJson({
      'id': 2, 'claim_number': 'CLM-1', 'customer_name': 'Kadam', 'issue_date': '2026-10-16', 'reason_label': 'Leakage',
      'claimed_qty': 10, 'status': 'approved', 'approved_qty': 10, 'rate': 56.5, 'credit_amount': 565,
      'settlement': 'refund', 'refund_method': 'upi', 'delivered_qty': 12, 'other_claims_qty': 5, 'photo_ids': [],
    });
    expect(c.maxApprovable, 7);
    expect(c.settlementLabel, 'Refunded by UPI');
  });

  testWidgets('Admin KPI cards fit on a phone with large text', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: AppTheme.lightTheme,
      home: MediaQuery(
        data: const MediaQueryData(size: Size(360, 780), textScaler: TextScaler.linear(1.3)),
        child: Scaffold(
          body: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(children: [
              DateSwitcher(day: DateTime(2026, 10, 16), onChanged: (_) {}),
              const SizedBox(height: 10),
              const KpiRow(
                KpiCard(icon: Icons.account_balance_wallet_outlined, label: 'Total outstanding', value: '₹18,47,554.50', sub: '7 customers'),
                KpiCard(icon: Icons.schedule, label: 'Ordering for tomorrow', value: 'Closed', sub: 'closed at 9:00 PM'),
              ),
            ]),
          ),
        ),
      ),
    ));
    expect(tester.takeException(), isNull);
    expect(find.text('Total outstanding'), findsOneWidget);
  });

  test('Bill reads claim deductions, refunded claims and extra paid', () {
    final b = BillItem.fromJson({
      'id': 9, 'invoice_number': 'BILL-1', 'period_label': '16 OCT 2026', 'total_qty': 27, 'amount': 1539,
      'balance_due': 0, 'payment_status': 'paid', 'original_qty': 27, 'claims_qty': 0, 'claims_amount': 0,
      'paid_amount': 1539, 'excess_paid': 0,
      'adjustments': [
        {'claim_qty': 5, 'amount': 285, 'mode': 'refunded'},
        {'claim_qty': 2, 'amount': 114, 'mode': 'deducted'},
      ],
    });
    expect(b.isPaid, isTrue);
    expect(b.refundedQty, 5);
    expect(b.refundedAmount, 285);
    expect(b.excessPaid, 0);
  });
  for (final sysBar in [0.0, 24.0, 48.0]) {
    testWidgets('Tab content stays above the floating bar (system bar $sysBar)', (tester) async {
      tester.view.physicalSize = const Size(1080, 2392);
      tester.view.devicePixelRatio = 2.625;
      tester.view.padding = FakeViewPadding(bottom: sysBar * 2.625);
      tester.view.viewPadding = FakeViewPadding(bottom: sysBar * 2.625);
      addTearDown(tester.view.reset);
      const items = [(Icons.home_outlined, Icons.home, 'Home'), (Icons.report_outlined, Icons.report, 'Problems')];
      Widget shell(Widget tab) => MaterialApp(
            home: Scaffold(
              extendBody: true,
              body: tab,
              bottomNavigationBar: FloatingNavBar(items: items, currentIndex: 1, onTap: (_) {}),
            ),
          );

      // Problems tab: the "Report a problem" button must sit fully above the bar
      await tester.pumpWidget(shell(const ClaimsScreen()));
      await tester.pump(const Duration(seconds: 1));
      final barBox = tester.getRect(find.descendant(of: find.byType(FloatingNavBar), matching: find.byType(Container)).first);
      final fab = tester.getRect(find.byType(FloatingActionButton));
      expect(fab.bottom, lessThanOrEqualTo(barBox.top), reason: 'button $fab, bar $barBox');

      // A long tab list: after scrolling to the end, the last item is above the bar
      await tester.pumpWidget(shell(Builder(
        builder: (context) => ListView(
          padding: EdgeInsets.fromLTRB(16, 16, 16, navBarListPadding(context)),
          children: [for (var i = 0; i < 40; i++) SizedBox(height: 60, child: Text('Row $i'))],
        ),
      )));
      await tester.drag(find.byType(ListView), const Offset(0, -5000));
      await tester.pumpAndSettle();
      final last = tester.getRect(find.text('Row 39'));
      final barBox2 = tester.getRect(find.descendant(of: find.byType(FloatingNavBar), matching: find.byType(Container)).first);
      expect(last.bottom, lessThanOrEqualTo(barBox2.top));
    });
  }
  test('Notifications: list parsing, read state and time labels', () {
    final r = NoticeList.fromJson({
      'unread': 1,
      'items': [
        {'id': 2, 'kind': 'bill_created', 'title': 'New bill BILL-1', 'body': 'Milk bill', 'link': 'bills',
         'created_at': '2026-10-17T10:00:00Z', 'read': false},
        {'id': 1, 'kind': 'claim_rejected', 'title': 'Claim not approved', 'body': 'x', 'link': null,
         'created_at': null, 'read': true},
      ],
    });
    expect(r.unread, 1);
    expect(r.items.first.link, 'bills');
    expect(r.items.first.createdAt!.isUtc, isFalse); // shown in phone time
    expect(r.items.first.markedRead().read, isTrue);
    expect(r.items.last.createdAt, isNull);

    final now = DateTime(2026, 10, 17, 22, 0);
    expect(noticeTime(now.subtract(const Duration(seconds: 20)), now: now), 'Just now');
    expect(noticeTime(now.subtract(const Duration(minutes: 5)), now: now), '5 min ago');
    expect(noticeTime(DateTime(2026, 10, 17, 9, 5), now: now), 'Today, 9:05 AM');
    expect(noticeTime(DateTime(2026, 10, 16, 21, 30), now: now), 'Yesterday, 9:30 PM');
    expect(noticeTime(DateTime(2026, 10, 2, 8, 0), now: now), '2 Oct, 8:00 AM');
    expect(noticeStyle('claim_approved').$2, AppTheme.freshGreen);
  });
  test('Day summary reads the automatic dispatch and hold', () {
    final s = DaySummary.fromJson({
      'date': '2026-10-18', 'active_customers': 7, 'customers_ordered': 5, 'not_ordered': [], 'cancelled': 0,
      'total_litres': 1200, 'total_amount': 68400, 'status_counts': {'confirmed': 5}, 'waiting_dispatch': 5,
      'order_deadline': '2026-10-17T21:00:00', 'customers_can_order': false,
      'dispatch': {'dispatch_at': '2026-10-18T04:00', 'time_passed': false, 'on_hold': true,
                   'hold_note': 'Tanker late', 'customers_told': false, 'waiting_orders': 5,
                   'dispatched_orders': 0, 'auto_dispatched_at': null, 'can_hold': true},
    });
    expect(s.dispatch!.onHold, isTrue);
    expect(s.dispatch!.holdNote, 'Tanker late');
    expect(s.dispatch!.dispatchAt, DateTime(2026, 10, 18, 4));
    expect(s.dispatch!.autoDispatchedAt, isNull);
    expect(s.dispatch!.canHold, isTrue);
    final old = DaySummary.fromJson({
      'date': '2026-10-18', 'active_customers': 7, 'customers_ordered': 0, 'total_litres': 0, 'total_amount': 0,
    });
    expect(old.dispatch, isNull);
  });
  test('Legal pages open on the same server as the API', () {
    expect(ApiService.siteUrl('/privacy').path, '/privacy');
    expect(ApiService.siteUrl('/terms').toString(), endsWith(':8000/terms'));
  });

  testWidgets('Login shows the terms and privacy consent', (tester) async {
    await tester.pumpWidget(app());
    expect(find.textContaining('By logging in you agree', findRichText: true), findsOneWidget);
    expect(find.textContaining('Privacy Policy', findRichText: true), findsOneWidget);
  });
  test('Several products read correctly everywhere', () {
    final day = DayPlan.fromJson({
      'date': '2026-10-20', 'day_name': 'Tuesday', 'total_qty': 15, 'total_amount': 1580, 'source': 'order',
      'status': 'delivered', 'editable': false, 'orders_closed': true, 'order_deadline': '2026-10-19T21:00',
      'items': [
        {'product_id': 1, 'product_name': 'Cow Milk', 'unit': 'L', 'quantity': 10, 'rate': 57, 'delivered_quantity': 10},
        {'product_id': 3, 'product_name': 'Paneer', 'unit': 'kg', 'quantity': 1.5, 'rate': 400, 'delivered_quantity': 1},
      ],
    });
    expect(day.hasOrder, isTrue);
    expect(day.what, '10 L Cow Milk, 1.5 kg Paneer');
    expect(day.deliveredWhat, '10 L Cow Milk, 1 kg Paneer');
    expect(day.deliveredShort, isTrue);
    final one = DayPlan.fromJson({
      'date': '2026-10-21', 'day_name': 'Wednesday', 'total_qty': 20, 'total_amount': 1140, 'status': 'confirmed',
      'editable': false, 'orders_closed': false, 'order_deadline': '2026-10-20T21:00',
      'items': [{'product_id': 1, 'product_name': 'Cow Milk', 'unit': 'L', 'quantity': 20, 'rate': 57}],
    });
    expect(one.what, '20 L');
    final bill = BillItem.fromJson({
      'id': 1, 'invoice_number': 'B', 'period_label': 'OCT', 'total_qty': 14, 'amount': 1512, 'balance_due': 1512,
      'payment_status': 'pending',
      'products': [{'product': 'Cow Milk', 'unit': 'L', 'qty': 10}, {'product': 'Paneer', 'unit': 'kg', 'qty': 1.5}],
      'adjustments': [{'product': 'Paneer', 'unit': 'kg', 'claim_qty': 0.5, 'amount': 200, 'mode': 'deducted'}],
    });
    expect(bill.what, '10 L Cow Milk, 1.5 kg Paneer');
    expect(bill.adjustments.first.text, '0.5 kg Paneer');
    final old = BillItem.fromJson({'id': 2, 'invoice_number': 'B2', 'period_label': 'SEP', 'total_qty': 816, 'amount': 46512,
      'balance_due': 0, 'payment_status': 'paid', 'products': [{'product': 'Cow Milk', 'unit': 'L', 'qty': 816}]});
    expect(old.what, '816 L');
    // An order of paneer only has no litres but is delivered, not "not delivered"
    final o = AdminOrder.fromJson({'id': 1, 'customer_id': 2, 'status': 'delivered', 'total_litres': 0, 'delivered_litres': 0,
      'total_amount': 800, 'billed_amount': 800, 'what': '2 kg Paneer', 'delivered_what': '2 kg Paneer', 'is_short': false});
    expect(o.notDelivered, isFalse);
    expect(adminOrderStatus(o).$1, 'Delivered');
    expect(wholeUnit('packet'), isTrue);
    expect(qtyUnit(1.5, 'kg'), '1.5 kg');
  });
}
