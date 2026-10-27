import { useState } from "react";
import { Button } from "./ui/primitives";

export function Notice({ children, error = false, onClose }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return <div className={`ip-alert ${error ? "error" : "info"}`} role={error ? "alert" : "status"}><div className="body">{children}</div><Button size="s" variant="ghost" icon="x" aria-label="Закрыть сообщение" onClick={() => { setDismissed(true); onClose?.(); }} /></div>;
}
