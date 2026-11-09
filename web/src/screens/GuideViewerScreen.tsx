import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import {
  ArrowLeft, ArrowsIn, ArrowsOut, ArrowUpRight, BookOpen, CaretLeft, CaretRight, DownloadSimple, MagnifyingGlassMinus, MagnifyingGlassPlus,
} from '@phosphor-icons/react';

import { api, projectPageUrl, PUBLIC_HOST } from '../api';
import { font, radius, useTheme } from '../theme';
import { Icon, Skeleton, T } from '../ui';

// 이용 가이드북 뷰어 (/guide/{학번}). 브라우저마다 다른 기본 PDF 뷰어 대신 pdf.js 로 직접 그린다.
type Info = { student_no: string; slug: string; name: string; title: string; url: string; guide_name: string; kind: 'pdf' | 'image'; file_url: string };

const PDFJS = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38';
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3];

// pdf.js 4.x 는 ES 모듈이라 번들러(Metro)를 거치지 않고 <script type="module"> 로 불러 window 에 걸어 둔다
let pdfjsPromise: Promise<any> | null = null;
function loadPdfjs(): Promise<any> {
  if (pdfjsPromise) return pdfjsPromise;
  pdfjsPromise = new Promise((resolve, reject) => {
    const w = window as any;
    if (w.pdfjsLib) return resolve(w.pdfjsLib);
    const done = () => {
      w.pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS}/pdf.worker.min.mjs`;
      resolve(w.pdfjsLib);
    };
    window.addEventListener('s26:pdfjs', done, { once: true });
    const s = document.createElement('script');
    s.type = 'module';
    s.textContent = `import * as p from '${PDFJS}/pdf.min.mjs'; window.pdfjsLib = p; window.dispatchEvent(new Event('s26:pdfjs'));`;
    s.onerror = () => reject(new Error('PDF 뷰어를 불러오지 못했어요'));
    document.head.appendChild(s);
    setTimeout(() => !w.pdfjsLib && reject(new Error('PDF 뷰어를 불러오지 못했어요. 인터넷 연결을 확인하세요')), 20000);
  });
  pdfjsPromise.catch(() => (pdfjsPromise = null));
  return pdfjsPromise;
}

export const guidePathNo = () => window.location.pathname.match(/^\/guide\/(\d{4})\/?$/)?.[1] ?? null;

export default function GuideViewerScreen({ studentNo }: { studentNo: string }) {
  const t = useTheme();
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState('');
  const [doc, setDoc] = useState<any>(null);
  const [sizes, setSizes] = useState<{ w: number; h: number }[]>([]); // 각 페이지 원래 크기 (scale 1)
  const [page, setPage] = useState(1);
  const [zoom, setZoom] = useState(1); // 1 = 화면 폭에 맞춤
  const [width, setWidth] = useState(0);
  const [loading, setLoading] = useState(0); // 내려받은 비율 0~1
  const [full, setFull] = useState(false);
  const scroller = useRef<HTMLDivElement | null>(null);
  const pageEls = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    api<Info>(`/public/guides/${studentNo}/info`)
      .then((i) => {
        setInfo(i);
        document.title = `${i.title} 이용 가이드북 | science26`;
      })
      .catch((e) => setError(e.status === 404 ? '이 프로젝트에는 이용 가이드북이 없어요.' : e.message));
  }, [studentNo]);

  // PDF 열기
  useEffect(() => {
    if (info?.kind !== 'pdf') return;
    let cancelled = false;
    let task: any;
    loadPdfjs()
      .then(async (pdfjs) => {
        // isEvalSupported: false — 글꼴 처리에 eval 을 쓰지 않게 (악성 PDF 로 스크립트 실행 방지)
        task = pdfjs.getDocument({ url: info.file_url, isEvalSupported: false, disableRange: true, disableStream: true });
        task.onProgress = (p: { loaded: number; total: number }) => p.total && setLoading(p.loaded / p.total);
        const d = await task.promise;
        const out: { w: number; h: number }[] = [];
        for (let i = 1; i <= d.numPages; i++) {
          const vp = (await d.getPage(i)).getViewport({ scale: 1 });
          out.push({ w: vp.width, h: vp.height });
        }
        if (cancelled) return d.destroy();
        setSizes(out);
        setDoc(d);
      })
      .catch((e) => !cancelled && setError(e?.message?.includes('PDF') ? e.message : 'PDF 파일을 열지 못했어요.'));
    return () => {
      cancelled = true;
      task?.destroy?.();
    };
  }, [info]);

  // 보이는 폭 재기 (창 크기가 바뀌면 다시 맞춤)
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, [info]);

  const maxW = Math.max(...sizes.map((s) => s.w), 1);
  const fitScale = width ? Math.min((width - 32) / maxW, 1.6) : 1;
  const scale = fitScale * zoom;

  // 화면 근처에 온 페이지만 그린다 (긴 가이드북도 가볍게). 배율이 바뀌면 다시 그린다.
  useEffect(() => {
    if (!doc || !width) return;
    const rendered = new Set<number>();
    const tasks = new Map<number, any>();
    const draw = async (i: number) => {
      const holder = pageEls.current[i - 1];
      if (!holder || rendered.has(i)) return;
      rendered.add(i);
      const p = await doc.getPage(i);
      const vp = p.getViewport({ scale });
      const ratio = window.devicePixelRatio || 1;
      const canvas = document.createElement('canvas');
      canvas.width = Math.floor(vp.width * ratio);
      canvas.height = Math.floor(vp.height * ratio);
      canvas.style.width = `${vp.width}px`;
      canvas.style.height = `${vp.height}px`;
      canvas.style.display = 'block';
      const task = p.render({ canvasContext: canvas.getContext('2d')!, viewport: vp, transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined });
      tasks.set(i, task);
      try {
        await task.promise;
        holder.replaceChildren(canvas);
      } catch {
        rendered.delete(i);
      }
    };
    const near = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && draw(Number((e.target as HTMLElement).dataset.page))),
      { root: scroller.current, rootMargin: '800px 0px' },
    );
    pageEls.current.forEach((el) => el && near.observe(el));
    return () => {
      near.disconnect();
      tasks.forEach((task) => task.cancel());
    };
  }, [doc, scale, width]);

  // 지금 보고 있는 페이지 번호
  const onScroll = useCallback(() => {
    const el = scroller.current;
    if (!el) return;
    const mid = el.scrollTop + el.clientHeight / 3;
    let current = 1;
    pageEls.current.forEach((p, i) => p && p.offsetTop <= mid && (current = i + 1));
    setPage(current);
  }, []);

  const goTo = useCallback((n: number) => {
    const target = pageEls.current[Math.min(Math.max(n, 1), sizes.length) - 1];
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [sizes.length]);

  const zoomBy = useCallback((dir: 1 | -1) => {
    setZoom((z) => {
      const i = ZOOMS.findIndex((x) => x >= z - 0.001);
      return ZOOMS[Math.min(Math.max((i < 0 ? ZOOMS.length - 1 : i) + dir, 0), ZOOMS.length - 1)];
    });
  }, []);

  const toggleFull = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen?.();
  };
  useEffect(() => {
    const on = () => setFull(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', on);
    return () => document.removeEventListener('fullscreenchange', on);
  }, []);

  // 키보드: ←/→ 페이지, +/- 확대
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); goTo(page + 1); }
      else if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); goTo(page - 1); }
      else if (e.key === '+' || e.key === '=') zoomBy(1);
      else if (e.key === '-') zoomBy(-1);
      else if (e.key === '0') setZoom(1);
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [goTo, page, zoomBy]);

  const download = () => info && window.open(`${info.file_url}?download=true`, '_self');
  const isPdf = info?.kind === 'pdf';

  return (
    <View style={{ height: '100vh' as any, width: '100%', overflow: 'hidden', backgroundColor: t.bg }}>
      {/* 위쪽 도구 막대 */}
      <View style={{ backgroundColor: t.surface, borderBottomWidth: 1, borderBottomColor: t.border, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <Tool icon={ArrowLeft} label={info ? '작품 소개' : '전시관'} onPress={() => (window.location.href = info ? projectPageUrl(info.slug) : `https://${PUBLIC_HOST}/`)} />
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, minWidth: 160 }}>
          <BookOpen size={20} color={t.accent} weight="duotone" />
          <View style={{ flex: 1, minWidth: 0 }}>
            {info ? (
              <>
                <T variant="heading" style={{ fontSize: 15 }} numberOfLines={1}>{info.title}</T>
                <T variant="small" numberOfLines={1}>{info.name} {info.student_no} · 이용 가이드북</T>
              </>
            ) : error ? null : <Skeleton h={16} w={180} />}
          </View>
        </View>
        {isPdf && sizes.length > 0 && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
            <Tool icon={CaretLeft} label="이전 쪽" onPress={() => goTo(page - 1)} disabled={page <= 1} iconOnly />
            <PageInput page={page} total={sizes.length} onGo={goTo} />
            <Tool icon={CaretRight} label="다음 쪽" onPress={() => goTo(page + 1)} disabled={page >= sizes.length} iconOnly />
          </View>
        )}
        {info && (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
            <Tool icon={MagnifyingGlassMinus} label="축소" onPress={() => zoomBy(-1)} disabled={zoom <= ZOOMS[0]} iconOnly />
            <Pressable onPress={() => setZoom(1)} accessibilityRole="button" accessibilityLabel="화면 폭에 맞추기" style={{ minWidth: 52, alignItems: 'center' }}>
              <Text style={{ fontFamily: font.mono, fontSize: 13, color: t.textSub }}>{Math.round(zoom * 100)}%</Text>
            </Pressable>
            <Tool icon={MagnifyingGlassPlus} label="확대" onPress={() => zoomBy(1)} disabled={zoom >= ZOOMS[ZOOMS.length - 1]} iconOnly />
          </View>
        )}
        {info && <Tool icon={full ? ArrowsIn : ArrowsOut} label={full ? '전체 화면 끄기' : '전체 화면'} onPress={toggleFull} iconOnly />}
        {info && <Tool icon={DownloadSimple} label="내려받기" onPress={download} />}
        {info && <Tool icon={ArrowUpRight} label="작품 열기" onPress={() => window.open(info.url, '_blank')} primary />}
      </View>

      {/* 본문 */}
      <div
        ref={scroller}
        onScroll={onScroll}
        style={{ flex: 1, minHeight: 0, minWidth: 0, width: '100%', overflow: 'auto', position: 'relative', background: t.dark ? '#0b0b0d' : '#e7e7ea' }}
      >
        {error ? (
          <div style={{ display: 'grid', placeItems: 'center', height: '100%', padding: 24 }}>
            <View style={{ alignItems: 'center', gap: 12 }}>
              <BookOpen size={40} color={t.textMuted} weight="duotone" />
              <T>{error}</T>
              {info && <Tool icon={DownloadSimple} label="파일로 내려받기" onPress={download} primary />}
            </View>
          </div>
        ) : !info || (isPdf && !doc) ? (
          <div style={{ display: 'grid', placeItems: 'center', height: '100%' }}>
            <View style={{ alignItems: 'center', gap: 12, width: 240 }}>
              <T variant="sub">가이드북을 여는 중… {loading > 0 ? `${Math.round(loading * 100)}%` : ''}</T>
              <View style={{ height: 6, width: '100%', borderRadius: 3, backgroundColor: t.surfaceAlt, overflow: 'hidden' }}>
                <View style={[{ height: 6, backgroundColor: t.accent, width: `${Math.max(loading, 0.05) * 100}%` }, { transitionProperty: 'width', transitionDuration: '200ms' } as any]} />
              </View>
            </View>
          </div>
        ) : isPdf ? (
          <div style={{ padding: '16px 16px 48px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, minWidth: 'fit-content' }}>
            {sizes.map((s, i) => (
              <div
                key={i}
                data-page={i + 1}
                ref={(el) => { pageEls.current[i] = el; }}
                aria-label={`${i + 1}쪽`}
                style={{ width: s.w * scale, height: s.h * scale, background: '#fff', borderRadius: 4, overflow: 'hidden', boxShadow: '0 2px 12px rgba(0,0,0,0.18)', flexShrink: 0 }}
              />
            ))}
          </div>
        ) : (
          <div style={{ padding: 16, display: 'flex', justifyContent: 'center', minWidth: 'fit-content' }}>
            <img
              src={info.file_url}
              alt={`${info.title} 이용 가이드북`}
              style={{ width: zoom === 1 ? 'auto' : `${zoom * 100}%`, maxWidth: zoom === 1 ? '100%' : 'none', borderRadius: 4, boxShadow: '0 2px 12px rgba(0,0,0,0.18)', background: '#fff' }}
            />
          </div>
        )}
      </div>
    </View>
  );
}

function Tool({ icon: I, label, onPress, disabled, iconOnly, primary }: { icon: Icon; label: string; onPress: () => void; disabled?: boolean; iconOnly?: boolean; primary?: boolean }) {
  const t = useTheme();
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      {...({ title: label } as any)}
      style={({ hovered }: any) => ({
        flexDirection: 'row', alignItems: 'center', gap: 6, height: 34, paddingHorizontal: iconOnly ? 8 : 12, borderRadius: radius.control,
        backgroundColor: primary ? t.accent : hovered && !disabled ? t.surfaceAlt : 'transparent', opacity: disabled ? 0.35 : 1,
      })}
    >
      <I size={18} color={primary ? t.accentText : t.textSub} weight="bold" />
      {!iconOnly && <Text style={{ fontFamily: font.family, fontSize: 13.5, fontWeight: '700', color: primary ? t.accentText : t.textSub }}>{label}</Text>}
    </Pressable>
  );
}

// 쪽 번호를 직접 입력해서 이동
function PageInput({ page, total, onGo }: { page: number; total: number; onGo: (n: number) => void }) {
  const t = useTheme();
  const [text, setText] = useState(String(page));
  useEffect(() => setText(String(page)), [page]);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
      <input
        value={text}
        inputMode="numeric"
        aria-label="쪽 번호"
        onChange={(e) => setText(e.target.value.replace(/\D/g, ''))}
        onKeyDown={(e) => e.key === 'Enter' && text && onGo(Number(text))}
        onBlur={() => setText(String(page))}
        style={{ width: 40, height: 28, textAlign: 'center', fontFamily: font.mono, fontSize: 13, color: t.text, background: t.surfaceAlt, border: `1px solid ${t.border}`, borderRadius: 6, outline: 'none' }}
      />
      <Text style={{ fontFamily: font.mono, fontSize: 13, color: t.textMuted }}>/ {total}</Text>
    </View>
  );
}

// 상세 페이지용 미리보기: PDF 첫 쪽(또는 이미지)을 작게 그린다
export function GuideFirstPage({ fileUrl, kind, width }: { fileUrl: string; kind: 'pdf' | 'image'; width: number }) {
  const t = useTheme();
  const box = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<'loading' | 'ok' | 'error'>(kind === 'pdf' ? 'loading' : 'ok');
  const [pages, setPages] = useState(0);

  useEffect(() => {
    if (kind !== 'pdf' || !width) return;
    let cancelled = false;
    let task: any;
    loadPdfjs()
      .then(async (pdfjs) => {
        task = pdfjs.getDocument({ url: fileUrl, isEvalSupported: false, disableRange: true, disableStream: true });
        const d = await task.promise;
        const p = await d.getPage(1);
        const vp = p.getViewport({ scale: width / p.getViewport({ scale: 1 }).width });
        const ratio = window.devicePixelRatio || 1;
        const canvas = document.createElement('canvas');
        canvas.width = Math.floor(vp.width * ratio);
        canvas.height = Math.floor(vp.height * ratio);
        canvas.style.width = '100%';
        canvas.style.display = 'block';
        await p.render({ canvasContext: canvas.getContext('2d')!, viewport: vp, transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined }).promise;
        if (cancelled) return;
        box.current?.replaceChildren(canvas);
        setPages(d.numPages);
        setState('ok');
      })
      .catch(() => !cancelled && setState('error'));
    return () => {
      cancelled = true;
      task?.destroy?.();
    };
  }, [fileUrl, kind, width]);

  return (
    <View style={{ borderRadius: radius.control, overflow: 'hidden', backgroundColor: '#fff', borderWidth: 1, borderColor: t.border }}>
      {kind === 'image' ? (
        <img src={fileUrl} alt="이용 가이드북 미리보기" style={{ width: '100%', display: 'block', maxHeight: 520, objectFit: 'cover', objectPosition: 'top' }} />
      ) : (
        <>
          <div ref={box} style={{ maxHeight: 520, overflow: 'hidden' }} />
          {state === 'loading' && <Skeleton h={Math.round(width * 1.3)} r={0} />}
          {state === 'error' && (
            <View style={{ padding: 28, alignItems: 'center', gap: 8, backgroundColor: t.surfaceAlt }}>
              <BookOpen size={32} color={t.textMuted} weight="duotone" />
              <T variant="small">미리보기를 그리지 못했어요. 열기를 눌러 보세요.</T>
            </View>
          )}
          {pages > 1 && (
            <View style={{ position: 'absolute', right: 10, bottom: 10, backgroundColor: 'rgba(24,24,27,0.72)', borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4 }}>
              <Text style={{ fontFamily: font.family, color: '#f4f4f5', fontSize: 12.5, fontWeight: '700' }}>{pages}쪽</Text>
            </View>
          )}
        </>
      )}
    </View>
  );
}
