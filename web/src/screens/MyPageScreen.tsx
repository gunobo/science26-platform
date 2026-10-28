import { useCallback, useEffect, useState } from 'react';
import { Switch, useWindowDimensions, View } from 'react-native';
import { Eye, IdentificationCard, Trash, WarningOctagon } from '@phosphor-icons/react';

import { api, Me, Project } from '../api';
import { useTheme } from '../theme';
import { Button, Card, Field, Notice, Skeleton, T } from '../ui';
import { SettingsCard } from './DashboardScreen';
import { ProjectCard } from './PublicListScreen';

export default function MyPageScreen({ me, onDeleted }: { me: Me; onDeleted: () => void }) {
  const { width } = useWindowDimensions();
  const wide = width >= 980;
  const [project, setProject] = useState<Project | null>(null);

  const refresh = useCallback(async () => setProject(await api<Project>('/projects/me')), []);
  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!project)
    return (
      <View style={{ gap: 16 }}>
        <Skeleton h={120} r={16} />
        <Skeleton h={320} r={16} />
      </View>
    );

  const exists = project.status !== 'empty' || project.latest_release !== null;

  return (
    <View>
      <T variant="title" style={{ marginBottom: 20 }}>마이페이지</T>
      <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 20 : 0, alignItems: 'flex-start' }}>
        <View style={{ flex: 1, minWidth: 0, width: wide ? undefined : '100%' }}>
          <ProfileCard me={me} />
          <PreviewCard me={me} project={project} onChange={refresh} />
        </View>
        <View style={{ flex: 1.3, minWidth: 0, width: wide ? undefined : '100%' }}>
          <SettingsCard project={project} onChange={refresh} />
          {exists && <DeleteCard project={project} onDeleted={onDeleted} />}
        </View>
      </View>
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', gap: 12, paddingVertical: 9, borderTopWidth: 1, borderTopColor: t.border }}>
      <T variant="sub" style={{ width: 64 }}>{label}</T>
      <T style={{ flex: 1, color: t.text }} numberOfLines={1}>{value}</T>
    </View>
  );
}

function ProfileCard({ me }: { me: Me }) {
  return (
    <Card title="내 정보" icon={IdentificationCard}>
      <View style={{ marginTop: -9 }}>
        <Row label="이름" value={me.name || '-'} />
        <Row label="이메일" value={me.email} />
        <Row label="학번" value={me.student_no ?? '등록 전'} />
        <Row label="권한" value={me.role === 'admin' ? '관리자' : '학생'} />
      </View>
      <T variant="small" style={{ marginTop: 10 }}>이름과 학번은 선생님이 등록한 정보예요. 틀렸으면 선생님께 알려 주세요.</T>
    </Card>
  );
}

function PreviewCard({ me, project, onChange }: { me: Me; project: Project; onChange: () => void }) {
  const t = useTheme();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const live = !!project.active_release;

  const toggle = async (listed: boolean) => {
    setBusy(true);
    setError('');
    const fd = new FormData();
    fd.append('listed', String(listed));
    try {
      await api('/projects/me', { method: 'PATCH', body: fd });
      onChange();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="전시관에 보이는 모습" icon={Eye}>
      {live ? (
        <View style={{ marginHorizontal: -10, opacity: project.listed ? 1 : 0.45 }}>
          <ProjectCard
            width="100%"
            p={{
              student_no: project.student_no,
              slug: project.slug,
              name: me.name,
              title: project.title || `${project.student_no} 프로젝트`,
              description: project.description,
              type: project.type ?? 'static',
              status: project.status,
              thumbnail_url: project.thumbnail_url,
              url: project.url ?? '',
              views: project.visits?.total,
            }}
          />
        </View>
      ) : (
        <T variant="sub">배포에 성공하면 전시관에 카드가 생겨요.</T>
      )}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 16, paddingTop: 14, borderTopWidth: 1, borderTopColor: t.border }}>
        <View style={{ flex: 1 }}>
          <T style={{ color: t.text, fontWeight: '600' }}>전시관에 공개</T>
          <T variant="small">끄면 목록에서만 사라지고, 링크를 아는 사람은 계속 볼 수 있어요.</T>
        </View>
        <Switch value={project.listed} disabled={busy} onValueChange={toggle} trackColor={{ true: t.accent, false: t.borderStrong }} />
      </View>
      {error ? <View style={{ marginTop: 12 }}><Notice kind="error" text={error} /></View> : null}
    </Card>
  );
}

function DeleteCard({ project, onDeleted }: { project: Project; onDeleted: () => void }) {
  const t = useTheme();
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const remove = async () => {
    setBusy(true);
    setError('');
    try {
      await api('/projects/me', { method: 'DELETE' });
      // 워커가 스택과 DB 를 지우는 데 몇 초 걸린다
      setTimeout(onDeleted, 3000);
    } catch (e: any) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <Card title="프로젝트 삭제" icon={WarningOctagon} style={{ borderColor: t.dark ? '#5a2323' : '#f3c6c2' }}>
      <T variant="sub" style={{ marginBottom: 14 }}>
        배포된 페이지, 배포 기록, 올린 파일, 프로젝트 DB 데이터가 모두 지워지고 되돌릴 수 없어요. 지운 뒤 다시 올리면 새 프로젝트로 시작해요.
      </T>
      {!open ? (
        <Button label="삭제하기" kind="danger" icon={Trash} onPress={() => setOpen(true)} />
      ) : (
        <>
          <Field
            label={`확인을 위해 링크 이름 "${project.slug}" 을(를) 입력하세요`}
            value={confirm}
            onChangeText={setConfirm}
            autoCapitalize="none"
            placeholder={project.slug}
          />
          {error ? <Notice kind="error" text={error} /> : null}
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <Button label="영구 삭제" kind="danger" icon={Trash} busy={busy} disabled={confirm.trim() !== project.slug} onPress={remove} />
            <Button label="취소" kind="ghost" onPress={() => { setOpen(false); setConfirm(''); }} />
          </View>
        </>
      )}
    </Card>
  );
}
