import { useState } from 'react';
import { Pressable, Text, useWindowDimensions, View } from 'react-native';
import { ArrowLeft, Flask, GoogleLogo } from '@phosphor-icons/react';

import { API_BASE, api, json, PUBLIC_HOST } from '../api';
import { font, useTheme } from '../theme';
import { Button, Field, Notice, T } from '../ui';

const goGallery = () => (window.location.href = `https://${PUBLIC_HOST}/`);

const ERRORS: Record<string, string> = {
  domain: '학교 구글 계정으로만 로그인할 수 있어요.',
  oauth: '로그인에 실패했어요. 다시 시도해 주세요.',
};

export default function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  const error = typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('error') : null;
  const isLocal = typeof window !== 'undefined' && window.location.hostname.endsWith('localhost');
  const [email, setEmail] = useState('');
  const [devError, setDevError] = useState('');

  const devLogin = async () => {
    try {
      await api('/auth/dev-login', { method: 'POST', ...json({ email }) });
      onLogin();
    } catch (e: any) {
      setDevError(e.message);
    }
  };

  return (
    <View style={{ flex: 1, minHeight: '100vh' as any, flexDirection: wide ? 'row' : 'column', backgroundColor: t.bg }}>
      <View style={{ flex: wide ? 1.1 : undefined, backgroundColor: t.dark ? '#0b2a20' : '#064e3b', padding: wide ? 56 : 28, justifyContent: 'space-between', gap: 40 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 30, height: 30, borderRadius: 9, backgroundColor: '#d1fae5', alignItems: 'center', justifyContent: 'center' }}>
            <Flask size={18} color="#064e3b" weight="fill" />
          </View>
          <Text style={{ fontFamily: font.family, fontSize: 17, fontWeight: '800', color: '#ecfdf5', letterSpacing: -0.4 }}>science26</Text>
        </View>
        <View style={{ maxWidth: 520 }}>
          <Text style={{ fontFamily: font.family, fontSize: wide ? 44 : 30, lineHeight: wide ? 52 : 38, fontWeight: '800', letterSpacing: -1.2, color: '#ecfdf5' }}>
            올리면 바로{'\n'}배포되는 과학 프로젝트
          </Text>
          <Text style={{ fontFamily: font.family, fontSize: 16, lineHeight: 25, color: '#a7f3d0', marginTop: 16 }}>
            웹, 백엔드가 있는 웹앱, 안드로이드 앱까지. 파일을 올리면 science26.bssm.dev 에 내 페이지가 생겨요.
          </Text>
        </View>
        {wide && (
          <Pressable onPress={goGallery} style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', opacity: hovered ? 1 : 0.85 })}>
            <ArrowLeft size={16} color="#d1fae5" weight="bold" />
            <Text style={{ fontFamily: font.family, fontSize: 14.5, fontWeight: '600', color: '#d1fae5' }}>전시관 둘러보기</Text>
          </Pressable>
        )}
      </View>

      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28 }}>
        <View style={{ width: '100%', maxWidth: 380 }}>
          <T variant="title">로그인</T>
          <T style={{ marginTop: 6, marginBottom: 24 }}>학교 구글 계정으로 들어와 주세요.</T>
          {error && <Notice kind="error" text={ERRORS[error] || '로그인 중 문제가 생겼어요.'} />}
          <Button label="Google 계정으로 계속하기" icon={GoogleLogo} full onPress={() => (window.location.href = `${API_BASE}/auth/google/login`)} />

          {isLocal && (
            <View style={{ marginTop: 36, paddingTop: 24, borderTopWidth: 1, borderTopColor: t.border }}>
              <Field label="개발용 로그인" hint="로컬에서 DEV_LOGIN=true 일 때만 동작해요" value={email} onChangeText={setEmail} placeholder="학교 이메일" autoCapitalize="none" />
              {devError ? <Notice kind="error" text={devError} /> : null}
              <Button label="개발용 로그인" kind="secondary" full onPress={devLogin} />
            </View>
          )}
          {!wide && (
            <View style={{ marginTop: 20 }}>
              <Button label="전시관 둘러보기" kind="ghost" icon={ArrowLeft} onPress={goGallery} />
            </View>
          )}
        </View>
      </View>
    </View>
  );
}
