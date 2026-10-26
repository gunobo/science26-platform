import { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, TextInputProps, View, ViewStyle } from 'react-native';

export const c = {
  bg: '#f5f6f8',
  card: '#ffffff',
  border: '#e3e6eb',
  text: '#1b1f24',
  muted: '#6b7280',
  accent: '#2563eb',
  danger: '#dc2626',
  ok: '#16a34a',
  warn: '#d97706',
};

export function Card({ title, children, right, style }: { title?: string; children: ReactNode; right?: ReactNode; style?: ViewStyle }) {
  return (
    <View style={[s.card, style]}>
      {(title || right) && (
        <View style={s.cardHead}>
          {title ? <Text style={s.cardTitle}>{title}</Text> : <View />}
          {right}
        </View>
      )}
      {children}
    </View>
  );
}

type BtnProps = { label: string; onPress: () => void; kind?: 'primary' | 'ghost' | 'danger'; disabled?: boolean; busy?: boolean; small?: boolean };
export function Button({ label, onPress, kind = 'primary', disabled, busy, small }: BtnProps) {
  const bg = kind === 'primary' ? c.accent : kind === 'danger' ? c.danger : 'transparent';
  const fg = kind === 'ghost' ? c.text : '#fff';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || busy}
      style={({ pressed }) => [
        s.btn,
        small && s.btnSmall,
        { backgroundColor: bg, opacity: disabled ? 0.45 : pressed ? 0.8 : 1 },
        kind === 'ghost' && { borderWidth: 1, borderColor: c.border },
      ]}
    >
      {busy ? <ActivityIndicator color={fg} size="small" /> : <Text style={[s.btnText, { color: fg }, small && { fontSize: 13 }]}>{label}</Text>}
    </Pressable>
  );
}

export function Field({ label, hint, ...props }: TextInputProps & { label: string; hint?: string }) {
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput placeholderTextColor="#9aa1ab" {...props} style={[s.input, props.multiline && { minHeight: 80, textAlignVertical: 'top' }, props.style]} />
      {hint ? <Text style={s.hint}>{hint}</Text> : null}
    </View>
  );
}

export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <View style={s.seg}>
      {options.map((o) => (
        <Pressable key={o.value} onPress={() => onChange(o.value)} style={[s.segItem, value === o.value && s.segActive]}>
          <Text style={[s.segText, value === o.value && { color: '#fff' }]}>{o.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const STATUS: Record<string, [string, string]> = {
  empty: ['배포 전', c.muted],
  building: ['빌드 중', c.warn],
  running: ['실행 중', c.ok],
  sleeping: ['슬립', c.muted],
  stopped: ['중지됨', c.danger],
  failed: ['실패', c.danger],
  queued: ['대기', c.muted],
  validating: ['검사 중', c.warn],
  deploying: ['배포 중', c.warn],
  active: ['활성', c.ok],
  superseded: ['이전', c.muted],
};

export function Badge({ status }: { status: string }) {
  const [label, color] = STATUS[status] || [status, c.muted];
  return (
    <View style={[s.badge, { borderColor: color }]}>
      <Text style={{ color, fontSize: 12, fontWeight: '600' }}>{label}</Text>
    </View>
  );
}

export function Notice({ text, kind = 'info' }: { text: string; kind?: 'info' | 'error' | 'warn' | 'ok' }) {
  const color = kind === 'error' ? c.danger : kind === 'warn' ? c.warn : kind === 'ok' ? c.ok : c.accent;
  return (
    <View style={[s.notice, { borderLeftColor: color }]}>
      <Text style={{ color: c.text, lineHeight: 20 }}>{text}</Text>
    </View>
  );
}

export const s = StyleSheet.create({
  card: { backgroundColor: c.card, borderRadius: 14, borderWidth: 1, borderColor: c.border, padding: 18, marginBottom: 16 },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 8 },
  cardTitle: { fontSize: 17, fontWeight: '700', color: c.text },
  btn: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 9, alignItems: 'center', justifyContent: 'center', minHeight: 40 },
  btnSmall: { paddingHorizontal: 10, paddingVertical: 6, minHeight: 30 },
  btnText: { fontWeight: '600', fontSize: 14 },
  label: { fontSize: 13, fontWeight: '600', color: c.text, marginBottom: 6 },
  hint: { fontSize: 12, color: c.muted, marginTop: 4 },
  input: { borderWidth: 1, borderColor: c.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 9, fontSize: 14, color: c.text, backgroundColor: '#fff' },
  seg: { flexDirection: 'row', borderWidth: 1, borderColor: c.border, borderRadius: 9, overflow: 'hidden', alignSelf: 'flex-start', marginBottom: 14 },
  segItem: { paddingHorizontal: 14, paddingVertical: 8 },
  segActive: { backgroundColor: c.accent },
  segText: { fontWeight: '600', color: c.text, fontSize: 14 },
  badge: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 2, alignSelf: 'flex-start' },
  notice: { borderLeftWidth: 4, backgroundColor: '#f8fafc', padding: 12, borderRadius: 6, marginBottom: 12 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  muted: { color: c.muted, fontSize: 13 },
  mono: { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12, color: '#e5e7eb' },
  logBox: { backgroundColor: '#0f172a', borderRadius: 8, padding: 12, maxHeight: 360 },
});
