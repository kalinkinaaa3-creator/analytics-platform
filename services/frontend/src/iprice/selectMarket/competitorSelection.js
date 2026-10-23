import { api } from "../../api/client";

export function saveCompetitorSelection({ snapshotId, productId, keys, mode, reason, revision }) {
  return api.post(`/v1/select-market/iprice/snapshots/${snapshotId}/products/${productId}/competitors/`, {
    competitor_product_keys: keys, selection_mode: mode, reason, expected_revision: revision,
  });
}
