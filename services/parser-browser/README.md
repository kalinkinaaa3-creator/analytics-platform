[Windows application and installer](WINDOWS_APP.md)

# Windows-исполнитель Тары: тестовое окружение

Исполнитель забирает до пяти заданий через API и отправляет HTML серверу.
Разбор свойств/цен, 404, сохранение, отбор ссылок мастера/DAG и отчёты остаются
в существующем серверном коде. Sitemap DAG также получает Windows-исполнитель.
Cookies находятся только в памяти исполнителя и профиле Chromium.

## Подготовка тестового сервера

Перенести изменения backend/frontend и миграцию 0067. В `.env` рядом с
`docker-compose.yml` добавить:

```dotenv
TARA_WORKER_KEY=<отдельный случайный секрет минимум 32 байта>
```

Ключ исполнителя не должен совпадать с общим `INTERNAL_API_KEY`.
Сгенерировать локально: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Не добавлять `.env` и ключ в Git, сообщения или инструкции.

При отсутствии активной загрузки Тары:

```bash
cd /opt/analytics-platform
docker compose run --rm --no-deps django python manage.py migrate
docker compose up -d --no-deps --force-recreate django
```

Обновить фронтенд обычным для тестового окружения способом. Панель вместо
загрузки JSON показывает подключение исполнителя и ожидание. Старый режим
загрузки сессии удалён; переключателя обратно нет. Миграция 0067 удаляет
таблицу истории загрузок сессий и связь с ней, не затрагивая цены и задания.
Миграция 0066 остаётся в истории проекта. Не удалять применённые миграции.
Сервис `parser-browser` удалён из Compose; после остановки старых запусков
его старый контейнер можно отдельно остановить и удалить. Эта инструкция
относится только к тестовому серверу; рабочий сервер не обновлять.

## Подготовка Windows

Из каталога `services/parser-browser`:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Отдельный Chromium с отдельным профилем:

```powershell
& "C:\files\userMK\Chromium\bin\chrome.exe" --user-data-dir="$env:TEMP\tara-service-tab-check" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9223 "https://moskva.tara.ru/catalog/nalivnaya_tara/plastikovaya_yemkost_200_litrov/?oid=241441"
```

Оставить одну вкладку Тары с настоящей карточкой. Не публиковать порт 9223.
В PowerShell того же компьютера задать адрес API и тот же отдельный ключ:

```powershell
$env:TARA_WORKER_API = 'http://127.0.0.1:18000/api'
$taraSecret = Read-Host 'Ключ Windows-исполнителя' -AsSecureString
$taraCredential = New-Object System.Management.Automation.PSCredential('worker', $taraSecret)
$env:TARA_WORKER_KEY = $taraCredential.GetNetworkCredential().Password
& .\.venv\Scripts\python.exe .\worker.py
```

API тестового сервера по этому адресу проверен с Windows. Если доступ обеспечен
пробросом портов, сохранять подключение. Для нелокального API требуется HTTPS;
проверка сертификатов включена. Рабочее окружение/VPN этой версией не проверены.

## Первая проверка

Не начинать с полного мастера. На сервере создать ограниченный запуск:

```bash
docker exec analytics-django python manage.py load_tara_products --limit 5 --workers 5 --classified-only
```

Запускать только одну очередь Тары одновременно. Исполнитель не создаёт её сам:
он ждёт задания. Если все классифицированные товары уже загружены сегодня,
очередь может оказаться пустой; не очищать базу для получения пяти заданий.
После подтверждения сохранения пяти карточек проверять мастер и DAG.

## Поведение

- Отказ: текущая группа завершается, вкладка обновляется один раз, cookies
  копируются в отдельные HTTP-клиенты, повторяются только заблокированные URL.
- Повторный отказ: исполнитель останавливается. Открыть карточку вручную,
  проверить доступ и повторно запустить `worker.py`. Сервер сохраняет прогресс
  и ждёт до четырёх часов; ожидание не продлевается каждым эпизодом.
- Потеря API: результаты хранятся в `outbox/`, новые задания не забираются до
  отправки. Просроченные результаты отвергаются сервером, товар обрабатывается
  заново после возобновления. Нельзя переносить outbox между окружениями.
- Отмена запуска: поздние результаты не принимаются. Полученные до отмены
  результаты остаются в базе.
- Ctrl+C останавливает исполнитель, Chromium остаётся открытым.
- Другой экземпляр исполнителя не допускается, пока прежний отправляет
  heartbeat. После остановки может потребоваться до 90 секунд для смены владельца.

Это первая интеграция, массовая загрузка ещё не подтверждена. Нужны проверки
на тестовом PostgreSQL: параллельные транзакции, отключение исполнителя во время
группы, отмена и повторная доставка. Локальные тесты используют SQLite.

## Результаты предварительной проверки

На Windows Chromium 146.0.7680.246 пять прямых HTTP-запросов получили 200
примерно за 2,9 секунды на группу. После естественного истечения cookie:
пять 401, одно обновление служебной вкладки, пять повторов 200 примерно за
2,4 секунды на группу повторов. Это проверка загрузки страниц, не полного
сохранения через новый API. Каталог старой диагностики удалён.




################################################ устаревший запуск
Ниже порядок **для тестового окружения на Windows**. Все команды выполняйте в **PowerShell**, копируя каждый блок отдельно.

**1. Откройте PowerShell и перейдите в папку исполнителя**

```powershell
Set-Location -LiteralPath 'C:\Users\adminMK\Desktop\ВСЁ\! projects django second\django\analytics-platform\services\parser-browser'
```

**2. Только при первой установке — создайте окружение и установите зависимости**

При обычном запуске **пропускайте этот шаг**.

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**3. Запустите отдельный Chromium**

Если Chromium для Тары уже открыт с портом `9223`, второй экземпляр запускать не нужно.

```powershell
& "C:\files\userMK\Chromium\bin\chrome.exe" --user-data-dir="$env:TEMP\tara-service-tab-check" --remote-debugging-address=127.0.0.1 --remote-debugging-port=9223 "https://moskva.tara.ru/catalog/nalivnaya_tara/plastikovaya_yemkost_200_litrov/?oid=241441"
```

В открывшемся окне:

- дождитесь отображения карточки товара;
- оставьте **одну вкладку Тары** с карточкой;
- не закрывайте это окно во время загрузки.

**4. Проверьте подключение к Chromium**

В PowerShell выполните:

```powershell
(Invoke-RestMethod -Uri 'http://127.0.0.1:9223/json/version').Browser
```

Должна появиться версия браузера, например:

```text
Chrome/146.0.7680.246
```

Если команда сообщает об ошибке подключения, к запуску исполнителя пока не переходите.

**5. Укажите адрес API и порт браузера**

В том же окне PowerShell:

```powershell
$env:TARA_WORKER_API = 'http://127.0.0.1:18000/api'
$env:TARA_WORKER_CDP = 'http://127.0.0.1:9223'
```

Рабочий сервер:
```powershell
$env:TARA_WORKER_API = 'https://finebi.ipt.ls:8443/api'
$env:TARA_WORKER_CDP = 'http://127.0.0.1:9223'
```

Это адрес вашего уже проверенного тестового подключения. Если для него используется проброс портов, он должен оставаться работающим.

**6. Введите ключ исполнителя**

Сначала выполните:

```powershell
$taraSecret = Read-Host 'Введите TARA_WORKER_KEY тестового сервера' -AsSecureString
```

Когда появится приглашение, вставьте **значение `TARA_WORKER_KEY` из настроек тестового сервера** и нажмите Enter. Ввод будет скрыт.

Затем выполните обе строки:

```powershell
$taraCredential = New-Object System.Management.Automation.PSCredential('worker', $taraSecret)
$env:TARA_WORKER_KEY = $taraCredential.GetNetworkCredential().Password
```

**7. Запустите исполнитель**

```powershell
& .\.venv\Scripts\python.exe .\worker.py
```

Оставьте PowerShell открытым. Исполнитель будет ждать задания — само его включение не запускает новый обход.

**8. Запустите мастер на фронте**

Откройте iPrice. В блоке Тары должно отображаться:

**Windows-исполнитель: подключён.**

Нажмите **«Запустить парсеры»**. Если мастер уже запущен, повторно нажимать не нужно: исполнитель получит задания, когда очередь дойдёт до Тары.

На время работы оставьте включёнными компьютер, Chromium, PowerShell и подключение к тестовому API. Компьютер не должен переходить в спящий режим.

**При следующем запуске** повторяйте шаги **1 и 3–7**. Если исполнитель уже работает, повторно запускать его не нужно. Для остановки используйте **Ctrl+C** в его окне PowerShell.









################################################ копия профиля
**Старые команды запуска не нужны.** Нужно один раз скопировать профиль, затем выбрать копию в приложении.

**1. Остановите исполнитель и закройте все окна Chromium.**

Дождитесь завершения процессов Chromium, чтобы скопировать согласованные файлы cookies и настроек.

**2. Откройте PowerShell и выполните блок:**

```powershell
$taraSource = 'C:\files\userMK\Chromium\profile'
$taraCopy = Join-Path $env:LOCALAPPDATA (
    'AnalyticsPlatform\TaraProfiles\profile-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
)

if (-not (Test-Path -LiteralPath "$taraSource\Local State")) {
    throw 'Не найден исходный профиль Chromium'
}

New-Item -ItemType Directory -Path $taraCopy -Force | Out-Null

robocopy "$taraSource" "$taraCopy" /E /XJ /R:1 /W:1 `
    /XF DevToolsActivePort SingletonLock SingletonCookie SingletonSocket LOCK `
    /XD Cache Code Cache GPUCache ShaderCache GrShaderCache

if ($LASTEXITCODE -ge 8) {
    throw "Ошибка копирования: robocopy завершился с кодом $LASTEXITCODE"
}

Write-Host "Профиль скопирован в: $taraCopy"
```

Копируется **весь каталог `profile`**, включая `Local State` и `Default`. Исходник не изменяется.

**3. В приложении исполнителя:**

- Chromium: `C:\files\userMK\Chromium\bin\chrome.exe`;
- **Профиль Chromium:** путь, напечатанный после «Профиль скопирован в»;
- **не добавляйте `\Default`** в конец;
- нажмите **«Подключить исполнитель»**.

**4. Проверьте `chrome://version` открывшегося окна.**

Профиль должен находиться в новой папке:

```text
...\AnalyticsPlatform\TaraProfiles\profile-...\Default
```

После этого обычный Chromium можно открыть для своей работы — профили будут раздельными. Копия содержит ваши браузерные данные, поэтому не передавайте её другим. **После переноса ненужные вкладки в скопированном профиле можно удалить**