"""Read reports, facets and detail records from the same published lead mart."""
from dataclasses import replace
from types import SimpleNamespace

from .clickhouse import COLUMNS, TABLE_NAME
from .crm_marts import MartUnavailable, SnapshotChanged
from .dashboard_query import GROUP_EXPRESSIONS, LeadDashboardQuery, UNTRACKED_DEPARTMENT_NAME


class PublishedLeadQuery(LeadDashboardQuery):
    def __init__(self, client=None):
        super().__init__(client)
        self.snapshot = self.version()

    def version(self):
        rows = self.client.execute(
            "SELECT toString(uuid) FROM system.tables WHERE database = 'default' AND name = 'bitrix_lead_analytics'"
        )
        if not rows:
            raise MartUnavailable("Lead mart is not published")
        return rows[0][0]

    def check(self):
        if self.version() != self.snapshot:
            raise SnapshotChanged("Lead publication changed during the request")

    def detail_where(self, filters, options):
        where, args = self._where(filters)
        kind = options.get("segment_type")
        keys = options.get("segment_keys") or ([options["segment_key"]] if options.get("segment_key") else [])
        if kind in self.DIMENSIONS and keys:
            where += f" AND ({self.DIMENSIONS[kind][0]}) IN %(segments)s"
            args["segments"] = tuple(keys)
        if kind == "low_quality_status":
            where += " AND is_low_quality = 1 AND is_apm = 0"
        if options.get("period"):
            where += f" AND {GROUP_EXPRESSIONS[filters.group_by]} = %(period)s"
            args["period"] = options["period"]
        return where, args

    def detail_summary(self, filters, options):
        where, args = self.detail_where(filters, options)
        return self._dict_rows(f"""SELECT count() AS total,
            countIf(is_return_customer = 1) AS return_customers,
            sumOrNull(opportunity) AS opportunity,
            avgOrNull(processing_duration_days) AS processing_duration_days
            FROM {TABLE_NAME} WHERE {where}""", args)[0]

    def detail_rows(self, filters, options, *, limit=1000, offset=0):
        where, args = self.detail_where(filters, options)
        field = options.get("sort_by", "source_created_at")
        if field not in COLUMNS:
            raise ValueError("Unknown lead sort field")
        direction = "DESC" if options.get("sort_direction", "desc") == "desc" else "ASC"
        # Match PostgreSQL's existing NULL ordering.
        nulls = "FIRST" if direction == "DESC" else "LAST"
        args.update(limit=limit, offset=offset)
        rows = self._dict_rows(f"""SELECT {', '.join(COLUMNS)} FROM {TABLE_NAME}
            WHERE {where} ORDER BY {field} {direction} NULLS {nulls}, lead_id ASC
            LIMIT %(limit)s OFFSET %(offset)s""", args)
        for row in rows:
            for key in ("is_return_customer", "is_apm", "is_low_quality", "is_unmapped", "is_processed", "is_final"):
                row[key] = None if row[key] is None else bool(row[key])
        return rows

    def export_rows(self, filters, options, *, batch_size=1000):
        offset = 0
        while True:
            rows = self.detail_rows(filters, options, limit=batch_size, offset=offset)
            self.check()
            yield from (SimpleNamespace(**row) for row in rows)
            if len(rows) < batch_size:
                break
            offset += batch_size

    def options(self, filters=None, personal_ids=None):
        def facet(field, columns, *, extra="1", counted=False, order=None):
            if filters is None:
                where, args = "1", {}
            else:
                changes = {field: ()}
                if field == "department_names":
                    changes["exclude_untracked_department"] = False
                elif personal_ids is not None:
                    changes.update(manager_ids=tuple(personal_ids) or (-1,), exclude_untracked_department=False)
                where, args = self._where(replace(filters, **changes))
            expression = columns
            if field == "department_names" and filters and filters.tracked_manager_ids is not None:
                expression = "if(manager_id IN %(facet_tracked)s, department_name, %(facet_untracked)s) AS effective_department"
                args.update(facet_tracked=filters.tracked_manager_ids or (-1,), facet_untracked=UNTRACKED_DEPARTMENT_NAME)
                columns = "effective_department"
                extra = "effective_department != ''"
            suffix = f", count() AS lead_count" if counted else ""
            return self._dict_rows(f"SELECT {expression}{suffix} FROM {TABLE_NAME} WHERE {where} AND ({extra}) GROUP BY {columns} ORDER BY {order or columns}", args)

        departments = facet("department_names", "department_name", extra="department_name != ''")
        return {
            "departments": [{"department_name": row.get("effective_department", row.get("department_name"))} for row in departments],
            "managers": facet("manager_ids", "manager_id, manager_name", extra="manager_id IS NOT NULL", order="manager_name, manager_id"),
            "projects": facet("project_ids", "project_id, project_name", counted=True, order="lead_count DESC, project_name, project_id"),
            "sources": facet("source_ids", "source_id, source_name", counted=True, order="lead_count DESC, source_name, source_id"),
            "semantic_statuses": facet("semantic_status_ids", "status_semantic_id", extra="status_semantic_id != ''", counted=True, order="lead_count DESC, status_semantic_id"),
            "statuses": facet("status_ids", "status_id, status_name, dashboard_status, is_apm", counted=True, order="lead_count DESC, status_name, status_id"),
        }
