import { ComponentType, ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  Text,
  TextInput,
  TextInputProps,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';
import { IconProps } from '@phosphor-icons/react';

import { font, radius, Theme, useTheme } from './theme';

// react-native-web 전용 스타일(transition 등)은 RN 타입에 없어서 따로 둔다
const web = (s: Record<string, unknown>) => s as unknown as ViewStyle;
const ease = web({ transitionProperty: 'transform, background-color, border-color, opacity', transitionDuration: '160ms', transitionTimingFunction: 'cubic-bezier(0.16, 1, 0.3, 1)' });

export type Icon = ComponentType<IconProps>;

export function T({ children, style, variant = 'body', numberOfLines }: { children: ReactNode; style?: TextStyle | TextStyle[]; variant?: 'display' | 'title' | 'heading' | 'body' | 'sub' | 'small' | 'mono'; numberOfLines?: number }) {
  const t = useTheme();
  const v: Record<string, TextStyle> = {
    display: { fontSize: 40, lineHeight: 46, fontWeight: '800', letterSpacing: -1.2, color: t.text },
    title: { fontSize: 24, lineHeight: 30, fontWeight: '700', letterSpacing: -0.5, color: t.text },
    heading: { fontSize: 17, lineHeight: 24, fontWeight: '700', letterSpacing: -0.2, color: t.text },
    body: { fontSize: 15, lineHeight: 23, color: t.textSub },
    sub: { fontSize: 14, lineHeight: 21, color: t.textMuted },
    small: { fontSize: 13, lineHeight: 18, color: t.textMuted },
    mono: { fontSize: 12.5, lineHeight: 19, color: t.logText, fontFamily: font.mono },
  };
  return (
    <Text numberOfLines={numberOfLines} style={[{ fontFamily: variant === 'mono' ? font.mono : font.family }, v[variant], style as TextStyle]}>
      {children}
    </Text>
  );
}

export function Card({ title, icon: I, children, right, style, padded = true }: { title?: string; icon?: Icon; children: ReactNode; right?: ReactNode; style?: ViewStyle; padded?: boolean }) {
  const t = useTheme();
  return (
    <View
      style={[
        { backgroundColor: t.surface, borderRadius: radius.card, borderWidth: 1, borderColor: t.border, marginBottom: 16, overflow: 'hidden' },
        web({ boxShadow: `0 1px 2px ${t.shadow}, 0 8px 24px ${t.shadow}` }),
        style,
      ]}
    >
      {(title || right) && (
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, paddingHorizontal: 20, paddingTop: 18, paddingBottom: padded ? 4 : 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {I && <I size={18} color={t.textMuted} weight="bold" />}
            {title ? <T variant="heading">{title}</T> : null}
          </View>
          {right}
        </View>
      )}
      <View style={padded ? { padding: 20, paddingTop: title || right ? 12 : 20 } : undefined}>{children}</View>
    </View>
  );
}

type BtnKind = 'primary' | 'secondary' | 'ghost' | 'danger';
export function Button({ label, onPress, kind = 'primary', icon: I, disabled, busy, small, full }: { label: string; onPress: () => void; kind?: BtnKind; icon?: Icon; disabled?: boolean; busy?: boolean; small?: boolean; full?: boolean }) {
  const t = useTheme();
  const palette: Record<BtnKind, { bg: string; fg: string; border: string; hover: string }> = {
    primary: { bg: t.accent, fg: t.accentText, border: t.accent, hover: t.dark ? '#5ee0b0' : '#065f46' },
    secondary: { bg: t.surface, fg: t.text, border: t.borderStrong, hover: t.surfaceAlt },
    ghost: { bg: 'transparent', fg: t.textSub, border: 'transparent', hover: t.surfaceAlt },
    danger: { bg: t.surface, fg: t.danger, border: t.borderStrong, hover: t.dangerSoft },
  };
  const p = palette[kind];
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || busy}
      accessibilityRole="button"
      style={({ pressed, hovered }: any) => [
        {
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 7,
          borderRadius: radius.control,
          borderWidth: 1,
          borderColor: p.border,
          backgroundColor: hovered && !disabled ? p.hover : p.bg,
          paddingHorizontal: small ? 11 : 16,
          minHeight: small ? 32 : 42,
          opacity: disabled ? 0.45 : 1,
          alignSelf: full ? 'stretch' : 'flex-start',
          transform: [{ scale: pressed ? 0.98 : 1 }],
        },
        ease,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={p.fg} size="small" />
      ) : (
        <>
          {I && <I size={small ? 15 : 17} color={p.fg} weight="bold" />}
          <Text numberOfLines={1} style={{ fontFamily: font.family, color: p.fg, fontWeight: '600', fontSize: small ? 13 : 14.5 }}>
            {label}
          </Text>
        </>
      )}
    </Pressable>
  );
}

export function Field({ label, hint, error, style, ...props }: TextInputProps & { label?: string; hint?: string; error?: string }) {
  const t = useTheme();
  return (
    <View style={{ marginBottom: 14, gap: 6 }}>
      {label ? <Text style={{ fontFamily: font.family, fontSize: 13.5, fontWeight: '600', color: t.textSub }}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={t.textMuted}
        {...props}
        style={[
          {
            fontFamily: font.family,
            borderWidth: 1,
            borderColor: error ? t.danger : t.borderStrong,
            borderRadius: radius.control,
            paddingHorizontal: 13,
            paddingVertical: 10,
            fontSize: 15,
            color: t.text,
            backgroundColor: t.surface,
          },
          props.multiline ? { minHeight: 92, textAlignVertical: 'top' } : null,
          web({ outlineColor: t.accent }),
          style as TextStyle,
        ]}
      />
      {error ? <T variant="small" style={{ color: t.danger }}>{error}</T> : hint ? <T variant="small">{hint}</T> : null}
    </View>
  );
}

export function Segmented<V extends string>({ value, options, onChange }: { value: V; options: { value: V; label: string; icon?: Icon }[]; onChange: (v: V) => void }) {
  const t = useTheme();
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 4, padding: 4, borderRadius: radius.control + 4, backgroundColor: t.surfaceAlt, alignSelf: 'flex-start', marginBottom: 16 }}>
      {options.map((o) => {
        const active = value === o.value;
        const I = o.icon;
        return (
          <Pressable
            key={o.value}
            onPress={() => onChange(o.value)}
            style={[
              { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.control, backgroundColor: active ? t.surface : 'transparent' },
              active && web({ boxShadow: `0 1px 3px ${t.shadow}` }),
              ease,
            ]}
          >
            {I && <I size={16} color={active ? t.accent : t.textMuted} weight={active ? 'fill' : 'regular'} />}
            <Text style={{ fontFamily: font.family, fontWeight: '600', fontSize: 14, color: active ? t.text : t.textMuted }}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const STATUS: Record<string, [string, keyof Theme, keyof Theme]> = {
  empty: ['배포 전', 'textMuted', 'surfaceAlt'],
  building: ['빌드 중', 'warn', 'warnSoft'],
  running: ['실행 중', 'ok', 'okSoft'],
  sleeping: ['쉬는 중', 'textMuted', 'surfaceAlt'],
  stopped: ['중지됨', 'danger', 'dangerSoft'],
  failed: ['실패', 'danger', 'dangerSoft'],
  queued: ['대기', 'textMuted', 'surfaceAlt'],
  validating: ['검사 중', 'warn', 'warnSoft'],
  deploying: ['배포 중', 'warn', 'warnSoft'],
  active: ['서비스 중', 'ok', 'okSoft'],
  superseded: ['이전 버전', 'textMuted', 'surfaceAlt'],
  // 관리자 학생 현황
  deployed: ['제출 완료', 'ok', 'okSoft'],
  no_upload: ['미제출', 'warn', 'warnSoft'],
  not_logged_in: ['미접속', 'danger', 'dangerSoft'],
  test: ['테스트', 'textMuted', 'surfaceAlt'],
};

export function Badge({ status, label }: { status: string; label?: string }) {
  const t = useTheme();
  const [text, fg, bg] = STATUS[status] || [status, 'textMuted', 'surfaceAlt'];
  return (
    <View style={{ borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 3, backgroundColor: t[bg] as string, alignSelf: 'flex-start' }}>
      <Text style={{ fontFamily: font.family, color: t[fg] as string, fontSize: 12.5, fontWeight: '700' }}>{label ?? text}</Text>
    </View>
  );
}

export function Notice({ text, kind = 'info', icon: I }: { text: string; kind?: 'info' | 'error' | 'warn' | 'ok'; icon?: Icon }) {
  const t = useTheme();
  const map = { info: [t.surfaceAlt, t.textSub], error: [t.dangerSoft, t.danger], warn: [t.warnSoft, t.warn], ok: [t.okSoft, t.ok] } as const;
  const [bg, fg] = map[kind];
  return (
    <View style={{ flexDirection: 'row', gap: 10, backgroundColor: bg, padding: 13, borderRadius: radius.control, marginBottom: 14 }}>
      {I && <I size={18} color={fg} weight="bold" style={{ marginTop: 2 } as any} />}
      <Text style={{ flex: 1, fontFamily: font.family, color: kind === 'info' ? t.textSub : fg, fontSize: 14, lineHeight: 21 }}>{text}</Text>
    </View>
  );
}

export function FilePick({ label, file, onPress, icon: I }: { label: string; file?: string | null; onPress: () => void; icon: Icon }) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      style={({ hovered }: any) => [
        { flexDirection: 'row', alignItems: 'center', gap: 14, borderWidth: 1.5, borderStyle: 'dashed', borderColor: hovered ? t.accent : t.borderStrong, borderRadius: radius.control + 4, padding: 18, backgroundColor: hovered ? t.accentSoft : 'transparent', marginBottom: 12 },
        ease,
      ]}
    >
      <View style={{ width: 42, height: 42, borderRadius: radius.control, backgroundColor: file ? t.accent : t.surfaceAlt, alignItems: 'center', justifyContent: 'center' }}>
        <I size={21} color={file ? t.accentText : t.textMuted} weight="bold" />
      </View>
      <View style={{ flex: 1 }}>
        <T variant="heading" style={{ fontSize: 15 }} numberOfLines={1}>{file || label}</T>
        <T variant="small">{file ? '다시 누르면 다른 파일을 고를 수 있어요' : '눌러서 파일 선택'}</T>
      </View>
    </Pressable>
  );
}

export function Skeleton({ h = 16, w = '100%', r = 8 }: { h?: number; w?: number | `${number}%`; r?: number }) {
  const t = useTheme();
  return <View style={[{ height: h, width: w, borderRadius: r, backgroundColor: t.surfaceAlt }, web({ animation: 's26pulse 1.4s ease-in-out infinite' })]} />;
}

export function Divider() {
  const t = useTheme();
  return <View style={{ height: 1, backgroundColor: t.border, marginVertical: 4 }} />;
}

export const layout = { maxWidth: 1180, gutter: 20 };
