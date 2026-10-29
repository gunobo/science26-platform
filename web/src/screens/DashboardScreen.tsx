import * as DocumentPicker from 'expo-document-picker';
import { ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { Linking, Pressable, ScrollView, Switch, Text, useWindowDimensions, View } from 'react-native';
import {
  AndroidLogo, ArrowCounterClockwise, Eye, ArrowUpRight, Browser, ClockCounterClockwise, Copy, DeviceMobile, FileZip, FilmStrip, GearSix,
  GithubLogo, Image as ImageIcon, Key, PencilSimple, Play, Plug, Plus, Robot, Warning as WarningIcon, Stack, Stop, Terminal, Trash, UploadSimple,
} from '@phosphor-icons/react';

import { API_BASE, api, ApiError, json, Project, ProjectType, PUBLIC_HOST, Release, UPLOAD_HOST, Warning } from '../api';
import { font, radius, useTheme } from '../theme';
import { Badge, Button, Card, ConfirmDialog, Field, FilePick, Notice, Segmented, Skeleton, T } from '../ui';

const BUSY_STATES = ['queued', 'validating', 'building', 'deploying'];

async function pick(types: string[], multiple = false): Promise<File[]> {
  const res = await DocumentPicker.getDocumentAsync({ type: types, multiple, copyToCacheDirectory: false });
  if (res.canceled) return [];
  return res.assets.map((a) => a.file).filter((f): f is File => !!f);
}

export default function DashboardScreen({ onEditInfo }: { onEditInfo: () => void }) {
  const { width } = useWindowDimensions();
  const wide = width >= 980;
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

  if (!project)
    return (
      <View style={{ gap: 16 }}>
        <Skeleton h={120} r={16} />
        <Skeleton h={320} r={16} />
      </View>
    );
  const busy = releases.some((r) => BUSY_STATES.includes(r.state));

  const main = (
    <>
      <AiHelpCard slug={project.slug} />
      <UploadCard disabled={busy} onUploaded={(id) => { setWatching(id); refresh(); }} />
      {watching && <BuildLogCard releaseId={watching} onDone={refresh} />}
      {project.active_release && <RuntimeCard project={project} onChange={refresh} />}
    </>
  );
  const side = (
    <>
      <ReleasesCard releases={releases} activeId={project.active_release?.id} busy={busy} onWatch={setWatching} onChange={refresh} />
      {project.type === 'fullstack' && <EnvCard />}
      <McpCard />
    </>
  );

  return (
    <View>
      <Hero project={project} onEditInfo={onEditInfo} />
      {wide ? (
        <View style={{ flexDirection: 'row', gap: 20, alignItems: 'flex-start' }}>
          <View style={{ flex: 1.55, minWidth: 0 }}>{main}</View>
          <View style={{ flex: 1, minWidth: 0 }}>{side}</View>
        </View>
      ) : (
        <View>
          {main}
          {side}
        </View>
      )}
    </View>
  );
}

// ---- 상단: 내 프로젝트 요약 ----

function Hero({ project, onEditInfo }: { project: Project; onEditInfo: () => void }) {
  const t = useTheme();
  const live = project.url && project.active_release;
  const [copied, setCopied] = useState(false);
  return (
    <View style={{ marginBottom: 24, gap: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <T variant="title">{project.title || '내 프로젝트'}</T>
        <Badge status={project.status} />
        {!project.listed && project.active_release && <Badge status="empty" label="전시관에서 숨김" />}
        {project.active_release && project.visits && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }} accessibilityLabel={`조회수 ${project.visits.total}, 오늘 ${project.visits.today}`}>
            <Eye size={16} color={t.textMuted} weight="bold" />
            <T variant="sub">조회수 {project.visits.total.toLocaleString('ko-KR')} · 오늘 {project.visits.today.toLocaleString('ko-KR')}</T>
          </View>
        )}
        <Button label="정보 수정" kind="ghost" small icon={PencilSimple} onPress={onEditInfo} />
      </View>
      {live ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Pressable onPress={() => Linking.openURL(project.url!)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Text style={{ fontFamily: font.family, color: t.accent, fontSize: 16, fontWeight: '600' }}>{project.url!.replace('https://', '')}</Text>
            <ArrowUpRight size={16} color={t.accent} weight="bold" />
          </Pressable>
          <Button
            label={copied ? '복사됨' : '주소 복사'}
            kind="ghost"
            small
            icon={Copy}
            onPress={() => {
              navigator.clipboard?.writeText(project.url!);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          />
        </View>
      ) : (
        <T>아직 배포된 버전이 없어요. 아래에서 결과물을 올리면 몇십 초 안에 내 페이지가 생겨요.</T>
      )}
    </View>
  );
}

// ---- AI 코딩 도구로 배포 준비 ----

type AiType = 'auto' | ProjectType;
const AI_TYPE_TEXT: Record<AiType, string> = {
  auto: '어떤 타입(정적 웹, 풀스택, 앱)이 맞는지 먼저 골라 주고',
  static: '정적 웹 타입으로',
  fullstack: '풀스택(docker compose) 타입으로',
  app: '모바일 앱 타입으로 (Android 는 APK, iPhone 은 TestFlight 링크나 시연 영상)',
};

function AiHelpCard({ slug }: { slug: string }) {
  const t = useTheme();
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<AiType>('auto');
  const base = `https://${PUBLIC_HOST}/ai`;
  const download = `curl -fsSLO ${base}/AGENTS.md && curl -fsSLO ${base}/CLAUDE.md`;
  const prompt =
    `이 프로젝트를 science26 에 배포하려고 해. AGENTS.md 의 규칙을 꼼꼼히 읽고 ${AI_TYPE_TEXT[type]} 배포할 수 있게 고쳐 줘. ` +
    `내 링크 이름은 ${slug} 이고 주소는 https://${PUBLIC_HOST}/students/${slug}/ 야. ` +
    `필요하면 빌드까지 해서 올릴 zip 을 만들어 주고, 끝나면 AGENTS.md 마지막 항목대로 무엇을 어떻게 올리면 되는지 알려 줘.`;

  return (
    <Card
      title="AI로 배포 준비하기"
      icon={Robot}
      right={<Button label={open ? '접기' : '펼치기'} kind="ghost" small onPress={() => setOpen(!open)} />}
    >
      <T variant="sub" style={{ marginBottom: open ? 16 : 0 }}>
        Codex 나 Claude Code 에게 science26 규칙을 알려주면 경로 설정, docker-compose 작성까지 알아서 맞춰 줘요.
      </T>
      {open && (
        <View style={{ gap: 4 }}>
          <Step n={1} title="프로젝트 폴더에서 규칙 파일 받기">
            <CopyBox text={download} />
            <T variant="small">
              Codex 는 AGENTS.md, Claude Code 는 CLAUDE.md 를 자동으로 읽어요. Windows PowerShell 에서는 curl 대신 curl.exe 로 쓰세요.{' '}
              <Text style={{ color: t.accent, fontWeight: '600' }} onPress={() => window.open(`${base}/AGENTS.md`, '_blank')}>
                규칙 내용 보기
              </Text>
            </T>
          </Step>
          <Step n={2} title="AI 에게 이렇게 말하기">
            <Segmented
              value={type}
              onChange={setType}
              options={[
                { value: 'auto', label: 'AI가 고르기' },
                { value: 'static', label: '정적 웹' },
                { value: 'fullstack', label: '풀스택' },
                { value: 'app', label: '앱' },
              ]}
            />
            <CopyBox text={prompt} wrap />
          </Step>
          <Step n={3} title="AI 가 알려준 파일이나 저장소를 아래에서 올리기" last>
            <T variant="small">API 키 같은 비밀값은 AI 에게 주지 말고, 배포 후 환경변수 칸에 직접 넣으세요.</T>
          </Step>
        </View>
      )}
    </Card>
  );
}

// ---- AI 코딩 도구에서 바로 배포 (MCP) ----

type DeployToken = { id: string; name: string; prefix: string; created_at: string; expires_at: string; last_used_at: string | null };
const MCP_URL = `https://${UPLOAD_HOST}/api/mcp`;
const day = (iso: string) => new Date(iso).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' });

function McpCard() {
  const t = useTheme();
  const [tokens, setTokens] = useState<DeployToken[] | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [revoke, setRevoke] = useState<DeployToken | null>(null);

  const load = useCallback(() => {
    api<DeployToken[]>('/projects/me/tokens').then(setTokens).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  const create = async () => {
    setBusy(true);
    setError('');
    try {
      const r = await api<DeployToken & { token: string }>('/projects/me/tokens', { method: 'POST', ...json({ name: 'AI 연결' }) });
      setCreated(r.token);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!revoke) return;
    setBusy(true);
    try {
      await api(`/projects/me/tokens/${revoke.id}`, { method: 'DELETE' });
      setRevoke(null);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const claude = `claude mcp add --transport http science26 ${MCP_URL} --header "Authorization: Bearer ${created ?? 'TOKEN'}"`;
  const jsonCfg = JSON.stringify({ mcpServers: { science26: { url: MCP_URL, headers: { Authorization: `Bearer ${created ?? 'TOKEN'}` } } } }, null, 2);

  return (
    <Card title="AI에서 바로 배포 (MCP)" icon={Plug}>
      <T variant="sub" style={{ marginBottom: 14 }}>
        Claude Code, Cursor 같은 AI 도구에 연결하면 "science26 에 배포해줘" 한마디로 빌드, 업로드, 실패 로그 확인까지 해요. 이 토큰은 내 프로젝트에만 쓸 수 있어요.
      </T>
      {error ? <Notice kind="error" text={error} /> : null}

      {created ? (
        <View style={{ gap: 10, marginBottom: 14 }}>
          <Notice kind="warn" icon={WarningIcon} text="토큰은 지금 한 번만 보여요. 다른 사람에게 보여 주거나 GitHub 에 올리면 그 사람이 내 프로젝트를 바꿀 수 있어요. 새어 나갔으면 바로 지우세요." />
          <T style={{ fontWeight: '700', color: t.text }}>Claude Code: 프로젝트 폴더 터미널에서</T>
          <CopyBox text={claude} wrap />
          <T style={{ fontWeight: '700', color: t.text }}>Cursor 등: 내 컴퓨터 전체 설정 (~/.cursor/mcp.json)</T>
          <CopyBox text={jsonCfg} wrap />
          <T variant="small">
            프로젝트 폴더 안 설정 파일(.mcp.json, .cursor/mcp.json)에 넣으면 git 으로 같이 올라갈 수 있어요. 위처럼 내 컴퓨터 설정에만 넣으세요. 연결한 뒤 AI 에게 "science26 에 배포해줘" 라고 말하면 돼요.
          </T>
          <View style={{ alignSelf: 'flex-start' }}>
            <Button label="다 적었어요" kind="secondary" small onPress={() => setCreated(null)} />
          </View>
        </View>
      ) : null}

      {!tokens && !error && <Skeleton h={48} />}
      {tokens?.map((tk) => (
        <View key={tk.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderTopWidth: 1, borderTopColor: t.border }}>
          <Key size={17} color={t.textMuted} />
          <View style={{ flex: 1 }}>
            <T variant="mono" style={{ color: t.text }}>{tk.prefix}…</T>
            <T variant="small">
              {day(tk.expires_at)}까지 · {tk.last_used_at ? `마지막 사용 ${day(tk.last_used_at)}` : '아직 안 씀'}
            </T>
          </View>
          <Button label="지우기" kind="ghost" small icon={Trash} onPress={() => setRevoke(tk)} />
        </View>
      ))}
      <View style={{ alignSelf: 'flex-start', marginTop: 10 }}>
        <Button label="토큰 만들기" icon={Plus} small busy={busy} disabled={(tokens?.length ?? 0) >= 3} onPress={create} />
      </View>
      {tokens && tokens.length >= 3 && <T variant="small" style={{ marginTop: 6 }}>토큰은 3개까지예요. 안 쓰는 토큰을 지워 주세요.</T>}
      <T variant="small" style={{ marginTop: 10 }}>토큰은 30일 뒤 만료돼요. 모바일 앱(APK)은 여기서 올려야 해요.</T>

      <ConfirmDialog
        open={!!revoke}
        title="이 토큰을 지울까요?"
        confirmLabel="지우기"
        danger
        busy={busy}
        onConfirm={remove}
        onCancel={() => setRevoke(null)}
      >
        <T>{revoke?.prefix}… 토큰으로 연결한 AI 도구는 바로 배포할 수 없게 돼요.</T>
      </ConfirmDialog>
    </Card>
  );
}

function Step({ n, title, children, last }: { n: number; title: string; children: ReactNode; last?: boolean }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', gap: 12 }}>
      <View style={{ alignItems: 'center' }}>
        <View style={{ width: 26, height: 26, borderRadius: 13, backgroundColor: t.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ fontFamily: font.family, fontWeight: '800', fontSize: 13, color: t.accent }}>{n}</Text>
        </View>
        {!last && <View style={{ width: 2, flex: 1, backgroundColor: t.border, marginVertical: 4 }} />}
      </View>
      <View style={{ flex: 1, minWidth: 0, paddingBottom: last ? 0 : 18, gap: 8 }}>
        <T variant="heading" style={{ fontSize: 15, marginTop: 2 }}>{title}</T>
        {children}
      </View>
    </View>
  );
}

function CopyBox({ text, wrap }: { text: string; wrap?: boolean }) {
  const t = useTheme();
  const [copied, setCopied] = useState(false);
  return (
    <View style={{ backgroundColor: t.logBg, borderRadius: radius.control, padding: 12, gap: 10 }}>
      <T variant="mono" numberOfLines={wrap ? undefined : 1} style={{ color: t.logText }}>{text}</T>
      <View style={{ alignSelf: 'flex-end' }}>
        <Button
          label={copied ? '복사됨' : '복사'}
          kind="secondary"
          small
          icon={Copy}
          onPress={() => {
            navigator.clipboard?.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        />
      </View>
    </View>
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
  const [video, setVideo] = useState<File | null>(null);
  const [testflight, setTestflight] = useState('');
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
        if (!appTitle.trim()) throw new Error('앱 이름을 입력하세요');
        if (!apk && !video && !testflight.trim()) throw new Error('APK, TestFlight 링크, 시연 영상 중 하나 이상을 넣어 주세요');
        if (shots.length === 0) throw new Error('스크린샷을 1장 이상 골라 주세요');
        fd.append('title', appTitle);
        fd.append('description', appDesc);
        fd.append('testflight_url', testflight.trim());
        if (apk) fd.append('apk', apk);
        if (video) fd.append('video', video);
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
      setVideo(null);
      setShots([]);
      onUploaded(res.release_id);
    } catch (e: any) {
      setError(e instanceof ApiError && e.code === 'COMPOSE_FORBIDDEN_KEY' ? `compose 규칙 위반: ${e.message}` : e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="새 버전 올리기" icon={UploadSimple}>
      <Segmented
        value={type}
        onChange={setType}
        options={[
          { value: 'static', label: '정적 웹', icon: Browser },
          { value: 'fullstack', label: '풀스택', icon: Stack },
          { value: 'app', label: '모바일 앱', icon: DeviceMobile },
        ]}
      />
      {type === 'static' && (
        <>
          <FilePick icon={FileZip} label="빌드 결과 zip 또는 index.html (최대 100MB)" file={file?.name} onPress={async () => setFile((await pick(['application/zip', '.zip', 'text/html', '.html']))[0] ?? null)} />
          <Hint>
            페이지는 <Code>/students/링크이름/</Code> 아래에서 열려요. 에셋 경로는 상대경로여야 해서 Vite는 <Code>base: './'</Code>, Expo는 <Code>experiments.baseUrl</Code> 을 설정하세요.
          </Hint>
        </>
      )}
      {type === 'fullstack' && (
        <>
          <Segmented
            value={source}
            onChange={setSource}
            options={[
              { value: 'file', label: 'zip 업로드', icon: FileZip },
              { value: 'git', label: 'GitHub 저장소', icon: GithubLogo },
            ]}
          />
          {source === 'file' ? (
            <FilePick icon={FileZip} label="프로젝트 zip (최대 200MB)" file={file?.name} onPress={async () => setFile((await pick(['application/zip', '.zip']))[0] ?? null)} />
          ) : (
            <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
              <View style={{ flex: 3, minWidth: 220 }}>
                <Field label="저장소 주소" value={repo} onChangeText={setRepo} autoCapitalize="none" placeholder="https://github.com/아이디/저장소" />
              </View>
              <View style={{ flex: 1, minWidth: 120 }}>
                <Field label="브랜치" value={branch} onChangeText={setBranch} autoCapitalize="none" />
              </View>
            </View>
          )}
          <Hint>
            루트에 <Code>docker-compose.yml</Code> 이 필요해요. 공개할 서비스에 <Code>science26.public=true</Code>, API 서비스에는 <Code>science26.api=true</Code> 라벨을 붙이세요. DB와 Redis는 넣지 말고 자동으로 들어가는 <Code>DATABASE_URL</Code>, <Code>REDIS_URL</Code> 을 쓰면 돼요.
          </Hint>
        </>
      )}
      {type === 'app' && (
        <>
          <Hint>
            아래 셋 중 <Text style={{ fontWeight: '700' }}>하나 이상</Text>을 넣으면 소개 페이지가 만들어지고, 설치 버튼과 QR 코드가 자동으로 붙어요.
            iPhone 용 앱은 직접 설치 파일을 받을 수 없어서 TestFlight 링크나 시연 영상을 써요. React Native·Flutter 앱이면 웹으로 빌드해 정적 웹으로 올리는 방법도 있어요.
          </Hint>
          <View style={{ flexDirection: 'row', gap: 12, flexWrap: 'wrap' }}>
            <View style={{ flex: 1, minWidth: 220 }}>
              <FilePick icon={AndroidLogo} label="Android: 서명된 APK (선택, 150MB)" file={apk?.name} onPress={async () => setApk((await pick(['application/vnd.android.package-archive', '.apk']))[0] ?? null)} />
            </View>
            <View style={{ flex: 1, minWidth: 220 }}>
              <FilePick icon={FilmStrip} label="시연 영상 (선택, mp4·webm·mov 100MB)" file={video?.name} onPress={async () => setVideo((await pick(['video/mp4', 'video/webm', 'video/quicktime', '.mp4', '.webm', '.mov']))[0] ?? null)} />
            </View>
          </View>
          <Field label="iPhone: TestFlight 공개 링크 (선택)" value={testflight} onChangeText={setTestflight} autoCapitalize="none" placeholder="https://testflight.apple.com/join/..." />
          <FilePick icon={ImageIcon} label="스크린샷 1~5장 (필수)" file={shots.length ? `스크린샷 ${shots.length}장` : null} onPress={async () => setShots((await pick(['image/*'], true)).slice(0, 5))} />
          <Field label="앱 이름" value={appTitle} onChangeText={setAppTitle} />
          <Field label="설명" value={appDesc} onChangeText={setAppDesc} multiline hint="소개 페이지에 그대로 보여요." />
        </>
      )}
      {error ? <Notice kind="error" text={error} /> : null}
      {warnings.map((w, i) => (
        <Notice key={i} kind="warn" text={`${w.message}${w.paths?.length ? `\n발견된 경로: ${w.paths.join(', ')}` : ''}`} />
      ))}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 4 }}>
        <Button label="올리고 배포하기" icon={UploadSimple} onPress={submit} busy={busy} disabled={disabled} />
        {disabled && <T variant="small">지금 빌드가 진행 중이에요. 끝나면 다시 올릴 수 있어요.</T>}
      </View>
    </Card>
  );
}

function Hint({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text style={{ fontFamily: font.family, fontSize: 13.5, lineHeight: 21, color: t.textMuted, marginBottom: 16 }}>{children}</Text>;
}

function Code({ children }: { children: ReactNode }) {
  const t = useTheme();
  return <Text style={{ fontFamily: font.mono, fontSize: 12.5, color: t.text, backgroundColor: t.surfaceAlt, borderRadius: 5, paddingHorizontal: 4 }}>{children}</Text>;
}

// ---- 빌드 로그 (SSE) ----

const STEPS = [
  { key: 'validating', label: '검사' },
  { key: 'building', label: '빌드' },
  { key: 'deploying', label: '배포' },
  { key: 'active', label: '완료' },
];

function BuildLogCard({ releaseId, onDone }: { releaseId: string; onDone: () => void }) {
  const t = useTheme();
  const [lines, setLines] = useState<string[]>([]);
  const [state, setState] = useState('queued');
  const scroll = useRef<ScrollView>(null);

  useEffect(() => {
    setLines([]);
    setState('queued');
    const es = new EventSource(`${API_BASE}/releases/${releaseId}/logs`, { withCredentials: true });
    es.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.kind === 'state') setState(data.line);
      else if (data.kind === 'end') {
        setState(data.line);
        if (data.error) setLines((l) => [...l, `오류: ${data.error}`]);
        es.close();
        onDone();
      } else setLines((l) => [...l.slice(-1500), data.line]);
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [releaseId, onDone]);

  const idx = STEPS.findIndex((s) => s.key === state);
  const failed = state === 'failed';
  return (
    <Card title="빌드 진행" icon={Terminal} right={<Badge status={state} />}>
      <View style={{ flexDirection: 'row', gap: 6, marginBottom: 14 }}>
        {STEPS.map((s, i) => {
          const done = idx >= i || state === 'superseded';
          return (
            <View key={s.key} style={{ flex: 1, gap: 6 }}>
              <View style={{ height: 4, borderRadius: 2, backgroundColor: failed && i === Math.max(idx, 0) ? t.danger : done ? t.accent : t.surfaceAlt }} />
              <T variant="small" style={{ color: done ? t.text : t.textMuted, fontWeight: done ? '600' : '400' }}>{s.label}</T>
            </View>
          );
        })}
      </View>
      <ScrollView ref={scroll} style={{ backgroundColor: t.logBg, borderRadius: radius.control, padding: 14, maxHeight: 340 }} onContentSizeChange={() => scroll.current?.scrollToEnd({ animated: false })}>
        {lines.length === 0 ? <T variant="mono">빌드를 기다리는 중…</T> : lines.map((l, i) => <T key={i} variant="mono">{l}</T>)}
      </ScrollView>
    </Card>
  );
}

// ---- 실행 관리 ----

function RuntimeCard({ project, onChange }: { project: Project; onChange: () => void }) {
  const t = useTheme();
  const [logs, setLogs] = useState<string[] | null>(null);
  const [service, setService] = useState('');
  // 'stopped' / 'running': 그 상태가 될 때까지 버튼 자리를 스켈레톤으로 막는다 (연속 클릭 방지)
  const [waitFor, setWaitFor] = useState<'stopped' | 'running' | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!waitFor) return;
    if (project.status === waitFor) {
      setWaitFor(null);
      return;
    }
    const tick = setInterval(onChange, 2000);
    const giveUp = setTimeout(() => setWaitFor(null), 60000);
    return () => { clearInterval(tick); clearTimeout(giveUp); };
  }, [waitFor, project.status, onChange]);

  const act = async (target: 'stopped' | 'running') => {
    if (waitFor) return;
    setWaitFor(target);
    setError('');
    try {
      await api(target === 'stopped' ? '/projects/me/stop' : '/projects/me/start', { method: 'POST' });
    } catch (e: any) {
      setError(e.message);
      setWaitFor(null);
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
    <Card title="실행 관리" icon={GearSix}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
        {waitFor ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }} accessibilityState={{ busy: true }}>
            <Skeleton h={42} w={110} r={radius.control} />
            <T variant="small" style={{ color: t.warn, fontWeight: '700' }}>{waitFor === 'stopped' ? '중지하는 중…' : '시작하는 중…'}</T>
          </View>
        ) : running ? (
          <Button label="중지" kind="danger" icon={Stop} onPress={() => act('stopped')} />
        ) : (
          <Button label="다시 시작" icon={Play} onPress={() => act('running')} />
        )}
        {project.type === 'fullstack' && <T variant="small" style={{ flex: 1, minWidth: 200 }}>30분 동안 방문이 없으면 쉬었다가, 누가 열면 다시 켜져요.</T>}
      </View>
      {error ? <Notice kind="error" text={error} /> : null}
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
        {project.type === 'fullstack' && (
          <View style={{ width: 200 }}>
            <Field label="서비스" value={service} onChangeText={setService} placeholder="비우면 전체" autoCapitalize="none" />
          </View>
        )}
        <View style={{ marginBottom: 14 }}>
          <Button label="로그 보기" kind="secondary" icon={Terminal} onPress={loadLogs} />
        </View>
      </View>
      {logs && (
        <ScrollView style={{ backgroundColor: t.logBg, borderRadius: radius.control, padding: 14, maxHeight: 340 }}>
          {logs.length === 0 ? <T variant="mono">(로그 없음)</T> : logs.map((l, i) => <T key={i} variant="mono">{l}</T>)}
        </ScrollView>
      )}
    </Card>
  );
}

// ---- 링크 이름·소개 ----

export function SettingsCard({ project, onChange }: { project: Project; onChange: () => void }) {
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
      setMsg({ kind: 'ok', text: res.redeploying ? '저장했어요. 새 주소로 다시 배포하는 중이에요.' : '저장했어요.' });
      setThumb(null);
      onChange();
    } catch (e: any) {
      setMsg({ kind: 'error', text: e.message });
    } finally {
      setSaving(false);
    }
  };

  const preview = `science26.bssm.dev/students/${slug.trim().toLowerCase() || project.student_no}/`;
  return (
    <Card title="프로젝트 정보" icon={GearSix}>
      <Field label="링크 이름" value={slug} onChangeText={setSlug} autoCapitalize="none" placeholder={project.student_no} hint={`${preview}\n영문 소문자, 숫자, 하이픈만 쓸 수 있어요. 학번 주소로 들어와도 새 주소로 연결돼요.`} />
      <Field label="제목" value={title} onChangeText={setTitle} placeholder="전시관에 보일 제목" />
      <Field label="설명" value={description} onChangeText={setDescription} multiline placeholder="어떤 프로젝트인지 한두 문장으로" />
      <FilePick icon={ImageIcon} label="썸네일 이미지 (전시관 카드에 보여요)" file={thumb?.name} onPress={async () => setThumb((await pick(['image/*']))[0] ?? null)} />
      {msg && <Notice kind={msg.kind} text={msg.text} />}
      <Button label="저장" onPress={save} busy={saving} />
    </Card>
  );
}

// ---- 릴리스 ----

function ReleasesCard({ releases, activeId, busy, onWatch, onChange }: { releases: Release[]; activeId?: string; busy: boolean; onWatch: (id: string) => void; onChange: () => void }) {
  const t = useTheme();
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
    <Card title="배포 기록" icon={ClockCounterClockwise}>
      {error ? <Notice kind="error" text={error} /> : null}
      <View style={{ gap: 8 }}>
        {releases.slice(0, 8).map((r, i) => {
          const canRollback = i < 5 && (r.state === 'superseded' || r.id === activeId);
          return (
            <View key={r.id} style={{ backgroundColor: r.id === activeId ? t.accentSoft : t.surfaceAlt, borderRadius: radius.control, padding: 12, gap: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <T variant="heading" style={{ fontSize: 15 }}>v{r.version}</T>
                <Badge status={r.state} />
                <View style={{ flex: 1 }} />
                <T variant="small">{new Date(r.created_at).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</T>
              </View>
              <T variant="small" numberOfLines={1}>{r.source_ref}</T>
              {r.error ? <T variant="small" style={{ color: t.danger }} numberOfLines={3}>{r.error.split('\n')[0]}</T> : null}
              <View style={{ flexDirection: 'row', gap: 6 }}>
                <Button label="로그" kind="secondary" small icon={Terminal} onPress={() => onWatch(r.id)} />
                {canRollback && (
                  <Button label={r.id === activeId ? '다시 배포' : '이 버전으로'} kind="secondary" small icon={ArrowCounterClockwise} disabled={busy} onPress={() => rollback(r)} />
                )}
              </View>
            </View>
          );
        })}
      </View>
    </Card>
  );
}

// ---- 환경변수 ----

type EnvRow = { key: string; value: string | null; secret: boolean; isNew?: boolean };

function EnvCard() {
  const t = useTheme();
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
    <Card title="환경변수" icon={Key} right={<Button label="추가" kind="secondary" small icon={Plus} onPress={() => setRows((r) => [...r, { key: '', value: '', secret: false, isNew: true }])} />}>
      <T variant="small" style={{ marginBottom: 14 }}>DATABASE_URL, REDIS_URL, BASE_PATH, PUBLIC_URL 은 자동으로 들어가요. 비밀값은 저장 후 다시 볼 수 없어요.</T>
      {rows.length === 0 && <T variant="sub" style={{ marginBottom: 14 }}>아직 추가한 변수가 없어요.</T>}
      {rows.map((r, i) => (
        <View key={i} style={{ borderTopWidth: i ? 1 : 0, borderTopColor: t.border, paddingTop: i ? 12 : 0, marginBottom: 4 }}>
          <Field label="이름" value={r.key} onChangeText={(v) => update(i, { key: v })} placeholder="API_KEY" autoCapitalize="characters" />
          <Field label="값" value={r.value ?? ''} onChangeText={(v) => update(i, { value: v })} placeholder={r.value === null ? '저장된 값 유지 (바꿀 때만 입력)' : ''} secureTextEntry={r.secret} />
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Switch value={r.secret} onValueChange={(v) => update(i, { secret: v })} trackColor={{ true: t.accent, false: t.borderStrong }} />
            <T variant="small">비밀값으로 숨기기</T>
            <View style={{ flex: 1 }} />
            <Button label="삭제" kind="ghost" small icon={Trash} onPress={() => setRows((rs) => rs.filter((_, j) => j !== i))} />
          </View>
        </View>
      ))}
      {msg && <Notice kind={msg.kind} text={msg.text} />}
      <Button label="저장" onPress={save} />
    </Card>
  );
}
