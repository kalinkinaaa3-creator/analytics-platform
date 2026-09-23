import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';

const labels = {
  queued: 'В очереди', dispatching: 'Запускается', running: 'Выполняется',
  waiting_session: 'Ожидается Windows-исполнитель', success: 'Обход завершён',
  failed: 'Ошибка', cancelled: 'Отменён',
};
const active = new Set(['queued', 'dispatching', 'running', 'waiting_session']);
const base = '/v1/datasets/parsers/tara';

export function TaraWorkerPanel({ canEdit }) {
  const [run, setRun] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async (signal) => {
    try {
      const response = await api.get(`${base}/status/`, { signal });
      setRun(response.data.run);
      setError('');
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
  async function cancel() {
    if (!window.confirm('Отменить загрузку Тары? Уже полученные данные сохранятся.')) return;
    setBusy(true); setError('');
    try {
      await api.post(`${base}/${run.id}/cancel/`);
      await load();
    } catch (e) { setError(e.response?.data?.message || 'Не удалось отменить запуск'); }
    finally { setBusy(false); }
  }
  const counts = run?.counts || {};
  return <section className="iprice-parser-status tara-worker-panel" aria-live="polite">
    <h3>Парсер Тары</h3>
    {run ? <>
      <p><b>{labels[run.status] || run.status}</b> · Запуск #{run.id} · {run.origin === 'master' ? 'Мастер: категоризированные товары' : run.origin === 'dag' ? 'Airflow: все категории' : 'Команда'}</p>
      <p>Успешно: {counts.success || 0} из {run.total}. Страница не найдена: {counts.not_found || 0}. Ошибки: {counts.error || 0}.</p>
      <p>Windows-исполнитель: {run.worker_ready ? 'подключён' : 'не подключён'}.</p>
      {run.wait_until && run.status === 'waiting_session' && <p>Ожидание до {new Date(run.wait_until).toLocaleString('ru-RU')}. Откройте служебную вкладку Chromium и запустите Windows-исполнитель. Прогресс сохранён.</p>}
      {run.error && <p>{run.error}</p>}
      {canEdit && active.has(run.status) && <button type="button" disabled={busy} onClick={cancel}>Отменить запуск Тары</button>}
    </> : <p>Здесь появится состояние запуска Тары и подключения Windows-исполнителя.</p>}
    {error && <p className="iprice-data-operation-error">{error}</p>}
  </section>;
}
