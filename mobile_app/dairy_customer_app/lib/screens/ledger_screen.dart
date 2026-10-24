import 'package:flutter/material.dart';

import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/ui.dart';
import 'error_view.dart';

class LedgerStatementScreen extends StatefulWidget {
  const LedgerStatementScreen({super.key});

  @override
  State<LedgerStatementScreen> createState() => _LedgerStatementScreenState();
}

class _LedgerStatementScreenState extends State<LedgerStatementScreen> {
  LedgerStatement? _statement;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final s = await ApiService.getLedger();
      setState(() => _statement = s);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = _statement;
    return Scaffold(
      appBar: AppBar(title: const Text('Account Statement')),
      body: _loading && s == null
          ? const Center(child: CircularProgressIndicator(color: AppTheme.navy))
          : _error != null && s == null
              ? ErrorView(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: EdgeInsets.fromLTRB(16, 16, 16, 32 + MediaQuery.paddingOf(context).bottom),
                    children: [
                      _header(s!),
                      const SizedBox(height: 10),
                      const Text('+ adds to your dues   •   − reduces them   •   newest first',
                          textAlign: TextAlign.center, style: TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                      const SizedBox(height: 10),
                      if (s.transactions.isEmpty)
                        const Card(
                          child: Padding(
                            padding: EdgeInsets.all(24),
                            child: Text('No transactions yet.', textAlign: TextAlign.center, style: TextStyle(color: AppTheme.textMuted)),
                          ),
                        )
                      else
                        Card(
                          child: Column(
                            children: [
                              for (var i = s.transactions.length - 1; i >= 0; i--) ...[
                                _transactionRow(s.transactions[i]),
                                if (i > 0) const Divider(height: 1, indent: 16, endIndent: 16),
                              ],
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
    );
  }

  Widget _header(LedgerStatement s) {
    final out = s.currentOutstanding;
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
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(out < 0 ? 'YOUR ADVANCE' : 'NET OUTSTANDING',
                    style: const TextStyle(color: Colors.white70, fontSize: 11.5, fontWeight: FontWeight.w700, letterSpacing: 0.6)),
                const SizedBox(height: 4),
                FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerLeft,
                  child: Text(rupees(out.abs()),
                      style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w800)),
                ),
                Text(out > 0 ? 'to pay' : (out < 0 ? 'will be used in your next bill' : 'all clear'),
                    style: TextStyle(color: out > 0 ? const Color(0xFFFFC2C2) : const Color(0xFF7CE0AE), fontSize: 12.5)),
                if (s.unbilledAmount > 0)
                  Text('incl. ${rupees(s.unbilledAmount)} delivered, not billed yet',
                      style: const TextStyle(color: Color(0xFFFFE3A3), fontSize: 12)),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              const Text('Credit limit', style: TextStyle(color: Colors.white70, fontSize: 12)),
              Text(s.creditLimit > 0 ? rupees(s.creditLimit) : 'No limit',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
            ],
          ),
        ],
      ),
    );
  }

  static const _types = {
    'opening_balance': ('Opening balance', AppTheme.textMuted),
    'sales_invoice': ('Bill', AppTheme.primaryBlue),
    'payment': ('Payment', AppTheme.freshGreen),
    'credit_note': ('Claim credit', AppTheme.warmAmber),
    'refund': ('Refund', AppTheme.warmAmber),
  };

  /// Negative running balance = money paid in advance
  String _balanceText(double v) => v < 0 ? '${rupees(-v)} advance' : rupees(v);

  Widget _transactionRow(LedgerTransaction t) {
    final isDebit = t.debit > 0;
    final (label, color) = _types[t.type] ?? (t.type.replaceAll('_', ' '), AppTheme.textMuted);
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    StatusChip(label, color: color),
                    const SizedBox(width: 8),
                    Text(niceDate(t.date), style: const TextStyle(color: AppTheme.textMuted, fontSize: 12)),
                  ],
                ),
                const SizedBox(height: 6),
                Text(t.narration, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                if (t.refNo.isNotEmpty)
                  Text(t.refNo, style: const TextStyle(fontFamily: 'monospace', fontSize: 11.5, color: AppTheme.textMuted)),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(isDebit ? '+ ${rupees(t.debit)}' : '− ${rupees(t.credit)}',
                  style: TextStyle(fontSize: 15.5, fontWeight: FontWeight.w800, color: isDebit ? AppTheme.alertRose : AppTheme.freshGreen)),
              const SizedBox(height: 4),
              Text('Bal ${_balanceText(t.balance)}', style: const TextStyle(fontSize: 11.5, color: AppTheme.textMuted)),
            ],
          ),
        ],
      ),
    );
  }
}
