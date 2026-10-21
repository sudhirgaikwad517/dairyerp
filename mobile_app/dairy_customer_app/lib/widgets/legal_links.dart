import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';

/// Opens one of the dairy's public pages (/privacy, /terms, /delete-account) in the browser.
Future<void> openLegalPage(BuildContext context, String path) async {
  final ok = await launchUrl(ApiService.siteUrl(path), mode: LaunchMode.externalApplication);
  if (!ok && context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open the page')));
  }
}

/// "By logging in you agree to the Terms & Conditions and Privacy Policy" with tappable links.
class LoginConsentText extends StatefulWidget {
  const LoginConsentText({super.key});

  @override
  State<LoginConsentText> createState() => _LoginConsentTextState();
}

class _LoginConsentTextState extends State<LoginConsentText> {
  late final TapGestureRecognizer _terms = TapGestureRecognizer()..onTap = () => openLegalPage(context, '/terms');
  late final TapGestureRecognizer _privacy = TapGestureRecognizer()..onTap = () => openLegalPage(context, '/privacy');

  @override
  void dispose() {
    _terms.dispose();
    _privacy.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    const link = TextStyle(color: AppTheme.primaryBlue, fontWeight: FontWeight.w700, decoration: TextDecoration.underline);
    return Text.rich(
      TextSpan(
        text: 'By logging in you agree to the ',
        children: [
          TextSpan(text: 'Terms & Conditions', style: link, recognizer: _terms),
          const TextSpan(text: ' and '),
          TextSpan(text: 'Privacy Policy', style: link, recognizer: _privacy),
          const TextSpan(text: '.'),
        ],
      ),
      textAlign: TextAlign.center,
      style: const TextStyle(fontSize: 12, color: AppTheme.textMuted, height: 1.4),
    );
  }
}
