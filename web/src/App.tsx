import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, View } from 'react-native';

import { api, ApiError, isPublicHost, Me } from './api';
import AdminScreen from './screens/AdminScreen';
import DashboardScreen from './screens/DashboardScreen';
import LoginScreen from './screens/LoginScreen';
import PublicListScreen from './screens/PublicListScreen';
import { Button, c, Card } from './ui';

type Tab = 'project' | 'admin';

export default function App() {
  if (isPublicHost()) return <PublicListScreen />;
  return <Dashboard />;
}

function Dashboard() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [tab, setTab] = useState<Tab>('project');

  const load = useCallback(async () => {
    try {
      const m = await api<Me>('/me');
      setMe(m);
      if (m.role === 'admin' && !m.mapped) setTab('admin');
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setMe(null);
      else setMe(null);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (me === undefined)
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: c.bg }}>
        <ActivityIndicator />
      </View>
    );
  if (me === null) return <LoginScreen onLogin={load} />;

  const logout = async () => {
    await api('/auth/logout', { method: 'POST' });
    setMe(null);
  };

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <View style={{ backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: c.border }}>
        <View style={{ maxWidth: 1040, width: '100%', alignSelf: 'center', paddingHorizontal: 16, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
          <Text style={{ fontSize: 18, fontWeight: '800', color: c.text }}>science26</Text>
          {me.role === 'admin' && (
            <View style={{ flexDirection: 'row', gap: 4 }}>
              {me.mapped && <TabButton label="내 프로젝트" active={tab === 'project'} onPress={() => setTab('project')} />}
              <TabButton label="관리자" active={tab === 'admin'} onPress={() => setTab('admin')} />
            </View>
          )}
          <View style={{ flex: 1 }} />
          <Text style={{ color: c.muted, fontSize: 13 }}>
            {me.name || me.email}
            {me.student_no ? ` · ${me.student_no}` : ''}
          </Text>
          <Button label="로그아웃" kind="ghost" small onPress={logout} />
        </View>
      </View>
      <ScrollView contentContainerStyle={{ maxWidth: 1040, width: '100%', alignSelf: 'center', padding: 16 }}>
        {!me.mapped && me.role !== 'admin' ? (
          <Card title="등록 대기 중">
            <Text style={{ color: c.text, lineHeight: 22 }}>
              {me.email} 계정이 아직 학번과 연결되지 않았어요. 선생님께 학번 등록을 요청한 뒤 새로고침하세요.
            </Text>
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

function TabButton({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={{ paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, backgroundColor: active ? '#eef2ff' : 'transparent' }}>
      <Text style={{ fontWeight: '600', color: active ? c.accent : c.muted }}>{label}</Text>
    </Pressable>
  );
}
