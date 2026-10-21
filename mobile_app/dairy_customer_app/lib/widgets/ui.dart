import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// White rounded tile with an outlined icon above a label (3 per row on Home and Menu).
class ActionTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? iconColor;
  final String? badge;

  const ActionTile({super.key, required this.icon, required this.label, required this.onTap, this.iconColor, this.badge});

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppTheme.border),
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Badge(
                isLabelVisible: badge != null,
                label: Text(badge ?? ''),
                child: Icon(icon, size: 26, color: iconColor ?? AppTheme.navy),
              ),
              const SizedBox(height: 8),
              Text(label,
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 12.5, height: 1.2, fontWeight: FontWeight.w500, color: AppTheme.textMain)),
            ],
          ),
        ),
      ),
    );
  }
}

/// Grid of [ActionTile]s, three per row.
class TileGrid extends StatelessWidget {
  final List<Widget> children;

  const TileGrid({super.key, required this.children});

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 3,
      shrinkWrap: true,
      // No automatic padding: the floating bottom bar would otherwise add empty space below the grid
      padding: EdgeInsets.zero,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: 0.95,
      children: children,
    );
  }
}

/// Section heading with an optional "View All" link.
class SectionHeader extends StatelessWidget {
  final String title;
  final VoidCallback? onViewAll;

  const SectionHeader(this.title, {super.key, this.onViewAll});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 22, bottom: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(title, style: AppTheme.sectionTitle),
          if (onViewAll != null)
            InkWell(
              onTap: onViewAll,
              child: Container(
                padding: const EdgeInsets.only(bottom: 2),
                decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: AppTheme.textMuted))),
                child: const Text('View All', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w500)),
              ),
            ),
        ],
      ),
    );
  }
}

/// Light cyan notice with a bell, e.g. the order cut-off reminder.
class InfoBanner extends StatelessWidget {
  final String text;
  final IconData icon;

  const InfoBanner(this.text, {super.key, this.icon = Icons.notifications_active});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      decoration: BoxDecoration(color: AppTheme.infoBanner, borderRadius: BorderRadius.circular(14)),
      child: Row(
        children: [
          Icon(icon, color: AppTheme.warmAmber, size: 26),
          const SizedBox(width: 12),
          Expanded(child: Text(text, style: const TextStyle(fontSize: 14, height: 1.35, color: AppTheme.textMain))),
        ],
      ),
    );
  }
}

/// Small coloured status label.
class StatusChip extends StatelessWidget {
  final String text;
  final Color color;

  const StatusChip(this.text, {super.key, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
      child: Text(text, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
    );
  }
}
