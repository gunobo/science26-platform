import { useState } from 'react';
import { Text, View } from 'react-native';

import { API_BASE, api, json } from '../api';
import { Button, c, Card, Field, Notice } from '../ui';

const ERRORS: Record<string, string> = {
  domain: '학교 구글 계정으로만 로그인할 수 있어요.',
  oauth: '로그인에 실패했어요. 다시 시도해 주세요.',
};

export default function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const error = typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('error') : null;
  const isLocal = typeof window !== 'undefined' && window.location.hostname === 'localhost';
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
    <View style={{ flex: 1, backgroundColor: c.bg, alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <Card style={{ width: '100%', maxWidth: 420 }}>
        <Text style={{ fontSize: 24, fontWeight: '800', color: c.text, marginBottom: 6 }}>science26</Text>
        <Text style={{ color: c.muted, marginBottom: 20, lineHeight: 20 }}>
          과학 프로젝트를 올리면 science26.bssm.dev 에 바로 배포돼요.
        </Text>
        {error && <Notice kind="error" text={ERRORS[error] || '로그인 오류'} />}
        <Button label="학교 구글 계정으로 로그인" onPress={() => (window.location.href = `${API_BASE}/auth/google/login`)} />
        {isLocal && (
          <View style={{ marginTop: 24 }}>
            <Field label="개발용 로그인 (DEV_LOGIN=true)" value={email} onChangeText={setEmail} placeholder="학교 이메일" />
            {devError ? <Notice kind="error" text={devError} /> : null}
            <Button label="개발용 로그인" kind="ghost" onPress={devLogin} />
          </View>
        )}
      </Card>
    </View>
  );
}
