import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Space a tab's scrolling list needs at the bottom so its last item is not hidden
/// behind the floating bar (the shell's `extendBody` puts the bar height into the
/// bottom padding).
double navBarListPadding(BuildContext context) => MediaQuery.paddingOf(context).bottom + 24;

/// Lifts a tab's floating action button above the floating bar. Scaffold already keeps
/// the button clear of the phone's own system bar, so only the extra part is added.
Widget aboveNavBar(BuildContext context, Widget fab) {
  final lift = MediaQuery.paddingOf(context).bottom - MediaQuery.viewPaddingOf(context).bottom;
  return Padding(padding: EdgeInsets.only(bottom: lift > 0 ? lift : 0), child: fab);
}

/// Dark navy floating bottom bar with outlined icons.
class FloatingNavBar extends StatelessWidget {
  /// (icon, selected icon, label) for each tab
  final List<(IconData, IconData, String)> items;
  final int currentIndex;
  final ValueChanged<int> onTap;

  const FloatingNavBar({super.key, required this.items, required this.currentIndex, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      minimum: const EdgeInsets.fromLTRB(12, 0, 12, 10),
      child: Container(
        height: 68,
        decoration: BoxDecoration(
          color: AppTheme.navy,
          borderRadius: BorderRadius.circular(22),
          boxShadow: [BoxShadow(color: AppTheme.navy.withValues(alpha: 0.25), blurRadius: 16, offset: const Offset(0, 6))],
        ),
        child: Row(
          children: List.generate(items.length, (i) {
            final (icon, activeIcon, label) = items[i];
            final selected = i == currentIndex;
            return Expanded(
              child: InkWell(
                borderRadius: BorderRadius.circular(22),
                onTap: () => onTap(i),
                child: Semantics(
                  selected: selected,
                  button: true,
                  label: label,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        width: selected ? 26 : 0,
                        height: 3,
                        margin: const EdgeInsets.only(bottom: 6),
                        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(2)),
                      ),
                      Icon(selected ? activeIcon : icon, color: selected ? Colors.white : Colors.white70, size: 24),
                      const SizedBox(height: 3),
                      Text(label,
                          style: TextStyle(
                              color: selected ? Colors.white : Colors.white70,
                              fontSize: 12,
                              fontWeight: selected ? FontWeight.w700 : FontWeight.w500)),
                    ],
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
