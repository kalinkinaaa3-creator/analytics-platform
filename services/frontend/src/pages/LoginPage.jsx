import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import "../styles/login.css";

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
            <label className="login-organization" htmlFor="login-organization">Организация</label>
            <select id="login-organization" value={organizationId} onChange={event => setOrganizationId(event.target.value)} disabled={busy} autoFocus>
              {pending.organizations.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}
            </select>
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
