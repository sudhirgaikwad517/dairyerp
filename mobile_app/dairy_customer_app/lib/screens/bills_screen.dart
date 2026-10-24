import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/ui.dart';
import 'error_view.dart';
import 'ledger_screen.dart';
import '../widgets/floating_nav_bar.dart';

/// Download a milk statement for any period in the dairy's bill format, plus bills issued by the dairy.
class BillsScreen extends StatefulWidget {
  const BillsScreen({super.key});

  @override
  State<BillsScreen> createState() => _BillsScreenState();
}

class _BillsScreenState extends State<BillsScreen> {
  String _type = 'monthly';
  DateTime _month = DateTime(DateTime.now().year, DateTime.now().month);
  int _half = DateTime.now().day <= 15 ? 1 : 2;
  DateTime _day = DateTime.now();
  DateTimeRange? _range;
  List<BillItem>? _bills;
  String? _billsError;
  double? _outstanding;
  double _unbilled = 0;

  @override
  void initState() {
    super.initState();
    _loadBills();
  }

  Future<void> _loadBills() async {
    try {
      // Bills and the account balance together, so "total to pay" matches the statement
      final results = await Future.wait([ApiService.getBills(), ApiService.getLedger()]);
      if (!mounted) return;
      setState(() {
        _bills = results[0] as List<BillItem>;
        final ledger = results[1] as LedgerStatement;
        _outstanding = ledger.currentOutstanding;
        _unbilled = ledger.unbilledAmount;
        _billsError = null;
      });
    } on ApiException catch (e) {
      setState(() => _billsError = e.message);
    }
  }

  Future<void> _open(Uri url) async {
    final ok = await launchUrl(url, mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open the PDF')));
    }
  }

  Map<String, String> _params() {
    switch (_type) {
      case 'fortnightly':
        return {'bill_type': 'fortnightly', 'ref_date': ApiService.isoDate(DateTime(_month.year, _month.month, _half == 1 ? 1 : 16))};
      case 'daily':
        return {'bill_type': 'daily', 'ref_date': ApiService.isoDate(_day)};
      case 'custom':
        return {
          'bill_type': 'custom',
          'start_date': ApiService.isoDate(_range!.start),
          'end_date': ApiService.isoDate(_range!.end),
        };
      default:
        return {'bill_type': 'monthly', 'ref_date': ApiService.isoDate(_month)};
    }
  }

  Future<void> _pickMonth() async {
    final now = DateTime.now();
    final months = List.generate(12, (i) => DateTime(now.year, now.month - i));
    final picked = await showModalBottomSheet<DateTime>(
      context: context,
      builder: (ctx) => ListView(
        shrinkWrap: true,
        children: months
            .map((m) => ListTile(
                  title: Text(DateFormat('MMMM yyyy').format(m)),
                  trailing: m == _month ? const Icon(Icons.check, color: AppTheme.primaryBlue) : null,
                  onTap: () => Navigator.pop(ctx, m),
                ))
            .toList(),
      ),
    );
    if (picked != null) setState(() => _month = picked);
  }

  Future<void> _pickDay() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _day,
      firstDate: DateTime(now.year - 1),
      lastDate: now,
    );
    if (picked != null) setState(() => _day = picked);
  }

  Future<void> _pickRange() async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 1),
      lastDate: now,
      initialDateRange: _range,
    );
    if (picked != null) {
      if (picked.duration.inDays > 61) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Choose at most 62 days')));
        }
        return;
      }
      setState(() => _range = picked);
    }
  }

  @override
  Widget build(BuildContext context) {
    final canDownload = _type != 'custom' || _range != null;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Bills'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: TextButton.icon(
              onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const LedgerStatementScreen())),
              icon: const Icon(Icons.account_balance_wallet_outlined, color: AppTheme.navy, size: 20),
              label: const Text('Statement', style: TextStyle(color: AppTheme.navy, fontWeight: FontWeight.w700)),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadBills,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          // Room for the floating bottom bar
          padding: EdgeInsets.fromLTRB(16, 16, 16, navBarListPadding(context)),
          children: [
            if (_bills != null && _outstanding != null) ...[
              _summary(_bills!, _outstanding!, _unbilled),
              const SizedBox(height: 18),
            ],
            const Text('Bills from the dairy', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
            const SizedBox(height: 10),
            if (_billsError != null)
              ErrorView(message: _billsError!, onRetry: _loadBills)
            else if (_bills == null)
              const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator(color: AppTheme.navy)))
            else if (_bills!.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text('No bills yet.', textAlign: TextAlign.center, style: TextStyle(color: AppTheme.textMuted)),
                ),
              )
            else
              for (final b in _bills!) ...[_billCard(b), const SizedBox(height: 10)],
            const SizedBox(height: 10),
            _statementCard(canDownload),
          ],
        ),
      ),
    );
  }

  /// Unpaid bills, milk not billed yet, advance and what is to be paid now.
  Widget _summary(List<BillItem> bills, double outstanding, double unbilled) {
    final unpaid = bills.fold<double>(0, (s, b) => s + (b.balanceDue > 0 ? b.balanceDue : 0));
    final diff = ((outstanding - unpaid - unbilled) * 100).round() / 100;
    Widget cell(String label, String value, Color color) => Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: const TextStyle(fontSize: 11.5, color: Colors.white70, fontWeight: FontWeight.w600)),
              const SizedBox(height: 4),
              FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: color)),
              ),
            ],
          ),
        );
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0B2545), Color(0xFF13406B), Color(0xFF0E7FB5)],
          stops: [0, 0.6, 1],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(outstanding < 0 ? 'YOUR ADVANCE WITH DAIRY' : 'TOTAL TO PAY NOW',
              style: const TextStyle(color: Colors.white70, fontSize: 11.5, fontWeight: FontWeight.w700, letterSpacing: 0.6)),
          const SizedBox(height: 4),
          Text(rupees(outstanding.abs()),
              style: const TextStyle(color: Colors.white, fontSize: 30, fontWeight: FontWeight.w800, height: 1.1)),
          const SizedBox(height: 14),
          const Divider(color: Colors.white24, height: 1),
          const SizedBox(height: 12),
          Row(
            children: [
              cell('Unpaid bills', rupees(unpaid), const Color(0xFFFFC2C2)),
              if (unbilled > 0) cell('Not billed yet', rupees(unbilled), const Color(0xFFFFE3A3)),
              if (diff < 0) cell('Advance', '− ${rupees(-diff)}', const Color(0xFF7CE0AE)),
              if (diff > 0) cell('Other dues', rupees(diff), const Color(0xFFFFC2C2)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _billCard(BillItem b) {
    final (status, color) = b.isPaid
        ? ('Paid', AppTheme.freshGreen)
        : b.isPartPaid
            ? ('Part paid', AppTheme.warmAmber)
            : ('Unpaid', AppTheme.alertRose);
    final notes = <String>[
      for (final a in b.adjustments.where((a) => !a.refunded)) 'Claim ${a.text} deducted (−${rupees(a.amount)})',
      for (final a in b.adjustments.where((a) => a.refunded))
        'Claim ${a.text} refunded to you separately (${rupees(a.amount)}), not deducted here',
      if (b.advance > 0) 'Advance used ${rupees(b.advance)}',
      if (b.paidAmount > 0) 'Paid ${rupees(b.paidAmount)}',
      if (b.excessPaid > 0) '${rupees(b.excessPaid)} extra paid, kept as advance',
    ];
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(b.periodLabel, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800)),
                      const SizedBox(height: 2),
                      Text(b.invoiceNumber, style: const TextStyle(fontFamily: 'monospace', fontSize: 12, color: AppTheme.textMuted)),
                    ],
                  ),
                ),
                StatusChip(status, color: color),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(b.what, style: const TextStyle(color: AppTheme.textMuted, fontSize: 13)),
                      const SizedBox(height: 2),
                      Text(b.isPaid ? 'Fully paid' : 'Balance ${rupees(b.balanceDue)}',
                          style: TextStyle(fontWeight: FontWeight.w700, color: b.isPaid ? AppTheme.freshGreen : AppTheme.alertRose)),
                    ],
                  ),
                ),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(rupees(b.amount), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppTheme.navy)),
                    const SizedBox(height: 4),
                    OutlinedButton.icon(
                      onPressed: () => _open(ApiService.billPdfUrl(b.id)),
                      style: OutlinedButton.styleFrom(
                        visualDensity: VisualDensity.compact,
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      ),
                      icon: const Icon(Icons.picture_as_pdf_outlined, size: 18),
                      label: const Text('PDF'),
                    ),
                  ],
                ),
              ],
            ),
            if (notes.isNotEmpty) ...[
              const Divider(height: 20),
              for (final n in notes)
                Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Text(n, style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted)),
                ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _statementCard(bool canDownload) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Row(
              children: [
                Icon(Icons.picture_as_pdf_outlined, color: AppTheme.alertRose),
                SizedBox(width: 8),
                Text('Download milk statement', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
              ],
            ),
            const SizedBox(height: 4),
            const Text('Day-wise milk, rate and amount in the dairy bill format (PDF).',
                style: TextStyle(fontSize: 12.5, color: AppTheme.textMuted)),
            const SizedBox(height: 12),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'monthly', label: Text('Month')),
                ButtonSegment(value: 'fortnightly', label: Text('15 Days')),
                ButtonSegment(value: 'daily', label: Text('Day')),
                ButtonSegment(value: 'custom', label: Text('Custom')),
              ],
              selected: {_type},
              showSelectedIcon: false,
              onSelectionChanged: (s) => setState(() => _type = s.first),
            ),
            const SizedBox(height: 12),
            if (_type == 'monthly' || _type == 'fortnightly')
              OutlinedButton.icon(
                onPressed: _pickMonth,
                icon: const Icon(Icons.calendar_month),
                label: Text(DateFormat('MMMM yyyy').format(_month)),
              ),
            if (_type == 'fortnightly') ...[
              const SizedBox(height: 8),
              SegmentedButton<int>(
                segments: [
                  const ButtonSegment(value: 1, label: Text('1 - 15')),
                  ButtonSegment(value: 2, label: Text('16 - ${DateUtils.getDaysInMonth(_month.year, _month.month)}')),
                ],
                selected: {_half},
                showSelectedIcon: false,
                onSelectionChanged: (s) => setState(() => _half = s.first),
              ),
            ],
            if (_type == 'daily')
              OutlinedButton.icon(
                onPressed: _pickDay,
                icon: const Icon(Icons.event),
                label: Text(DateFormat('dd MMM yyyy').format(_day)),
              ),
            if (_type == 'custom')
              OutlinedButton.icon(
                onPressed: _pickRange,
                icon: const Icon(Icons.date_range),
                label: Text(_range == null
                    ? 'Choose dates'
                    : '${DateFormat('dd MMM').format(_range!.start)} - ${DateFormat('dd MMM yyyy').format(_range!.end)}'),
              ),
            const SizedBox(height: 12),
            ElevatedButton.icon(
              onPressed: canDownload ? () => _open(ApiService.statementPdfUrl(_params())) : null,
              icon: const Icon(Icons.download_rounded),
              label: const Text('Download PDF'),
            ),
          ],
        ),
      ),
    );
  }
}
