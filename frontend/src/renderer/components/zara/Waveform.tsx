import React, { useEffect, useRef, useMemo } from 'react';
import './Waveform.css';

/**
 * ZARA Waveform — Visualizador de forma de onda de áudio
 * 
 * Dois modos:
 * - 'bars': Barras verticais estilo equalizador (padrão)
 * - 'wave': Forma de onda contínua estilo osciloscópio
 * - 'ring': Anel radial (estilo orb simplificado)
 * 
 * Usa design tokens e respeita prefers-reduced-motion
 */

export type WaveformMode = 'bars' | 'wave' | 'ring';
export type WaveformDirection = 'up' | 'down' | 'center' | 'mirror';

export interface WaveformProps {
  /** Nível de áudio 0-1 (pode ser array para múltiplas bandas) */
  level: number | number[];
  /** Modo visual */
  mode?: WaveformMode;
  /** Direção das barras (para mode='bars') */
  direction?: WaveformDirection;
  /** Número de barras (para mode='bars') */
  barCount?: number;
  /** Cor do accent (usa token se omitido) */
  accentColor?: string;
  /** Cor de fundo das barras inativas */
  trackColor?: string;
  /** Altura do componente */
  height?: number | string;
  /** Largura do componente */
  width?: number | string;
  /** Suavização da animação (0-1, maior = mais suave) */
  smoothing?: number;
  /** Mostrar grade de referência */
  showGrid?: boolean;
  /** Modo "ao vivo" - anima mesmo com level constante */
  live?: boolean;
  /** Velocidade da animação live (ms por frame) */
  liveSpeed?: number;
  /** ClassName adicional */
  className?: string;
  /** Style adicional */
  style?: React.CSSProperties;
  /** Callback quando nível passa threshold */
  onThreshold?: (exceeded: boolean) => void;
  /** Threshold para callback (0-1) */
  threshold?: number;
}

const DEFAULT_BAR_COUNT = 32;
const DEFAULT_SMOOTHING = 0.85;
const DEFAULT_LIVE_SPEED = 50;

/** Gera níveis aleatórios para modo live */
function generateLiveLevels(count: number, baseLevel: number): number[] {
  return Array.from({ length: count }, (_, i) => {
    const variance = 0.3 + Math.random() * 0.4;
    const decay = Math.pow(0.7, i / count * 3);
    return Math.max(0, Math.min(1, baseLevel * variance * decay + Math.random() * 0.1));
  });
}

/** Normaliza entrada para array de níveis */
function normalizeLevels(level: number | number[], count: number): number[] {
  if (Array.isArray(level)) {
    // Interpola ou trunca para count barras
    if (level.length === count) return level.map(l => Math.max(0, Math.min(1, l)));
    const result: number[] = [];
    for (let i = 0; i < count; i++) {
      const srcIndex = (i / count) * (level.length - 1);
      const idx0 = Math.floor(srcIndex);
      const idx1 = Math.min(idx0 + 1, level.length - 1);
      const t = srcIndex - idx0;
      result.push(Math.max(0, Math.min(1, level[idx0] * (1 - t) + level[idx1] * t)));
    }
    return result;
  }
  // Level único - distribui com decaimento
  const base = Math.max(0, Math.min(1, level));
  return Array.from({ length: count }, (_, i) => 
    base * Math.pow(0.8, i / count * 2)
  );
}

export const Waveform: React.FC<WaveformProps> = ({
  level,
  mode = 'bars',
  direction = 'up',
  barCount = DEFAULT_BAR_COUNT,
  accentColor,
  trackColor,
  height = 60,
  width = '100%',
  smoothing = DEFAULT_SMOOTHING,
  showGrid = false,
  live = false,
  liveSpeed = DEFAULT_LIVE_SPEED,
  className = '',
  style,
  onThreshold,
  threshold = 0.7,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();
  const livePhaseRef = useRef(0);
  const thresholdTriggeredRef = useRef(false);

  // Resolve cores dos tokens se não passadas
  const resolvedAccentColor = useMemo(() => 
    accentColor || 'var(--accent-primary, #8FC17F)', [accentColor]);
  const resolvedTrackColor = useMemo(() => 
    trackColor || 'var(--border-subtle, rgba(190,211,184,0.11))', [trackColor]);

  // Normaliza níveis
  const targetLevels = useMemo(() => normalizeLevels(level, barCount), [level, barCount]);

  // Verifica threshold
  useEffect(() => {
    if (!onThreshold) return;
    const maxLevel = Math.max(...targetLevels);
    const exceeded = maxLevel >= threshold;
    if (exceeded !== thresholdTriggeredRef.current) {
      thresholdTriggeredRef.current = exceeded;
      onThreshold(exceeded);
    }
  }, [targetLevels, onThreshold, threshold]);

  // Loop de animação
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
    let reducedMotion = prefersReducedMotion;
    const updateMotion = () => { reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false; };
    window.matchMedia?.('(prefers-reduced-motion: reduce)')?.addEventListener?.('change', updateMotion);

    let lastTime = performance.now();
    let currentLevels = new Array(barCount).fill(0);

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const drawBars = (levels: number[], w: number, h: number) => {
      const barWidth = Math.max(1, w / barCount * 0.7);
      const gap = (w - barWidth * barCount) / (barCount + 1);
      const maxHeight = h * 0.9;

      ctx.clearRect(0, 0, w, h);

      // Grid
      if (showGrid) {
        ctx.strokeStyle = 'var(--border-subtle, rgba(190,211,184,0.08))';
        ctx.lineWidth = 1;
        for (let i = 1; i < 4; i++) {
          const y = (h / 4) * i;
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(w, y);
          ctx.stroke();
        }
      }

      // Track (fundo)
      ctx.fillStyle = resolvedTrackColor;
      for (let i = 0; i < barCount; i++) {
              const x = gap + i * (barWidth + gap);

              switch (direction) {
                case 'up':
                case 'down':
                case 'center':
                case 'mirror':
                  break;
              }

              const targetH = levels[i] * maxHeight;
        
        if (direction === 'center') {
          ctx.fillRect(x, h / 2 - targetH / 2, barWidth, targetH);
        } else if (direction === 'mirror') {
          ctx.fillRect(x, h / 2 - targetH, barWidth, targetH * 2);
        } else {
          const actualY = direction === 'up' ? h - targetH - 2 : 2;
          const actualH = targetH;
          ctx.fillRect(x, actualY, barWidth, actualH);
        }
      }

      // Barras ativas (accent)
      ctx.fillStyle = resolvedAccentColor;
      for (let i = 0; i < barCount; i++) {
        const x = gap + i * (barWidth + gap);
        const targetH = levels[i] * maxHeight;

        if (direction === 'up') {
          ctx.fillRect(x, h - targetH - 2, barWidth, targetH);
        } else if (direction === 'down') {
          ctx.fillRect(x, 2, barWidth, targetH);
        } else if (direction === 'center') {
          ctx.fillRect(x, h / 2 - targetH / 2, barWidth, targetH);
        } else if (direction === 'mirror') {
          ctx.fillRect(x, h / 2 - targetH, barWidth, targetH * 2);
        }
      }

      // Pico (linha no topo da barra)
      ctx.fillStyle = 'var(--text-on-accent, white)';
      for (let i = 0; i < barCount; i++) {
        if (levels[i] > 0.15) {
          const x = gap + i * (barWidth + gap);
          const targetH = levels[i] * maxHeight;
          let peakY: number;
          
          if (direction === 'up') peakY = h - targetH - 2;
          else if (direction === 'down') peakY = 2 + targetH;
          else if (direction === 'center') peakY = h / 2 - targetH / 2;
          else peakY = h / 2 - targetH;
          
          ctx.fillRect(x, peakY, barWidth, Math.max(1, barWidth * 0.3));
        }
      }
    };

    const drawWave = (levels: number[], w: number, h: number) => {
      ctx.clearRect(0, 0, w, h);
      
      if (showGrid) {
        ctx.strokeStyle = 'var(--border-subtle, rgba(190,211,184,0.08))';
        ctx.lineWidth = 1;
        for (let i = 1; i < 4; i++) {
          const y = (h / 4) * i;
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(w, y);
          ctx.stroke();
        }
        ctx.beginPath();
        ctx.moveTo(0, h / 2);
        ctx.lineTo(w, h / 2);
        ctx.stroke();
      }

      // Track
      ctx.strokeStyle = resolvedTrackColor;
      ctx.lineWidth = 2;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      ctx.moveTo(0, h / 2);
      for (let i = 0; i < barCount; i++) {
        const x = (i / (barCount - 1)) * w;
        ctx.lineTo(x, h / 2);
      }
      ctx.stroke();

      // Wave
      ctx.strokeStyle = resolvedAccentColor;
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(0, h / 2);
      for (let i = 0; i < barCount; i++) {
        const x = (i / (barCount - 1)) * w;
        const y = h / 2 - levels[i] * h * 0.4;
        ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Mirror abaixo
      ctx.globalAlpha = 0.3;
      ctx.beginPath();
      ctx.moveTo(0, h / 2);
      for (let i = 0; i < barCount; i++) {
        const x = (i / (barCount - 1)) * w;
        const y = h / 2 + levels[i] * h * 0.4;
        ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
    };

    const drawRing = (levels: number[], w: number, h: number) => {
      const size = Math.min(w, h);
      const cx = w / 2;
      const cy = h / 2;
      const innerRadius = size * 0.25;
      const outerRadius = size * 0.45;
      const maxAmplitude = (outerRadius - innerRadius) * 0.8;

      ctx.clearRect(0, 0, w, h);

      // Track ring
      ctx.strokeStyle = resolvedTrackColor;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cx, cy, (innerRadius + outerRadius) / 2, 0, Math.PI * 2);
      ctx.stroke();

      // Active segments
      const segmentAngle = (Math.PI * 2) / barCount;
      ctx.strokeStyle = resolvedAccentColor;
      ctx.lineWidth = 3;
      ctx.lineCap = 'round';

      for (let i = 0; i < barCount; i++) {
        const angle = i * segmentAngle - Math.PI / 2;
        const amplitude = levels[i] * maxAmplitude;
        const r1 = innerRadius;
        const r2 = innerRadius + amplitude;

        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(angle) * r1, cy + Math.sin(angle) * r1);
        ctx.lineTo(cx + Math.cos(angle) * r2, cy + Math.sin(angle) * r2);
        ctx.stroke();
      }

      // Center dot
      ctx.fillStyle = resolvedAccentColor;
      ctx.beginPath();
      ctx.arc(cx, cy, innerRadius * 0.4, 0, Math.PI * 2);
      ctx.fill();
    };

    const animate = (time: number) => {
      const elapsed = Math.min(0.1, (time - lastTime) / 1000);
      lastTime = time;

      const canvasRect = canvas.getBoundingClientRect();
      const w = canvasRect.width;
      const h = canvasRect.height;

      if (live && !reducedMotion) {
        // Modo live: gera níveis sintéticos baseados no level médio
        const avgLevel = targetLevels.reduce((a, b) => a + b, 0) / targetLevels.length;
        livePhaseRef.current += elapsed * (liveSpeed / 1000) * 2 * Math.PI;
        const syntheticLevels = generateLiveLevels(barCount, avgLevel);
        
        // Modula com fase
        for (let i = 0; i < barCount; i++) {
          const phaseOffset = (i / barCount) * Math.PI * 2;
          const modulation = 0.7 + 0.3 * Math.sin(livePhaseRef.current + phaseOffset);
          currentLevels[i] = syntheticLevels[i] * modulation;
        }
      } else {
        // Modo normal: suaviza para targetLevels
        for (let i = 0; i < barCount; i++) {
          currentLevels[i] += (targetLevels[i] - currentLevels[i]) * (1 - Math.pow(smoothing, elapsed * 60));
        }
      }

      // Desenha baseado no modo
      switch (mode) {
        case 'wave':
          drawWave(currentLevels, w, h);
          break;
        case 'ring':
          drawRing(currentLevels, w, h);
          break;
        case 'bars':
        default:
          drawBars(currentLevels, w, h);
          break;
      }

      animationRef.current = requestAnimationFrame(animate);
    };

    resize();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
    window.addEventListener('resize', resize);

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animationRef.current!);
      resizeObserver.disconnect();
      window.removeEventListener('resize', resize);
      window.matchMedia?.('(prefers-reduced-motion: reduce)')?.removeEventListener?.('change', updateMotion);
    };
  }, [mode, direction, barCount, resolvedAccentColor, resolvedTrackColor, height, width, smoothing, showGrid, live, liveSpeed, targetLevels]);

  const modeClass = `waveform--${mode}`;
  const directionClass = mode === 'bars' ? `waveform--${direction}` : '';

  return (
    <canvas
      ref={canvasRef}
      className={`waveform ${modeClass} ${directionClass} ${className}`}
      style={{
        width,
        height,
        display: 'block',
        ...style,
      }}
      aria-hidden="true"
      role="img"
      aria-label={`Visualizador de áudio: ${mode}, nível ${Array.isArray(level) ? 'múltiplas bandas' : Math.round(level * 100)}%`}
    />
  );
};

export default Waveform;