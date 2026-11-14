// Small badges for exercise intensity and equipment status. Colours come from the shared Badge.
import { Badge, type BadgeVariant } from '../../../shared/components/Badge';
import type { EquipmentStatus, Intensity } from '../types.log';

const INTENSITY: Record<Intensity, { variant: BadgeVariant; label: string }> = {
  light: { variant: 'good', label: 'Light' },
  moderate: { variant: 'info', label: 'Moderate' },
  hard: { variant: 'review', label: 'Hard' },
};

const EQUIPMENT: Record<string, { variant: BadgeVariant; label: string }> = {
  available: { variant: 'good', label: 'Available' },
  low: { variant: 'low', label: 'Low stock' },
  out_of_stock: { variant: 'stale', label: 'Out of stock' },
  expired: { variant: 'stale', label: 'Expired' },
  unknown: { variant: 'missing', label: 'Unknown' },
};

export function IntensityBadge({ intensity }: { intensity: Intensity }) {
  const { variant, label } = INTENSITY[intensity];
  return <Badge variant={variant}>{label}</Badge>;
}

export function EquipmentStatusBadge({ status }: { status: EquipmentStatus }) {
  const { variant, label } = EQUIPMENT[status] ?? { variant: 'neutral' as BadgeVariant, label: status };
  return <Badge variant={variant}>{label}</Badge>;
}
