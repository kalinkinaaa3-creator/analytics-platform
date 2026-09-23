"""Windows-only page transport; server owns parsing, queue and persistence."""
import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import requests
from playwright.async_api import async_playwright

BASE = os.environ.get('TARA_WORKER_API', 'http://127.0.0.1:18000/api').rstrip('/')
KEY = os.environ.get('TARA_WORKER_KEY', '')
CDP = os.environ.get('TARA_WORKER_CDP', 'http://127.0.0.1:9223')
OUTBOX = Path(__file__).with_name('outbox')
OWNER = uuid.uuid4().hex
BLOCKS = (401,403,429,502)


def allowed(url):
    try:
        u = urlsplit(url)
        return u.scheme == 'https' and not u.username and not u.password and u.port in (None,443) and (u.hostname == 'tara.ru' or (u.hostname or '').endswith('.tara.ru'))
    except (ValueError,TypeError):
        return False


def card(html):
    return any(s in html.lower() for s in ('topic__heading','props_block__wrapper','price_matrix_block','price_wrapper_block'))


def api(path, data):
    with requests.Session() as client:
        client.trust_env = False
        response = client.post(BASE+'/v1/datasets/parsers/tara/worker/'+path,
                              json=data, headers={'X-Tara-Worker-Key':KEY}, timeout=(10,30), allow_redirects=False)
        if response.status_code in (401,403):
            raise PermissionError('Windows executor key rejected')
        if response.status_code in (404,409) and path.startswith('tasks/'):
            return {'discarded':True}
        response.raise_for_status()
        return response.json()


def get_page(task, cookies, headers):
    url = task['url']
    if not allowed(url):
        raise ValueError('Server supplied an unexpected URL')
    try:
        with requests.Session() as client:
            client.trust_env = False
            client.headers.update(headers)
            for c in cookies:
                d = c['domain'].lstrip('.')
                if d != 'tara.ru' and not d.endswith('.tara.ru'):
                    continue
                client.cookies.set(c['name'],c['value'],domain=c['domain'],path=c['path'],
                                   secure=c.get('secure',False),expires=int(c['expires']) if c.get('expires',-1)>0 else None)
            with client.get(url, timeout=(10,20),allow_redirects=False,stream=True) as response:
                chunks=[]; size=0; started=time.monotonic()
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>8*1024*1024 or time.monotonic()-started>30:
                        raise ValueError('Page exceeds diagnostic transport limits')
                    chunks.append(chunk)
                raw=b''.join(chunks)
                html=raw.decode(response.encoding if response.encoding and response.encoding.lower()!='iso-8859-1' else 'utf-8',errors='replace')
                blocked=response.status_code in BLOCKS or (response.status_code!=404 and not card(html) and ('forbidden' in html.lower() or '/__qrator/qauth.js' in html.lower()))
                return {'status':response.status_code,'html':html,'final_url':url,'blocked':blocked,'error':None}
    except (requests.RequestException, ValueError) as exc:
        # No cookie/header values in diagnostics.
        reason = type(exc).__name__
        if isinstance(exc, ValueError):
            reason = 'ResponseSizeOrTimeLimit'
        return {'status':503,'html':'','final_url':url,'blocked':False,'error':'network','reason':reason}


def transient(payload):
    return not payload['blocked'] and (bool(payload.get('error')) or payload['status'] in (500,503,504))


async def fetch_with_retries(task, cookies, headers):
    started = time.monotonic()
    for attempt in range(1, 4):
        payload = await asyncio.to_thread(get_page, task, cookies, headers)
        payload['attempts'] = attempt
        if not transient(payload):
            return payload
        print(json.dumps({'task':task['id'], 'url':task['url'], 'attempt':attempt,
                          'status':payload['status'], 'reason':payload.get('reason') or 'HTTP server error'}), flush=True)
        # Bound retries within the server's six-minute task lease, including recovery.
        if attempt == 3 or time.monotonic() - started >= 120:
            if payload.get('error'):
                payload['error'] = 'request_exhausted'
            return payload
        await asyncio.sleep(attempt * 2)


def batch_network_failure(payloads):
    return sum(transient(p) for p in payloads) * 2 >= len(payloads)


def spool(task, payload):
    OUTBOX.mkdir(parents=True,exist_ok=True)
    path=OUTBOX/(str(task['id'])+'-'+task['token']+'.json')
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps({'task_id':task['id'],'token':task['token'],'payload':payload,'api':BASE}),encoding='utf-8')
    temp.replace(path)


async def flush():
    for path in sorted(OUTBOX.glob('*.json')):
        item=json.loads(path.read_text(encoding='utf-8'))
        if item.get('api') != BASE:
            continue
        await asyncio.to_thread(api,f"tasks/{item['task_id']}/result/",{'token':item['token'],'payload':item['payload']})
        path.unlink()


async def refresh(page):
    statuses=[]
    def capture(response):
        if response.request.is_navigation_request() and response.frame==page.main_frame:
            statuses.append(response.status)
    page.on('response',capture)
    try:
        await page.reload(wait_until='domcontentloaded',timeout=45000)
        for _ in range(30):
            await page.wait_for_timeout(1000)
            if statuses and statuses[-1]==200 and card(await page.content()):
                return True
            if statuses and statuses[-1] in (403,502):
                break
        return False
    finally:
        page.remove_listener('response',capture)


async def main(stop_event=None):
    def stopping():
        return stop_event is not None and stop_event.is_set()

    async def pause(seconds):
        for _ in range(seconds):
            if stopping():
                return
            await asyncio.sleep(1)
    endpoint=urlsplit(BASE)
    if not KEY or (endpoint.scheme!='https' and not (endpoint.scheme=='http' and endpoint.hostname in ('localhost','127.0.0.1'))):
        raise ValueError('Set a worker key and HTTPS API (HTTP allowed for loopback only)')
    if urlsplit(CDP).hostname not in ('localhost','127.0.0.1'):
        raise ValueError('CDP must be local')
    async with async_playwright() as pw:
        browser=await pw.chromium.connect_over_cdp(CDP,timeout=15000)
        pages=[(c,p) for c in browser.contexts for p in c.pages if allowed(p.url)]
        if len(pages)!=1 or not card(await pages[0][1].content()):
            raise ValueError('Open exactly one Tara product service tab in the diagnostic browser')
        context,page=pages[0]
        headers={'User-Agent':await page.evaluate('navigator.userAgent'),'Accept-Language':'ru-RU,ru;q=0.9'}
        async def heartbeat():
            while True:
                await asyncio.sleep(20)
                try:
                    await asyncio.to_thread(api,'claim/',{'owner':OWNER,'ready':True,'pull':False})
                except requests.RequestException:
                    print('API heartbeat unavailable; results will remain in outbox.',flush=True)
        await asyncio.to_thread(api,'claim/',{'owner':OWNER,'ready':True,'pull':False})
        print('Windows executor connected; waiting for server tasks.', flush=True)
        pulse=asyncio.create_task(heartbeat())
        try:
            while not stopping():
                if pulse.done():
                    await pulse
                try:
                    await flush()
                    data=await asyncio.to_thread(api,'claim/',{'owner':OWNER,'ready':True})
                except requests.RequestException:
                    print('API unavailable; waiting 10 seconds.',flush=True)
                    await pause(10)
                    continue
                tasks=data['tasks']
                if not tasks:
                    await pause(3)
                    continue
                cookies=await context.cookies()
                payloads=await asyncio.gather(*(fetch_with_retries(t,cookies,headers) for t in tasks))
                blocked=[i for i,p in enumerate(payloads) if p['blocked']]
                recovered=True
                if blocked:
                    try:
                        recovered=await refresh(page)
                    except Exception:
                        recovered=False
                    if recovered:
                        cookies=await context.cookies()
                        retried=await asyncio.gather(*(asyncio.to_thread(get_page,tasks[i],cookies,headers) for i in blocked))
                        for p in retried:
                            if p.get('error'):
                                p['error'] = 'request_exhausted'
                        for i,p in zip(blocked,retried): payloads[i]=p
                        recovered=not any(p['blocked'] for p in payloads)
                for task,payload in zip(tasks,payloads):
                    spool(task,payload)
                    print(json.dumps({'task':task['id'],'url':task['url'],'status':payload['status'],
                                      'blocked':payload['blocked'],'error':payload.get('error'),
                                      'reason':payload.get('reason'),'attempts':payload.get('attempts')}),flush=True)
                try:
                    await flush()
                except requests.RequestException:
                    print('Results saved locally; API upload will be retried.',flush=True)
                if not recovered:
                    print('Paused: check the service tab/network, then restart the executor.',flush=True)
                    return
                if batch_network_failure(payloads):
                    print('Network/server failures in most of the batch; waiting 30 seconds before the next batch. Heartbeat remains active.',flush=True)
                    await pause(30)
        finally:
            pulse.cancel()
            await asyncio.gather(pulse,return_exceptions=True)
            try:
                await asyncio.to_thread(api,'claim/',{'owner':OWNER,'ready':False,'pull':False})
            except Exception:
                pass
            # Do not close the user-started browser/context.


if __name__=='__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Executor stopped. Browser left open.')
