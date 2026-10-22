import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../utils/format.dart';
import 'ui.dart';

/// One product line of an order: quantity x rate = amount.
class OrderLineView {
  final String name;
  final String unit;
  final double qty;
  final double rate;
  final double amount;
  final double? delivered; // set once delivered

  const OrderLineView({
    required this.name,
    required this.unit,
    required this.qty,
    required this.rate,
    required this.amount,
    this.delivered,
  });

  bool get short => delivered != null && delivered! < qty;
}

/// Product-wise table of an order: each product with quantity x rate and its amount, then the total.
class OrderLinesTable extends StatelessWidget {
  final List<OrderLineView> lines;
  final double total;
  final String totalLabel;

  const OrderLinesTable({super.key, required this.lines, required this.total, this.totalLabel = 'Total'});

  @override
  Widget build(BuildContext context) {
    const head = TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: AppTheme.textMuted, letterSpacing: 0.4);
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 10),
            decoration: const BoxDecoration(
              color: Color(0xFFF6F8FA),
              borderRadius: BorderRadius.vertical(top: Radius.circular(12)),
            ),
            child: const Row(
              children: [
                Expanded(child: Text('PRODUCT', style: head)),
                Text('AMOUNT', style: head),
              ],
            ),
          ),
          for (var i = 0; i < lines.length; i++) ...[
            if (i > 0) const Divider(height: 1, indent: 14, endIndent: 14),
            _line(lines[i]),
          ],
          Container(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            decoration: const BoxDecoration(
              color: AppTheme.infoBanner,
              borderRadius: BorderRadius.vertical(bottom: Radius.circular(12)),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '$totalLabel${lines.length > 1 ? ' (${lines.length} products)' : ''}',
                    style: const TextStyle(fontWeight: FontWeight.w800, color: AppTheme.navy),
                  ),
                ),
                Text(
                  rupees(total),
                  style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: AppTheme.navy),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _line(OrderLineView l) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(l.name, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, height: 1.25)),
                const SizedBox(height: 3),
                Text(
                  '${qtyUnit(l.qty, l.unit)} × ${rupees(l.rate)}',
                  style: const TextStyle(fontSize: 13, color: AppTheme.textMuted),
                ),
                if (l.short)
                  Padding(
                    padding: const EdgeInsets.only(top: 3),
                    child: Text(
                      'Delivered ${qtyUnit(l.delivered!, l.unit)}',
                      style: const TextStyle(fontSize: 12.5, color: AppTheme.warmAmber, fontWeight: FontWeight.w600),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Text(
            rupees(l.amount),
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: AppTheme.textMain),
          ),
        ],
      ),
    );
  }
}

/// Bottom sheet with an order's details: date, status, the product table and an optional note / actions.
Future<T?> showOrderDetailsSheet<T>(
  BuildContext context, {
  required String title,
  String? subtitle,
  required String statusText,
  required Color statusColor,
  required List<OrderLineView> lines,
  required double total,
  String totalLabel = 'Total',
  Widget? note,
  List<Widget> actions = const [],
}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: Colors.white,
    builder: (ctx) => SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(ctx).height * 0.85),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppTheme.navy),
                        ),
                        if (subtitle != null && subtitle.isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 2),
                            child: Text(subtitle, style: const TextStyle(fontSize: 13, color: AppTheme.textMuted)),
                          ),
                      ],
                    ),
                  ),
                  StatusChip(statusText, color: statusColor),
                ],
              ),
              const SizedBox(height: 16),
              if (lines.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Text('No products on this order.', style: TextStyle(color: AppTheme.textMuted)),
                )
              else
                OrderLinesTable(lines: lines, total: total, totalLabel: totalLabel),
              if (note != null) ...[const SizedBox(height: 14), note],
              if (actions.isNotEmpty) ...[
                const SizedBox(height: 16),
                for (final a in actions) Padding(padding: const EdgeInsets.only(bottom: 8), child: a),
              ],
            ],
          ),
        ),
      ),
    ),
  );
}

/// Small grey note with an icon (e.g. "Locked at 1:00 AM").
class SheetNote extends StatelessWidget {
  final IconData icon;
  final String text;
  final Color color;

  const SheetNote(this.text, {super.key, this.icon = Icons.info_outline, this.color = AppTheme.textMuted});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(10)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: const TextStyle(fontSize: 13, height: 1.35, color: AppTheme.textMain)),
          ),
        ],
      ),
    );
  }
}
