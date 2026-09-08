# Загрузка сделок Bitrix24

Сделки загружаются в PostgreSQL вместе с `refresh_bitrix24`:

- `bitrix24_deal` — сделки всех доступных воронок, связи с лидом,
  компанией и контактами, сумма, валюта, ответственный, даты и исходный ответ API.
- `bitrix24_deal_category` — воронки.
- `bitrix24_crm_dictionary` — стадии: `DEAL_STAGE` и `DEAL_STAGE_<id>`.
- `bitrix24_crm_field` — описание полей сделок, `entity_type_id=2`.
- `bitrix24_stage_history` и `bitrix24_stage_interval` — история и интервалы
  стадий сделок, `entity_type_id=2`. Лиды остаются с типом `1`.

Как и у лидов, фиксированной начальной даты нет: первый запуск получает всю
доступную API историю. Затем сделки выбираются по `updatedTime`, история —
по `CREATED_TIME`, с перекрытием 10 минут. Отдельные курсоры не пересекаются
с курсорами лидов. Неуспешный проход не продвигает курсор; сохранённые страницы
при повторе обновляются по уникальным ключам без дублей.

`close_date` — поле `closedate` из Bitrix, оно может содержать плановую дату.
Для анализа фактического завершения следует использовать историю стадий.
Наличие связи `lead_id` не обязательно: сделка может быть создана без лида.

## Первое развёртывание

После переноса кода применить миграции:

```bash
docker exec analytics-django python manage.py migrate
```

Первую загрузку рекомендуется выполнить вручную в устойчивой терминальной
сессии (например, tmux), когда плановое обновление CRM не выполняется:

```bash
docker exec analytics-django python manage.py refresh_bitrix24
```

У существующей задачи Airflow лимит 3 часа; длительность первичной загрузки
всей истории зависит от объёма и ограничений API. Расписание DAG не изменено.
Следующие плановые обновления автоматически включают сделки. При ошибках
работают существующие `fail_sync` и уведомления `send_bitrix_message`.
Table health проверяет также состояния загрузки сделок, воронок, полей и истории.

Отдельные команды для диагностики/повторного запуска:

```bash
docker exec analytics-django python manage.py sync_bitrix24 deal_categories --mode full
docker exec analytics-django python manage.py sync_bitrix24 deal_stages --mode full
docker exec analytics-django python manage.py sync_bitrix24 deal_fields --mode full
docker exec analytics-django python manage.py sync_bitrix24 deals
docker exec analytics-django python manage.py sync_bitrix24 deal_stage_history
docker exec analytics-django python manage.py refresh_bitrix24 --skip-bitrix
```

Эти команды выполнять последовательно, без параллельной загрузки CRM.
Режим `deals --mode full` перечитывает сделки и помечает отсутствующие в полном
ответе как удалённые; инкрементальное обновление не обнаруживает удаления.
Учётная запись API должна иметь доступ ко всем нужным сделкам и воронкам.
Данные за пределами её прав не попадут в выгрузку.

Фронт и витрины ClickHouse для сделок не добавлялись. Формула общей скорости
сделки пока не определяется; сохранены исходные переходы и длительности стадий.

API: [сделки](https://apidocs.bitrix24.com/api-reference/crm/deals/),
[история стадий](https://apidocs.bitrix24.com/api-reference/crm/crm-stage-history-list.html).
