import 'dart:convert';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

import '../models/admin_models.dart';
import '../models/dairy_models.dart';

/// Thrown for any failed request; [message] is safe to show to the customer.
class ApiException implements Exception {
  final String message;
  final int? statusCode;
  ApiException(this.message, [this.statusCode]);

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => message;
}

class ApiService {
  /// Server address. Defaults to this computer; for a phone or emulator pass the server's address, e.g.
  ///   flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000/api/v1
  ///   (Android emulator: http://10.0.2.2:8000/api/v1)
  /// In the browser the app is served by the server itself, so it uses the same address.
  static final String baseUrl = const bool.hasEnvironment('API_BASE_URL')
      ? const String.fromEnvironment('API_BASE_URL')
      : kIsWeb
          ? '${Uri.base.origin}/api/v1'
          : 'http://127.0.0.1:8000/api/v1';

  /// A page on the dairy's website (same server), e.g. /privacy, /terms, /delete-account.
  static Uri siteUrl(String path) => Uri.parse(baseUrl.replaceFirst(RegExp(r'/api/v1/?$'), '') + path);

  static const _storage = FlutterSecureStorage();
  static const _tokenKey = 'auth_token';
  static const _roleKey = 'auth_role';
  static const _nameKey = 'auth_name';
  static String? _token;

  /// customer, admin or super_admin (decides which part of the app is shown)
  static String? role;
  static String? userName;

  static bool get isAdmin => role == 'admin' || role == 'super_admin';

  /// Called when the server rejects the saved login, so the app can return to the login screen.
  static void Function()? onSessionExpired;

  static Future<bool> restoreSession() async {
    _token = await _storage.read(key: _tokenKey);
    if (_token == null) return false;
    role = await _storage.read(key: _roleKey);
    userName = await _storage.read(key: _nameKey);
    if (role == null) {
      // Logged in with an older version of the app: ask the server who this is
      try {
        final me = await _send('GET', '/auth/me');
        await _saveUser(me as Map<String, dynamic>);
      } on ApiException catch (e) {
        if (e.isUnauthorized) return false;
        role = 'customer';
      }
    }
    return true;
  }

  static Future<void> _saveUser(Map<String, dynamic> user) async {
    role = user['role'] as String?;
    userName = user['full_name'] as String?;
    await _storage.write(key: _roleKey, value: role);
    await _storage.write(key: _nameKey, value: userName);
  }

  /// Customers log in with their mobile number; dairy admins with their username.
  static Future<void> login(String username, String password) async {
    final data = await _send('POST', '/auth/login', body: {
      'username': username,
      'password': password,
      'app': 'mobile',
    }, authenticated: false);
    _token = data['access_token'] as String;
    await _storage.write(key: _tokenKey, value: _token);
    await _saveUser(data['user'] as Map<String, dynamic>);
  }

  static Future<void> logout() async {
    _token = null;
    role = null;
    userName = null;
    await _storage.delete(key: _tokenKey);
    await _storage.delete(key: _roleKey);
    await _storage.delete(key: _nameKey);
  }

  // ---------------- Admin section ----------------

  static Future<DaySummary> adminDaySummary(DateTime day) async =>
      DaySummary.fromJson(await _send('GET', '/orders/day-summary?day=${_isoDate(day)}'));

  /// Excel of one day's orders (opened in the browser; the token goes in the link).
  static Uri adminOrdersExcelUrl(DateTime day) =>
      Uri.parse('$baseUrl/orders/export').replace(queryParameters: {'day': _isoDate(day), 'access_token': _token ?? ''});

  static Future<void> holdDispatch(DateTime day, String note) async =>
      _send('PUT', '/orders/dispatch-hold', body: {'day': _isoDate(day), 'note': note});

  static Future<void> releaseDispatchHold(DateTime day) async =>
      _send('DELETE', '/orders/dispatch-hold?day=${_isoDate(day)}');

  static Future<List<AdminOrder>> adminOrders(DateTime day) async {
    final List list = await _send('GET', '/orders/?order_date=${_isoDate(day)}');
    return list.map((o) => AdminOrder.fromJson(o)).toList();
  }

  static Future<int> adminPendingClaims() async => ((await _send('GET', '/claims/summary'))['pending'] as num).toInt();

  static Future<List<AdminBill>> adminBills(DateTime monthStart) async {
    final end = DateTime(monthStart.year, monthStart.month + 1, 0);
    final List list = await _send('GET', '/billing/bills?start_date=${_isoDate(monthStart)}&end_date=${_isoDate(end)}');
    return list.map((b) => AdminBill.fromJson(b)).toList();
  }

  static Uri adminBillPdfUrl(int billId) =>
      Uri.parse('$baseUrl/billing/bills/$billId/pdf').replace(queryParameters: {'access_token': _token ?? ''});

  static Future<List<AdminCustomer>> adminCustomers() async {
    final List list = await _send('GET', '/customers/');
    return list.map((c) => AdminCustomer.fromJson(c)).toList();
  }

  static Future<List<AdminClaim>> adminClaims({String? status}) async {
    final List list = await _send('GET', '/claims/${status == null ? '' : '?status=$status'}');
    return list.map((c) => AdminClaim.fromJson(c)).toList();
  }

  static Future<AdminClaim> adminClaim(int id) async => AdminClaim.fromJson(await _send('GET', '/claims/$id'));

  /// mode: 'bill' (deduct from the bill) or 'refund' (paid back separately; needs refundMethod)
  static Future<void> approveClaim(int id, double litres,
      {String mode = 'bill', String? refundMethod, String? refundReference, String? note}) async {
    await _send('POST', '/claims/$id/approve', body: {
      'approved_qty': litres,
      'mode': mode,
      'refund_method': refundMethod,
      'refund_reference': refundReference,
      'note': note,
    });
  }

  static Future<void> rejectClaim(int id, String note) async {
    await _send('POST', '/claims/$id/reject', body: {'note': note});
  }

  static Future<void> changePassword(String current, String next) async {
    await _send('POST', '/auth/change-password', body: {
      'current_password': current,
      'new_password': next,
    });
  }

  static Future<CustomerProfile> getProfile() async {
    return CustomerProfile.fromJson(await _send('GET', '/me/profile'));
  }

  static Future<List<ProductItem>> getProducts() async {
    final List list = await _send('GET', '/me/products');
    return list.map((p) => ProductItem.fromJson(p)).toList();
  }

  static Future<List<OrderSummary>> getOrders({int limit = 30}) async {
    final List list = await _send('GET', '/me/orders?limit=$limit');
    return list.map((o) => OrderSummary.fromJson(o)).toList();
  }

  static Future<OrderResult> placeOrder(DateTime deliveryDate, List<Map<String, dynamic>> items) async {
    final data = await _send('POST', '/me/orders', body: {
      'delivery_date': _isoDate(deliveryDate),
      'items': items,
    });
    return OrderResult(OrderSummary.fromJson(data['order']), data['credit_warning'] as String?);
  }

  static Future<LedgerStatement> getLedger() async {
    return LedgerStatement.fromJson(await _send('GET', '/me/ledger'));
  }

  static Future<String> submitComplaint(String category, String description) async {
    final data = await _send('POST', '/me/complaints', body: {
      'category': category,
      'description': description,
    });
    return data['ticket_number'] as String;
  }

  /// Milk for each day from [start]: own order, skipped, or fixed schedule.
  static Future<List<DayPlan>> getDays({DateTime? start, int days = 14}) async {
    final query = start == null ? '' : 'start=${_isoDate(start)}&';
    final List list = await _send('GET', '/me/days?${query}days=$days');
    return list.map((d) => DayPlan.fromJson(d)).toList();
  }

  /// Set a day's milk; all quantities 0 means no milk that day.
  static Future<DayPlan> setDay(DateTime day, List<Map<String, dynamic>> items) async {
    return DayPlan.fromJson(await _send('PUT', '/me/days/${_isoDate(day)}', body: {'items': items}));
  }

  static Future<ClaimOptions> getClaimableDays() async {
    return ClaimOptions.fromJson(await _send('GET', '/me/claimable-days'));
  }

  static Future<List<ClaimItem>> getClaims() async {
    final List list = await _send('GET', '/me/claims');
    return list.map((c) => ClaimItem.fromJson(c)).toList();
  }

  static Future<ClaimItem> submitClaim({
    required String issueDate,
    required String reason,
    required double quantity,
    required String description,
    required List<XFile> photos,
    int? productId,
  }) async {
    final request = http.MultipartRequest('POST', Uri.parse('$baseUrl/me/claims'))
      ..fields['issue_date'] = issueDate
      ..fields['reason'] = reason
      ..fields['quantity'] = quantity.toString()
      ..fields['description'] = description;
    if (productId != null) request.fields['product_id'] = '$productId';
    if (_token != null) request.headers['Authorization'] = 'Bearer $_token';
    for (final photo in photos) {
      request.files.add(http.MultipartFile.fromBytes('photos', await photo.readAsBytes(), filename: photo.name));
    }
    http.Response res;
    try {
      res = await http.Response.fromStream(await request.send().timeout(const Duration(seconds: 60)));
    } catch (_) {
      throw ApiException('Could not upload. Check your internet connection and try again.');
    }
    final data = await _handle(res, authenticated: true);
    return ClaimItem.fromJson(data['claim']);
  }

  // ---- Bell notifications (customer: own; admin: the dairy's) ----

  static Future<NoticeList> getNotifications() async => NoticeList.fromJson(await _send('GET', '/notifications'));

  static Future<int> unreadNotifications() async =>
      ((await _send('GET', '/notifications/unread-count'))['unread'] as num).toInt();

  static Future<void> markNotificationRead(int id) async => _send('POST', '/notifications/$id/read');

  static Future<void> markAllNotificationsRead() async => _send('POST', '/notifications/read-all');

  /// Asks the dairy to close this customer's account. Returns the message to show.
  static Future<String> requestAccountDeletion(String reason) async {
    final data = await _send('POST', '/me/account-deletion', body: {'reason': reason});
    return (data['message'] as String?) ?? 'Request sent to the dairy.';
  }

  static Future<List<BillItem>> getBills() async {
    final List list = await _send('GET', '/me/bills');
    return list.map((b) => BillItem.fromJson(b)).toList();
  }

  /// Link to a PDF (opened in the browser / PDF viewer). Carries the login token because a plain link cannot send headers.
  static Uri statementPdfUrl(Map<String, String> params) =>
      Uri.parse('$baseUrl/me/statement/pdf').replace(queryParameters: {...params, 'access_token': _token ?? ''});

  static Uri billPdfUrl(int billId) =>
      Uri.parse('$baseUrl/me/bills/$billId/pdf').replace(queryParameters: {'access_token': _token ?? ''});

  static Uri fileUrl(int fileId) =>
      Uri.parse('$baseUrl/files/$fileId').replace(queryParameters: {'access_token': _token ?? ''});

  static String isoDate(DateTime d) => _isoDate(d);

  static String _isoDate(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  static Future<dynamic> _send(String method, String path,
      {Map<String, dynamic>? body, bool authenticated = true}) async {
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (authenticated && _token != null) headers['Authorization'] = 'Bearer $_token';
    final uri = Uri.parse('$baseUrl$path');

    http.Response res;
    try {
      final timeout = const Duration(seconds: 20);
      if (method == 'POST') {
        res = await http.post(uri, headers: headers, body: jsonEncode(body ?? {})).timeout(timeout);
      } else if (method == 'PUT') {
        res = await http.put(uri, headers: headers, body: jsonEncode(body ?? {})).timeout(timeout);
      } else if (method == 'DELETE') {
        res = await http.delete(uri, headers: headers).timeout(timeout);
      } else {
        res = await http.get(uri, headers: headers).timeout(timeout);
      }
    } catch (_) {
      throw ApiException('Cannot reach the dairy server. Check your internet connection and try again.');
    }
    return _handle(res, authenticated: authenticated);
  }

  static Future<dynamic> _handle(http.Response res, {required bool authenticated}) async {
    dynamic data;
    try {
      data = res.body.isEmpty ? null : jsonDecode(utf8.decode(res.bodyBytes));
    } catch (_) {
      data = null;
    }

    if (res.statusCode >= 200 && res.statusCode < 300) return data;

    final detail = data is Map ? data['detail'] : null;
    final message = detail is String ? detail : 'Something went wrong (${res.statusCode}). Please try again.';
    if (res.statusCode == 401 && authenticated) {
      await logout();
      onSessionExpired?.call();
    }
    throw ApiException(message, res.statusCode);
  }
}
