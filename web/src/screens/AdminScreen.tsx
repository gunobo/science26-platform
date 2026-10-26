import * as DocumentPicker from 'expo-document-picker';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Linking, Pressable, Text, TextInput, useWindowDimensions, View } from 'react-native';
import { ArrowsClockwise, ClipboardText, FileCsv, MagnifyingGlass, Sliders, Stop, Trash, UsersThree } from '@phosphor-icons/react';

import { api, json, Project } from '../api';
import { font, radius, useTheme } from '../theme';
import { Badge, Button, Card, Field, FilePick, Notice, Skeleton, T } from '../ui';

type AdminProject = Project & {
  owner: { email: string; name: string };
  stats: { cpu_percent: number; mem_bytes: number; containers: number; db_bytes?: number } | null;
};
type Settings = { upload_deadline: string | null; memory_mb: number; stack_memory_mb: number; cpus: number; pids: number };

const mb = (b?: number) => (b == null ? '-' : `${Math.round(b / 1024 / 1024)}MB`);

export default function AdminScreen() {
  const { width } = useWindowDimensions();
  const wide = width >= 980;
  return (
    <View>
      <ProjectsCard />
      <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 20 : 0, alignItems: 'flex-start' }}>
        <View style={{ flex: 1, minWidth: 0, width: wide ? undefined : '100%' }}>
          <ImportCard />
          <AuditCard />
        </View>
        <View style={{ flex: 1, minWidth: 0, width: wide ? undefined : '100%' }}>
          <SettingsCard />
        </View>
      </View>
    </View>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  const t = useTheme();
  return (
    <View style={{ minWidth: 96 }}>
      <Text style={{ fontFamily: font.family, fontSize: 28, fontWeight: '800', letterSpacing: -0.8, color: t.text }}>{value}</Text>
      <T variant="small">{label}</T>
    </View>
  );
}

function ProjectsCard() {
  const t = useTheme();
  const [rows, setRows] = useState<AdminProject[] | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');

  const load = useCallback(() => {
    api<AdminProject[]>('/admin/projects').then(setRows).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  const act = async (p: AdminProject, kind: 'stop' | 'delete') => {
    if (kind === 'delete' && !window.confirm(`${p.student_no} ${p.owner.name} 학생의 스택, DB, 파일을 모두 삭제할까요? 되돌릴 수 없어요.`)) return;
    try {
      await api(kind === 'stop' ? `/admin/projects/${p.student_no}/stop` : `/admin/projects/${p.student_no}`, { method: kind === 'stop' ? 'POST' : 'DELETE' });
      setTimeout(load, 2000);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const count = (s: string) => rows?.filter((p) => p.status === s).length ?? 0;
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows?.filter((p) => !q || [p.student_no, p.owner.name, p.title, p.slug].some((v) => v?.toLowerCase().includes(q)));
  }, [rows, query]);

  return (
    <Card title="전체 프로젝트" icon={UsersThree} right={<Button label="새로고침" kind="ghost" small icon={ArrowsClockwise} onPress={load} />}>
      {error ? <Notice kind="error" text={error} /> : null}
      {rows && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 28, marginBottom: 20 }}>
          <Stat label="전체" value={rows.length} />
          <Stat label="실행 중" value={count('running')} />
          <Stat label="쉬는 중" value={count('sleeping')} />
          <Stat label="빌드 중" value={count('building')} />
          <Stat label="실패" value={count('failed')} />
        </View>
      )}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: t.borderStrong, borderRadius: radius.control, paddingHorizontal: 12, marginBottom: 12, maxWidth: 360 }}>
        <MagnifyingGlass size={17} color={t.textMuted} />
        <TextInput value={query} onChangeText={setQuery} placeholder="학번, 이름, 제목" placeholderTextColor={t.textMuted} style={{ flex: 1, fontFamily: font.family, fontSize: 14.5, color: t.text, paddingVertical: 9, outlineStyle: 'none' } as any} />
      </View>
      {!rows && !error && (
        <View style={{ gap: 8 }}>
          <Skeleton h={52} />
          <Skeleton h={52} />
          <Skeleton h={52} />
        </View>
      )}
      <View style={{ gap: 6 }}>
        {shown?.map((p) => (
          <View key={p.student_no} style={{ backgroundColor: t.surfaceAlt, borderRadius: radius.control, padding: 12, gap: 6 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <T variant="heading" style={{ fontSize: 15, width: 44 }}>{p.student_no}</T>
              <T style={{ color: t.text, width: 72 }} numberOfLines={1}>{p.owner.name || '-'}</T>
              <Badge status={p.status} />
              <Pressable onPress={() => p.url && Linking.openURL(p.url)} style={{ flex: 1, minWidth: 140 }}>
                <T variant="sub" numberOfLines={1} style={{ color: t.accent }}>/{p.slug}  {p.title}</T>
              </Pressable>
              <T variant="small" style={{ fontFamily: font.mono }}>
                CPU {p.stats ? `${p.stats.cpu_percent.toFixed(1)}%` : '-'}   MEM {mb(p.stats?.mem_bytes)}   DB {mb(p.stats?.db_bytes)}
              </T>
              <Button label="중지" kind="secondary" small icon={Stop} onPress={() => act(p, 'stop')} />
              <Button label="삭제" kind="danger" small icon={Trash} onPress={() => act(p, 'delete')} />
            </View>
            {p.latest_release?.state === 'failed' && p.latest_release.error ? (
              <T variant="small" style={{ color: t.danger }} numberOfLines={2}>v{p.latest_release.version}: {p.latest_release.error}</T>
            ) : null}
          </View>
        ))}
      </View>
      {rows && rows.length === 0 ? <T variant="sub">아직 프로젝트가 없어요. 학번을 등록하면 학생들이 올리기 시작할 수 있어요.</T> : null}
    </Card>
  );
}

function ImportCard() {
  const t = useTheme();
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
    <Card title="학번 등록" icon={FileCsv}>
      <T variant="sub" style={{ marginBottom: 14 }}>
        CSV 한 줄에 한 명씩 email,학번,이름 순서로 적어 주세요. 등록된 학생만 업로드할 수 있어요.
      </T>
      <FilePick icon={FileCsv} label="CSV 파일 올리기" onPress={upload} />
      {error ? <Notice kind="error" text={error} /> : null}
      {result && (
        <>
          <Notice kind={result.errors.length ? 'warn' : 'ok'} text={`추가 ${result.created}명, 갱신 ${result.updated}명${result.errors.length ? `, 오류 ${result.errors.length}건` : ''}`} />
          {result.errors.map((e) => (
            <T key={e.line} variant="small" style={{ color: t.danger }}>{e.line}행: {e.message}</T>
          ))}
        </>
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
  if (!cfg) return <Skeleton h={300} r={16} />;

  const num = (k: keyof Settings) => (v: string) => setCfg({ ...cfg, [k]: Number(v) || 0 });
  const save = async () => {
    try {
      const d = deadline.trim() ? new Date(deadline.replace(' ', 'T')) : null;
      if (d && isNaN(d.getTime())) throw new Error('마감 시각은 2026-12-01 18:00 형식으로 적어 주세요');
      setCfg(await api('/admin/settings', { method: 'PUT', ...json({ ...cfg, upload_deadline: d?.toISOString() ?? null }) }));
      setMsg({ kind: 'ok', text: '저장했어요. 리소스 한도는 다음 배포부터 적용돼요.' });
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    }
  };

  return (
    <Card title="운영 설정" icon={Sliders}>
      <Field label="업로드 마감" value={deadline} onChangeText={setDeadline} placeholder="2026-12-01 18:00" hint="비우면 마감 없음. 마감 후에는 관리자만 올릴 수 있어요." />
      <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 130 }}><Field label="서비스당 메모리 (MB)" value={String(cfg.memory_mb)} onChangeText={num('memory_mb')} /></View>
        <View style={{ flex: 1, minWidth: 130 }}><Field label="스택 합계 (MB)" value={String(cfg.stack_memory_mb)} onChangeText={num('stack_memory_mb')} /></View>
      </View>
      <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 130 }}><Field label="CPU" value={String(cfg.cpus)} onChangeText={(v) => setCfg({ ...cfg, cpus: parseFloat(v) || 0 })} /></View>
        <View style={{ flex: 1, minWidth: 130 }}><Field label="프로세스 수 (PIDs)" value={String(cfg.pids)} onChangeText={num('pids')} /></View>
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
    <Card title="활동 기록" icon={ClipboardText} right={<Button label={open ? '접기' : '펼치기'} kind="ghost" small onPress={() => setOpen(!open)} />}>
      {!open ? (
        <T variant="sub">업로드, 배포, 삭제 같은 작업이 모두 기록돼요.</T>
      ) : (
        <View style={{ gap: 6 }}>
          {rows.map((r, i) => (
            <View key={i} style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
              <T variant="small" style={{ width: 130 }}>{new Date(r.at).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</T>
              <T variant="small" style={{ fontWeight: '700' }}>{r.action}</T>
              <T variant="small">{r.target}</T>
              <T variant="small" style={{ flex: 1 }} numberOfLines={1}>{r.actor ?? '-'}</T>
            </View>
          ))}
        </View>
      )}
    </Card>
  );
}
