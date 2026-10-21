import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/admin_models.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../utils/format.dart';
import '../../widgets/ui.dart';
import '../error_view.dart';
import 'admin_widgets.dart';
import '../../widgets/floating_nav_bar.dart';

/// Customers' bills for a month: billed, paid and balance, with the PDF.
class AdminBillsScreen extends StatefulWidget {
  const AdminBillsScreen({super.key});

  @override
  State<AdminBillsScreen> createState() => _AdminBillsScreenState();
}

class _AdminBillsScreenState extends State<AdminBillsScreen> {
  // Bills are usually made for the month that just ended
  DateTime _month = DateTime(DateTime.now().year, DateTime.now().month - 1);
  List<AdminBill> _bills = [];
  String? _error;
  bool _loading = true;
  String _filter = 'all'; // all | unpaid | paid

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final month = _month;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await ApiService.adminBills(month);
      if (month != _month) return;
      setState(() => _bills = list..sort((a, b) => a.customerName.compareTo(b.customerName)));
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _setMonth(DateTime m) {
    setState(() => _month = m);
    _load();
  }

  Future<void> _openPdf(AdminBill b) async {
    final ok = await launchUrl(ApiService.adminBillPdfUrl(b.id), mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open the PDF')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final shown = _bills.where((b) => _filter == 'all' || (_filter == 'paid' ? b.balanceDue <= 0 : b.balanceDue > 0)).toList();
    final billed = _bills.fold<double>(0, (s, b) => s + b.amount);
    final paid = _bills.fold<double>(0, (s, b) => s + b.paidAmount + b.advance);
    final balance = _bills.fold<double>(0, (s, b) => s + b.balanceDue);

    return Scaffold(
      appBar: AppBar(title: const Text('Bills')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: EdgeInsets.fromLTRB(16, 12, 16, navBarListPadding(context)),
          children: [
            MonthSwitcher(month: _month, onChanged: _setMonth),
            const SizedBox(height: 12),
            if (_loading && _bills.isEmpty && _error == null)
              const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator(color: AppTheme.navy)))
            else if (_error != null && _bills.isEmpty)
              ErrorView(message: _error!, onRetry: _load)
            else if (_bills.isEmpty)
              const EmptyNote('No bills for this month yet.\nBills are made from the web admin panel.', icon: Icons.receipt_long_outlined)
            else ...[
              _totals(billed, paid, balance),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                children: [
                  for (final (key, label) in const [('all', 'All'), ('unpaid', 'Unpaid'), ('paid', 'Paid')])
                    ChoiceChip(
                      label: Text(label),
                      selected: _filter == key,
                      labelStyle: TextStyle(color: _filter == key ? Colors.white : AppTheme.textMain, fontWeight: FontWeight.w600),
                      onSelected: (_) => setState(() => _filter = key),
                    ),
                ],
              ),
              const SizedBox(height: 10),
              if (shown.isEmpty) const EmptyNote('No bills in this list.'),
              for (final b in shown) ...[_billCard(b), const SizedBox(height: 10)],
            ],
          ],
        ),
      ),
    );
  }

  Widget _totals(double billed, double paid, double balance) {
    Widget cell(String label, double value, Color color) => Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: const TextStyle(fontSize: 12, color: Colors.white70)),
              const SizedBox(height: 4),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(rupees(value), style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: color)),
              ),
            ],
          ),
        );
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: AppTheme.navy, borderRadius: BorderRadius.circular(16)),
      child: Row(
        children: [
          cell('Billed (${_bills.length})', billed, Colors.white),
          cell('Received', paid, const Color(0xFF7CE0AE)),
          cell('Balance', balance, const Color(0xFFFFB4B4)),
        ],
      ),
    );
  }

  (String, Color) _status(AdminBill b) {
    if (b.balanceDue <= 0) return ('Paid', AppTheme.freshGreen);
    if (b.paidAmount + b.advance > 0) return ('Part paid', AppTheme.warmAmber);
    return ('Unpaid', AppTheme.alertRose);
  }

  Widget _billCard(AdminBill b) {
    final (text, color) = _status(b);
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => _showBill(b),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(b.customerName, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700))),
                  StatusChip(text, color: color),
                ],
              ),
              const SizedBox(height: 2),
              Text('${b.invoiceNumber} • ${b.periodLabel} • ${b.typeLabel}',
                  style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
              const Divider(height: 20),
              Row(
                children: [
                  Expanded(child: Text(b.what, style: const TextStyle(fontWeight: FontWeight.w600))),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text(rupees(b.amount), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: AppTheme.navy)),
                      if (b.balanceDue > 0)
                        Text('Balance ${rupees(b.balanceDue)}',
                            style: const TextStyle(fontSize: 12.5, color: AppTheme.alertRose, fontWeight: FontWeight.w600)),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showBill(AdminBill b) {
    Widget row(String label, String value, {Color? color, bool bold = false}) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 5),
          child: Row(
            children: [
              Expanded(child: Text(label, style: TextStyle(color: bold ? AppTheme.textMain : AppTheme.textMuted, fontWeight: bold ? FontWeight.w700 : FontWeight.w400))),
              Text(value, style: TextStyle(fontWeight: bold ? FontWeight.w800 : FontWeight.w600, color: color)),
            ],
          ),
        );
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: Colors.white,
      builder: (ctx) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(b.customerName, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
              Text('${b.invoiceNumber} • ${b.periodLabel}', style: const TextStyle(color: AppTheme.textMuted)),
              const Divider(height: 24),
              if (b.claimsQty > 0) ...[
                row('Delivered (before claims)', rupees(b.originalAmount)),
                row('Amount', rupees(b.originalAmount)),
                row('Less: claims', '- ${rupees(b.claimsAmount)}', color: AppTheme.alertRose),
                row('Net amount', rupees(b.amount), bold: true),
              ] else ...[
                row('Products', b.what),
                row('Amount', rupees(b.amount), bold: true),
              ],
              if (b.advance > 0) row('Advance used', '- ${rupees(b.advance)}'),
              row('Paid', rupees(b.paidAmount), color: AppTheme.freshGreen),
              row('Balance due', rupees(b.balanceDue), color: b.balanceDue > 0 ? AppTheme.alertRose : AppTheme.freshGreen, bold: true),
              if (b.excessPaid > 0) row('Excess paid (advance)', rupees(b.excessPaid), color: AppTheme.freshGreen),
              const Divider(height: 24),
              row("Customer's total outstanding", rupees(b.currentOutstanding < 0 ? 0 : b.currentOutstanding), bold: true),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: () => _openPdf(b),
                      icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
                      label: const Text('Open PDF'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => callNumber(ctx, b.customerPhone),
                      icon: const Icon(Icons.call_outlined, size: 18),
                      label: const Text('Call'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
