import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../utils/format.dart';
import '../../models/admin_models.dart';

DateTime dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);

/// "Today", "Tomorrow", "Yesterday" or "Fri, 16 Oct"
String dayLabel(DateTime day) {
  final diff = dateOnly(day).difference(dateOnly(DateTime.now())).inDays;
  if (diff == 0) return 'Today';
  if (diff == 1) return 'Tomorrow';
  if (diff == -1) return 'Yesterday';
  return DateFormat('EEE, dd MMM').format(day);
}

/// ‹ Today › with a calendar picker in the middle.
class DateSwitcher extends StatelessWidget {
  final DateTime day;
  final ValueChanged<DateTime> onChanged;

  const DateSwitcher({super.key, required this.day, required this.onChanged});

  Future<void> _pick(BuildContext context) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: day,
      firstDate: DateTime(2024),
      lastDate: DateTime.now().add(const Duration(days: 60)),
    );
    if (picked != null) onChanged(dateOnly(picked));
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTheme.border),
      ),
      child: Row(
        children: [
          IconButton(
            tooltip: 'Previous day',
            icon: const Icon(Icons.chevron_left_rounded, color: AppTheme.navy),
            onPressed: () => onChanged(day.subtract(const Duration(days: 1))),
          ),
          Expanded(
            child: InkWell(
              borderRadius: BorderRadius.circular(10),
              onTap: () => _pick(context),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Column(
                  children: [
                    Text(dayLabel(day), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppTheme.navy)),
                    Text(DateFormat('dd MMMM yyyy').format(day), style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                  ],
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Next day',
            icon: const Icon(Icons.chevron_right_rounded, color: AppTheme.navy),
            onPressed: () => onChanged(day.add(const Duration(days: 1))),
          ),
        ],
      ),
    );
  }
}

/// ‹ October 2026 › month switcher for bills.
class MonthSwitcher extends StatelessWidget {
  final DateTime month;
  final ValueChanged<DateTime> onChanged;

  const MonthSwitcher({super.key, required this.month, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTheme.border),
      ),
      child: Row(
        children: [
          IconButton(
            tooltip: 'Previous month',
            icon: const Icon(Icons.chevron_left_rounded, color: AppTheme.navy),
            onPressed: () => onChanged(DateTime(month.year, month.month - 1)),
          ),
          Expanded(
            child: Text(DateFormat('MMMM yyyy').format(month),
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: AppTheme.navy)),
          ),
          IconButton(
            tooltip: 'Next month',
            icon: const Icon(Icons.chevron_right_rounded, color: AppTheme.navy),
            onPressed: () => onChanged(DateTime(month.year, month.month + 1)),
          ),
        ],
      ),
    );
  }
}

/// Small white figure card: label, big value, optional line below.
class KpiCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final String? sub;
  final Color color;
  final VoidCallback? onTap;

  const KpiCard({super.key, required this.icon, required this.label, required this.value, this.sub, this.color = AppTheme.navy, this.onTap});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(borderRadius: BorderRadius.circular(16), border: Border.all(color: AppTheme.border)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(color: color.withValues(alpha: 0.1), borderRadius: BorderRadius.circular(8)),
                    child: Icon(icon, size: 18, color: color),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(label,
                        maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted, fontWeight: FontWeight.w500)),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(value, style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: color)),
              ),
              if (sub != null) ...[
                const SizedBox(height: 2),
                Text(sub!, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Two KPI cards side by side.
class KpiRow extends StatelessWidget {
  final Widget left;
  final Widget right;

  const KpiRow(this.left, this.right, {super.key});

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [Expanded(child: left), const SizedBox(width: 10), Expanded(child: right)],
      ),
    );
  }
}

/// Status of one delivery, as text + colour.
(String, Color) orderStatus(String status, {double? delivered, double ordered = 0}) {
  if (status == 'cancelled') return ('Cancelled', AppTheme.textMuted);
  if (delivered != null) {
    if (delivered <= 0) return ('Not delivered', AppTheme.alertRose);
    if (delivered < ordered) return ('Short', AppTheme.warmAmber);
    return ('Delivered', AppTheme.freshGreen);
  }
  if (status == 'out_for_delivery') return ('On the way', AppTheme.accentCyan);
  return ('Not dispatched', AppTheme.primaryBlue);
}

/// Status of an order from its per-product delivery (an order of paneer only has no litres).
(String, Color) adminOrderStatus(AdminOrder o) {
  if (o.status == 'cancelled') return ('Cancelled', AppTheme.textMuted);
  if (o.isDelivered) {
    if (o.notDelivered) return ('Not delivered', AppTheme.alertRose);
    if (o.isShort) return ('Short', AppTheme.warmAmber);
    return ('Delivered', AppTheme.freshGreen);
  }
  if (o.status == 'out_for_delivery') return ('On the way', AppTheme.accentCyan);
  return ('Not dispatched', AppTheme.primaryBlue);
}

Future<void> callNumber(BuildContext context, String phone) async {
  final number = phone.replaceAll(RegExp(r'[^0-9+]'), '');
  if (number.length < 10) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('No phone number saved')));
    return;
  }
  await launchUrl(Uri(scheme: 'tel', path: number));
}

/// Thumbnails of uploaded photos; tap to see full size.
class PhotoStrip extends StatelessWidget {
  final List<int> ids;
  final double size;

  const PhotoStrip(this.ids, {super.key, this.size = 84});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final id in ids)
          GestureDetector(
            onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => _PhotoView(id))),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: Image.network(
                ApiService.fileUrl(id).toString(),
                width: size,
                height: size,
                fit: BoxFit.cover,
                errorBuilder: (_, _, _) => Container(
                  width: size, height: size, color: AppTheme.border,
                  child: const Icon(Icons.broken_image_outlined, color: AppTheme.textMuted),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _PhotoView extends StatelessWidget {
  final int id;
  const _PhotoView(this.id);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(backgroundColor: Colors.black, foregroundColor: Colors.white, title: const Text('Photo')),
      body: Center(child: InteractiveViewer(child: Image.network(ApiService.fileUrl(id).toString()))),
    );
  }
}

/// Grey "nothing here" message inside a list.
class EmptyNote extends StatelessWidget {
  final String text;
  final IconData icon;
  const EmptyNote(this.text, {super.key, this.icon = Icons.inbox_outlined});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 40),
      child: Column(
        children: [
          Icon(icon, size: 42, color: AppTheme.textMuted),
          const SizedBox(height: 8),
          Text(text, textAlign: TextAlign.center, style: const TextStyle(color: AppTheme.textMuted)),
        ],
      ),
    );
  }
}

/// A day's products, one row per product with its sizes ('1 L × 500 • 500 ML × 200') and litres.
/// Shows the first [limit] products; the rest open in a sheet, so 15 products stay a short card.
class ProductBreakdown extends StatelessWidget {
  final List<DayProductTotal> products;
  final int limit;

  const ProductBreakdown({super.key, required this.products, this.limit = 3});

  static List<(String, List<DayProductTotal>)> groups(List<DayProductTotal> products) {
    final map = <String, List<DayProductTotal>>{};
    for (final p in products) {
      map.putIfAbsent(p.group, () => []).add(p);
    }
    return map.entries.map((e) => (e.key, e.value)).toList();
  }

  static Widget row((String, List<DayProductTotal>) g) {
    final (name, sizes) = g;
    final litres = sizes.fold<double>(0, (s, p) => s + p.litres);
    final detail = sizes
        .map((p) => p.variant.isNotEmpty ? '${p.variant} × ${qty(p.quantity)}' : qtyUnit(p.quantity, p.unit))
        .join('  •  ');
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppTheme.textMain)),
                const SizedBox(height: 2),
                Text(detail, style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted)),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Text(
            litres > 0 ? '${qty(litres)} L' : (sizes.length == 1 ? qtyUnit(sizes.first.quantity, sizes.first.unit) : ''),
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppTheme.navy),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final all = groups(products);
    final shown = all.take(limit).toList();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < shown.length; i++) ...[
          if (i > 0) const Divider(height: 1),
          row(shown[i]),
        ],
        if (all.length > limit)
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              style: TextButton.styleFrom(padding: EdgeInsets.zero, visualDensity: VisualDensity.compact),
              onPressed: () => showProductsSheet(context, products),
              child: Text('+ ${all.length - limit} more product${all.length - limit == 1 ? '' : 's'}'),
            ),
          ),
      ],
    );
  }
}

/// All of a day's products in a sheet.
Future<void> showProductsSheet(BuildContext context, List<DayProductTotal> products, {String title = 'Products'}) {
  final all = ProductBreakdown.groups(products);
  final litres = products.fold<double>(0, (s, p) => s + p.litres);
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: Colors.white,
    builder: (ctx) => SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(ctx).height * 0.8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
              child: Text('$title • ${all.length}${litres > 0 ? ' • ${qty(litres)} L' : ''}',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppTheme.navy)),
            ),
            Flexible(
              child: ListView.separated(
                shrinkWrap: true,
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                itemCount: all.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (_, i) => ProductBreakdown.row(all[i]),
              ),
            ),
          ],
        ),
      ),
    ),
  );
}

/// Searchable list of customer names (e.g. who has not ordered), fine for hundreds of names.
Future<void> showNamesSheet(BuildContext context, {required String title, required List<String> names}) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: Colors.white,
    builder: (_) => _NamesSheet(title: title, names: names),
  );
}

class _NamesSheet extends StatefulWidget {
  final String title;
  final List<String> names;

  const _NamesSheet({required this.title, required this.names});

  @override
  State<_NamesSheet> createState() => _NamesSheetState();
}

class _NamesSheetState extends State<_NamesSheet> {
  String _search = '';

  @override
  Widget build(BuildContext context) {
    final list = widget.names.where((n) => _search.isEmpty || n.toLowerCase().contains(_search)).toList();
    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(context).height * 0.8),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
                child: Text('${widget.title} • ${widget.names.length}',
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppTheme.navy)),
              ),
              if (widget.names.length > 8)
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 8),
                  child: TextField(
                    decoration: const InputDecoration(hintText: 'Search customer', prefixIcon: Icon(Icons.search), isDense: true),
                    onChanged: (v) => setState(() => _search = v.trim().toLowerCase()),
                  ),
                ),
              Flexible(
                child: list.isEmpty
                    ? const Padding(
                        padding: EdgeInsets.all(24),
                        child: Text('No customer matches.', textAlign: TextAlign.center, style: TextStyle(color: AppTheme.textMuted)),
                      )
                    : ListView.separated(
                        shrinkWrap: true,
                        padding: const EdgeInsets.fromLTRB(20, 0, 20, 16),
                        itemCount: list.length,
                        separatorBuilder: (_, _) => const Divider(height: 1),
                        itemBuilder: (_, i) => Padding(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          child: Text(list[i], style: const TextStyle(fontSize: 14.5)),
                        ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// "12 customers have not ordered ›": one row instead of hundreds of names; opens the list.
class NotOrderedRow extends StatelessWidget {
  final List<String> names;
  final String when; // 'today', 'tomorrow', 'this day'

  const NotOrderedRow({super.key, required this.names, this.when = 'this day'});

  @override
  Widget build(BuildContext context) {
    final n = names.length;
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => showNamesSheet(context, title: 'No order $when', names: names),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(borderRadius: BorderRadius.circular(14), border: Border.all(color: AppTheme.border)),
          child: Row(
            children: [
              const Icon(Icons.person_off_outlined, size: 20, color: AppTheme.warmAmber),
              const SizedBox(width: 10),
              Expanded(
                child: Text('$n customer${n == 1 ? ' has' : 's have'} not ordered $when',
                    style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600)),
              ),
              const Text('View', style: TextStyle(fontSize: 13, color: AppTheme.primaryBlue, fontWeight: FontWeight.w600)),
              const Icon(Icons.chevron_right, size: 20, color: AppTheme.primaryBlue),
            ],
          ),
        ),
      ),
    );
  }
}
