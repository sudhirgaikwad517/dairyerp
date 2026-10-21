import 'package:flutter/material.dart';

/// Clean navy-on-white look: pale background, white rounded cards, outlined icons.
class AppTheme {
  static const Color navy = Color(0xFF0B2545);
  static const Color primaryBlue = Color(0xFF13406B); // buttons, highlights
  static const Color primaryDark = navy; // dark cards / headers
  static const Color accentCyan = Color(0xFF0E9FB5);
  static const Color infoBanner = Color(0xFFD7F2F7);
  static const Color freshGreen = Color(0xFF12A15B);
  static const Color warmAmber = Color(0xFFE08A0B);
  static const Color alertRose = Color(0xFFE11D48);
  static const Color backgroundLight = Color(0xFFEEF3F2);
  static const Color surfaceCard = Colors.white;
  static const Color textMain = Color(0xFF0F172A);
  static const Color textMuted = Color(0xFF64748B);
  static const Color border = Color(0xFFE2E8F0);

  static ThemeData get lightTheme {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: navy,
        primary: primaryBlue,
        secondary: accentCyan,
        surface: surfaceCard,
        error: alertRose,
      ),
      scaffoldBackgroundColor: backgroundLight,
    );
    return base.copyWith(
      textTheme: base.textTheme.apply(bodyColor: textMain, displayColor: textMain),
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.white,
        foregroundColor: navy,
        surfaceTintColor: Colors.white,
        elevation: 0,
        scrolledUnderElevation: 0.5,
        centerTitle: false,
        titleTextStyle: TextStyle(color: navy, fontSize: 19, fontWeight: FontWeight.w700),
      ),
      cardTheme: CardThemeData(
        color: surfaceCard,
        surfaceTintColor: Colors.white,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: border),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: navy,
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: navy,
          side: const BorderSide(color: navy, width: 1.2),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: border)),
        enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: border)),
        focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: navy, width: 1.5)),
      ),
      chipTheme: base.chipTheme.copyWith(
        selectedColor: navy,
        secondarySelectedColor: navy,
        checkmarkColor: Colors.white,
        side: const BorderSide(color: border),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
      snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(backgroundColor: navy, foregroundColor: Colors.white),
    );
  }

  /// Section heading used on Home and Menu ("Orders", "Billing & Invoices", ...)
  static const TextStyle sectionTitle = TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: textMain);
}
