import * as DocumentPicker from 'expo-document-picker';
import { useCallback, useEffect, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';

import { api, json, Project } from '../api';
import { Badge, Button, c, Card, Field, Notice, s } from '../ui';

type AdminProject = Project & {
  owner: { email: string; name: string };
  stats: { cpu_percent: number; mem_bytes: number; containers: number; db_bytes?: number } | null;
};
type Settings = { upload_deadline: string | null; memory_mb: number; stack_memory_mb: number; cpus: number; pids: number };

const mb = (b?: number) => (b == null ? '-' : `${Math.round(b / 1024 / 1024)}MB`);

export default function AdminScreen() {
  return (
    <View>
      <ProjectsCard />
      <ImportCard />
      <SettingsCard />
      <AuditCard />
    </View>
  );
}

function ProjectsCard() {
  const [rows, setRows] = useState<AdminProject[] | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api<AdminProject[]>('/admin/projects').then(setRows).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const act = async (p: AdminProject, kind: 'stop' | 'delete') => {
    if (kind === 'delete' && !window.confirm(`${p.student_no} 의 스택·DB·파일을 모두 삭제할까요? 되돌릴 수 없어요.`)) return;
    try {
      await api(kind === 'stop' ? `/admin/projects/${p.student_no}/stop` : `/admin/projects/${p.student_no}`, { method: kind === 'stop' ? 'POST' : 'DELETE' });
      setTimeout(load, 2000);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const counts = rows?.reduce<Record<string, number>>((acc, p) => ({ ...acc, [p.status]: (acc[p.status] || 0) + 1 }), {});
  return (
    <Card title="전체 프로젝트" right={<Button label="새로고침" kind="ghost" small onPress={load} />}>
      {error ? <Notice kind="error" text={error} /> : null}
      {counts && (
        <Text style={[s.muted, { marginBottom: 10 }]}>
          총 {rows!.length}개 · {Object.entries(counts).map(([k, v]) => `${k} ${v}`).join(' · ')}
        </Text>
      )}
      {rows?.map((p) => (
        <View key={p.student_no} style={{ paddingVertical: 10, borderTopWidth: 1, borderTopColor: c.border }}>
          <View style={s.row}>
            <Text style={{ fontWeight: '700', width: 48, color: c.text }}>{p.student_no}</Text>
            <Text style={{ color: c.text, width: 80 }} numberOfLines={1}>{p.owner.name}</Text>
            <Badge status={p.status} />
            <Text style={s.muted}>{p.type ?? '-'}</Text>
            <Pressable onPress={() => p.url && Linking.openURL(p.url)}>
              <Text style={{ color: c.accent }} numberOfLines={1}>/{p.slug}</Text>
            </Pressable>
            <Text style={[s.muted, { flex: 1 }]} numberOfLines={1}>{p.title}</Text>
            <Text style={s.muted}>
              CPU {p.stats ? `${p.stats.cpu_percent.toFixed(1)}%` : '-'} · 메모리 {mb(p.stats?.mem_bytes)} · DB {mb(p.stats?.db_bytes)}
            </Text>
            <Button label="강제 중지" kind="ghost" small onPress={() => act(p, 'stop')} />
            <Button label="삭제" kind="danger" small onPress={() => act(p, 'delete')} />
          </View>
          {p.latest_release?.state === 'failed' && p.latest_release.error ? (
            <Text style={{ color: c.danger, fontSize: 12, marginTop: 4 }} numberOfLines={2}>v{p.latest_release.version}: {p.latest_release.error}</Text>
          ) : null}
        </View>
      ))}
      {rows && rows.length === 0 ? <Text style={s.muted}>아직 프로젝트가 없어요.</Text> : null}
    </Card>
  );
}

function ImportCard() {
  const [result, setResult] = useState<{ created: number; updated: number; errors: { line: number; message: string }[] } | null>(null);
  const [error, setError] = useState('');
  const upload = async () => {
    setError('');
    const res = await DocumentPicker.getDocumentAsync({ type: ['text/csv', '.csv'], copyToCacheDirectory: false });
    const file = !res.canceled && res.assets[0]?.file;
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      setResult(await api('/admin/users/import', { method: 'POST', body: fd }));
    } catch (e: any) {
      setError(e.message);
    }
  };
  return (
    <Card title="학번 매핑 CSV">
      <Text style={[s.muted, { marginBottom: 10 }]}>형식: email,학번,이름 (한 줄에 한 명, 헤더 있어도 됨). 매핑된 학생만 업로드할 수 있어요.</Text>
      <Button label="CSV 업로드" kind="ghost" onPress={upload} />
      {error ? <View style={{ marginTop: 10 }}><Notice kind="error" text={error} /></View> : null}
      {result && (
        <View style={{ marginTop: 10 }}>
          <Notice kind={result.errors.length ? 'warn' : 'ok'} text={`추가 ${result.created}명 · 갱신 ${result.updated}명${result.errors.length ? ` · 오류 ${result.errors.length}건` : ''}`} />
          {result.errors.map((e) => (
            <Text key={e.line} style={{ color: c.danger, fontSize: 13 }}>{e.line}행: {e.message}</Text>
          ))}
        </View>
      )}
    </Card>
  );
}

function toLocalInput(iso: string | null) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function SettingsCard() {
  const [cfg, setCfg] = useState<Settings | null>(null);
  const [deadline, setDeadline] = useState('');
  const [msg, setMsg] = useState<{ text: string; kind: 'ok' | 'error' } | null>(null);

  useEffect(() => {
    api<Settings>('/admin/settings').then((c) => {
      setCfg(c);
      setDeadline(toLocalInput(c.upload_deadline));
    });
  }, []);
  if (!cfg) return null;

  const num = (k: keyof Settings) => (t: string) => setCfg({ ...cfg, [k]: Number(t) || 0 });
  const save = async () => {
    try {
      const d = deadline.trim() ? new Date(deadline.replace(' ', 'T')) : null;
      if (d && isNaN(d.getTime())) throw new Error('마감 시각 형식: 2026-12-01 18:00');
      setCfg(await api('/admin/settings', { method: 'PUT', ...json({ ...cfg, upload_deadline: d?.toISOString() ?? null }) }));
      setMsg({ kind: 'ok', text: '저장했어요. 리소스 한도는 다음 배포부터 적용돼요.' });
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    }
  };

  return (
    <Card title="설정">
      <Field label="업로드 마감 (비우면 마감 없음)" value={deadline} onChangeText={setDeadline} placeholder="2026-12-01 18:00" hint="마감 후에는 관리자만 업로드할 수 있어요" />
      <View style={s.row}>
        <View style={{ width: 150 }}><Field label="서비스당 메모리(MB)" value={String(cfg.memory_mb)} onChangeText={num('memory_mb')} /></View>
        <View style={{ width: 150 }}><Field label="스택 합계(MB)" value={String(cfg.stack_memory_mb)} onChangeText={num('stack_memory_mb')} /></View>
        <View style={{ width: 110 }}><Field label="CPU" value={String(cfg.cpus)} onChangeText={(t) => setCfg({ ...cfg, cpus: parseFloat(t) || 0 })} /></View>
        <View style={{ width: 110 }}><Field label="PIDs" value={String(cfg.pids)} onChangeText={num('pids')} /></View>
      </View>
      {msg && <Notice kind={msg.kind} text={msg.text} />}
      <Button label="저장" onPress={save} />
    </Card>
  );
}

function AuditCard() {
  const [rows, setRows] = useState<{ at: string; actor: string | null; action: string; target: string }[]>([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (open) api('/admin/audit-logs').then(setRows);
  }, [open]);
  return (
    <Card title="감사 로그" right={<Button label={open ? '접기' : '보기'} kind="ghost" small onPress={() => setOpen(!open)} />}>
      {open &&
        rows.map((r, i) => (
          <Text key={i} style={{ fontSize: 13, color: c.text, paddingVertical: 3 }}>
            {new Date(r.at).toLocaleString('ko-KR')} · {r.actor ?? '-'} · {r.action} · {r.target}
          </Text>
        ))}
    </Card>
  );
}
