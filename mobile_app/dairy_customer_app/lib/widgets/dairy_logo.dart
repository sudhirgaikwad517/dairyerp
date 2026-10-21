import 'package:flutter/material.dart';

/// Akash Dairy Farm logo: milk bottle with a leaf on a blue rounded square.
/// Same drawing as the web logo (frontend/assets/logo.svg).
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
          borderRadius: BorderRadius.circular(size * 0.25),
          boxShadow: [
            BoxShadow(color: const Color(0xFF0B2545).withValues(alpha: 0.3), blurRadius: size * 0.25, offset: Offset(0, size * 0.08)),
          ],
        ),
        child: CustomPaint(size: Size.square(size), painter: _LogoPainter()),
      ),
    );
  }
}

class _LogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    // Drawn on a 64 x 64 grid, then scaled
    canvas.scale(size.width / 64, size.height / 64);
    const white = Colors.white;

    final bg = RRect.fromRectAndRadius(const Rect.fromLTWH(0, 0, 64, 64), const Radius.circular(16));
    canvas.drawRRect(
      bg,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0EA5E9), Color(0xFF0B2545)],
        ).createShader(const Rect.fromLTWH(0, 0, 64, 64)),
    );

    // Cap
    canvas.drawRRect(RRect.fromRectAndRadius(const Rect.fromLTWH(25, 9, 14, 5), const Radius.circular(1.6)), Paint()..color = white);

    // Bottle glass
    final bottle = Path()
      ..moveTo(26.5, 15.5)
      ..lineTo(37.5, 15.5)
      ..lineTo(37.5, 20.5)
      ..lineTo(43.5, 27.5)
      ..lineTo(43.5, 48.5)
      ..quadraticBezierTo(43.5, 54.5, 37.5, 54.5)
      ..lineTo(26.5, 54.5)
      ..quadraticBezierTo(20.5, 54.5, 20.5, 48.5)
      ..lineTo(20.5, 27.5)
      ..close();
    canvas.drawPath(bottle, Paint()..color = white.withValues(alpha: 0.18));
    canvas.drawPath(
      bottle,
      Paint()
        ..color = white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.4
        ..strokeJoin = StrokeJoin.round,
    );

    // Milk inside, with a wave on top
    final milk = Path()
      ..moveTo(20.5, 34)
      ..quadraticBezierTo(26.5, 30.5, 32, 34)
      ..quadraticBezierTo(37.5, 37.5, 43.5, 34)
      ..lineTo(43.5, 48.5)
      ..quadraticBezierTo(43.5, 54.5, 37.5, 54.5)
      ..lineTo(26.5, 54.5)
      ..quadraticBezierTo(20.5, 54.5, 20.5, 48.5)
      ..close();
    canvas.drawPath(milk, Paint()..color = white);

    // Leaf: "farm fresh"
    final leaf = Path()
      ..moveTo(32, 47.5)
      ..cubicTo(28.5, 46, 28, 42, 32, 39.5)
      ..cubicTo(36, 42, 35.5, 46, 32, 47.5)
      ..close();
    canvas.drawPath(leaf, Paint()..color = const Color(0xFF12A15B));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
