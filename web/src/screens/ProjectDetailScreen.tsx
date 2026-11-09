import { ReactNode, useEffect, useState } from 'react';
import { Image, Linking, Pressable, ScrollView, Text, useWindowDimensions, View } from 'react-native';
import {
  ArrowLeft, ArrowUpRight, BookOpen, CalendarBlank, Check, DownloadSimple, Eye, Flask, LinkSimple, Lightbulb, Notebook, TextAlignLeft, UploadSimple,
} from '@phosphor-icons/react';

import { api, PUBLIC_HOST, PublicCard, subjectLabel, UPLOAD_HOST } from '../api';
import SiteFooter from '../SiteFooter';
import { font, radius, useTheme } from '../theme';
import { Button, Icon, layout, Skeleton, SUBJECT_ICONS, T } from '../ui';
import { GuideFirstPage } from './GuideViewerScreen';
import { TYPES } from './PublicListScreen';

// 프로젝트 상세 (/project/{링크 이름}). 전시관 카드를 누르면 여기로 와서, 소개를 읽고 작품을 연다.
export const projectPathKey = () => {
  const m = window.location.pathname.match(/^\/project\/([^/]+)\/?$/);
  return m ? decodeURIComponent(m[1]) : null;
};

const home = () => (window.location.href = `https://${PUBLIC_HOST}/`);
const isTest = (no: string) => no[0] === '9';

export default function ProjectDetailScreen({ projectKey }: { projectKey: string }) {
  const t = useTheme();
  const { width } = useWindowDimensions();
  const wide = width >= 900;
  const narrow = width < 680;
  const [p, setP] = useState<PublicCard | null>(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  // 썸네일은 원래 비율 그대로 보여 준다 (16:9 화면 캡처를 4:3 으로 자르면 글자가 잘린다). 너무 길쭉하면 0.75~2 사이로.
  const [ratio, setRatio] = useState(4 / 3);
  useEffect(() => {
    if (!p?.thumbnail_url) return;
    Image.getSize(p.thumbnail_url, (w, h) => h && setRatio(Math.min(Math.max(w / h, 0.75), 2)), () => {});
  }, [p?.thumbnail_url]);

  useEffect(() => {
    api<PublicCard>(`/public/projects/${encodeURIComponent(projectKey)}`)
      .then((r) => {
        setP(r);
        document.title = `${r.title} | science26`;
      })
      .catch((e) => setError(e.status === 404 ? '프로젝트를 찾을 수 없어요. 아직 배포되지 않았거나 링크가 바뀌었을 수 있어요.' : '불러오지 못했어요. 잠시 후 새로고침해 주세요.'));
  }, [projectKey]);

  const type = p ? TYPES[p.type] : null;
  const SubjectIcon = p?.subject ? SUBJECT_ICONS[p.subject] : null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {}
  };
  const sideW = wide ? 380 : Math.min(width - layout.gutter * 2, 560);

  return (
    <ScrollView style={{ backgroundColor: t.bg }}>
      <View style={{ maxWidth: layout.maxWidth, width: '100%', alignSelf: 'center', paddingHorizontal: layout.gutter }}>
        {/* 머리글 (전시관과 같게) */}
        <View style={{ height: 68, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <Pressable onPress={home} accessibilityRole="link" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ width: 30, height: 30, borderRadius: 9, backgroundColor: t.accent, alignItems: 'center', justifyContent: 'center' }}>
              <Flask size={18} color={t.accentText} weight="fill" />
            </View>
            <Text style={{ fontFamily: font.family, fontSize: 17, fontWeight: '800', color: t.text, letterSpacing: -0.4 }}>science26</Text>
          </Pressable>
          {/* Button 은 alignSelf: flex-start 라 그냥 두면 위로 붙는다. 전시관처럼 View 로 감싸 세로 가운데 */}
          <View style={{ justifyContent: 'center' }}>
            <Button label={narrow ? '올리기' : '프로젝트 올리기'} icon={UploadSimple} small={narrow} kind="secondary" onPress={() => Linking.openURL(`https://${UPLOAD_HOST}/`)} />
          </View>
        </View>

        <Pressable onPress={home} accessibilityRole="link" style={({ hovered }: any) => ({ flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', marginTop: narrow ? 8 : 20, marginBottom: 20, opacity: hovered ? 0.7 : 1 })}>
          <ArrowLeft size={16} color={t.textSub} weight="bold" />
          <T variant="sub" style={{ fontWeight: '600' }}>전시관으로</T>
        </Pressable>

        {error ? (
          <View style={{ paddingVertical: 80, alignItems: 'center', gap: 16 }}>
            <T variant="title">앗, 열 수 없어요</T>
            <T variant="sub">{error}</T>
            <Button label="전시관 보기" onPress={home} />
          </View>
        ) : !p ? (
          <View style={{ flexDirection: wide ? 'row' : 'column', gap: 32 }}>
            <View style={{ flex: 1 }}><Skeleton h={wide ? 440 : 260} r={radius.card} /></View>
            <View style={{ width: wide ? 380 : '100%', gap: 14 }}>
              <Skeleton h={22} w={140} />
              <Skeleton h={40} />
              <Skeleton h={72} r={radius.card} />
              <Skeleton h={52} r={radius.control} />
            </View>
          </View>
        ) : (
          <>
            {/* 위: 큰 그림 + 핵심 정보 */}
            <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 40 : 24, alignItems: wide ? 'flex-start' : 'stretch' }}>
              <View style={{ flex: wide ? 1 : undefined, minWidth: 0 }}>
                <Pressable onPress={() => Linking.openURL(p.url)} accessibilityRole="link" accessibilityLabel={`${p.title} 작품 열기`}>
                  {({ hovered }: any) => (
                    <View style={{ aspectRatio: p.thumbnail_url ? ratio : 4 / 3, borderRadius: radius.card, overflow: 'hidden', backgroundColor: t.surfaceAlt, borderWidth: 1, borderColor: hovered ? t.accent : t.border }}>
                      {p.thumbnail_url ? (
                        <Image source={{ uri: p.thumbnail_url }} style={{ width: '100%', height: '100%' }} resizeMode="cover" accessibilityLabel={`${p.title} 썸네일`} />
                      ) : (
                        <View style={{ flex: 1, padding: narrow ? 24 : 40, justifyContent: 'space-between' }}>
                          {type && <type.icon size={36} color={t.textMuted} weight="duotone" />}
                          <Text numberOfLines={3} style={{ fontFamily: font.family, fontSize: narrow ? 34 : 48, lineHeight: narrow ? 40 : 56, fontWeight: '800', letterSpacing: -1.2, color: t.textSub }}>{p.title}</Text>
                        </View>
                      )}
                    </View>
                  )}
                </Pressable>
              </View>

              <View style={{ width: wide ? 380 : '100%', gap: 18 }}>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
                  {p.subject ? <Tag icon={SubjectIcon ?? undefined} label={subjectLabel(p.subject)} accent /> : null}
                  {type && <Tag icon={type.icon} label={type.label} />}
                  {p.status === 'sleeping' && <Tag label="열면 몇 초 뒤 깨어나요" />}
                </View>
                <T variant="display" style={narrow ? { fontSize: 30, lineHeight: 36 } : { fontSize: 36, lineHeight: 42 }}>{p.title}</T>

                {/* 제작자 */}
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: t.surface, borderWidth: 1, borderColor: t.border, borderRadius: radius.card, padding: 16 }}>
                  <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: t.accentSoft, alignItems: 'center', justifyContent: 'center' }}>
                    <Text style={{ fontFamily: font.family, fontSize: 16, fontWeight: '800', color: t.accent }}>{(p.name || '?').length > 2 ? p.name.slice(-2) : p.name || '?'}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <T variant="small" style={{ marginBottom: 2 }}>만든 사람</T>
                    <T variant="heading">{p.name || '이름 없음'}</T>
                    <T variant="sub">
                      {isTest(p.student_no) ? `테스트 계정 ${p.student_no}` : `${p.student_no[0]}학년 ${p.student_no[1]}반 ${Number(p.student_no.slice(2))}번 · ${p.student_no}`}
                    </T>
                  </View>
                </View>

                <Button label="작품 열기" icon={ArrowUpRight} full onPress={() => Linking.openURL(p.url)} />
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  {p.guide_url ? (
                    <View style={{ flex: 1 }}><Button label="이용 가이드북" icon={BookOpen} kind="secondary" full onPress={() => (window.location.href = p.guide_url!)} /></View>
                  ) : null}
                  <View style={{ flex: 1 }}><Button label={copied ? '링크 복사됨' : '링크 복사'} icon={copied ? Check : LinkSimple} kind="secondary" full onPress={copy} /></View>
                </View>

                <View style={{ flexDirection: 'row', gap: 20, flexWrap: 'wrap' }}>
                  <Meta icon={Eye} label={`조회 ${(p.views ?? 0).toLocaleString('ko-KR')}${p.views_today ? ` (오늘 ${p.views_today})` : ''}`} />
                  {p.updated_at && <Meta icon={CalendarBlank} label={`${new Date(p.updated_at).toLocaleDateString('ko-KR')} 업데이트`} />}
                </View>
              </View>
            </View>

            {/* 아래: 자세한 내용 */}
            <View style={{ flexDirection: wide ? 'row' : 'column', gap: wide ? 40 : 0, marginTop: 40, alignItems: 'flex-start' }}>
              <View style={{ flex: wide ? 1 : undefined, width: wide ? undefined : '100%', minWidth: 0 }}>
                <Section icon={TextAlignLeft} title="프로젝트 소개">
                  <T style={{ fontSize: 16, lineHeight: 27 }}>{p.description || '아직 소개를 적지 않았어요.'}</T>
                </Section>
                <Section icon={Notebook} title="연관 단원">
                  <T style={{ fontSize: 16, lineHeight: 27, color: p.unit ? t.text : t.textMuted }}>{p.unit || '아직 적지 않았어요.'}</T>
                </Section>
                <Section icon={Lightbulb} title="과학적 효과">
                  <T style={{ fontSize: 16, lineHeight: 27, color: p.effect ? t.text : t.textMuted }}>{p.effect || '아직 적지 않았어요.'}</T>
                </Section>
              </View>
              {p.guide_url && p.guide_file_url && p.guide_kind ? (
                <View style={{ width: wide ? 380 : '100%' }}>
                  <Section icon={BookOpen} title="이용 가이드북">
                    <Pressable onPress={() => (window.location.href = p.guide_url!)} accessibilityRole="link" accessibilityLabel="이용 가이드북 열기">
                      <GuideFirstPage fileUrl={p.guide_file_url} kind={p.guide_kind} width={sideW} />
                    </Pressable>
                    {p.guide_name ? <T variant="small" style={{ marginTop: 10, fontFamily: font.mono }} numberOfLines={1}>{p.guide_name}</T> : null}
                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
                      <View style={{ flex: 1 }}><Button label="크게 보기" icon={BookOpen} full onPress={() => (window.location.href = p.guide_url!)} /></View>
                      <View style={{ flex: 1 }}><Button label="내려받기" icon={DownloadSimple} kind="secondary" full onPress={() => Linking.openURL(`${p.guide_file_url}?download=true`)} /></View>
                    </View>
                  </Section>
                </View>
              ) : null}
            </View>
          </>
        )}
      </View>
      <View style={{ height: 40 }} />
      <SiteFooter />
    </ScrollView>
  );
}

function Tag({ label, icon: I, accent }: { label: string; icon?: Icon; accent?: boolean }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: radius.pill, paddingHorizontal: 11, paddingVertical: 5, backgroundColor: accent ? t.accentSoft : t.surfaceAlt }}>
      {I && <I size={14} color={accent ? t.accent : t.textSub} weight="bold" />}
      <T variant="small" style={{ fontWeight: '700', color: accent ? t.accent : t.textSub }}>{label}</T>
    </View>
  );
}

function Meta({ icon: I, label }: { icon: Icon; label: string }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <I size={16} color={t.textMuted} />
      <T variant="small">{label}</T>
    </View>
  );
}

function Section({ icon: I, title, children }: { icon: Icon; title: string; children: ReactNode }) {
  const t = useTheme();
  return (
    <View style={{ paddingVertical: 22, borderTopWidth: 1, borderTopColor: t.border }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <I size={19} color={t.accent} weight="duotone" />
        <T variant="heading">{title}</T>
      </View>
      {children}
    </View>
  );
}
