(() => {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    const dashboard = document.getElementById("id_dashboard");
    const departments = document.getElementById("id_departments");
    const panel = document.getElementById("department-recipients");
    if (!dashboard || !departments || !panel) return;
    let controller;
    let loading = false;
    departments.form?.addEventListener("submit", event => {
      if (loading) event.preventDefault();
    });
    const element = (tag, text) => { const node = document.createElement(tag); node.textContent = text; return node; };
    async function refresh(clearSelection = false) {
      controller?.abort();
      controller = new AbortController();
      const signal = controller.signal;
      const selected = clearSelection ? [] : [...departments.selectedOptions].map(option => option.value);
      const params = new URLSearchParams({ dashboard: dashboard.value });
      selected.forEach(value => params.append("departments", value));
      panel.replaceChildren(element("p", "Загружаем пользователей…"));
      departments.disabled = true;
      loading = true;
      try {
        const response = await fetch(`${panel.dataset.previewUrl}?${params}`, { signal, credentials: "same-origin" });
        if (!response.ok) throw new Error("preview failed");
        const data = await response.json();
        if (signal.aborted) return;
        departments.replaceChildren();
        [...new Set([...data.departments, ...selected])].sort((a, b) => a.localeCompare(b, "ru")).forEach(value => {
          const option = new Option(value, value, false, selected.includes(value));
          departments.append(option);
        });
        panel.replaceChildren();
        if (!dashboard.value) { panel.append(element("p", "Выберите дашборд.")); return; }
        panel.append(element("strong", `Организация: ${data.organization}`));
        const active = document.getElementById("id_is_active")?.checked &&
          (document.getElementById("id_can_view")?.checked || document.getElementById("id_can_edit")?.checked);
        panel.append(element("p", !active ? "Группа выключена: групповые права не выдаются." : `Получателей: ${data.users.filter(user => !user.excluded).length}. Исключений: ${data.users.filter(user => user.excluded).length}.`));
        if (!data.users.length) { panel.append(element("p", "В выбранных подразделениях нет активных пользователей с доступом к этой организации.")); return; }
        const table = document.createElement("table");
        const head = table.createTHead().insertRow();
        ["Пользователь", "ФИО", "Department name", "Доступ группы"].forEach(label => head.append(element("th", label)));
        const body = table.createTBody();
        data.users.forEach(user => {
          const row = body.insertRow();
          row.className = user.excluded ? "department-excluded" : "";
          [user.username, user.full_name, user.department, user.excluded ? "Исключение — не будет выдан" : active ? "Будет выдан при сохранении" : "Группа выключена"].forEach(value => row.append(element("td", value)));
        });
        panel.append(table);
      } catch (error) {
        if (!signal.aborted) panel.replaceChildren(element("p", "Не удалось загрузить список пользователей. Повторите выбор подразделения."));
      } finally {
        if (!signal.aborted) { departments.disabled = false; loading = false; }
      }
    }
    dashboard.addEventListener("change", () => refresh(true));
    departments.addEventListener("change", () => refresh());
    document.getElementById("id_is_active")?.addEventListener("change", () => refresh());
    document.getElementById("id_can_view")?.addEventListener("change", () => refresh());
    document.getElementById("id_can_edit")?.addEventListener("change", () => refresh());
    refresh();
  });
})();
