from collections import Counter, defaultdict


def flatten_regions_tree(data):
    """Flatten a v2 tree while preserving paths and reporting malformed nodes."""
    rows = []
    malformed = []

    def visit(nodes, path=(), parent_id=None, ancestor_ids=(), depth=1):
        if not isinstance(nodes, list):
            malformed.append({"path": list(path), "reason": "children_not_list"})
            return
        for position, node in enumerate(nodes):
            if not isinstance(node, dict):
                malformed.append({"path": list(path), "position": position, "reason": "node_not_object"})
                continue
            raw_id = node.get("id")
            label = node.get("label") or node.get("name")
            region_id = str(raw_id).strip() if raw_id is not None else ""
            label = str(label).strip() if label is not None else ""
            node_path = (*path, label or f"#{region_id or position}")
            if not region_id or not label:
                malformed.append({"path": list(node_path), "reason": "missing_id_or_label"})
            else:
                rows.append({
                    "id": region_id,
                    "label": label,
                    "parent_id": parent_id,
                    "ancestor_ids": list(ancestor_ids),
                    "depth": depth,
                    "path": list(node_path),
                })
            children = node.get("children", [])
            if children is None:
                children = []
            next_ancestors = (*ancestor_ids, region_id) if region_id else ancestor_ids
            visit(
                children,
                node_path,
                region_id or parent_id,
                next_ancestors,
                depth + 1,
            )

    visit(data.get("regions", []))
    return rows, malformed


def build_regions_v2_diagnostic(data):
    from datasets.models import YdWordstatIplastRegionRef, YdWordstatRegionRef

    rows, malformed = flatten_regions_tree(data)
    id_counts = Counter(row["id"] for row in rows)
    duplicate_ids = sorted(region_id for region_id, count in id_counts.items() if count > 1)
    numeric_ids = {int(region_id) for region_id in id_counts if region_id.isdigit()}
    non_numeric_ids = sorted(region_id for region_id in id_counts if not region_id.isdigit())

    current_regions = set(YdWordstatRegionRef.objects.values_list("region_value", flat=True))
    mappings = list(
        YdWordstatIplastRegionRef.objects.order_by("macroregion_label", "region_value")
        .values("region_value", "macroregion_label")
    )
    mapped_ids = {item["region_value"] for item in mappings}
    mapped_groups = {
        item["region_value"]: item["macroregion_label"] or "<NULL>"
        for item in mappings
    }
    tree_by_id = {row["id"]: row for row in rows}
    pools = defaultdict(list)
    for item in mappings:
        pools[item["macroregion_label"] or "<NULL>"].append(item["region_value"])

    pool_rows = []
    for name, region_ids in sorted(pools.items()):
        present = sorted(set(region_ids) & numeric_ids)
        missing = sorted(set(region_ids) - numeric_ids)
        pool_rows.append({
            "name": name,
            "configured": len(set(region_ids)),
            "present": len(present),
            "missing_ids": missing,
            "fits_api_limit": len(present) <= 100,
        })

    hierarchy_overlaps = []
    for descendant_id in sorted(mapped_ids & numeric_ids):
        descendant = tree_by_id[str(descendant_id)]
        for raw_ancestor_id in descendant["ancestor_ids"]:
            if not raw_ancestor_id.isdigit():
                continue
            ancestor_id = int(raw_ancestor_id)
            if ancestor_id not in mapped_ids:
                continue
            ancestor = tree_by_id[raw_ancestor_id]
            ancestor_group = mapped_groups[ancestor_id]
            descendant_group = mapped_groups[descendant_id]
            hierarchy_overlaps.append({
                "ancestor_id": ancestor_id,
                "ancestor_label": ancestor["label"],
                "ancestor_group": ancestor_group,
                "descendant_id": descendant_id,
                "descendant_label": descendant["label"],
                "descendant_group": descendant_group,
                "same_pool": ancestor_group == descendant_group,
            })

    return {
        "tree": {
            "nodes": len(rows),
            "unique_ids": len(id_counts),
            "max_depth": max((row["depth"] for row in rows), default=0),
            "malformed_nodes": len(malformed),
            "duplicate_ids": duplicate_ids,
            "non_numeric_ids": non_numeric_ids,
        },
        "current_region_reference": {
            "configured": len(current_regions),
            "present_in_v2": len(current_regions & numeric_ids),
            "missing_ids": sorted(current_regions - numeric_ids),
        },
        "iplast_mapping": {
            "configured": len(mapped_ids),
            "present_in_v2": len(mapped_ids & numeric_ids),
            "missing_ids": sorted(mapped_ids - numeric_ids),
            "new_tree_ids_outside_current_mapping": len(numeric_ids - mapped_ids),
            "pools": pool_rows,
        },
        "hierarchy_overlap_check": {
            "ok": not hierarchy_overlaps,
            "overlap_pairs": len(hierarchy_overlaps),
            "same_pool_pairs": sum(item["same_pool"] for item in hierarchy_overlaps),
            "cross_pool_pairs": sum(not item["same_pool"] for item in hierarchy_overlaps),
            "details": hierarchy_overlaps,
        },
        "malformed_examples": malformed[:20],
    }
