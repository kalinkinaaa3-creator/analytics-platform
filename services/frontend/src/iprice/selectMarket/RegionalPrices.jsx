import { fmtMoney } from "./archiveFormat";
import Icon from "./ui/Icon";

export function RegionalPrices({ entries = [], own = false }) {
  if (!entries.length) return <div />;
  return <details className="sm-regional-prices"><summary>Цены по регионам · {entries.length}</summary>
    <table className="ip-table"><thead><tr><th>Регион</th><th className="num">{own ? "Новая цена" : "Цена"}</th><th /></tr></thead>
      <tbody>{entries.map((entry, index) => <tr key={`${entry.region}-${index}`}><td>{entry.region || "—"}</td><td className="num">{fmtMoney(own ? entry.final_price : entry.price)}</td><td>{(entry.urls || [entry.url]).filter(url => /^https?:\/\//i.test(url || "")).map(url => <a key={url} href={url} target="_blank" rel="noopener noreferrer" aria-label={own ? "На нашем сайте" : "На сайте конкурента"} title={own ? "На нашем сайте" : "На сайте конкурента"}><Icon name="ext" /></a>)}</td></tr>)}</tbody>
    </table></details>;
}
