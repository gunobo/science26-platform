import * as DocumentPicker from 'expo-document-picker';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Linking, Pressable, ScrollView, Switch, Text, View } from 'react-native';

import { API_BASE, api, ApiError, json, Project, ProjectType, Release, Warning } from '../api';
import { Badge, Button, c, Card, Field, Notice, s, Segmented } from '../ui';

const BUSY_STATES = ['queued', 'validating', 'building', 'deploying'];

async function pick(types: string[], multiple = false): Promise<File[]> {
  const res = await DocumentPicker.getDocumentAsync({ type: types, multiple, copyToCacheDirectory: false });
  if (res.canceled) return [];
  return res.assets.map((a) => a.file).filter((f): f is File => !!f);
}

export default function DashboardScreen() {
  const [project, setProject] = useState<Project | null>(null);
  const [releases, setReleases] = useState<Release[]>([]);
  const [watching, setWatching] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [p, r] = await Promise.all([api<Project>('/projects/me'), api<Release[]>('/projects/me/releases')]);
    setProject(p);
    setReleases(r);
    const busy = r.find((x) => BUSY_STATES.includes(x.state));
    if (busy) setWatching(busy.id);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!project) return <Text style={s.muted}>불러오는 중…</Text>;
  const busy = releases.some((r) => BUSY_STATES.includes(r.state));

  return (
    <View>
      <OverviewCard project={project} onChange={refresh} />
      <UploadCard disabled={busy} onUploaded={(id) => { setWatching(id); refresh(); }} />
      {watching && <BuildLogCard releaseId={watching} onDone={refresh} />}
      <ReleasesCard releases={releases} activeId={project.active_release?.id} busy={busy} onWatch={setWatching} onChange={refresh} />
      {project.type === 'fullstack' && <EnvCard />}
      {project.active_release && <RuntimeCard project={project} onChange={refresh} />}
    </View>
  );
}

// ---- 개요·링크 이름·소개 ----

function OverviewCard({ project, onChange }: { project: Project; onChange: () => void }) {
  const [title, setTitle] = useState(project.title);
  const [description, setDescription] = useState(project.description);
  const [slug, setSlug] = useState(project.slug);
  const [thumb, setThumb] = useState<File | null>(null);
  const [msg, setMsg] = useState<{ text: string; kind: 'ok' | 'error' } | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    setMsg(null);
    const fd = new FormData();
    fd.append('title', title);
    fd.append('description', description);
    fd.append('slug', slug.trim().toLowerCase());
    if (thumb) fd.append('thumbnail', thumb);
    try {
      const res = await api<{ redeploying: boolean }>('/projects/me', { method: 'PATCH', body: fd });
      setMsg({ kind: 'ok', text: res.redeploying ? '저장했어요. 새 링크로 다시 배포하는 중이에요.' : '저장했어요.' });
      setThumb(null);
      onChange();
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    } finally {
      setSaving(false);
    }
  };

  const previewUrl = `https://science26.bssm.dev/students/${slug.trim().toLowerCase() || project.student_no}/`;

  return (
    <Card title="내 프로젝트" right={<Badge status={project.status} />}>
      {project.url && project.active_release ? (
        <Pressable onPress={() => Linking.openURL(project.url!)}>
          <Text style={{ color: c.accent, fontSize: 16, fontWeight: '600', marginBottom: 14 }}>{project.url}</Text>
        </Pressable>
      ) : (
        <Text style={[s.muted, { marginBottom: 14 }]}>아직 배포된 버전이 없어요. 아래에서 업로드하세요.</Text>
      )}
      <Field
        label="링크 이름"
        value={slug}
        onChangeText={setSlug}
        autoCapitalize="none"
        placeholder={project.student_no}
        hint={`${previewUrl}  ·  영문 소문자·숫자·하이픈, 바꾸면 자동 재배포되고 학번 주소는 새 주소로 연결돼요`}
      />
      <Field label="제목" value={title} onChangeText={setTitle} placeholder="공개 목록에 보일 제목" />
      <Field label="설명" value={description} onChangeText={setDescription} multiline placeholder="어떤 프로젝트인가요?" />
      <View style={[s.row, { marginBottom: 12 }]}>
        <Button label={thumb ? `썸네일: ${thumb.name}` : '썸네일 이미지 선택'} kind="ghost" small onPress={async () => setThumb((await pick(['image/*']))[0] ?? null)} />
      </View>
      {msg && <Notice kind={msg.kind} text={msg.text} />}
      <Button label="저장" onPress={save} busy={saving} />
    </Card>
  );
}

// ---- 업로드 ----

function UploadCard({ disabled, onUploaded }: { disabled: boolean; onUploaded: (releaseId: string) => void }) {
  const [type, setType] = useState<ProjectType>('static');
  const [source, setSource] = useState<'file' | 'git'>('file');
  const [file, setFile] = useState<File | null>(null);
  const [repo, setRepo] = useState('');
  const [branch, setBranch] = useState('main');
  const [apk, setApk] = useState<File | null>(null);
  const [shots, setShots] = useState<File[]>([]);
  const [appTitle, setAppTitle] = useState('');
  const [appDesc, setAppDesc] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [warnings, setWarnings] = useState<Warning[]>([]);

  const submit = async () => {
    setBusy(true);
    setError('');
    setWarnings([]);
    try {
      const fd = new FormData();
      let path = '/projects/me/releases';
      if (type === 'app') {
        path = '/projects/me/app';
        if (!apk) throw new Error('APK 파일을 선택하세요');
        fd.append('title', appTitle);
        fd.append('description', appDesc);
        fd.append('apk', apk);
        shots.forEach((f) => fd.append('screenshots', f));
      } else {
        fd.append('type', type);
        if (type === 'fullstack' && source === 'git') {
          fd.append('repo_url', repo.trim());
          fd.append('branch', branch.trim() || 'main');
        } else {
          if (!file) throw new Error('파일을 선택하세요');
          fd.append('file', file);
        }
      }
      const res = await api<{ release_id: string; warnings: Warning[] }>(path, { method: 'POST', body: fd });
      setWarnings(res.warnings);
      setFile(null);
      setApk(null);
      setShots([]);
      onUploaded(res.release_id);
    } catch (e: any) {
      setError(e instanceof ApiError && e.code === 'COMPOSE_FORBIDDEN_KEY' ? `compose 규칙 위반: ${e.message}` : e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="업로드">
      <Segmented
        value={type}
        onChange={setType}
        options={[
          { value: 'static', label: '정적 웹' },
          { value: 'fullstack', label: '풀스택' },
          { value: 'app', label: '모바일 앱' },
        ]}
      />
      {type === 'static' && (
        <>
          <Notice text="빌드된 dist 폴더를 zip 으로 묶거나 index.html 한 개를 올리세요. 페이지는 /students/링크이름/ 아래에서 열리니 에셋 경로는 상대경로여야 해요 (Vite: base: './', Expo: experiments.baseUrl)." />
          <Button label={file ? file.name : 'zip 또는 index.html 선택 (최대 100MB)'} kind="ghost" onPress={async () => setFile((await pick(['application/zip', '.zip', 'text/html', '.html']))[0] ?? null)} />
        </>
      )}
      {type === 'fullstack' && (
        <>
          <Notice text="루트에 docker-compose.yml 이 있어야 해요. 공개 서비스에 라벨 science26.public=true (API 서비스는 science26.api=true → /api 경로). DB·Redis 는 넣지 말고 주입되는 DATABASE_URL·REDIS_URL·BASE_PATH 를 쓰세요. ports·volumes·privileged 등은 금지." />
          <Segmented value={source} onChange={setSource} options={[{ value: 'file', label: 'zip 업로드' }, { value: 'git', label: 'GitHub 저장소' }]} />
          {source === 'file' ? (
            <Button label={file ? file.name : 'zip 선택 (최대 200MB)'} kind="ghost" onPress={async () => setFile((await pick(['application/zip', '.zip']))[0] ?? null)} />
          ) : (
            <>
              <Field label="저장소 주소" value={repo} onChangeText={setRepo} autoCapitalize="none" placeholder="https://github.com/아이디/저장소" />
              <Field label="브랜치" value={branch} onChangeText={setBranch} autoCapitalize="none" />
            </>
          )}
        </>
      )}
      {type === 'app' && (
        <>
          <Notice text="서명된 APK와 스크린샷 1~5장을 올리면 다운로드 버튼과 QR 코드가 있는 소개 페이지가 만들어져요." />
          <Field label="앱 이름" value={appTitle} onChangeText={setAppTitle} />
          <Field label="설명" value={appDesc} onChangeText={setAppDesc} multiline />
          <View style={s.row}>
            <Button label={apk ? apk.name : 'APK 선택 (최대 150MB)'} kind="ghost" onPress={async () => setApk((await pick(['application/vnd.android.package-archive', '.apk']))[0] ?? null)} />
            <Button label={shots.length ? `스크린샷 ${shots.length}장` : '스크린샷 선택 (1~5장)'} kind="ghost" onPress={async () => setShots((await pick(['image/*'], true)).slice(0, 5))} />
          </View>
        </>
      )}
      <View style={{ height: 14 }} />
      {error ? <Notice kind="error" text={error} /> : null}
      {warnings.map((w, i) => (
        <Notice key={i} kind="warn" text={`${w.message}${w.paths?.length ? `\n발견된 경로: ${w.paths.join(', ')}` : ''}`} />
      ))}
      <Button label={disabled ? '빌드 진행 중…' : '업로드하고 배포'} onPress={submit} busy={busy} disabled={disabled} />
    </Card>
  );
}

// ---- 빌드 로그 (SSE) ----

function BuildLogCard({ releaseId, onDone }: { releaseId: string; onDone: () => void }) {
  const [lines, setLines] = useState<string[]>([]);
  const [state, setState] = useState('queued');
  const scroll = useRef<ScrollView>(null);

  useEffect(() => {
    setLines([]);
    const es = new EventSource(`${API_BASE}/releases/${releaseId}/logs`, { withCredentials: true });
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.kind === 'state') setState(data.line);
      else if (data.kind === 'end') {
        setState(data.line);
        if (data.error) setLines((l) => [...l, `❌ ${data.error}`]);
        es.close();
        onDone();
      } else setLines((l) => [...l.slice(-1500), data.line]);
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [releaseId, onDone]);

  return (
    <Card title="빌드 로그" right={<Badge status={state} />}>
      <ScrollView ref={scroll} style={s.logBox} onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}>
        {lines.length === 0 ? <Text style={s.mono}>대기 중…</Text> : lines.map((l, i) => <Text key={i} style={s.mono}>{l}</Text>)}
      </ScrollView>
    </Card>
  );
}

// ---- 릴리스 ----

function ReleasesCard({ releases, activeId, busy, onWatch, onChange }: { releases: Release[]; activeId?: string; busy: boolean; onWatch: (id: string) => void; onChange: () => void }) {
  const [error, setError] = useState('');
  if (releases.length === 0) return null;
  const rollback = async (r: Release) => {
    setError('');
    try {
      await api('/projects/me/rollback', { method: 'POST', ...json({ release_id: r.id }) });
      onWatch(r.id);
      onChange();
    } catch (e: any) {
      setError(e.message);
    }
  };
  return (
    <Card title="릴리스 기록">
      {error ? <Notice kind="error" text={error} /> : null}
      {releases.slice(0, 10).map((r, i) => (
        <View key={r.id} style={{ paddingVertical: 10, borderTopWidth: 1, borderTopColor: c.border }}>
          <View style={s.row}>
            <Text style={{ fontWeight: '700', color: c.text, width: 40 }}>v{r.version}</Text>
            <Badge status={r.state} />
            <Text style={s.muted}>{new Date(r.created_at).toLocaleString('ko-KR')} · {r.source_ref}</Text>
            <View style={{ flex: 1 }} />
            <Button label="로그" kind="ghost" small onPress={() => onWatch(r.id)} />
            {i < 5 && (r.state === 'superseded' || r.id === activeId) && (
              <Button label={r.id === activeId ? '재배포' : '이 버전으로 롤백'} kind="ghost" small disabled={busy} onPress={() => rollback(r)} />
            )}
          </View>
          {r.error ? <Text style={{ color: c.danger, marginTop: 6, fontSize: 13 }}>{r.error.split('\n')[0]}</Text> : null}
        </View>
      ))}
    </Card>
  );
}

// ---- 환경변수 ----

type EnvRow = { key: string; value: string | null; secret: boolean; isNew?: boolean };

function EnvCard() {
  const [rows, setRows] = useState<EnvRow[]>([]);
  const [msg, setMsg] = useState<{ text: string; kind: 'ok' | 'error' } | null>(null);

  useEffect(() => {
    api<EnvRow[]>('/projects/me/env').then(setRows);
  }, []);

  const update = (i: number, patch: Partial<EnvRow>) => setRows((r) => r.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const save = async () => {
    // 마스킹된 비밀값을 비워둔 경우 null 로 보내 기존 값을 유지한다
    const payload = rows.map(({ key, value, secret, isNew }) => ({
      key,
      value: secret && !isNew && (value === '' || value === null) ? null : value,
      secret,
    }));
    try {
      const res = await api<{ note: string }>('/projects/me/env', { method: 'PUT', ...json(payload) });
      setMsg({ kind: 'ok', text: `저장했어요. ${res.note}` });
      setRows(await api<EnvRow[]>('/projects/me/env'));
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    }
  };

  return (
    <Card title="환경변수" right={<Button label="+ 추가" kind="ghost" small onPress={() => setRows((r) => [...r, { key: '', value: '', secret: false, isNew: true }])} />}>
      <Text style={[s.muted, { marginBottom: 10 }]}>DATABASE_URL · REDIS_URL · BASE_PATH · PUBLIC_URL 은 자동으로 들어가요. 비밀값은 저장 후 다시 볼 수 없어요.</Text>
      {rows.map((r, i) => (
        <View key={i} style={[s.row, { marginBottom: 8 }]}>
          <View style={{ width: 200 }}>
            <Field label="" value={r.key} onChangeText={(t) => update(i, { key: t })} placeholder="KEY" autoCapitalize="characters" />
          </View>
          <View style={{ flex: 1, minWidth: 180 }}>
            <Field
              label=""
              value={r.value ?? ''}
              onChangeText={(t) => update(i, { value: t })}
              placeholder={r.value === null ? '•••••• (그대로 두려면 비워두기)' : 'value'}
              secureTextEntry={r.secret}
            />
          </View>
          <View style={s.row}>
            <Text style={s.muted}>비밀</Text>
            <Switch value={r.secret} onValueChange={(v) => update(i, { secret: v })} />
          </View>
          <Button label="삭제" kind="ghost" small onPress={() => setRows((rs) => rs.filter((_, j) => j !== i))} />
        </View>
      ))}
      {msg && <Notice kind={msg.kind} text={msg.text} />}
      <Button label="저장" onPress={save} />
    </Card>
  );
}

// ---- 실행 상태·런타임 로그 ----

function RuntimeCard({ project, onChange }: { project: Project; onChange: () => void }) {
  const [logs, setLogs] = useState<string[] | null>(null);
  const [service, setService] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const act = async (path: string) => {
    setBusy(true);
    setError('');
    try {
      await api(path, { method: 'POST' });
      setTimeout(onChange, 2500);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const loadLogs = async () => {
    setError('');
    try {
      const q = service ? `?service=${encodeURIComponent(service)}` : '';
      setLogs((await api<{ lines: string[] }>(`/projects/me/runtime-logs${q}`)).lines);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const running = project.status === 'running';
  return (
    <Card title="실행 관리">
      <View style={[s.row, { marginBottom: 12 }]}>
        {running ? (
          <Button label="중지" kind="danger" busy={busy} onPress={() => act('/projects/me/stop')} />
        ) : (
          <Button label="시작" busy={busy} onPress={() => act('/projects/me/start')} />
        )}
        {project.type === 'fullstack' && <Text style={s.muted}>30분간 방문이 없으면 슬립하고, 첫 방문 때 다시 켜져요.</Text>}
      </View>
      {error ? <Notice kind="error" text={error} /> : null}
      <View style={[s.row, { marginBottom: 10 }]}>
        {project.type === 'fullstack' && (
          <View style={{ width: 180 }}>
            <Field label="" value={service} onChangeText={setService} placeholder="서비스 이름 (전체: 비움)" autoCapitalize="none" />
          </View>
        )}
        <Button label="런타임 로그 보기 (최근 500줄)" kind="ghost" onPress={loadLogs} />
      </View>
      {logs && (
        <ScrollView style={s.logBox}>
          {logs.length === 0 ? <Text style={s.mono}>(로그 없음)</Text> : logs.map((l, i) => <Text key={i} style={s.mono}>{l}</Text>)}
        </ScrollView>
      )}
    </Card>
  );
}
