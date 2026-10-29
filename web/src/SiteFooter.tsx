import { useEffect, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { EnvelopeSimple, GithubLogo } from '@phosphor-icons/react';

import { api, NOTICE_CHANGED } from './api';
import { font, useTheme } from './theme';
import { Icon, layout, T } from './ui';

type Site = { contact: string; github: string };

// 연락처는 메일 주소면 메일 쓰기, https 주소면 링크, 그 밖(전화번호 등)은 글자만
const contactHref = (c: string) => (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c) ? `mailto:${c}` : /^https:\/\//.test(c) ? c : null);

export default function SiteFooter() {
  const t = useTheme();
  const [site, setSite] = useState<Site | null>(null);

  useEffect(() => {
    const load = () => api<Site>('/public/site').then(setSite).catch(() => {});
    load();
    // 관리자가 운영 설정을 저장하면 바로 다시 읽는다
    window.addEventListener(NOTICE_CHANGED, load);
    return () => window.removeEventListener(NOTICE_CHANGED, load);
  }, []);

  return (
    <View style={{ borderTopWidth: 1, borderTopColor: t.border, marginTop: 24 }}>
      <View style={{ maxWidth: layout.maxWidth, width: '100%', alignSelf: 'center', paddingHorizontal: layout.gutter, paddingVertical: 28, flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 16 }}>
        <T variant="small" style={{ fontWeight: '700', color: t.textSub }}>science26</T>
        <T variant="small">우리가 직접 만든 과학 프로젝트 전시관</T>
        <View style={{ flex: 1 }} />
        {site?.contact ? <FooterLink icon={EnvelopeSimple} label={site.contact} href={contactHref(site.contact)} /> : null}
        {site?.github ? <FooterLink icon={GithubLogo} label="GitHub" href={site.github} /> : null}
      </View>
    </View>
  );
}

function FooterLink({ icon: I, label, href }: { icon: Icon; label: string; href: string | null }) {
  const t = useTheme();
  const body = (hovered = false) => (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <I size={16} color={hovered ? t.accent : t.textMuted} weight="bold" />
      <Text style={{ fontFamily: font.family, fontSize: 13, fontWeight: '600', color: hovered ? t.accent : t.textSub }}>{label}</Text>
    </View>
  );
  if (!href) return body();
  return (
    <Pressable onPress={() => Linking.openURL(href)} accessibilityRole="link" accessibilityLabel={label}>
      {({ hovered }: any) => body(hovered)}
    </Pressable>
  );
}
