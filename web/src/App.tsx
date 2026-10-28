import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, useColorScheme, View } from 'react-native';
import { Flask, Megaphone, ShieldCheck, SignOut, SquaresFour, Timer, UserCircle } from '@phosphor-icons/react';

import { api, ApiError, isPublicHost, Me, PUBLIC_HOST } from './api';
import AdminScreen from './screens/AdminScreen';
import DashboardScreen from './screens/DashboardScreen';
import LoginScreen from './screens/LoginScreen';
import MyPageScreen from './screens/MyPageScreen';
import PublicListScreen from './screens/PublicListScreen';
import { dark, font, installWebFont, light, radius, ThemeContext, useTheme } from './theme';
import { Button, Card, layout, Skeleton, T } from './ui';

installWebFont();

export default function App() {
  const scheme = useColorScheme();
  const theme = scheme === 'dark' ? dark : light;
  return (
    <ThemeContext.Provider value={theme}>
      <View style={{ flex: 1, backgroundColor: theme.bg }}>{isPublicHost() ? <PublicListScreen /> : <Workspace />}</View>
    </ThemeContext.Provider>
  );
}

type Tab = 'project' | 'mypage' | 'admin';

function Workspace() {
  const t = useTheme();
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [tab, setTab] = useState<Tab>('project');

  const load = useCallback(async () => {
    try {
      const m = await api<Me>('/me');
      setMe(m);
      if (m.role === 'admin' && !m.mapped) setTab('admin');
    } catch (e) {
      setMe(e instanceof ApiError && e.status === 401 ? null : null);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (me === undefined)
    return (
      <View style={{ padding: 24, gap: 12, maxWidth: layout.maxWidth, width: '100%', alignSelf: 'center' }}>
        <Skeleton h={28} w={180} />
        <Skeleton h={180} r={16} />
        <Skeleton h={240} r={16} />
      </View>
    );
  if (me === null) return <LoginScreen onLogin={load} />;

  const logout = async () => {
    await api('/auth/logout', { method: 'POST' });
    setMe(null);
  };

  return (
    <View style={{ flex: 1 }}>
      <View style={{ backgroundColor: t.surface, borderBottomWidth: 1, borderBottomColor: t.border }}>
        <View style={{ maxWidth: layout.maxWidth, width: '100%', alignSelf: 'center', paddingHorizontal: layout.gutter, height: 64, flexDirection: 'row', alignItems: 'center', gap: 20 }}>
          <Pressable onPress={() => (window.location.href = `https://${PUBLIC_HOST}/`)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 30, height: 30, borderRadius: 9, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center' }}>
              <Flask size={18} color={t.accentText} weight="fill" />
            </View>
            <Text style={{ fontFamily: font.family, fontSize: 17, fontWeight: '800', color: t.text, letterSpacing: -0.4 }}>science26</Text>
          </Pressable>
          <View style={{ flexDirection: 'row', gap: 4 }}>
            {me.mapped && <TabButton label="내 프로젝트" icon={SquaresFour} active={tab === 'project'} onPress={() => setTab('project')} />}
            {me.mapped && <TabButton label="마이페이지" icon={UserCircle} active={tab === 'mypage'} onPress={() => setTab('mypage')} />}
            {me.role === 'admin' && <TabButton label="관리자" icon={ShieldCheck} active={tab === 'admin'} onPress={() => setTab('admin')} />}
          </View>
          <View style={{ flex: 1 }} />
          <View style={{ alignItems: 'flex-end' }}>
            <T variant="small" style={{ color: t.text, fontWeight: '600' }} numberOfLines={1}>{me.name || me.email}</T>
            {me.student_no ? <T variant="small">{me.student_no}</T> : null}
          </View>
          <View style={{ justifyContent: 'center' }}>
            <Button label="로그아웃" kind="ghost" small icon={SignOut} onPress={logout} />
          </View>
        </View>
      </View>
      <ScrollView contentContainerStyle={{ maxWidth: layout.maxWidth, width: '100%', alignSelf: 'center', padding: layout.gutter, paddingTop: 28, paddingBottom: 64 }}>
        <NoticeBanner />
        {!me.mapped && me.role !== 'admin' ? (
          <Card style={{ maxWidth: 560 }}>
            <T variant="title" style={{ marginBottom: 8 }}>학번 등록을 기다리고 있어요</T>
            <T>{me.email} 계정이 아직 학번과 연결되지 않았어요. 선생님께 등록을 요청한 뒤 새로고침하면 바로 업로드할 수 있어요.</T>
          </Card>
        ) : tab === 'admin' && me.role === 'admin' ? (
          <AdminScreen />
        ) : tab === 'mypage' ? (
          <MyPageScreen me={me} onDeleted={() => setTab('project')} />
        ) : (
          <DashboardScreen onEditInfo={() => setTab('mypage')} />
        )}
      </ScrollView>
    </View>
  );
}

type NoticeData = { notice: string; upload_deadline: string | null };

function untilText(ms: number) {
  const h = Math.floor(ms / 3600000);
  if (h >= 24) return `${Math.floor(h / 24)}일 ${h % 24}시간`;
  if (h >= 1) return `${h}시간 ${Math.floor((ms % 3600000) / 60000)}분`;
  return `${Math.max(1, Math.floor(ms / 60000))}분`;
}

// 관리자가 운영 설정에 쓴 공지와 업로드 마감까지 남은 시간
function NoticeBanner() {
  const t = useTheme();
  const [data, setData] = useState<NoticeData | null>(null);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    api<NoticeData>('/notice').then(setData).catch(() => {});
    const id = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(id);
  }, []);
  if (!data) return null;
  const left = data.upload_deadline ? new Date(data.upload_deadline).getTime() - now : null;
  const showDeadline = left != null && left > 0 && left < 14 * 86400000;
  if (!data.notice && !showDeadline) return null;
  const urgent = showDeadline && left! < 86400000;
  const [bg, fg] = urgent ? [t.warnSoft, t.warn] : [t.accentSoft, t.accent];
  return (
    <View accessibilityRole="alert" style={{ backgroundColor: bg, borderRadius: radius.card, paddingHorizontal: 18, paddingVertical: 14, marginBottom: 20, gap: 8 }}>
      {data.notice ? (
        <View style={{ flexDirection: 'row', gap: 10, alignItems: 'flex-start' }}>
          <Megaphone size={19} color={fg} weight="fill" style={{ marginTop: 1 } as any} />
          <Text style={{ flex: 1, fontFamily: font.family, color: t.text, fontSize: 15, lineHeight: 22, fontWeight: '600' }}>{data.notice}</Text>
        </View>
      ) : null}
      {showDeadline ? (
        <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
          <Timer size={19} color={fg} weight="bold" />
          <Text style={{ fontFamily: font.family, color: fg, fontSize: 14, fontWeight: '700' }}>
            업로드 마감까지 {untilText(left!)} 남았어요
          </Text>
          <T variant="small">({new Date(data.upload_deadline!).toLocaleString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short', hour: '2-digit', minute: '2-digit' })})</T>
        </View>
      ) : null}
    </View>
  );
}

function TabButton({ label, icon: I, active, onPress }: { label: string; icon: typeof Flask; active: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 7, borderRadius: radius.control, backgroundColor: active ? t.accentSoft : hovered ? t.surfaceAlt : 'transparent' })}
    >
      <I size={16} color={active ? t.accent : t.textMuted} weight={active ? 'fill' : 'regular'} />
      <Text style={{ fontFamily: font.family, fontWeight: '600', fontSize: 14, color: active ? t.accent : t.textMuted }}>{label}</Text>
    </Pressable>
  );
}
