import 'package:intl/intl.dart';

final _rupees = NumberFormat.decimalPatternDigits(locale: 'en_IN', decimalDigits: 2);
final _plain = NumberFormat.decimalPattern('en_IN');

/// ₹1,23,456.50 (Indian digit grouping)
String rupees(double value) {
  final text = _rupees.format(value);
  return '₹${text.endsWith('.00') ? text.substring(0, text.length - 3) : text}';
}

/// 186 or 186.5
String qty(double value) => _plain.format(value);

/// How a unit is shown: Liter for L, the rest as they are (kg, packet)
String unitName(String unit) => unit == 'L' ? 'Liter' : unit;

/// 10 Liter, 1.5 kg, 2 packet
String qtyUnit(double value, String unit) => '${qty(value)} ${unitName(unit)}'.trim();

/// Units counted in whole numbers (no half packets)
bool wholeUnit(String unit) => const {'pcs', 'packet', 'box', 'pouch', 'bottle'}.contains(unit);

/// 2026-09-30 -> 30 Sep 2026
String niceDate(String iso) {
  final d = DateTime.tryParse(iso);
  return d == null ? iso : DateFormat('dd MMM yyyy').format(d);
}
