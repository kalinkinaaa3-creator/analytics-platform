import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';

const labels = {
  queued: 'В очереди', dispatching: 'Запускается', running: 'Выполняется',
  waiting_session: 'Ожидается сессия Chromium', success: 'Обход завершён',
  failed: 'Ошибка', cancelled: 'Отменён',
};
const active = new Set(['queued', 'dispatching', 'running', 'waiting_session']);
const base = '/v1/datasets/parsers/tara';

export function TaraSessionPanel({ canEdit }) {
  const [run, setRun] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState(null);
  const input = useRef(null);
  const load = useCallback(async (signal) => {
    try {
      const response = await api.get(`${base}/status/`, { signal });
      setRun(response.data.run);
    } catch (e) {
      if (e.code !== 'ERR_CANCELED') setError('Не удалось получить состояние Тары');
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      await load(controller.signal);
      if (!controller.signal.aborted) timer = setTimeout(poll, 10000);
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [load]);

  async function upload(event) {
    event.preventDefault();
    if (!file || !run) return;
    if (file.size > 1024 * 1024) { setError('Выберите JSON размером до 1 МБ'); return; }
    setBusy(true); setError(''); setMessage('');
    try {
      const body = new FormData(); body.append('file', file);
      const response = await api.post(`${base}/${run.id}/session/`, body);
      setMessage(response.data.message);
      setFile(null);
      if (input.current) input.current.value = '';
      await load();
    } catch (e) {
      setError(e.response?.data?.message || 'Не удалось загрузить сессию');
    } finally { setBusy(false); }
  }

  async function cancel() {
    if (!window.confirm('Отменить загрузку Тары? Уже полученные данные сохранятся.')) return;
    setBusy(true); setError('');
    try {
      await api.post(`${base}/${run.id}/cancel/`);
      setMessage('Запуск отменён'); await load();
    } catch (e) { setError(e.response?.data?.message || 'Не удалось отменить запуск'); }
    finally { setBusy(false); }
  }

  const checking = ['pending', 'checking'].includes(run?.upload?.status);
  const counts = run?.counts || {};
  return <section className="iprice-parser-status tara-session-panel" aria-live="polite">
    <h3>Сессия Тары</h3>
    {run ? <>
      <p><b>{labels[run.status] || run.status}</b> · Запуск #{run.id} · {run.origin === 'master' ? 'Мастер: категоризированные товары' : run.origin === 'dag' ? 'Airflow: все категории' : 'Команда'}</p>
      <p>Успешно: {counts.success || 0} из {run.total}. Страницы не найдены: {counts.not_found || 0}. Ошибки: {counts.error || 0}.</p>
      {run.wait_until && run.status === 'waiting_session' && <p>Загрузите рабочую сессию до {new Date(run.wait_until).toLocaleString('ru-RU')}. После проверки обработка продолжится автоматически.</p>}
      {run.error && <p>{run.error}</p>}
      {checking && run.status === 'waiting_session' && <p role="status">Проверяем сессию…</p>}
      {run.upload?.status === 'rejected' && run.status === 'waiting_session' && <p className="iprice-data-operation-error">{run.upload.error}</p>}
      {canEdit && run.status === 'waiting_session' && <form onSubmit={upload}>
        <label>Файл сессии Chromium (JSON, до 1 МБ)<input ref={input} type="file" accept=".json,application/json" disabled={busy || checking} onChange={e => setFile(e.target.files?.[0] || null)} /></label>
        <button type="submit" className="iprice-parser-run-button" disabled={!file || busy || checking}>{busy ? 'Загружаем…' : 'Загрузить сессию'}</button>
      </form>}
      {canEdit && active.has(run.status) && <button type="button" disabled={busy} onClick={cancel}>Отменить запуск Тары</button>}
    </> : <p>Когда для загрузки потребуется новая сессия, здесь появится форма загрузки.</p>}
    {error && <p className="iprice-data-operation-error">{error}</p>}
    {message && <p>{message}</p>}
    {canEdit && <details><summary>Как выгрузить сессию из Chromium</summary>
      <ol>
        <li>Установите Node.js 22 или новее. Скачайте <a href="/tara/export-session.mjs" download>инструмент экспорта</a> и <a href="/tara/chromium-session.md" download>подробную инструкцию</a>.</li>
        <li>В Chromium откройте chrome://version и запишите путь к программе и профилю. Закройте все окна Chromium, сохранив незавершённую работу.</li>
        <li>Запустите Chromium с вашим профилем и локальным портом отладки по инструкции.</li>
        <li>Откройте карточку на spb.tara.ru, обновите страницу и убедитесь, что цена видна. Оставьте одну вкладку этого сайта.</li>
        <li>Запустите инструмент экспорта и сразу загрузите созданный JSON в эту форму.</li>
        <li>Закройте Chromium с отладкой и откройте обычным ярлыком. Дождитесь сообщения о продолжении загрузки.</li>
      </ol>
    </details>}
  </section>;
}
