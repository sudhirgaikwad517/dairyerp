import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import '../widgets/dairy_logo.dart';
import '../widgets/dev_credit.dart';
import '../widgets/legal_links.dart';

class LoginScreen extends StatefulWidget {
  final VoidCallback onLoggedIn;
  final String? message;

  const LoginScreen({super.key, required this.onLoggedIn, this.message});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _mobileController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  bool _staff = false; // customer logs in with mobile number, dairy staff with username
  String? _error;

  @override
  void initState() {
    super.initState();
    _error = widget.message;
  }

  @override
  void dispose() {
    _mobileController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  void _setStaff(bool staff) {
    if (staff == _staff) return;
    setState(() {
      _staff = staff;
      _error = null;
      _mobileController.clear();
      _formKey.currentState?.reset();
    });
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ApiService.login(_mobileController.text.trim(), _passwordController.text);
      widget.onLoggedIn();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.light,
      child: Scaffold(
        backgroundColor: AppTheme.backgroundLight,
        body: SingleChildScrollView(
          child: Column(
            children: [
              _header(context),
              Transform.translate(
                offset: const Offset(0, -44),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 18),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 420),
                    child: _formCard(),
                  ),
                ),
              ),
              Transform.translate(
                offset: const Offset(0, -28),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 24),
                  child: Text(
                    "Don't have a login or forgot your password?\nPlease call the dairy.",
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppTheme.textMuted, fontSize: 13, height: 1.4),
                  ),
                ),
              ),
              Transform.translate(
                offset: const Offset(0, -18),
                child: const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 28),
                  child: LoginConsentText(),
                ),
              ),
              Transform.translate(
                offset: const Offset(0, -12),
                child: const DevCredit(),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _header(BuildContext context) {
    final top = MediaQuery.of(context).padding.top;
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(24, top + 40, 24, 76),
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0B2545), Color(0xFF13406B), Color(0xFF0E7FB5)],
          stops: [0, 0.55, 1],
        ),
      ),
      child: const Column(
        children: [
          DairyLogo(size: 112),
          SizedBox(height: 16),
          Text('Akash Dairy Farm',
              style: TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.w800, letterSpacing: -0.3)),
          SizedBox(height: 4),
          Text('Fresh milk, delivered every morning',
              style: TextStyle(color: Color(0xCCFFFFFF), fontSize: 14)),
        ],
      ),
    );
  }

  Widget _formCard() {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 22),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(color: AppTheme.navy.withValues(alpha: 0.12), blurRadius: 30, offset: const Offset(0, 12)),
        ],
      ),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Welcome back', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AppTheme.textMain)),
            const SizedBox(height: 2),
            Text(_staff ? 'Log in with your dairy staff username' : 'Log in with your registered mobile number',
                style: const TextStyle(color: AppTheme.textMuted, fontSize: 13.5)),
            const SizedBox(height: 18),
            _roleSwitch(),
            const SizedBox(height: 18),
            TextFormField(
              key: ValueKey(_staff),
              controller: _mobileController,
              keyboardType: _staff ? TextInputType.text : TextInputType.phone,
              autocorrect: false,
              autofillHints: [_staff ? AutofillHints.username : AutofillHints.telephoneNumber],
              textInputAction: TextInputAction.next,
              decoration: _input(
                label: _staff ? 'Username' : 'Mobile number',
                hint: _staff ? 'Your username' : '10-digit mobile number',
                icon: _staff ? Icons.badge_outlined : Icons.phone_android,
              ),
              validator: (v) {
                final text = (v ?? '').trim();
                if (_staff) return text.isEmpty ? 'Enter your username' : null;
                final digits = text.replaceAll(RegExp(r'\D'), '');
                return digits.length < 10 ? 'Enter your 10-digit mobile number' : null;
              },
            ),
            const SizedBox(height: 14),
            TextFormField(
              controller: _passwordController,
              obscureText: _obscure,
              autofillHints: const [AutofillHints.password],
              textInputAction: TextInputAction.done,
              onFieldSubmitted: (_) => _submit(),
              decoration: _input(label: 'Password', icon: Icons.lock_outline).copyWith(
                suffixIcon: IconButton(
                  icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                  tooltip: _obscure ? 'Show password' : 'Hide password',
                  onPressed: () => setState(() => _obscure = !_obscure),
                ),
              ),
              validator: (v) => (v ?? '').isEmpty ? 'Enter your password' : null,
            ),
            if (_error != null) ...[
              const SizedBox(height: 14),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.alertRose.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppTheme.alertRose.withValues(alpha: 0.25)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.error_outline, color: AppTheme.alertRose, size: 20),
                    const SizedBox(width: 8),
                    Expanded(child: Text(_error!, style: const TextStyle(color: AppTheme.alertRose, fontWeight: FontWeight.w500))),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 20),
            SizedBox(
              height: 52,
              child: ElevatedButton(
                onPressed: _loading ? null : _submit,
                style: ElevatedButton.styleFrom(
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                  disabledBackgroundColor: AppTheme.navy.withValues(alpha: 0.6),
                ),
                child: _loading
                    ? const SizedBox(height: 22, width: 22, child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white))
                    : const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text('Log In', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                          SizedBox(width: 8),
                          Icon(Icons.arrow_forward_rounded, size: 20),
                        ],
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _roleSwitch() {
    Widget option(String label, IconData icon, bool staff) {
      final selected = _staff == staff;
      return Expanded(
        child: GestureDetector(
          onTap: _loading ? null : () => _setStaff(staff),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            padding: const EdgeInsets.symmetric(vertical: 10),
            decoration: BoxDecoration(
              color: selected ? Colors.white : Colors.transparent,
              borderRadius: BorderRadius.circular(10),
              boxShadow: selected ? [BoxShadow(color: Colors.black.withValues(alpha: 0.08), blurRadius: 4, offset: const Offset(0, 1))] : null,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, size: 18, color: selected ? AppTheme.navy : AppTheme.textMuted),
                const SizedBox(width: 6),
                Flexible(
                  child: FittedBox(
                    fit: BoxFit.scaleDown,
                    child: Text(label,
                        maxLines: 1,
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13.5,
                          color: selected ? AppTheme.navy : AppTheme.textMuted,
                        )),
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(color: const Color(0xFFE8EEF3), borderRadius: BorderRadius.circular(13)),
      child: Row(
        children: [
          option('Customer', Icons.storefront_outlined, false),
          const SizedBox(width: 4),
          option('Dairy Staff', Icons.admin_panel_settings_outlined, true),
        ],
      ),
    );
  }

  InputDecoration _input({required String label, String? hint, required IconData icon}) {
    OutlineInputBorder border(Color color, [double width = 1]) => OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: color, width: width),
        );
    return InputDecoration(
      labelText: label,
      hintText: hint,
      prefixIcon: Icon(icon),
      filled: true,
      fillColor: const Color(0xFFF8FAFC),
      border: border(AppTheme.border),
      enabledBorder: border(AppTheme.border),
      focusedBorder: border(AppTheme.primaryBlue, 1.6),
      errorBorder: border(AppTheme.alertRose),
      focusedErrorBorder: border(AppTheme.alertRose, 1.6),
    );
  }
}
