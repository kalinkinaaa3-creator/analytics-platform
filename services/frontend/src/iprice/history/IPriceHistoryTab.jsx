import {
  IPriceSnapshotCompare,
} from "./IPriceSnapshotCompare";


export function IPriceHistoryTab({
  snapshots,
  selectedSnapshotId,
  loading = false,
  realtimeEvent,
  onOpenProduct,
}) {
  return (
    <IPriceSnapshotCompare
      snapshots={snapshots}
      selectedSnapshotId={selectedSnapshotId}
      loading={loading}
      realtimeEvent={realtimeEvent}
      onOpenProduct={onOpenProduct}
    />
  );
}
