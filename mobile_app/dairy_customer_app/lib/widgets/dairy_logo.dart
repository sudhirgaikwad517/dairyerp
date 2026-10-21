import 'package:flutter/material.dart';

/// Akash Dairy Farm logo (Gir cow badge). Same picture as the web logo
/// (frontend/assets/logo-192.png) and the app icon.
class DairyLogo extends StatelessWidget {
  final double size;

  const DairyLogo({super.key, this.size = 72});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: 'Akash Dairy Farm logo',
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          color: Colors.white,
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(color: const Color(0xFF0B2545).withValues(alpha: 0.25), blurRadius: size * 0.2, offset: Offset(0, size * 0.06)),
          ],
        ),
        child: ClipOval(
          child: Image.asset('assets/logo.png', width: size, height: size, fit: BoxFit.cover, filterQuality: FilterQuality.medium),
        ),
      ),
    );
  }
}
