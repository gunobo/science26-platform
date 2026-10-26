import { createContext, useContext } from 'react';
import { Platform } from 'react-native';

// 바탕은 zinc 계열 중립색, 포인트 색은 에메랄드 하나만 쓴다.
// 모서리: 카드 16, 버튼·입력 10, 칩·배지는 완전히 둥글게.
export type Theme = {
  dark: boolean;
  bg: string;
  surface: string;
  surfaceAlt: string;
  border: string;
  borderStrong: string;
  text: string;
  textSub: string;
  textMuted: string;
  accent: string;
  accentText: string;
  accentSoft: string;
  danger: string;
  dangerSoft: string;
  warn: string;
  warnSoft: string;
  ok: string;
  okSoft: string;
  logBg: string;
  logText: string;
  shadow: string;
};

export const light: Theme = {
  dark: false,
  bg: '#f4f4f5',
  surface: '#fcfcfc',
  surfaceAlt: '#ececee',
  border: '#e4e4e7',
  borderStrong: '#d4d4d8',
  text: '#18181b',
  textSub: '#3f3f46',
  textMuted: '#62626b',
  accent: '#047857',
  accentText: '#f8fffc',
  accentSoft: '#e3f4ec',
  danger: '#b42318',
  dangerSoft: '#fdecea',
  warn: '#a15c07',
  warnSoft: '#fdf3e1',
  ok: '#047857',
  okSoft: '#e3f4ec',
  logBg: '#131316',
  logText: '#d4d4d8',
  shadow: 'rgba(24, 24, 27, 0.06)',
};

export const dark: Theme = {
  dark: true,
  bg: '#0f0f11',
  surface: '#18181b',
  surfaceAlt: '#232327',
  border: '#2a2a2f',
  borderStrong: '#3a3a40',
  text: '#f2f2f3',
  textSub: '#d0d0d4',
  textMuted: '#a1a1aa',
  accent: '#34d399',
  accentText: '#062b1f',
  accentSoft: '#12302a',
  danger: '#f87171',
  dangerSoft: '#3a1717',
  warn: '#fbbf24',
  warnSoft: '#36290d',
  ok: '#34d399',
  okSoft: '#12302a',
  logBg: '#0a0a0c',
  logText: '#d4d4d8',
  shadow: 'rgba(0, 0, 0, 0.3)',
};

export const ThemeContext = createContext<Theme>(light);
export const useTheme = () => useContext(ThemeContext);

export const font = {
  family: 'Pretendard, -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif',
  mono: 'ui-monospace, "SF Mono", Menlo, Consolas, monospace',
};

export const radius = { card: 16, control: 10, pill: 999 };

/** 웹에서 Pretendard 를 불러오고 전역 기본값을 맞춘다. */
export function installWebFont() {
  if (Platform.OS !== 'web' || typeof document === 'undefined' || document.getElementById('s26-font')) return;
  const link = document.createElement('link');
  link.id = 's26-font';
  link.rel = 'stylesheet';
  link.href = 'https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css';
  document.head.appendChild(link);
  const style = document.createElement('style');
  style.textContent = `
    html, body { font-family: ${font.family}; -webkit-font-smoothing: antialiased; }
    input, textarea, button { font-family: inherit; }
    :focus-visible { outline: 2px solid #059669; outline-offset: 2px; }
    @keyframes s26pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    @media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
  `;
  document.head.appendChild(style);
}
