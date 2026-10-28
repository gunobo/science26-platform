import * as DocumentPicker from 'expo-document-picker';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Linking, Pressable, Switch, Text, TextInput, useWindowDimensions, View } from 'react-native';
import {
  ArrowClockwise, ArrowCounterClockwise, ArrowsClockwise, Bell, CaretLeft, CaretRight, ClipboardText, Copy, MicrosoftExcelLogo, Student, UserPlus, FileCsv, Key, MagnifyingGlass, PencilSimple, Play, SignIn,
  Sliders, Sparkle, Stop, Trash, UploadSimple, UsersThree,
} from '@phosphor-icons/react';

import { API_BASE, api, json, Project } from '../api';
import { font, radius, useTheme } from '../theme';
import { Badge, Button, Card, ConfirmDialog, Field, FilePick, Icon, Notice, Segmented, Skeleton, T } from '../ui';

type AdminProject = Project & {
  busy?: boolean;
  owner: { email: string; name: string };
  visits?: { total: number; today: number };
  stats: { cpu_percent: number; mem_bytes: number; containers: number; db_bytes?: number } | null;
};
type Settings = { upload_deadline: string | null; memory_mb: number; stack_memory_mb: number; cpus: number; pids: number };

const mb = (b?: number) => (b == null ? '-' : `${Math.round(b / 1024 / 1024)}MB`);

export default function AdminScreen() {
  const { width } = useWindowDimensions();
  const wide = width >= 980;
  return (
    <View>
      <StudentsCard />
      <ProjectsCard />
      <ActivityCard />
      <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 20 : 0, alignItems: 'flex-start' }}>
        <View style={{ flex: 1, minWidth: 0, width: wide ? undefined : '100%' }}>
          <ImportCard />
          <AddStudentCard />
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

type StudentRow = {
  student_no: string;
  grade: string;
  class: string;
  number: string;
  name: string;
  email: string;
  logged_in: boolean;
  is_test: boolean;
  is_admin?: boolean;
  state: 'deployed' | 'building' | 'failed' | 'no_upload' | 'not_logged_in';
  project: { slug: string; title: string; type: string | null; status: string; url: string | null } | null;
};
type StudentFilter = 'all' | 'missing' | 'not_logged_in' | 'deployed';

function StudentsCard() {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const [rows, setRows] = useState<StudentRow[] | null>(null);
  const [error, setError] = useState('');
  const [room, setRoom] = useState('all'); // '1-4' 형식
  const [filter, setFilter] = useState<StudentFilter>('missing');
  const [query, setQuery] = useState('');
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    api<StudentRow[]>('/admin/students').then((r) => { setRows(r); setError(''); }).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [load]);

  // 테스트 계정은 반 통계에 섞이지 않게 따로 묶는다
  const roomOf = (s: StudentRow) => (s.is_test ? 'test' : `${s.grade}-${s.class}`);
  const rooms = useMemo(() => {
    const m = new Map<string, { total: number; done: number }>();
    rows?.forEach((s) => {
      const r = m.get(roomOf(s)) ?? { total: 0, done: 0 };
      r.total += 1;
      if (s.state === 'deployed') r.done += 1;
      m.set(roomOf(s), r);
    });
    // 테스트 묶음은 맨 뒤
    return [...m.entries()].sort(([a], [b]) => (a === 'test' ? 1 : b === 'test' ? -1 : a.localeCompare(b)));
  }, [rows]);

  const inRoom = rows?.filter((s) => (room === 'all' ? !s.is_test : roomOf(s) === room)) ?? [];
  const missing = (s: StudentRow) => s.state !== 'deployed';
  const shown = inRoom.filter((s) => {
    if (filter === 'missing' && !missing(s)) return false;
    if (filter === 'not_logged_in' && s.state !== 'not_logged_in') return false;
    if (filter === 'deployed' && s.state !== 'deployed') return false;
    const q = query.trim().toLowerCase();
    return !q || [s.student_no, s.name, s.email, s.project?.title ?? ''].some((v) => v.toLowerCase().includes(q));
  });
  const done = inRoom.filter((s) => s.state === 'deployed').length;
  const notIn = inRoom.filter((s) => s.state === 'not_logged_in').length;

  // 계정 삭제: 확인 창에서 학번을 입력해야 진행, 지워질 때까지 카드는 스켈레톤
  const [toDelete, setToDelete] = useState<StudentRow | null>(null);
  const [confirmNo, setConfirmNo] = useState('');
  const [deleting, setDeleting] = useState<string[]>([]);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const removeAccount = async () => {
    if (!toDelete) return;
    const no = toDelete.student_no;
    setDeleteBusy(true);
    try {
      await api(`/admin/users/${no}?confirm=${encodeURIComponent(confirmNo.trim())}`, { method: 'DELETE' });
      setDeleting((d) => [...d, no]);
      setToDelete(null);
      setConfirmNo('');
    } catch (e: any) {
      setError(e.message);
      setToDelete(null);
    } finally {
      setDeleteBusy(false);
    }
  };
  useEffect(() => {
    if (!deleting.length) return;
    const still = deleting.filter((no) => rows?.some((r) => r.student_no === no));
    if (still.length !== deleting.length) setDeleting(still);
    if (!still.length) return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [deleting, rows, load]);

  const copyMissing = () => {
    const names = inRoom.filter(missing).map((s) => `${s.student_no} ${s.name}`).join('\n');
    navigator.clipboard?.writeText(names);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const cols = width >= 1100 ? 3 : width >= 720 ? 2 : 1;

  return (
    <Card title="학생 현황" icon={Student} right={<Button label="새로고침" kind="ghost" small icon={ArrowsClockwise} onPress={load} />}>
      {error ? <Notice kind="error" text={error} /> : null}
      {!rows && !error && <Skeleton h={120} />}
      {rows && rows.length === 0 && <T variant="sub">아직 등록된 학생이 없어요. 아래 학번 등록에서 CSV 를 올려 주세요.</T>}
      {rows && rows.length > 0 && (
        <>
          {/* 학반 선택: 반마다 제출 현황을 같이 보여준다 */}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
            <RoomChip label="전체" sub={`${rows.filter((s) => !s.is_test && s.state === 'deployed').length}/${rows.filter((s) => !s.is_test).length}`} active={room === 'all'} onPress={() => setRoom('all')} />
            {rooms.map(([r, c]) => {
              const [g, cl] = r.split('-');
              return <RoomChip key={r} label={r === 'test' ? '테스트 계정' : `${g}학년 ${cl}반`} sub={`${c.done}/${c.total}`} complete={c.done === c.total} active={room === r} onPress={() => setRoom(r)} />;
            })}
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 28, marginBottom: 16 }}>
            <Stat label="학생" value={inRoom.length} />
            <Stat label="제출 완료" value={done} />
            <Stat label="미제출" value={inRoom.length - done} />
            <Stat label="한 번도 접속 안 함" value={notIn} />
          </View>

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
            <Segmented
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'missing', label: '미제출' },
                { value: 'not_logged_in', label: '미접속' },
                { value: 'deployed', label: '제출 완료' },
                { value: 'all', label: '전체' },
              ]}
            />
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: t.borderStrong, borderRadius: radius.control, paddingHorizontal: 12, marginBottom: 16, flex: 1, minWidth: 180, maxWidth: 300 }}>
              <MagnifyingGlass size={17} color={t.textMuted} />
              <TextInput value={query} onChangeText={setQuery} placeholder="이름, 학번" placeholderTextColor={t.textMuted} accessibilityLabel="학생 검색" style={{ flex: 1, fontFamily: font.family, fontSize: 14.5, color: t.text, paddingVertical: 9, outlineStyle: 'none' } as any} />
            </View>
            {inRoom.length - done > 0 && (
              <View style={{ marginBottom: 16 }}>
                <Button label={copied ? '복사됨' : '미제출 명단 복사'} kind="secondary" small icon={Copy} onPress={copyMissing} />
              </View>
            )}
            <View style={{ marginBottom: 16 }}>
              {/* 지금 고른 학반·필터 그대로 내려받는다 (같은 출처 GET 이라 로그인 쿠키가 그대로 쓰인다) */}
              <Button
                label="엑셀로 받기"
                kind="secondary"
                small
                icon={MicrosoftExcelLogo}
                disabled={shown.length === 0}
                onPress={() => window.open(`${API_BASE}/admin/students/export.xlsx?room=${encodeURIComponent(room)}&filter=${filter}`, '_blank')}
              />
            </View>
          </View>

          {shown.length === 0 ? (
            <T variant="sub">{filter === 'missing' ? '이 반은 모두 제출했어요.' : '해당하는 학생이 없어요.'}</T>
          ) : (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -4 }}>
              {shown.map((s) => deleting.includes(s.student_no) ? (
                <View key={s.student_no} style={{ width: `${100 / cols}%`, padding: 4 }}>
                  <View style={{ backgroundColor: t.surfaceAlt, borderRadius: radius.control, padding: 10, gap: 8 }} accessibilityState={{ busy: true }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <T variant="heading" style={{ fontSize: 14.5 }}>{s.student_no}</T>
                      <T style={{ color: t.text }} numberOfLines={1}>{s.name || '-'}</T>
                      <T variant="small" style={{ color: t.danger, fontWeight: '700' }}>삭제하는 중…</T>
                    </View>
                    <Skeleton h={12} w="70%" />
                  </View>
                </View>
              ) : (
                <View key={s.student_no} style={{ width: `${100 / cols}%`, padding: 4 }}>
                  <View style={{ backgroundColor: t.surfaceAlt, borderRadius: radius.control, padding: 10, gap: 4 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <T variant="heading" style={{ fontSize: 14.5 }}>{s.student_no}</T>
                      <T style={{ color: t.text, flex: 1 }} numberOfLines={1}>{s.name || '-'}</T>
                      {s.is_test && <Badge status="test" label="테스트" />}
                      <Badge status={s.state} />
                      {!s.is_admin && (
                        <Pressable
                          onPress={() => { setConfirmNo(''); setToDelete(s); }}
                          accessibilityRole="button"
                          accessibilityLabel={`${s.student_no} ${s.name} 계정 삭제`}
                          style={({ hovered }: any) => ({ padding: 4, borderRadius: 6, backgroundColor: hovered ? t.dangerSoft : 'transparent' })}
                        >
                          <Trash size={15} color={t.textMuted} />
                        </Pressable>
                      )}
                    </View>
                    {s.project?.url ? (
                      <Pressable onPress={() => Linking.openURL(s.project!.url!)}>
                        <T variant="small" numberOfLines={1} style={{ color: t.accent }}>{s.project.title || `/${s.project.slug}`}</T>
                      </Pressable>
                    ) : (
                      <T variant="small" numberOfLines={1}>{s.state === 'not_logged_in' ? s.email : s.project?.title || '올린 프로젝트 없음'}</T>
                    )}
                  </View>
                </View>
              ))}
            </View>
          )}
        </>
      )}
      <ConfirmDialog
        open={!!toDelete}
        title="정말 이 계정을 삭제하시겠어요?"
        confirmLabel="영구 삭제"
        danger
        busy={deleteBusy}
        confirmDisabled={!toDelete || confirmNo.trim() !== toDelete.student_no}
        onConfirm={removeAccount}
        onCancel={() => setToDelete(null)}
      >
        {toDelete && (
          <>
            <T>
              <Text style={{ fontWeight: '800' }}>{toDelete.student_no} {toDelete.name}</Text> ({toDelete.email})
            </T>
            <T variant="sub">계정과 프로젝트, 배포된 페이지, 학생 DB 데이터, 올린 파일, 조회수가 모두 지워지고 되돌릴 수 없어요. 다시 쓰려면 학번을 새로 등록해야 해요.</T>
            <Field
              label={`확인을 위해 학번 ${toDelete.student_no} 을(를) 입력하세요`}
              value={confirmNo}
              onChangeText={setConfirmNo}
              keyboardType="number-pad"
              placeholder={toDelete.student_no}
              autoFocus
            />
            {confirmNo.trim() !== toDelete.student_no && confirmNo.length >= 4 && (
              <T variant="small" style={{ color: t.danger }}>학번이 맞지 않아요</T>
            )}
          </>
        )}
      </ConfirmDialog>
    </Card>
  );
}

function RoomChip({ label, sub, active, complete, onPress }: { label: string; sub: string; active: boolean; complete?: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={({ hovered }: any) => ({
        flexDirection: 'row', alignItems: 'center', gap: 6, height: 34, paddingHorizontal: 12, borderRadius: radius.pill, borderWidth: 1,
        borderColor: active ? t.text : t.borderStrong,
        backgroundColor: active ? t.text : hovered ? t.surfaceAlt : t.surface,
      })}
    >
      <Text style={{ fontFamily: font.family, fontWeight: '700', fontSize: 13.5, color: active ? t.bg : t.text }}>{label}</Text>
      <Text style={{ fontFamily: font.mono, fontSize: 12, color: active ? t.bg : complete ? t.ok : t.textMuted }}>{sub}</Text>
    </Pressable>
  );
}

function ProjectsCard() {
  const t = useTheme();
  const [rows, setRows] = useState<AdminProject[] | null>(null);
  const [disk, setDisk] = useState<{ used: number; total: number; block_ratio: number } | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');

  const load = useCallback(() => {
    api<AdminProject[]>('/admin/projects').then(setRows).catch((e) => setError(e.message));
    api<{ disk: { used: number; total: number; block_ratio: number } }>('/admin/system').then((r) => setDisk(r.disk)).catch(() => {});
  }, []);
  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  // 학번 → 진행 중인 작업. 워커가 실제로 끝낼 때까지 그 행을 스켈레톤으로 막아 연속 클릭을 막는다.
  const [pending, setPending] = useState<Record<string, 'stop' | 'delete'>>({});
  const done = (no: string) => setPending(({ [no]: _, ...rest }) => rest);

  const act = async (p: AdminProject, kind: 'stop' | 'delete') => {
    if (pending[p.student_no]) return;
    if (kind === 'delete' && !window.confirm(`${p.student_no} ${p.owner.name} 학생의 스택, DB, 파일을 모두 삭제할까요? 되돌릴 수 없어요.`)) return;
    setPending((s) => ({ ...s, [p.student_no]: kind }));
    try {
      await api(kind === 'stop' ? `/admin/projects/${p.student_no}/stop` : `/admin/projects/${p.student_no}`, { method: kind === 'stop' ? 'POST' : 'DELETE' });
    } catch (e: any) {
      setError(e.message);
      done(p.student_no);
      return;
    }
    // 끝날 때까지 2초마다 확인 (최대 60초)
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const list = await api<AdminProject[]>('/admin/projects').catch(() => null);
      if (!list) continue;
      setRows(list);
      const now = list.find((x) => x.student_no === p.student_no);
      if (kind === 'delete' ? !now : now?.status !== 'running') break;
    }
    done(p.student_no);
  };

  // 전체 재배포: 확인 창 → 예약 → 잠금이 풀릴 때까지 진행률 표시
  const SECONDS_PER_PROJECT = 20; // 빌드 없이 다시 띄우기 + 헬스체크, 학생 앱에 따라 다름
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [redeploying, setRedeploying] = useState(false);
  const [redeployMsg, setRedeployMsg] = useState<{ text: string; kind: 'ok' | 'warn' | 'error' } | null>(null);
  const [batch, setBatch] = useState<string[] | null>(null); // 이번에 예약한 학번
  const [skipped, setSkipped] = useState<string[]>([]);
  const activeCount = rows?.filter((p) => p.active_release).length ?? 0;
  const minutes = (n: number) => Math.max(1, Math.ceil((n * SECONDS_PER_PROJECT) / 60));

  const redeployAll = async () => {
    setRedeploying(true);
    setRedeployMsg(null);
    try {
      const r = await api<{ queued: string[]; skipped: string[] }>('/admin/projects/redeploy-all', { method: 'POST' });
      // 서버가 잠금을 걸어 둔 상태라, 다음 목록을 받기 전에도 '처리 중'으로 보여 준다 (바로 완료로 오판하지 않게)
      setRows((prev) => prev?.map((p) => (r.queued.includes(p.student_no) ? { ...p, busy: true } : p)) ?? prev);
      setSkipped(r.skipped);
      setBatch(r.queued);
      setConfirmOpen(false);
      load();
    } catch (e: any) {
      setRedeployMsg({ kind: 'error', text: e.message });
      setConfirmOpen(false);
    } finally {
      setRedeploying(false);
    }
  };

  // 진행 중이면 3초마다 갱신, 모두 끝나면 완료 표시
  const remaining = batch ? batch.filter((no) => rows?.find((p) => p.student_no === no)?.busy) : [];
  useEffect(() => {
    if (!batch) return;
    if (rows && remaining.length === 0) {
      setRedeployMsg({
        kind: skipped.length ? 'warn' : 'ok',
        text: `전체 재배포 완료: ${batch.length}개 프로젝트를 다시 띄웠어요.` +
          (skipped.length ? ` 빌드 중이라 건너뛴 프로젝트: ${skipped.join(', ')} (빌드가 끝나면 자동으로 새 설정이 붙어요)` : ''),
      });
      setBatch(null);
      return;
    }
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [batch, rows, remaining.length, load, skipped]);
  const finished = batch ? batch.length - remaining.length : 0;

  const count = (s: string) => rows?.filter((p) => p.status === s).length ?? 0;
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows?.filter((p) => !q || [p.student_no, p.owner.name, p.title, p.slug].some((v) => v?.toLowerCase().includes(q)));
  }, [rows, query]);

  return (
    <Card
      title="전체 프로젝트"
      icon={UsersThree}
      right={
        <View style={{ flexDirection: 'row', gap: 4 }}>
          <Button label="전체 재배포" kind="ghost" small icon={ArrowClockwise} disabled={!!batch || activeCount === 0} onPress={() => setConfirmOpen(true)} />
          <Button label="새로고침" kind="ghost" small icon={ArrowsClockwise} onPress={load} />
        </View>
      }
    >
      <ConfirmDialog
        open={confirmOpen}
        title="정말 전체 재배포하시겠어요?"
        confirmLabel="전체 재배포"
        busy={redeploying}
        onConfirm={redeployAll}
        onCancel={() => setConfirmOpen(false)}
      >
        <T>서비스 중인 프로젝트 <Text style={{ fontWeight: '800' }}>{activeCount}개</Text>를 지금 버전 그대로 하나씩 다시 띄워요.</T>
        <T>예상 시간: <Text style={{ fontWeight: '800' }}>약 {minutes(activeCount)}분</Text> (프로젝트당 약 {SECONDS_PER_PROJECT}초, 학생 앱에 따라 달라요)</T>
        <T variant="sub">빌드는 하지 않고, 새로 뜰 때까지 기존 페이지가 계속 응답해서 학생 페이지는 끊기지 않아요. 지금 빌드 중인 프로젝트는 건너뛰어요.</T>
      </ConfirmDialog>
      {batch && (
        <View style={{ backgroundColor: t.warnSoft, borderRadius: radius.control, padding: 14, gap: 10, marginBottom: 14 }} accessibilityState={{ busy: true }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <T style={{ color: t.text, fontWeight: '700' }}>전체 재배포 중 {finished}/{batch.length}</T>
            <T variant="small">남은 시간 약 {minutes(remaining.length)}분</T>
          </View>
          {skipped.length > 0 && <T variant="small">빌드 중이라 건너뜀: {skipped.join(', ')}</T>}
          <View style={{ height: 6, borderRadius: 3, backgroundColor: t.surface, overflow: 'hidden' }}>
            <View style={[{ height: 6, borderRadius: 3, backgroundColor: t.warn, width: `${batch.length ? (finished / batch.length) * 100 : 0}%` }, { transitionProperty: 'width', transitionDuration: '400ms' } as any]} />
          </View>
        </View>
      )}
      {redeployMsg ? <Notice kind={redeployMsg.kind} text={redeployMsg.text} /> : null}
      {error ? <Notice kind="error" text={error} /> : null}
      {rows && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 28, marginBottom: 20 }}>
          <Stat label="전체" value={rows.length} />
          <Stat label="실행 중" value={count('running')} />
          <Stat label="쉬는 중" value={count('sleeping')} />
          <Stat label="빌드 중" value={count('building')} />
          <Stat label="실패" value={count('failed')} />
          {disk && <Stat label={`디스크 % (${Math.round(disk.block_ratio * 100)}% 넘으면 업로드 중단)`} value={Math.round((disk.used / disk.total) * 100)} />}
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
        {shown?.map((p) => p.busy && batch?.includes(p.student_no) && !pending[p.student_no] ? (
          <View key={p.student_no} style={{ backgroundColor: t.surfaceAlt, borderRadius: radius.control, padding: 12 }} accessibilityState={{ busy: true }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <T variant="heading" style={{ fontSize: 15, width: 44 }}>{p.student_no}</T>
              <T style={{ color: t.text, width: 72 }} numberOfLines={1}>{p.owner.name || '-'}</T>
              <T variant="small" style={{ color: t.warn, fontWeight: '700' }}>재배포 중…</T>
              <View style={{ flex: 1 }}><Skeleton h={14} /></View>
              <Skeleton h={32} w={150} r={radius.control} />
            </View>
          </View>
        ) : pending[p.student_no] ? (
          <View key={p.student_no} style={{ backgroundColor: t.surfaceAlt, borderRadius: radius.control, padding: 12, gap: 8 }} accessibilityState={{ busy: true }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <T variant="heading" style={{ fontSize: 15, width: 44 }}>{p.student_no}</T>
              <T style={{ color: t.text, width: 72 }} numberOfLines={1}>{p.owner.name || '-'}</T>
              <T variant="small" style={{ color: pending[p.student_no] === 'delete' ? t.danger : t.warn, fontWeight: '700' }}>
                {pending[p.student_no] === 'delete' ? '삭제하는 중…' : '중지하는 중…'}
              </T>
              <View style={{ flex: 1 }}><Skeleton h={14} /></View>
              <Skeleton h={32} w={150} r={radius.control} />
            </View>
          </View>
        ) : (
          <View key={p.student_no} style={{ backgroundColor: t.surfaceAlt, borderRadius: radius.control, padding: 12, gap: 6 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <T variant="heading" style={{ fontSize: 15, width: 44 }}>{p.student_no}</T>
              <T style={{ color: t.text, width: 72 }} numberOfLines={1}>{p.owner.name || '-'}</T>
              <Badge status={p.status} />
              <Pressable onPress={() => p.url && Linking.openURL(p.url)} style={{ flex: 1, minWidth: 140 }}>
                <T variant="sub" numberOfLines={1} style={{ color: t.accent }}>/{p.slug}  {p.title}</T>
              </Pressable>
              <T variant="small" style={{ fontFamily: font.mono }}>
                조회 {p.visits?.total ?? 0}(오늘 {p.visits?.today ?? 0})   CPU {p.stats ? `${p.stats.cpu_percent.toFixed(1)}%` : '-'}   MEM {mb(p.stats?.mem_bytes)}   DB {mb(p.stats?.db_bytes)}
              </T>
              <Button label="중지" kind="secondary" small icon={Stop} disabled={p.status !== 'running' && p.status !== 'sleeping'} onPress={() => act(p, 'stop')} />
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

function AddStudentCard() {
  const t = useTheme();
  const [email, setEmail] = useState('');
  const [no, setNo] = useState('');
  const [name, setName] = useState('');
  const [isTest, setIsTest] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; kind: 'ok' | 'error' } | null>(null);

  const add = async () => {
    setBusy(true);
    setMsg(null);
    try {
      await api('/admin/users', { method: 'POST', ...json({ email, student_no: no, name, is_test: isTest }) });
      setMsg({ kind: 'ok', text: `${no} ${name || email} 추가했어요.${isTest ? ' 이 구글 계정으로 학생 화면에 로그인할 수 있어요.' : ''}` });
      setEmail('');
      setNo('');
      setName('');
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="학생 한 명 추가" icon={UserPlus}>
      <T variant="sub" style={{ marginBottom: 14 }}>
        테스트 계정은 학교 계정이 아닌 구글 계정(개인 Gmail 등)도 학생으로 로그인할 수 있어요. 학생 현황에서는 반 통계와 따로 보여요.
      </T>
      <Field label="구글 계정 이메일" value={email} onChangeText={setEmail} autoCapitalize="none" placeholder="tester@gmail.com" />
      <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
        <View style={{ flex: 1, minWidth: 110 }}>
          <Field label="학번 (4자리)" value={no} onChangeText={(v) => setNo(v.replace(/\D/g, '').slice(0, 4))} placeholder="9901" keyboardType="number-pad" />
        </View>
        <View style={{ flex: 2, minWidth: 140 }}>
          <Field label="이름" value={name} onChangeText={setName} placeholder="테스트 학생" />
        </View>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
        <Switch value={isTest} onValueChange={setIsTest} trackColor={{ true: t.accent, false: t.borderStrong }} />
        <T style={{ color: t.text }}>테스트 계정</T>
        <T variant="small">끄면 일반 학생처럼 학교 계정만 로그인할 수 있어요</T>
      </View>
      {msg && <Notice kind={msg.kind} text={msg.text} />}
      <Button label="추가" icon={UserPlus} busy={busy} disabled={!email.includes('@') || no.length !== 4} onPress={add} />
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

type Activity = {
  at: string;
  action: string;
  target: string;
  detail: string;
  actor: string | null;
  actor_name: string | null;
  actor_student_no: string | null;
};

type Kind = 'all' | 'login' | 'project' | 'admin';
const ACTIONS: Record<string, { label: string; kind: Exclude<Kind, 'all'>; icon: Icon }> = {
  first_login: { label: '첫 접속', kind: 'login', icon: SignIn },
  register: { label: '프로젝트 등록', kind: 'project', icon: Sparkle },
  upload: { label: '새 버전 업로드', kind: 'project', icon: UploadSimple },
  update_info: { label: '정보 수정', kind: 'project', icon: PencilSimple },
  rollback: { label: '롤백', kind: 'project', icon: ArrowCounterClockwise },
  slug: { label: '링크 이름 변경 재배포', kind: 'project', icon: PencilSimple },
  env: { label: '환경변수 변경', kind: 'project', icon: Key },
  stop: { label: '중지', kind: 'project', icon: Stop },
  start: { label: '다시 시작', kind: 'project', icon: Play },
  self_delete: { label: '프로젝트 삭제', kind: 'project', icon: Trash },
  admin_stop: { label: '관리자 중지', kind: 'admin', icon: Stop },
  delete: { label: '관리자 삭제', kind: 'admin', icon: Trash },
  import_users: { label: '학번 등록', kind: 'admin', icon: FileCsv },
  settings: { label: '운영 설정 변경', kind: 'admin', icon: Sliders },
  redeploy_all: { label: '전체 재배포', kind: 'admin', icon: ArrowClockwise },
  add_user: { label: '학생 추가', kind: 'admin', icon: UserPlus },
  add_test_user: { label: '테스트 계정 추가', kind: 'admin', icon: UserPlus },
  delete_test_user: { label: '테스트 계정 삭제', kind: 'admin', icon: Trash },
  delete_user: { label: '학생 계정 삭제', kind: 'admin', icon: Trash },
};

function ago(iso: string) {
  const sec = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 60) return '방금';
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`;
  return new Date(iso).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

type ActivityPage = { items: Activity[]; total: number; page: number; size: number; today: Record<string, number> };
const PAGE_SIZE = 20;

function ActivityCard() {
  const t = useTheme();
  const [data, setData] = useState<ActivityPage | null>(null);
  const [kind, setKind] = useState<Kind>('all');
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api<ActivityPage>(`/admin/audit-logs?page=${page}&size=${PAGE_SIZE}&kind=${kind}`)
      .then((r) => { setData(r); setError(''); })
      .catch((e) => setError(e.message));
  }, [page, kind]);
  useEffect(() => {
    load();
    // 새 활동은 첫 페이지에만 들어오므로 첫 페이지일 때만 자동 새로고침 (뒤 페이지는 보는 중에 밀리지 않게)
    if (page !== 1) return;
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [load, page]);

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const changeKind = (k: Kind) => { setKind(k); setPage(1); };

  return (
    <Card title="최근 활동" icon={Bell} right={<Button label="새로고침" kind="ghost" small icon={ArrowsClockwise} onPress={load} />}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 28, marginBottom: 16 }}>
        <Stat label="오늘 첫 접속" value={data?.today.first_login ?? 0} />
        <Stat label="오늘 프로젝트 등록" value={data?.today.register ?? 0} />
        <Stat label="오늘 업로드" value={data?.today.upload ?? 0} />
        <Stat label="오늘 정보 수정" value={data?.today.update_info ?? 0} />
      </View>
      <Segmented
        value={kind}
        onChange={changeKind}
        options={[
          { value: 'all', label: '전체' },
          { value: 'login', label: '접속' },
          { value: 'project', label: '프로젝트' },
          { value: 'admin', label: '관리자' },
        ]}
      />
      {error ? <Notice kind="error" text={error} /> : null}
      {!data && !error && <Skeleton h={160} />}
      {data && data.items.length === 0 && <T variant="sub">아직 기록이 없어요.</T>}
      <View style={{ gap: 2 }}>
        {data?.items.map((r, i) => {
          const a = ACTIONS[r.action] ?? { label: r.action, kind: 'admin' as const, icon: ClipboardText };
          const I = a.icon;
          const highlight = r.action === 'first_login' || r.action === 'register';
          return (
            <View key={`${r.at}-${i}`} style={{ flexDirection: 'row', gap: 12, paddingVertical: 10, borderTopWidth: i ? 1 : 0, borderTopColor: t.border }}>
              <View style={{ width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: highlight ? t.accentSoft : t.surfaceAlt }}>
                <I size={17} color={highlight ? t.accent : t.textMuted} weight="bold" />
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <T style={{ color: t.text, fontWeight: '700' }}>{a.label}</T>
                  <T variant="sub" numberOfLines={1}>
                    {r.actor_name || r.actor || '알 수 없음'}{r.actor_student_no ? ` ${r.actor_student_no}` : ''}
                  </T>
                  <View style={{ flex: 1 }} />
                  <T variant="small">{ago(r.at)}</T>
                </View>
                {r.detail ? (
                  <T variant="small" numberOfLines={2} style={{ marginTop: 2 }}>{r.detail.split(' | ').join('  ·  ')}</T>
                ) : r.target && r.action !== 'first_login' ? (
                  <T variant="small" style={{ marginTop: 2 }}>{r.target}</T>
                ) : null}
              </View>
            </View>
          );
        })}
      </View>
      {data && data.total > PAGE_SIZE && (
        <Pager page={page} pages={pages} total={data.total} onChange={setPage} />
      )}
    </Card>
  );
}

function Pager({ page, pages, total, onChange }: { page: number; pages: number; total: number; onChange: (p: number) => void }) {
  const t = useTheme();
  // 현재 페이지 주변 5개 + 처음·끝
  const nums = Array.from(new Set([1, ...Array.from({ length: 5 }, (_, i) => page - 2 + i), pages]))
    .filter((n) => n >= 1 && n <= pages)
    .sort((a, b) => a - b);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: t.border }}>
      <T variant="small">전체 {total}건 · {page}/{pages} 페이지</T>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
        <Button label="이전" kind="ghost" small icon={CaretLeft} disabled={page <= 1} onPress={() => onChange(page - 1)} />
        {nums.map((n, i) => (
          <View key={n} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            {i > 0 && n - nums[i - 1] > 1 && <T variant="small">…</T>}
            <Pressable
              onPress={() => onChange(n)}
              accessibilityRole="button"
              accessibilityLabel={`${n} 페이지`}
              style={({ hovered }: any) => ({
                minWidth: 32, height: 32, borderRadius: radius.control, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6,
                backgroundColor: n === page ? t.accent : hovered ? t.surfaceAlt : 'transparent',
              })}
            >
              <Text style={{ fontFamily: font.family, fontSize: 13.5, fontWeight: '700', color: n === page ? t.accentText : t.textSub }}>{n}</Text>
            </Pressable>
          </View>
        ))}
        <Button label="다음" kind="ghost" small icon={CaretRight} disabled={page >= pages} onPress={() => onChange(page + 1)} />
      </View>
    </View>
  );
}
