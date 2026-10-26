import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Linking, Pressable, ScrollView, Text, TextInput, useWindowDimensions, View } from 'react-native';

import { api, PublicCard } from '../api';
import { c, s } from '../ui';

const TYPE_LABEL = { static: '웹', fullstack: '웹앱', app: '앱' } as const;

export default function PublicListScreen() {
  const [cards, setCards] = useState<PublicCard[] | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const { width } = useWindowDimensions();
  const cols = width > 960 ? 3 : width > 620 ? 2 : 1;

  useEffect(() => {
    api<PublicCard[]>('/public/projects').then(setCards).catch((e) => setError(e.message));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!cards || !q) return cards;
    return cards.filter((p) => [p.title, p.name, p.student_no, p.slug, p.description].some((t) => t?.toLowerCase().includes(q)));
  }, [cards, query]);

  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={{ maxWidth: 1080, width: '100%', alignSelf: 'center', padding: 16 }}>
      <Text style={{ fontSize: 30, fontWeight: '800', color: c.text, marginTop: 24 }}>science26</Text>
      <Text style={{ color: c.muted, marginTop: 4, marginBottom: 20 }}>학생 과학 프로젝트 모음</Text>
      <TextInput value={query} onChangeText={setQuery} placeholder="제목·이름·학번 검색" placeholderTextColor="#9aa1ab" style={[s.input, { marginBottom: 20, maxWidth: 360 }]} />
      {error ? <Text style={{ color: c.danger }}>{error}</Text> : null}
      {!filtered && !error ? <ActivityIndicator /> : null}
      {filtered && filtered.length === 0 ? <Text style={s.muted}>아직 공개된 프로젝트가 없어요.</Text> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -8 }}>
        {filtered?.map((p) => (
          <View key={p.student_no} style={{ width: `${100 / cols}%`, padding: 8 }}>
            <Pressable onPress={() => Linking.openURL(p.url)} style={({ hovered }: any) => [s.card, { padding: 0, overflow: 'hidden', marginBottom: 0 }, hovered && { borderColor: c.accent }]}>
              <View style={{ aspectRatio: 16 / 9, backgroundColor: '#e9edf3', alignItems: 'center', justifyContent: 'center' }}>
                {p.thumbnail_url ? (
                  <Image source={{ uri: p.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" />
                ) : (
                  <Text style={{ fontSize: 34, fontWeight: '800', color: '#b6bfcc' }}>{p.title.slice(0, 1)}</Text>
                )}
              </View>
              <View style={{ padding: 14 }}>
                <View style={[s.row, { marginBottom: 4 }]}>
                  <Text style={{ fontSize: 12, color: c.accent, fontWeight: '700' }}>{TYPE_LABEL[p.type] ?? ''}</Text>
                  {p.status === 'sleeping' && <Text style={{ fontSize: 12, color: c.muted }}>· 슬립 (열면 깨어나요)</Text>}
                </View>
                <Text style={{ fontSize: 16, fontWeight: '700', color: c.text }} numberOfLines={1}>{p.title}</Text>
                <Text style={[s.muted, { marginTop: 2 }]}>{p.student_no} {p.name}</Text>
                {p.description ? <Text style={{ color: c.text, marginTop: 8, lineHeight: 19 }} numberOfLines={2}>{p.description}</Text> : null}
              </View>
            </Pressable>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}
