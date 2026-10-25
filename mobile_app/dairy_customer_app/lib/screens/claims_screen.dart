import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../models/dairy_models.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import 'error_view.dart';
import '../widgets/floating_nav_bar.dart';

/// Spoiled / short / not delivered milk reported by the customer, with the dairy's decision.
class ClaimsScreen extends StatefulWidget {
  const ClaimsScreen({super.key});

  @override
  State<ClaimsScreen> createState() => _ClaimsScreenState();
}

class _ClaimsScreenState extends State<ClaimsScreen> {
  List<ClaimItem> _claims = [];
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
      final claims = await ApiService.getClaims();
      setState(() => _claims = claims);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _newClaim() async {
    final created = await Navigator.push<ClaimItem>(context, MaterialPageRoute(builder: (_) => const NewClaimScreen()));
    if (created != null) {
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Problem ${created.claimNumber} sent. The dairy will check and reply.'),
          backgroundColor: AppTheme.freshGreen,
        ));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Milk Problems')),
      floatingActionButton: aboveNavBar(
        context,
        FloatingActionButton.extended(
          onPressed: _newClaim,
          icon: const Icon(Icons.report_problem_outlined),
          label: const Text('Report a problem'),
          backgroundColor: AppTheme.alertRose,
          foregroundColor: Colors.white,
        ),
      ),
      body: _loading && _claims.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : _error != null && _claims.isEmpty
              ? ErrorView(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: _claims.isEmpty
                      ? ListView(
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: EdgeInsets.only(bottom: 72 + navBarListPadding(context)),
                          children: const [
                            Padding(
                              padding: EdgeInsets.all(32),
                              child: Text(
                                'Milk spoiled, less milk, or not delivered?\nReport it here with photos. '
                                'Once the dairy approves, the amount is reduced from your bill.',
                                textAlign: TextAlign.center,
                                style: TextStyle(color: Colors.black54),
                              ),
                            ),
                          ],
                        )
                      : ListView.builder(
                          physics: const AlwaysScrollableScrollPhysics(),
                          // Room for the button and the floating bottom bar
                          padding: EdgeInsets.fromLTRB(16, 16, 16, 72 + navBarListPadding(context)),
                          itemCount: _claims.length,
                          itemBuilder: (_, i) => _claimCard(_claims[i]),
                        ),
                ),
    );
  }

  Widget _claimCard(ClaimItem c) {
    final color = c.status == 'approved'
        ? AppTheme.freshGreen
        : (c.status == 'rejected' ? Colors.black45 : AppTheme.warmAmber);
    final statusText = c.status == 'approved'
        ? 'Approved ${qtyUnit(c.approvedQty, c.unit)} • ${rupees(c.creditAmount)}'
        : (c.status == 'rejected' ? 'Rejected' : 'Waiting for dairy to check');
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(niceDate(c.issueDate), style: const TextStyle(fontWeight: FontWeight.bold)),
                Text(c.claimNumber, style: const TextStyle(fontSize: 11, color: Colors.black45, fontFamily: 'monospace')),
              ],
            ),
            const SizedBox(height: 4),
            Text('${c.reasonLabel} • ${qtyUnit(c.claimedQty, c.unit)}${c.productName.isNotEmpty ? ' ${c.productName}' : ''}',
                style: const TextStyle(fontSize: 13)),
            const SizedBox(height: 4),
            Text(c.description, style: const TextStyle(fontSize: 12, color: Colors.black54)),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(8)),
              child: Text(statusText, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 12)),
            ),
            if (c.settlementText.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(c.settlementText, style: const TextStyle(fontSize: 12, color: Colors.black54)),
            ],
            if ((c.adminNote ?? '').isNotEmpty) ...[
              const SizedBox(height: 4),
              Text('Dairy: ${c.adminNote}', style: const TextStyle(fontSize: 12, fontStyle: FontStyle.italic)),
            ],
          ],
        ),
      ),
    );
  }
}

class NewClaimScreen extends StatefulWidget {
  const NewClaimScreen({super.key});

  @override
  State<NewClaimScreen> createState() => _NewClaimScreenState();
}

class _NewClaimScreenState extends State<NewClaimScreen> {
  static const _maxPhotos = 5;
  final _picker = ImagePicker();
  final _qtyController = TextEditingController();
  final _descController = TextEditingController();
  ClaimOptions? _options;
  ClaimableDay? _day;
  ClaimProduct? _product; // which product the problem is with
  String _reason = 'spoiled';
  final List<XFile> _photos = [];
  final Map<String, Uint8List> _previews = {};
  bool _loading = true;
  bool _submitting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _qtyController.dispose();
    _descController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final options = await ApiService.getClaimableDays();
      setState(() {
        _options = options;
        _day = options.days.isNotEmpty ? options.days.first : null;
        _product = _firstProduct(_day);
      });
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  ClaimProduct? _firstProduct(ClaimableDay? d) => d == null || d.products.isEmpty ? null : d.products.first;

  // The product chosen, or (older server) the day's single product
  String get _unit => _product?.unit ?? 'L';
  double get _available => _product?.availableQty ?? (_day?.availableQty ?? 0);
  double get _rate => _product?.rate ?? (_day?.rate ?? 0);

  Future<void> _addPhoto(ImageSource source) async {
    if (_photos.length >= _maxPhotos) return;
    try {
      final photo = await _picker.pickImage(source: source, maxWidth: 1600, imageQuality: 85);
      if (photo == null) return;
      final bytes = await photo.readAsBytes();
      setState(() {
        _photos.add(photo);
        _previews[photo.path] = bytes;
      });
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not open the camera / gallery. Check app permissions.')),
        );
      }
    }
  }

  Future<void> _submit() async {
    final day = _day;
    final quantity = double.tryParse(_qtyController.text) ?? 0;
    String? problem;
    if (day == null) {
      problem = 'Choose the delivery date';
    } else if (day.products.length > 1 && _product == null) {
      problem = 'Choose which product had the problem';
    } else if (quantity <= 0) {
      problem = 'Enter how much was affected';
    } else if (wholeUnit(_unit) && quantity != quantity.roundToDouble()) {
      problem = 'Enter a whole number of ${unitName(_unit)}';
    } else if (quantity > _available + 0.0001) {
      problem = 'You can report at most ${qtyUnit(_available, _unit)} for this date';
    } else if (_descController.text.trim().isEmpty) {
      problem = 'Describe what happened';
    } else if (_photos.isEmpty && _reason != 'not_delivered') {
      problem = 'Add at least one photo';
    }
    if (problem != null) {
      setState(() => _error = problem);
      return;
    }
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final claim = await ApiService.submitClaim(
        issueDate: day!.date,
        reason: _reason,
        quantity: quantity,
        description: _descController.text.trim(),
        photos: _photos,
        productId: _product?.productId,
      );
      if (mounted) Navigator.pop(context, claim);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final options = _options;
    return Scaffold(
      appBar: AppBar(title: const Text('Report a Problem')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : options == null
              ? ErrorView(message: _error ?? 'Could not load', onRetry: () {
                  setState(() => _loading = true);
                  _load();
                })
              : options.days.isEmpty
                  ? const Center(
                      child: Padding(
                        padding: EdgeInsets.all(32),
                        child: Text('No delivered milk in the last 7 days to report a problem for.',
                            textAlign: TextAlign.center, style: TextStyle(color: Colors.black54)),
                      ),
                    )
                  : ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        const Text('Which delivery?', style: TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        DropdownButtonFormField<ClaimableDay>(
                          initialValue: _day,
                          isExpanded: true,
                          decoration: const InputDecoration(border: OutlineInputBorder()),
                          items: options.days
                              .map((d) => DropdownMenuItem(
                                    value: d,
                                    child: Text('${niceDate(d.date)} • ${d.deliveredText}', overflow: TextOverflow.ellipsis),
                                  ))
                              .toList(),
                          onChanged: (d) => setState(() {
                            _day = d;
                            _product = _firstProduct(d);
                          }),
                        ),
                        if (_day != null && _day!.products.length > 1) ...[
                          const SizedBox(height: 16),
                          const Text('Which product?', style: TextStyle(fontWeight: FontWeight.bold)),
                          const SizedBox(height: 8),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: _day!.products
                                .map((p) => ChoiceChip(
                                      label: Text('${p.name} (${qtyUnit(p.deliveredQty, p.unit)})'),
                                      selected: _product?.productId == p.productId,
                                      onSelected: (_) => setState(() => _product = p),
                                    ))
                                .toList(),
                          ),
                        ],
                        if (_day != null && _product != null && _product!.availableQty < _product!.deliveredQty)
                          Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text('Already reported for this day; up to ${qtyUnit(_product!.availableQty, _unit)} left',
                                style: const TextStyle(fontSize: 12, color: Colors.black54)),
                          ),
                        const SizedBox(height: 16),
                        const Text('What went wrong?', style: TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: options.reasons.entries
                              .map((e) => ChoiceChip(
                                    label: Text(e.value),
                                    selected: _reason == e.key,
                                    onSelected: (_) => setState(() => _reason = e.key),
                                  ))
                              .toList(),
                        ),
                        const SizedBox(height: 16),
                        TextField(
                          controller: _qtyController,
                          keyboardType: wholeUnit(_unit) ? TextInputType.number : const TextInputType.numberWithOptions(decimal: true),
                          inputFormatters: [FilteringTextInputFormatter.allow(wholeUnit(_unit) ? RegExp(r'^\d*') : RegExp(r'^\d*\.?\d{0,2}'))],
                          decoration: InputDecoration(
                            labelText: 'How much was affected?',
                            suffixText: unitName(_unit),
                            helperText: _rate <= 0 ? null : 'Rate ${rupees(_rate)}/${unitName(_unit)}',
                            border: const OutlineInputBorder(),
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextField(
                          controller: _descController,
                          maxLines: 3,
                          maxLength: 500,
                          decoration: const InputDecoration(
                            labelText: 'What happened? When did you notice it?',
                            hintText: 'e.g. 10 pouches were sour when opened at 7 am',
                            border: OutlineInputBorder(),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text('Photos (${_photos.length}/$_maxPhotos)', style: const TextStyle(fontWeight: FontWeight.bold)),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            ..._photos.map((p) => Stack(
                                  children: [
                                    ClipRRect(
                                      borderRadius: BorderRadius.circular(8),
                                      child: Image.memory(_previews[p.path]!, width: 90, height: 90, fit: BoxFit.cover),
                                    ),
                                    Positioned(
                                      right: 0,
                                      top: 0,
                                      child: InkWell(
                                        onTap: () => setState(() {
                                          _photos.remove(p);
                                          _previews.remove(p.path);
                                        }),
                                        child: Container(
                                          color: Colors.black54,
                                          child: const Icon(Icons.close, color: Colors.white, size: 18),
                                        ),
                                      ),
                                    ),
                                  ],
                                )),
                            if (_photos.length < _maxPhotos) ...[
                              OutlinedButton.icon(
                                onPressed: () => _addPhoto(ImageSource.camera),
                                icon: const Icon(Icons.photo_camera),
                                label: const Text('Camera'),
                              ),
                              OutlinedButton.icon(
                                onPressed: () => _addPhoto(ImageSource.gallery),
                                icon: const Icon(Icons.photo_library),
                                label: const Text('Gallery'),
                              ),
                            ],
                          ],
                        ),
                        if (_error != null) ...[
                          const SizedBox(height: 12),
                          Text(_error!, style: const TextStyle(color: AppTheme.alertRose)),
                        ],
                        const SizedBox(height: 20),
                        ElevatedButton.icon(
                          onPressed: _submitting ? null : _submit,
                          icon: _submitting
                              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                              : const Icon(Icons.send),
                          label: const Text('Send to Dairy'),
                        ),
                      ],
                    ),
    );
  }
}
