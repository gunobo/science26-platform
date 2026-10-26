import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, useColorScheme, View } from 'react-native';
import { Flask, ShieldCheck, SignOut, SquaresFour } from '@phosphor-icons/react';

import { api, ApiError, isPublicHost, Me, PUBLIC_HOST } from './api';
import AdminScreen from './screens/AdminScreen';
import DashboardScreen from './screens/DashboardScreen';
import LoginScreen from './screens/LoginScreen';
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

type Tab = 'project' | 'admin';

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
          {me.role === 'admin' && (
            <View style={{ flexDirection: 'row', gap: 4 }}>
              {me.mapped && <TabButton label="내 프로젝트" icon={SquaresFour} active={tab === 'project'} onPress={() => setTab('project')} />}
              <TabButton label="관리자" icon={ShieldCheck} active={tab === 'admin'} onPress={() => setTab('admin')} />
            </View>
          )}
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
        {!me.mapped && me.role !== 'admin' ? (
          <Card style={{ maxWidth: 560 }}>
            <T variant="title" style={{ marginBottom: 8 }}>학번 등록을 기다리고 있어요</T>
            <T>{me.email} 계정이 아직 학번과 연결되지 않았어요. 선생님께 등록을 요청한 뒤 새로고침하면 바로 업로드할 수 있어요.</T>
          </Card>
        ) : tab === 'admin' && me.role === 'admin' ? (
          <AdminScreen />
        ) : (
          <DashboardScreen />
        )}
      </ScrollView>
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
