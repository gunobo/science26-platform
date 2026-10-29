import { useEffect, useMemo, useState } from 'react';
import { Image, Linking, Pressable, ScrollView, Text, TextInput, useWindowDimensions, View } from 'react-native';
import { ArrowUpRight, Browser, DeviceMobile, Eye, Fire, Flask, Info, MagnifyingGlass, Stack, UploadSimple } from '@phosphor-icons/react';

import { api, PublicCard, UPLOAD_HOST } from '../api';
import SiteFooter from '../SiteFooter';
import { font, radius, useTheme } from '../theme';
import { Button, Icon, layout, Skeleton, T } from '../ui';

type Filter = 'all' | 'static' | 'fullstack' | 'app';
const TYPES: Record<Exclude<Filter, 'all'>, { label: string; icon: Icon }> = {
  static: { label: '웹', icon: Browser },
  fullstack: { label: '웹앱', icon: Stack },
  app: { label: '앱', icon: DeviceMobile },
};

type Sort = 'hot' | 'views' | 'recent' | 'no';
const SORTS: { value: Sort; label: string }[] = [
  { value: 'no', label: '학번순' },
  { value: 'hot', label: '인기순' },
  { value: 'views', label: '조회수순' },
  { value: 'recent', label: '최신순' },
];
const roomOf = (no: string) => `${no[0]}-${no[1]}`;

const goUpload = () => Linking.openURL(`https://${UPLOAD_HOST}/`);

export default function PublicListScreen() {
  const t = useTheme();
  const [cards, setCards] = useState<PublicCard[] | null>(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [sort, setSort] = useState<Sort>('no');
  const [room, setRoom] = useState('all');
  const [showFormula, setShowFormula] = useState(false);
  const { width } = useWindowDimensions();
  const cols = width >= 1080 ? 3 : width >= 680 ? 2 : 1;
  const narrow = width < 680;

  useEffect(() => {
    api<PublicCard[]>('/public/projects').then(setCards).catch(() => setError('목록을 불러오지 못했어요. 잠시 후 새로고침해 주세요.'));
  }, []);

  // 반 목록은 공개된 프로젝트가 있는 반만 (9로 시작하는 테스트 학번은 뺀다)
  const rooms = useMemo(() => [...new Set((cards ?? []).filter((p) => p.student_no[0] !== '9').map((p) => roomOf(p.student_no)))].sort(), [cards]);
  // 인기 TOP 3 는 필터와 상관없이 전체에서 정한다
  const ranks = useMemo(() => {
    const top = [...(cards ?? [])].filter((p) => (p.hot ?? 0) > 0).sort((a, b) => (b.hot ?? 0) - (a.hot ?? 0)).slice(0, 3);
    return new Map(top.map((p, i) => [p.student_no, i + 1]));
  }, [cards]);

  const filtered = useMemo(() => {
    if (!cards) return null;
    const q = query.trim().toLowerCase();
    const list = cards.filter(
      (p) =>
        (filter === 'all' || p.type === filter) &&
        (room === 'all' || roomOf(p.student_no) === room) &&
        (!q || [p.title, p.name, p.student_no, p.slug, p.description].some((v) => v?.toLowerCase().includes(q))),
    );
    const by: Record<Sort, (a: PublicCard, b: PublicCard) => number> = {
      hot: (a, b) => (b.hot ?? 0) - (a.hot ?? 0),
      views: (a, b) => (b.views ?? 0) - (a.views ?? 0),
      recent: (a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? ''),
      no: () => 0,
    };
    // 동점이면 학번순 (서버가 학번순으로 준다 → 안정 정렬)
    return [...list].sort((a, b) => by[sort](a, b) || a.student_no.localeCompare(b.student_no));
  }, [cards, query, filter, room, sort]);

  return (
    <ScrollView style={{ backgroundColor: t.bg }}>
      <View style={{ maxWidth: layout.maxWidth, width: '100%', alignSelf: 'center', paddingHorizontal: layout.gutter }}>
        <View style={{ height: 68, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 30, height: 30, borderRadius: 9, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center' }}>
              <Flask size={18} color={t.accentText} weight="fill" />
            </View>
            <Text style={{ fontFamily: font.family, fontSize: 17, fontWeight: '800', color: t.text, letterSpacing: -0.4 }}>science26</Text>
          </View>
          <View style={{ justifyContent: 'center' }}>
            <Button label={narrow ? '올리기' : '프로젝트 올리기'} icon={UploadSimple} small={narrow} onPress={goUpload} />
          </View>
        </View>

        <View style={{ paddingTop: narrow ? 28 : 56, paddingBottom: 32, maxWidth: 720 }}>
          <T variant="display" style={narrow ? { fontSize: 32, lineHeight: 38 } : undefined}>
            우리가 직접 만든{'\n'}과학 프로젝트
          </T>
          <T variant="body" style={{ marginTop: 14, fontSize: 17, lineHeight: 26 }}>
            {cards ? `${cards.length}개의 프로젝트가 공개되어 있어요. ` : ''}눌러서 바로 체험해 보세요.
          </T>
        </View>

        <View style={{ flexDirection: narrow ? 'column' : 'row', gap: 12, alignItems: narrow ? 'stretch' : 'center', marginBottom: 24 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: t.surface, borderWidth: 1, borderColor: t.borderStrong, borderRadius: radius.control, paddingHorizontal: 12, flex: narrow ? undefined : 1, maxWidth: narrow ? undefined : 380 }}>
            <MagnifyingGlass size={18} color={t.textMuted} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="제목, 이름, 학번으로 찾기"
              placeholderTextColor={t.textMuted}
              accessibilityLabel="프로젝트 검색"
              style={{ flex: 1, fontFamily: font.family, fontSize: 15, color: t.text, paddingVertical: 11, outlineStyle: 'none' } as any}
            />
          </View>
          <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
            <Chip label="전체" active={filter === 'all'} onPress={() => setFilter('all')} />
            {(Object.keys(TYPES) as (keyof typeof TYPES)[]).map((k) => (
              <Chip key={k} label={TYPES[k].label} icon={TYPES[k].icon} active={filter === k} onPress={() => setFilter(k)} />
            ))}
          </View>
        </View>

        {cards && cards.length > 0 && (
          <View style={{ marginTop: -10, marginBottom: 24, gap: 10 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {SORTS.map((o) => (
                <SortTab key={o.value} label={o.label} active={sort === o.value} onPress={() => setSort(o.value)} />
              ))}
              {sort === 'hot' && (
                <Pressable onPress={() => setShowFormula((v) => !v)} accessibilityRole="button" accessibilityLabel="인기 점수 계산 방법" style={{ padding: 6 }}>
                  <Info size={17} color={t.textMuted} weight={showFormula ? 'fill' : 'regular'} />
                </Pressable>
              )}
              {rooms.length > 1 && (
                <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap', marginLeft: narrow ? 0 : 'auto' as any }}>
                  <SortTab label="모든 반" active={room === 'all'} onPress={() => setRoom('all')} />
                  {rooms.map((r) => (
                    <SortTab key={r} label={`${r[0]}학년 ${r[2]}반`} active={room === r} onPress={() => setRoom(r)} />
                  ))}
                </View>
              )}
            </View>
            {sort === 'hot' && showFormula && (
              <View style={{ backgroundColor: t.surfaceAlt, borderRadius: radius.control, padding: 14, gap: 4, maxWidth: 620 }}>
                <T style={{ color: t.text, fontWeight: '700' }}>인기 점수 = Σ (d일 전 방문자 × 0.8ᵈ) + 3 × log₂(1 + 누적 조회수)</T>
                <T variant="small">최근 14일 방문자를 더하는데, 하루 지날 때마다 20%씩 덜 쳐요 (오늘 1배, 일주일 전 약 0.2배). 요즘 많이 보는 프로젝트가 위로 와요.</T>
                <T variant="small">누적 조회수는 로그로 조금만 더해서, 처음에 몰린 조회수만으로 1등을 계속 지키지는 못해요.</T>
              </View>
            )}
          </View>
        )}

        {error ? <T style={{ color: t.danger, marginBottom: 24 }}>{error}</T> : null}

        <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -10, paddingBottom: 40 }}>
          {!filtered && !error &&
            Array.from({ length: cols * 2 }).map((_, i) => (
              <View key={i} style={{ width: `${100 / cols}%`, padding: 10, gap: 12 }}>
                <Skeleton h={220} r={radius.card} />
                <Skeleton h={18} w="60%" />
                <Skeleton h={14} w="40%" />
              </View>
            ))}
          {filtered?.map((p) => <ProjectCard key={p.student_no} p={p} rank={ranks.get(p.student_no)} width={`${100 / cols}%`} />)}
          {filtered && filtered.length === 0 && (
            <View style={{ width: '100%', padding: 10 }}>
              <View style={{ borderWidth: 1.5, borderStyle: 'dashed', borderColor: t.borderStrong, borderRadius: radius.card, padding: 40, alignItems: 'flex-start', gap: 10 }}>
                <T variant="title">{cards?.length ? '조건에 맞는 프로젝트가 없어요' : '아직 공개된 프로젝트가 없어요'}</T>
                <T>{cards?.length ? '검색어나 분류를 바꿔 보세요.' : '첫 번째 프로젝트를 올려서 전시관을 열어 주세요.'}</T>
                {!cards?.length && <Button label="프로젝트 올리기" icon={UploadSimple} onPress={goUpload} />}
              </View>
            </View>
          )}
        </View>
      </View>
      <SiteFooter />
    </ScrollView>
  );
}

function SortTab({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={({ hovered }: any) => ({ paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.control, backgroundColor: active ? t.accentSoft : hovered ? t.surfaceAlt : 'transparent' })}
    >
      <Text style={{ fontFamily: font.family, fontSize: 14, fontWeight: active ? '700' : '500', color: active ? t.accent : t.textMuted }}>{label}</Text>
    </Pressable>
  );
}

function Chip({ label, icon: I, active, onPress }: { label: string; icon?: Icon; active: boolean; onPress: () => void }) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={({ hovered }: any) => ({
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingHorizontal: 14,
        height: 38,
        borderRadius: radius.pill,
        borderWidth: 1,
        borderColor: active ? t.text : t.borderStrong,
        backgroundColor: active ? t.text : hovered ? t.surfaceAlt : t.surface,
      })}
    >
      {I && <I size={15} color={active ? t.bg : t.textMuted} weight="bold" />}
      <Text style={{ fontFamily: font.family, fontWeight: '600', fontSize: 14, color: active ? t.bg : t.textSub }}>{label}</Text>
    </Pressable>
  );
}

export function ProjectCard({ p, width, rank }: { p: PublicCard; width: `${number}%`; rank?: number }) {
  const t = useTheme();
  const type = TYPES[p.type];
  return (
    <View style={{ width, padding: 10 }}>
      <Pressable
        onPress={() => p.url && Linking.openURL(p.url)}
        accessibilityRole="link"
        accessibilityLabel={`${p.title} 열기`}
        style={({ hovered, pressed }: any) => [
          { borderRadius: radius.card, transform: [{ translateY: hovered && !pressed ? -3 : 0 }] },
          { transitionProperty: 'transform', transitionDuration: '200ms', transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)' } as any,
        ]}
      >
        {({ hovered }: any) => (
          <View>
            <View style={{ aspectRatio: 4 / 3, borderRadius: radius.card, overflow: 'hidden', backgroundColor: t.surfaceAlt, borderWidth: 1, borderColor: hovered ? t.accent : t.border }}>
              {p.thumbnail_url ? (
                <Image source={{ uri: p.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel={`${p.title} 썸네일`} />
              ) : (
                <View style={{ flex: 1, padding: 22, paddingTop: rank != null ? 52 : 22, paddingBottom: p.views != null ? 48 : 22, justifyContent: 'space-between' }}>
                  {type && <type.icon size={26} color={t.textMuted} weight="duotone" />}
                  <Text numberOfLines={2} style={{ fontFamily: font.family, fontSize: 30, lineHeight: 36, fontWeight: '800', letterSpacing: -0.8, color: t.textSub }}>
                    {p.title}
                  </Text>
                </View>
              )}
              {p.views != null && (
                <View
                  accessibilityLabel={`조회수 ${p.views}`}
                  style={{ position: 'absolute', right: 12, bottom: 12, flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: 'rgba(24,24,27,0.72)', borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 }}
                >
                  <Eye size={14} color="#f4f4f5" weight="bold" />
                  <Text style={{ fontFamily: font.family, color: '#f4f4f5', fontSize: 12.5, fontWeight: '700' }}>{p.views.toLocaleString('ko-KR')}</Text>
                </View>
              )}
              {rank != null && (
                <View
                  accessibilityLabel={`인기 ${rank}위`}
                  style={{ position: 'absolute', left: 12, top: 12, flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: rank === 1 ? '#ea580c' : 'rgba(24,24,27,0.72)', borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 }}
                >
                  <Fire size={14} color="#fff7ed" weight="fill" />
                  <Text style={{ fontFamily: font.family, color: '#fff7ed', fontSize: 12.5, fontWeight: '800' }}>인기 {rank}위</Text>
                </View>
              )}
              {p.status === 'sleeping' && (
                <View style={{ position: 'absolute', right: 12, top: 12, backgroundColor: t.surface, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 }}>
                  <T variant="small" style={{ color: t.textSub, fontWeight: '600' }}>열면 몇 초 뒤 깨어나요</T>
                </View>
              )}
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingTop: 14, paddingHorizontal: 2 }}>
              <View style={{ flex: 1 }}>
                <T variant="heading" numberOfLines={1}>{p.title}</T>
                <T variant="sub" numberOfLines={1} style={{ marginTop: 2 }}>
                  {p.name} {p.student_no}{type ? `  |  ${type.label}` : ''}
                </T>
              </View>
              <ArrowUpRight size={20} color={hovered ? t.accent : t.textMuted} weight="bold" />
            </View>
            {p.description ? (
              <T variant="sub" numberOfLines={2} style={{ marginTop: 6, paddingHorizontal: 2 }}>{p.description}</T>
            ) : null}
          </View>
        )}
      </Pressable>
    </View>
  );
}
