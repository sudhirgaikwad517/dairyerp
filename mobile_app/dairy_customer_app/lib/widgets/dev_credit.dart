import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme/app_theme.dart';

/// Small "Design Developed By Prowexa Technologies Pvt. Ltd" line; opens www.prowexa.com.
class DevCredit extends StatelessWidget {
  final Color color;

  const DevCredit({super.key, this.color = AppTheme.textMuted});

  static final Uri website = Uri.parse('https://www.prowexa.com');

  @override
  Widget build(BuildContext context) {
    return Center(
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => launchUrl(website, mode: LaunchMode.externalApplication),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
          child: Text.rich(
            TextSpan(
              text: 'Design Developed By ',
              children: const [
                TextSpan(text: 'Prowexa Technologies Pvt. Ltd', style: TextStyle(fontWeight: FontWeight.w700)),
              ],
            ),
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 11, color: color.withValues(alpha: 0.85)),
          ),
        ),
      ),
    );
  }
}
