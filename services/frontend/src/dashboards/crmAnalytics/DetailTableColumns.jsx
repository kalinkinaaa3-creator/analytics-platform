export function DetailTableColumns({ columns }) {
  return <colgroup>{columns.map(([key]) => <col key={key} className={key === "title" ? "crm-detail-col--title" : key === "processing_duration_days" ? "crm-detail-col--duration" : "crm-detail-col"} />)}</colgroup>;
}
