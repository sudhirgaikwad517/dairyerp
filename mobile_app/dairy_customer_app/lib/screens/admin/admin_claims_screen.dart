import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../models/admin_models.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../utils/format.dart';
import '../../widgets/ui.dart';
import '../error_view.dart';
import 'admin_widgets.dart';

/// Customer claims (spoiled / short / not delivered): review and decide.
class AdminClaimsScreen extends StatefulWidget {
  const AdminClaimsScreen({super.key});

  @override
  State<AdminClaimsScreen> createState() => _AdminClaimsScreenState();
}

class _AdminClaimsScreenState extends State<AdminClaimsScreen> {
  String _status = 'pending';
  List<AdminClaim> _claims = [];
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final status = _status;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final list = await ApiService.adminClaims(status: status.isEmpty ? null : status);
      if (status != _status) return;
      setState(() => _claims = list);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _open(AdminClaim c) async {
    final changed = await Navigator.push<bool>(context, MaterialPageRoute(builder: (_) => AdminClaimDetailScreen(claimId: c.id)));
    if (changed == true) _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Claims')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
          children: [
            Wrap(
              spacing: 8,
              children: [
                for (final (key, label) in const [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('', 'All')])
                  ChoiceChip(
                    label: Text(label),
                    selected: _status == key,
                    labelStyle: TextStyle(color: _status == key ? Colors.white : AppTheme.textMain, fontWeight: FontWeight.w600),
                    onSelected: (_) {
                      setState(() => _status = key);
                      _load();
                    },
                  ),
              ],
            ),
            const SizedBox(height: 12),
            if (_loading && _claims.isEmpty)
              const Padding(padding: EdgeInsets.all(40), child: Center(child: CircularProgressIndicator(color: AppTheme.navy)))
            else if (_error != null && _claims.isEmpty)
              ErrorView(message: _error!, onRetry: _load)
            else if (_claims.isEmpty)
              EmptyNote(_status == 'pending' ? 'No claims waiting. All clear!' : 'No claims here.', icon: Icons.task_alt)
            else
              for (final c in _claims) ...[_card(c), const SizedBox(height: 10)],
          ],
        ),
      ),
    );
  }

  Widget _card(AdminClaim c) {
    final color = c.status == 'pending' ? AppTheme.warmAmber : (c.status == 'approved' ? AppTheme.freshGreen : AppTheme.textMuted);
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => _open(c),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(child: Text(c.customerName, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700))),
                  StatusChip(c.status[0].toUpperCase() + c.status.substring(1), color: color),
                ],
              ),
              const SizedBox(height: 4),
              Text('${c.reasonLabel} • ${niceDate(c.issueDate)}', style: const TextStyle(fontSize: 13, color: AppTheme.textMuted)),
              const SizedBox(height: 8),
              Row(
                children: [
                  Text('${qtyUnit(c.claimedQty, c.unit)} ${c.productName} claimed', style: const TextStyle(fontWeight: FontWeight.w600)),
                  if (c.photoIds.isNotEmpty) ...[
                    const SizedBox(width: 8),
                    const Icon(Icons.photo_outlined, size: 16, color: AppTheme.accentCyan),
                    Text(' ${c.photoIds.length}', style: const TextStyle(fontSize: 12, color: AppTheme.accentCyan)),
                  ],
                  const Spacer(),
                  Text(
                    c.status == 'approved' ? rupees(c.creditAmount) : (c.status == 'pending' ? '≈ ${rupees(c.claimedQty * c.rate)}' : ''),
                    style: const TextStyle(fontWeight: FontWeight.w800, color: AppTheme.navy),
                  ),
                ],
              ),
              if (c.status == 'approved')
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(c.settlementLabel, style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class AdminClaimDetailScreen extends StatefulWidget {
  final int claimId;

  const AdminClaimDetailScreen({super.key, required this.claimId});

  @override
  State<AdminClaimDetailScreen> createState() => _AdminClaimDetailScreenState();
}

class _AdminClaimDetailScreenState extends State<AdminClaimDetailScreen> {
  AdminClaim? _claim;
  String? _error;
  bool _saving = false;
  bool _changed = false;
  final _litres = TextEditingController();
  final _note = TextEditingController();
  final _reference = TextEditingController();
  String _mode = 'bill';
  String? _refundMethod;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _litres.dispose();
    _note.dispose();
    _reference.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final c = await ApiService.adminClaim(widget.claimId);
      setState(() {
        _claim = c;
        _error = null;
        _litres.text = qty(c.maxApprovable);
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    }
  }

  void _snack(String text, {Color? color}) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text), backgroundColor: color));

  Future<bool> _confirm(String title, String body) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(body),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Confirm')),
        ],
      ),
    );
    return ok == true;
  }

  Future<void> _approve() async {
    final c = _claim!;
    final litres = double.tryParse(_litres.text.replaceAll(',', '').trim()) ?? 0;
    if (litres <= 0) return _snack('Enter the litres to approve, or reject the claim.');
    if (litres > c.maxApprovable + 0.001) return _snack('At most ${qtyUnit(c.maxApprovable, c.unit)} can be approved.');
    if (wholeUnit(c.unit) && litres != litres.roundToDouble()) return _snack('${c.productName} is counted per ${unitName(c.unit)}; enter a whole number.');
    if (_mode == 'refund' && _refundMethod == null) return _snack('Choose how the refund was paid.');
    final amount = rupees(litres * c.rate);
    final body = _mode == 'refund'
        ? 'Refund $amount to ${c.customerName} separately. The bill will not change.'
        : 'Deduct ${qtyUnit(litres, c.unit)} ${c.productName} ($amount) from ${c.customerName}\'s bill${c.billedIn != null ? ' ${c.billedIn}' : ''}.';
    if (!await _confirm('Approve claim?', body)) return;
    setState(() => _saving = true);
    try {
      await ApiService.approveClaim(c.id, litres,
          mode: _mode,
          refundMethod: _mode == 'refund' ? _refundMethod : null,
          refundReference: _reference.text.trim().isEmpty ? null : _reference.text.trim(),
          note: _note.text.trim().isEmpty ? null : _note.text.trim());
      _changed = true;
      _snack('Claim approved', color: AppTheme.freshGreen);
      await _load();
    } on ApiException catch (e) {
      _snack(e.message, color: AppTheme.alertRose);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _reject() async {
    final note = _note.text.trim();
    if (note.isEmpty) return _snack('Write a reason in the note so the customer knows why.');
    if (!await _confirm('Reject claim?', 'The customer will see: "$note"')) return;
    setState(() => _saving = true);
    try {
      await ApiService.rejectClaim(_claim!.id, note);
      _changed = true;
      _snack('Claim rejected');
      await _load();
    } on ApiException catch (e) {
      _snack(e.message, color: AppTheme.alertRose);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = _claim;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.pop(context, _changed);
      },
      child: Scaffold(
        appBar: AppBar(title: Text(c?.claimNumber ?? 'Claim')),
        body: c == null
            ? (_error != null ? ErrorView(message: _error!, onRetry: _load) : const Center(child: CircularProgressIndicator(color: AppTheme.navy)))
            : ListView(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                children: [
                  _claimCard(c),
                  const SectionHeader('Delivery record'),
                  _deliveryCard(c),
                  const SectionHeader('Decision'),
                  c.status == 'pending' ? _decisionForm(c) : _decided(c),
                ],
              ),
      ),
    );
  }

  Widget _row(String label, String value, {Color? color}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(width: 130, child: Text(label, style: const TextStyle(color: AppTheme.textMuted))),
            Expanded(child: Text(value, style: TextStyle(fontWeight: FontWeight.w600, color: color))),
          ],
        ),
      );

  Widget _claimCard(AdminClaim c) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(c.customerName, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
            if (c.createdAt != null)
              Text('Reported ${DateFormat('dd MMM, h:mm a').format(c.createdAt!)}', style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
            const Divider(height: 20),
            _row('Delivery date', niceDate(c.issueDate)),
            _row('Problem', c.reasonLabel),
            _row('Product', c.productName),
            _row('Claimed', qtyUnit(c.claimedQty, c.unit), color: AppTheme.alertRose),
            _row('Customer says', c.description),
            if (c.photoIds.isNotEmpty) ...[
              const SizedBox(height: 10),
              PhotoStrip(c.photoIds),
            ] else
              const Padding(padding: EdgeInsets.only(top: 6), child: Text('No photos attached.', style: TextStyle(color: AppTheme.textMuted))),
          ],
        ),
      ),
    );
  }

  Widget _deliveryCard(AdminClaim c) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _row('Ordered', qtyUnit(c.orderedQty, c.unit)),
            _row('Delivered', qtyUnit(c.deliveredQty, c.unit)),
            _row('Other claims', qtyUnit(c.otherClaimsQty, c.unit)),
            for (final d in c.deliveries) ...[
              const Divider(height: 20),
              Text('${d.driverName ?? 'Delivery boy'}${d.deliveredAt != null ? ' • ${DateFormat('dd MMM, h:mm a').format(d.deliveredAt!)}' : ''}',
                  style: const TextStyle(fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text('${d.status.replaceAll('_', ' ')} • received by ${d.deliveredTo ?? '-'}',
                  style: const TextStyle(fontSize: 13, color: AppTheme.textMuted)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (d.photoIds.isNotEmpty) PhotoStrip(d.photoIds) else const Text('No delivery photo', style: TextStyle(color: AppTheme.warmAmber)),
                  if (d.signature != null && d.signature!.contains(','))
                    Container(
                      height: 84,
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(border: Border.all(color: AppTheme.border), borderRadius: BorderRadius.circular(10), color: Colors.white),
                      child: Image.memory(base64Decode(d.signature!.split(',').last), fit: BoxFit.contain),
                    )
                  else
                    const Text('No signature', style: TextStyle(color: AppTheme.warmAmber)),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _decisionForm(AdminClaim c) {
    final billNote = c.billedIn != null
        ? 'This day is already billed in ${c.billedIn}. That bill will be reduced now.'
            '${c.billedBalanceDue == 0 ? ' The bill is fully paid, so the amount becomes advance for the next bill.' : ''}'
        : 'Not billed yet. It will be deducted when the bill is made.';
    final litres = double.tryParse(_litres.text) ?? 0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _litres,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(
                labelText: 'Approve litres (max ${qty(c.maxApprovable)})',
                helperText: 'Rate ${rupees(c.rate)}/${unitName(c.unit)} • credit ${rupees(litres * c.rate)}',
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 14),
            const Text('How to settle', style: TextStyle(fontWeight: FontWeight.w700)),
            const SizedBox(height: 6),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'bill', label: Text('Deduct from bill'), icon: Icon(Icons.receipt_long_outlined)),
                ButtonSegment(value: 'refund', label: Text('Refund'), icon: Icon(Icons.currency_rupee)),
              ],
              selected: {_mode},
              onSelectionChanged: (s) => setState(() => _mode = s.first),
            ),
            const SizedBox(height: 8),
            Text(
              _mode == 'bill' ? billNote : 'Pay the money back yourself. The bill stays as it is; the claim is shown on it as refunded.',
              style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted, height: 1.35),
            ),
            if (_mode == 'refund') ...[
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _refundMethod,
                decoration: const InputDecoration(labelText: 'Refund paid by'),
                items: const [
                  DropdownMenuItem(value: 'cash', child: Text('Cash')),
                  DropdownMenuItem(value: 'upi', child: Text('UPI')),
                  DropdownMenuItem(value: 'bank_transfer', child: Text('Bank transfer')),
                ],
                onChanged: (v) => setState(() => _refundMethod = v),
              ),
              const SizedBox(height: 10),
              TextField(controller: _reference, decoration: const InputDecoration(labelText: 'Reference / UTR (optional)')),
            ],
            const SizedBox(height: 12),
            TextField(
              controller: _note,
              maxLength: 300,
              decoration: const InputDecoration(labelText: 'Note to customer (needed to reject)'),
            ),
            const SizedBox(height: 6),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(foregroundColor: AppTheme.alertRose, side: const BorderSide(color: AppTheme.alertRose)),
                    onPressed: _saving ? null : _reject,
                    child: const Text('Reject'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(backgroundColor: AppTheme.freshGreen),
                    onPressed: _saving ? null : _approve,
                    child: _saving
                        ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                        : const Text('Approve'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _decided(AdminClaim c) {
    final approved = c.status == 'approved';
    return Card(
      color: approved ? const Color(0xFFE8F7EF) : const Color(0xFFF1F5F9),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(approved ? 'APPROVED' : 'REJECTED',
                style: TextStyle(fontWeight: FontWeight.w800, letterSpacing: 1, color: approved ? AppTheme.freshGreen : AppTheme.textMuted)),
            const SizedBox(height: 6),
            if (approved) ...[
              Text('${qtyUnit(c.approvedQty, c.unit)} × ${rupees(c.rate)} = ${rupees(c.creditAmount)}', style: const TextStyle(fontWeight: FontWeight.w700)),
              Text(c.settlementLabel + (c.billedIn != null && c.settlement != 'refund' ? ' • ${c.billedIn}' : '')),
            ],
            if (c.adminNote != null) Text('Note: ${c.adminNote}'),
            const SizedBox(height: 8),
            const Text('To undo this decision, use the web admin panel.', style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
          ],
        ),
      ),
    );
  }
}
