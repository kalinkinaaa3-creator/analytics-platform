import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import "../styles/login.css";

function OrganizationPicker({ organizations, value, onChange, disabled }) {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  const trigger = useRef(null);
  const options = useRef([]);
  const selected = organizations.findIndex(org => String(org.id) === value);

  useEffect(() => {
    function closeOutside(event) {
      if (!root.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);

  useEffect(() => {
    if (open) options.current[Math.max(selected, 0)]?.focus();
  }, [open, selected]);

  return <div className="login-org-picker" ref={root}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}
    onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
    }}>
    <button id="login-organization" className="login-org-trigger" type="button" ref={trigger}
      disabled={disabled} autoFocus aria-expanded={open} aria-controls="login-org-options"
      aria-labelledby="login-org-label login-org-value"
      onClick={() => setOpen(!open)}
      onKeyDown={event => { if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); setOpen(true); } }}>
      <span id="login-org-value">{organizations[selected]?.name}</span>
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
    </button>
    {open && <div id="login-org-options" className="login-org-options" role="group" aria-labelledby="login-org-label">
      {organizations.map((org, index) => <button type="button" key={org.id}
        ref={element => { options.current[index] = element; }} disabled={disabled}
        aria-pressed={index === selected}
        onKeyDown={event => {
          let next;
          if (event.key === "ArrowDown") next = (index + 1) % organizations.length;
          if (event.key === "ArrowUp") next = (index - 1 + organizations.length) % organizations.length;
          if (event.key === "Home") next = 0;
          if (event.key === "End") next = organizations.length - 1;
          if (next !== undefined) { event.preventDefault(); options.current[next]?.focus(); }
        }}
        onClick={() => { onChange(String(org.id)); setOpen(false); trigger.current?.focus(); }}>
        <span>{org.name}</span>
        {index === selected && <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3 8 3 3 7-7" /></svg>}
      </button>)}
    </div>}
  </div>;
}

export function LoginPage() {
  const navigate = useNavigate();
  const { login, completeLogin } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(null);
  const [organizationId, setOrganizationId] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (busy) return;
    setError("");
    setBusy(true);
    try {
      if (pending) {
        await completeLogin(pending, organizationId);
      } else {
        const session = await login(username, password);
        setPassword("");
        if (session.organizations.length > 1) {
          setOrganizationId(String(session.organization.id));
          setPending(session);
          return;
        }
        await completeLogin(session, session.organization.id);
      }
      navigate("/", { replace: true });
    } catch (err) {
      if (pending && err.response?.status === 401) {
        setPending(null);
        setError("Время выбора истекло. Введите пароль повторно.");
      } else {
        setError(err.response?.data?.detail || (pending
          ? "Не удалось открыть организацию. Повторите попытку."
          : "Не удалось войти. Проверьте логин и пароль."));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-container">
        <h2>Вход в систему</h2>
        {error && <div className="error" role="alert">{error}</div>}
        <form onSubmit={handleSubmit} aria-busy={busy}>
          {pending ? <>
            <label id="login-org-label" className="login-organization" htmlFor="login-organization">Организация</label>
            <OrganizationPicker organizations={pending.organizations} value={organizationId} onChange={setOrganizationId} disabled={busy} />
            <p className="login-account">{username}</p>
          </> : <>
            <input type="text" placeholder="Имя пользователя" aria-label="Имя пользователя" autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} disabled={busy} required />
            <input type="password" placeholder="Пароль" aria-label="Пароль" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} disabled={busy} required />
          </>}
          <button type="submit" disabled={busy}>{busy ? "Вход…" : "Войти"}</button>
          {pending && <button className="login-back" type="button" disabled={busy} onClick={() => { setPending(null); setError(""); }}>Другая учётная запись</button>}
        </form>
      </div>
    </div>
  );
}
