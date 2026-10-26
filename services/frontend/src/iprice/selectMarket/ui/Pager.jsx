import Icon from "./Icon";
import { fmtNumber } from "../archiveFormat";

export function Pager({ page, totalPages, count, pageSize, onPage, onPageSize, disabled = false }) {
  if (count === 0) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(count, page * pageSize);
  const pages = [];
  const add = (p) => { if (p >= 1 && p <= totalPages && !pages.includes(p)) pages.push(p); };
  add(1); add(page - 1); add(page); add(page + 1); add(totalPages);
  pages.sort((a, b) => a - b);
  return (
    <div className="ip-pager">
      <span>{count == null ? `${page} / ${totalPages}` : <>Показаны {fmtNumber(from)}–{fmtNumber(to)} из {fmtNumber(count)}</>}</span>
      <div className="ip-row">
        {onPageSize ? (
          <label className="ip-row small muted">
            На странице
            <select className="ip-select" style={{ width: 76, height: 28 }} aria-label="Строк на странице" disabled={disabled} value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}>
              {[25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        ) : null}
        <div className="pages">
          <button type="button" aria-label="Назад" disabled={disabled || page <= 1} onClick={() => onPage(page - 1)}><Icon name="chevLeft" size={14} /></button>
          {pages.map((p, i) => (
            <span key={p} style={{ display: "contents" }}>
              {i > 0 && p - pages[i - 1] > 1 ? <span className="quiet">…</span> : null}
              <button type="button" disabled={disabled} aria-current={p === page} onClick={() => onPage(p)}>{p}</button>
            </span>
          ))}
          <button type="button" aria-label="Вперёд" disabled={disabled || page >= totalPages} onClick={() => onPage(page + 1)}><Icon name="chev" size={14} /></button>
        </div>
      </div>
    </div>
  );
}
