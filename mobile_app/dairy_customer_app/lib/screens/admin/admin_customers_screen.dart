import 'package:flutter/material.dart';

import '../../models/admin_models.dart';
import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../utils/format.dart';
import '../error_view.dart';
import 'admin_widgets.dart';

/// Customers with their rate, route and dues; one tap to call.
class AdminCustomersScreen extends StatefulWidget {
  final bool sortByDues;

  const AdminCustomersScreen({super.key, this.sortByDues = false});

  @override
  State<AdminCustomersScreen> createState() => _AdminCustomersScreenState();
}

class _AdminCustomersScreenState extends State<AdminCustomersScreen> {
  List<AdminCustomer> _customers = [];
  String? _error;
  bool _loading = true;
  String _search = '';
  late bool _byDues = widget.sortByDues;
  bool _showInactive = false;

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
      final list = await ApiService.adminCustomers();
      setState(() => _customers = list);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final list = _customers
        .where((c) => (_showInactive || c.isActive) &&
            (_search.isEmpty || c.name.toLowerCase().contains(_search) || c.code.toLowerCase().contains(_search) || c.phone.contains(_search)))
        .toList()
      ..sort((a, b) => _byDues ? b.outstanding.compareTo(a.outstanding) : a.name.compareTo(b.name));
    final dues = list.fold<double>(0, (s, c) => s + (c.outstanding > 0 ? c.outstanding : 0));

    return Scaffold(
      appBar: AppBar(title: Text(widget.sortByDues ? 'Customer Dues' : 'Customers')),
      body: _loading && _customers.isEmpty
          ? const Center(child: CircularProgressIndicator(color: AppTheme.navy))
          : _error != null && _customers.isEmpty
              ? ErrorView(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                    children: [
                      TextField(
                        decoration: const InputDecoration(hintText: 'Search name, code or mobile', prefixIcon: Icon(Icons.search), isDense: true),
                        onChanged: (v) => setState(() => _search = v.trim().toLowerCase()),
                      ),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 8,
                        runSpacing: 4,
                        children: [
                          ChoiceChip(
                            label: const Text('A–Z'),
                            selected: !_byDues,
                            labelStyle: TextStyle(color: !_byDues ? Colors.white : AppTheme.textMain, fontWeight: FontWeight.w600),
                            onSelected: (_) => setState(() => _byDues = false),
                          ),
                          ChoiceChip(
                            label: const Text('Highest dues'),
                            selected: _byDues,
                            labelStyle: TextStyle(color: _byDues ? Colors.white : AppTheme.textMain, fontWeight: FontWeight.w600),
                            onSelected: (_) => setState(() => _byDues = true),
                          ),
                          FilterChip(
                            label: const Text('Inactive too'),
                            selected: _showInactive,
                            labelStyle: TextStyle(color: _showInactive ? Colors.white : AppTheme.textMain, fontWeight: FontWeight.w600),
                            onSelected: (v) => setState(() => _showInactive = v),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text('${list.length} customers • total dues ${rupees(dues)}',
                          style: const TextStyle(fontSize: 12.5, color: AppTheme.textMuted)),
                      const SizedBox(height: 10),
                      if (list.isEmpty) const EmptyNote('No customer matches.'),
                      for (final c in list) ...[_card(c), const SizedBox(height: 10)],
                    ],
                  ),
                ),
    );
  }

  Widget _card(AdminCustomer c) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
        child: Row(
          children: [
            CircleAvatar(
              radius: 22,
              backgroundColor: c.isActive ? AppTheme.navy : AppTheme.textMuted,
              child: Text(c.name.isEmpty ? '?' : c.name[0].toUpperCase(),
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(c.name + (c.isActive ? '' : ' (inactive)'), style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text('${c.code} • ${c.routeName}${c.milkRate != null ? ' • ${rupees(c.milkRate!)}${c.rateProduct != null ? ' ${c.rateProduct}' : '/Liter'}' : ''}',
                      style: const TextStyle(fontSize: 12, color: AppTheme.textMuted)),
                  const SizedBox(height: 4),
                  Text(
                    c.outstanding > 0 ? 'Due ${rupees(c.outstanding)}' : (c.outstanding < 0 ? 'Advance ${rupees(-c.outstanding)}' : 'No dues'),
                    style: TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700,
                      color: c.outstanding > 0 ? (c.overLimit ? AppTheme.alertRose : AppTheme.warmAmber) : AppTheme.freshGreen,
                    ),
                  ),
                  if (c.overLimit)
                    Text('Over credit limit ${rupees(c.creditLimit)}', style: const TextStyle(fontSize: 12, color: AppTheme.alertRose)),
                ],
              ),
            ),
            IconButton(
              tooltip: 'Call ${c.name}',
              onPressed: () => callNumber(context, c.phone),
              icon: const Icon(Icons.call, color: AppTheme.freshGreen),
            ),
          ],
        ),
      ),
    );
  }
}
