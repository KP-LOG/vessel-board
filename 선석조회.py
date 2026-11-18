# -*- coding: utf-8 -*-
"""
부산 북항 터미널 선석배정현황 조회 → 모선 일정 변경 확인판용 데이터 파일 생성

조회 대상 (모두 로그인 불필요, 공개 화면)
- 허치슨 : https://custom.hktl.com/jsp/T01/sunsuk.jsp  (오늘 기준 전체, 페이지 넘김)
- BPT(신선대·감만) : https://info.bptc.co.kr/Berth_status_text_servlet_sw_kr  (조회기간 일주일)

결과 파일: 같은 폴더의 선석데이터.js (확인판 HTML이 읽음)
실행: 선석조회.bat 더블클릭, 또는  python 선석조회.py
한 터미널 조회가 실패해도 다른 터미널 결과는 저장하고, 실패한 터미널은 이전 결과를 그대로 둡니다.
"""
import datetime
import json
import os
import re
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '선석데이터.js')
UA = {'User-Agent': 'Mozilla/5.0'}


def post(url, form, referer=None, timeout=40):
    headers = dict(UA)
    if referer:
        headers['Referer'] = referer
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('cp949', 'replace')


def clean(cell):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', cell).replace('&nbsp;', ' ')).strip()


def to_local(t):
    # '2026/11/18 10:00(:00)' → '2026-11-18T10:00'
    m = re.match(r'(\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2})', t or '')
    return f'{m[1]}-{m[2]}-{m[3]}T{m[4]}:{m[5]}' if m else None


def now():
    return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M')


# ───────── 허치슨 ─────────
HK_URL = 'https://custom.hktl.com/jsp/T01/sunsuk.jsp'
HK_STATE = {'CCCCCC': '출항', 'FFFF99': '접안중', 'CCFFFF': '예정'}  # 행 배경색 범례


def hk_parse(html):
    rows = []
    for m in re.finditer(r'<tr bgcolor="#(\w+)"[^>]*>(.*?)</tr>', html, re.S | re.I):
        tds = [clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', m.group(2), re.S | re.I)]
        if len(tds) < 14:
            continue
        voy = tds[1]
        rows.append({
            'id': 'HK-' + tds[0], 'terminal': '허치슨', 'vvd': tds[0],
            'voyage': '' if voy == '/' else voy, 'berth': tds[2],
            'eta': to_local(tds[4]), 'etd': to_local(tds[6]), 'closing': to_local(tds[7]),
            'vessel': tds[11], 'line': tds[12], 'state': HK_STATE.get(m.group(1).upper(), ''),
        })
    return rows


def fetch_hk():
    today = datetime.date.today()
    base = {'langType': 'K', 'mainType': 'T01', 'subType': '01', 'optType': 'T', 'terminal': 'HBCTLIB',
            'year': today.strftime('%Y'), 'month': today.strftime('%m'), 'day': today.strftime('%d'),
            'ctrno': '', 'startPage': '1'}
    first = post(HK_URL, {**base, 'currentPage': '1'})
    m = re.search(r'전체 조회 건수\s*:\s*(\d+)', re.sub(r'<[^>]+>', ' ', first))
    total = int(m.group(1)) if m else None
    rows, page = hk_parse(first), 2
    while page <= 20 and (total is None or len(rows) < total):
        got = hk_parse(post(HK_URL, {**base, 'currentPage': str(page)}))
        if not got:
            break
        rows += got
        page += 1
    return rows, total


# ───────── BPT (신선대·감만) ─────────
BPT_URL = 'https://info.bptc.co.kr/Berth_status_text_servlet_sw_kr'
BPT_REF = 'https://info.bptc.co.kr/content/sw/frame/berth_status_text_frame_sw_kr.jsp?p_id=BETX_SH_KR&snb_num=2&snb_div=service'


def fetch_bpt():
    # 조회기간 일주일(week), 항로 전체, 선사 전체, 입항예정일시 순, 선석 전체(신선대+감만)
    html = post(BPT_URL, {'v_time': 'week', 'ROCD': 'ALL', 'v_oper_cd': '', 'ORDER': 'item2', 'v_gu': 'A'},
                referer=BPT_REF)
    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S | re.I):
        tds = [clean(x) for x in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S | re.I)]
        # 구분|선석|모선항차|선박명|접안|선사|입항예정|입항|작업완료|출항|반입마감|양하|선적|S/H|전배|항로|검역
        if len(tds) < 16 or tds[0] not in ('신선대', '감만'):
            continue
        state = '작업완료' if tds[8] else ('접안중' if tds[7] else '예정')
        rows.append({
            'id': 'BP-' + tds[2], 'terminal': tds[0], 'vvd': tds[2], 'voyage': tds[2], 'berth': tds[1],
            'eta': to_local(tds[6]), 'etd': to_local(tds[9]), 'closing': to_local(tds[10]),
            'vessel': tds[3], 'line': tds[5], 'state': state,
        })
    return rows, None


SOURCES = [
    ('HKTL', '허치슨', fetch_hk),
    ('BPT', '신선대·감만', fetch_bpt),
]


def load_old():
    try:
        with open(OUT, encoding='utf-8') as f:
            txt = f.read()
        return json.loads(txt[txt.index('{'):txt.rindex('}') + 1])
    except Exception:
        return {'sources': {}}


LOG = os.path.join(HERE, '선석조회_기록.txt')


def log(msg):
    # 화면 출력 + 실행 기록 파일에 남김 (작업 스케줄러로 창 없이 돌 때 확인용)
    print(msg)
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(f'{now()} {msg}\n')
    except Exception:
        pass


def main():
    data = load_old()
    data.setdefault('sources', {})
    ok_any = False
    for key, label, fn in SOURCES:
        try:
            rows, total = fn()
            seen, uniq = set(), []
            for r in rows:
                if r['id'] not in seen and r['eta'] and r['etd']:
                    seen.add(r['id'])
                    uniq.append(r)
            if not uniq:
                raise RuntimeError('조회 결과가 0건입니다 (사이트 화면이 바뀌었을 수 있음)')
            data['sources'][key] = {'label': label, 'fetchedAt': now(), 'count': len(uniq), 'rows': uniq}
            ok_any = True
            log(f'[성공] {label}: {len(uniq)}척' + (f' (사이트 표시 {total}건)' if total else ''))
        except Exception as e:
            log(f'[실패] {label}: {e}  → 이전 조회 결과를 그대로 둡니다.')

    if ok_any:
        with open(OUT, 'w', encoding='utf-8') as f:
            f.write('// 선석조회.py가 자동 생성하는 파일입니다. 직접 고치지 마세요.\n')
            f.write('window.BERTH_DATA = ' + json.dumps(data, ensure_ascii=False, indent=1) + ';\n')
        print(f'저장: {OUT}')
        try:
            notify_changes(data)
        except Exception as e:
            log(f'[알림 실패] {e}')
        try:
            publish_web()
        except Exception as e:
            log(f'[웹 갱신 실패] {e}')


# ───────── 웹(Vercel) 갱신 ─────────
# 조회 결과 선석데이터.js를 vessel-board 저장소에 복사 → GitHub에 올리고 → Vercel에 배포한다.
# 알림_설정.json 의 "web_publish": false 로 끌 수 있다.
WEB_REPO = os.path.join(HERE, 'vessel-board')
VERCEL = os.path.join(os.environ.get('APPDATA', ''), 'npm', 'vercel.cmd')


def run(cmd, timeout=240):
    import subprocess
    r = subprocess.run(cmd, cwd=WEB_REPO, capture_output=True, timeout=timeout,
                       creationflags=0x08000000)  # CREATE_NO_WINDOW
    out = (r.stdout or b'').decode('utf-8', 'replace') + (r.stderr or b'').decode('utf-8', 'replace')
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])} 실패: {out.strip()[-300:]}")
    return out


def publish_web():
    settings = read_json(SETTINGS, {})
    if not settings.get('web_publish', False) or not os.path.isdir(os.path.join(WEB_REPO, '.git')):
        return
    import shutil
    shutil.copyfile(OUT, os.path.join(WEB_REPO, '선석데이터.js'))
    run(['git', 'add', '선석데이터.js'])
    if not run(['git', 'status', '--porcelain', '선석데이터.js']).strip():
        return  # 바뀐 내용 없음
    run(['git', 'commit', '-q', '-m', f'선석데이터 자동 갱신 {now()}'])
    try:
        run(['git', 'push', '-q', 'origin', 'main'])
    except RuntimeError:
        run(['git', 'pull', '-q', '--rebase', 'origin', 'main'])
        run(['git', 'push', '-q', 'origin', 'main'])
    run([VERCEL, 'deploy', '--prod', '--yes'], timeout=300)
    log('[웹 갱신] GitHub 업로드 + Vercel 배포 완료 (https://vessel-board.vercel.app)')


# ───────── 변경 알림 ─────────
# 확인판의 [🔔 알림 연결]로 저장된 추적모선.json(사용자가 추가한 모선 + 안내 기준시간)을 읽어,
# 새 조회 결과가 기준시간과 달라진 모선이 생기면 Windows 알림을 띄운다. (같은 변경은 한 번만 알림)
WATCH = os.path.join(HERE, '추적모선.json')
STATE = os.path.join(HERE, '알림_상태.json')
SETTINGS = os.path.join(HERE, '알림_설정.json')
SITE_OF = {'허치슨': 'HKTL', '신선대': 'BPT', '감만': 'BPT'}


def norm(x):
    x = re.sub(r'^M/?V\s+', '', str(x or '').upper())
    return re.sub(r'[^A-Z0-9]', '', x)


def find_row(v, rows):
    """확인판(findRow)과 같은 기준: 이전에 찾은 건 → 선명 일치 → 선명 일부 일치, 항차·입항시간으로 좁힘"""
    same = [r for r in rows if r['terminal'] == v['terminal']]
    key = v.get('matchId') or v.get('id')
    hit = [r for r in same if r['id'] == key]
    if not hit:
        hit = [r for r in same if norm(r['vessel']) == norm(v['vessel'])]
    if not hit:
        n = norm(v['vessel'])
        if len(n) >= 4:
            hit = [r for r in same if n in norm(r['vessel']) or norm(r['vessel']) in n]
    if not hit:
        return None
    voy = norm(v.get('voyage'))
    if voy:
        by = [r for r in hit if voy in norm(r.get('voyage')) or voy in norm(r.get('vvd'))]
        hit = by or hit
    ref = v.get('eta')
    try:
        t = datetime.datetime.fromisoformat(ref) if ref else datetime.datetime.now()
    except ValueError:
        t = datetime.datetime.now()
    hit.sort(key=lambda r: abs((datetime.datetime.fromisoformat(r['eta']) - t).total_seconds()))
    return hit[0]


def fmt(t):
    if not t:
        return '—'
    d = datetime.datetime.fromisoformat(t)
    return f"{d:%m/%d}({'월화수목금토일'[d.weekday()]}) {d:%H:%M}"


def diff_text(base, cur):
    if not base or base == cur:
        return ''
    h = (datetime.datetime.fromisoformat(cur) - datetime.datetime.fromisoformat(base)).total_seconds() / 3600
    a = abs(h)
    a = int(a) if a == int(a) else round(a, 1)
    return f" ({a}시간 {'지연' if h > 0 else '당겨짐'})"


def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def notify_changes(data):
    watch = read_json(WATCH, None)
    if not watch:
        return  # 확인판에서 알림을 연결하지 않음
    state = read_json(STATE, {})
    found = []
    for v in watch.get('vessels', []):
        src = data['sources'].get(SITE_OF.get(v.get('terminal'), ''), {})
        if not v.get('baseEta') or not src.get('rows'):
            continue  # 기준시간 없는 신규 모선은 알림 대상 아님
        r = find_row(v, src['rows'])
        if not r:
            continue
        changed = r['eta'] != v['baseEta'] or r['etd'] != v['baseEtd']
        sig = f"{v['baseEta']}|{v['baseEtd']}|{r['eta']}|{r['etd']}"
        if not changed:
            state.pop(v['id'], None)
            continue
        if state.get(v['id']) == sig:
            continue  # 이미 알린 변경
        state[v['id']] = sig
        lines = [f"[{v['terminal']}] {v['vessel']} {v.get('voyage') or ''}".strip()]
        if r['eta'] != v['baseEta']:
            lines.append(f"  접안: {fmt(v['baseEta'])} → {fmt(r['eta'])}{diff_text(v['baseEta'], r['eta'])}")
        if r['etd'] != v['baseEtd']:
            lines.append(f"  출항: {fmt(v['baseEtd'])} → {fmt(r['etd'])}{diff_text(v['baseEtd'], r['etd'])}")
        found.append('\n'.join(lines))

    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    if not found:
        return

    title = f'모선 일정 변경 {len(found)}척 — 확인이 필요합니다'
    body = '\n'.join(found)
    log(f'[알림] {title}\n{body}')
    settings = read_json(SETTINGS, {'windows_toast': True})
    if settings.get('windows_toast', True):
        toast(title, body)


def toast(title, body):
    """Windows 알림 센터에 알림 표시 (PowerShell 기본 기능 사용, 별도 설치 없음)"""
    import base64
    import subprocess
    from xml.sax.saxutils import escape
    short = body if len(body) <= 230 else body[:227] + '…'
    xml = ('<toast duration="long"><visual><binding template="ToastGeneric">'
           f'<text>{escape(title)}</text><text>{escape(short)}</text>'
           '<text>모선_일정_변경_확인판에서 확인하세요.</text></binding></visual></toast>')
    ps = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{base64.b64encode(xml.encode('utf-8')).decode()}')));"
        "$t = [Windows.UI.Notifications.ToastNotification]::new($x);"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
        "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($t)"
    )
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-EncodedCommand',
                    base64.b64encode(ps.encode('utf-16-le')).decode()],
                   creationflags=0x08000000, timeout=60)  # CREATE_NO_WINDOW


if __name__ == '__main__':
    main()
