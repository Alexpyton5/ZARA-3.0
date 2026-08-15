import React, { useEffect, useRef } from 'react';

export type ZaraVoiceState =
  | 'STANDBY'
  | 'IDLE'
  | 'LISTENING'
  | 'THINKING'
  | 'SPEAKING'
  | 'PROCESSING'
  | 'SLEEPING'
  | 'MUTED';

export type ZaraOrbTheme = 'light' | 'dark';

interface ZaraVoiceOrbProps {
  state: ZaraVoiceState;
  level: number;
  theme: ZaraOrbTheme;
}

interface Particle {
  angle: number;
  speed: number;
  cord: 0 | 1;
  size: number;
  alpha: number;
  phase: number;
}

interface Point {
  x: number;
  y: number;
}

const TAU = Math.PI * 2;
const SAMPLE_COUNT = 196;
const PARTICLE_COUNT = 34;

function clamp(value: number, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value));
}

function makeParticles(): Particle[] {
  const golden = 0.6180339887498949;
  return Array.from({ length: PARTICLE_COUNT }, (_, index) => {
    const sequence = (index * golden) % 1;
    return {
      angle: TAU * ((index / PARTICLE_COUNT + sequence * 0.17) % 1),
      speed: 0.12 + (index % 7) * 0.018,
      cord: (index % 3 === 0 ? 1 : 0) as 0 | 1,
      size: 0.62 + (index % 5) * 0.13,
      alpha: 0.38 + (index % 6) * 0.075,
      phase: TAU * sequence,
    };
  });
}

function stateTarget(state: ZaraVoiceState, level: number, reducedMotion: boolean) {
  if (reducedMotion) return state === 'MUTED' || state === 'SLEEPING' ? 0.015 : 0.055;

  const audio = clamp(level);
  switch (state) {
    case 'SPEAKING':
      return 0.16 + Math.pow(audio, 0.72) * 0.84;
    case 'LISTENING':
      return 0.10 + Math.pow(audio, 0.78) * 0.48;
    case 'THINKING':
    case 'PROCESSING':
      return 0.25;
    case 'MUTED':
    case 'SLEEPING':
      return 0.012;
    case 'IDLE':
    case 'STANDBY':
    default:
      return 0.045;
  }
}

function stateSpeed(state: ZaraVoiceState, level: number, reducedMotion: boolean) {
  if (reducedMotion) return 0;
  switch (state) {
    case 'SPEAKING': return 1.12 + clamp(level) * 1.55;
    case 'LISTENING': return 0.72 + clamp(level) * 0.38;
    case 'THINKING':
    case 'PROCESSING': return 0.62;
    case 'MUTED':
    case 'SLEEPING': return 0.06;
    default: return 0.18;
  }
}

function pointOnCord(
  theta: number,
  cord: 0 | 1,
  centerX: number,
  centerY: number,
  size: number,
  energy: number,
  phase: number,
): Point {
  const baseRadius = size * (cord === 0 ? 0.302 : 0.347);
  const cordShift = cord === 0 ? 0 : 0.58;
  const amplitude = size * (0.0034 + energy * 0.0165);

  // Three low-amplitude harmonics keep the ring organic without making it wobble as one rigid object.
  const wave =
    Math.sin(theta * 3 + phase * 1.08 + cordShift) * 0.54 +
    Math.sin(theta * 7 - phase * 0.66 + cordShift * 1.8) * 0.30 +
    Math.sin(theta * 11 + phase * 0.31 - cordShift) * 0.16;
  const micro = Math.sin(theta * 17 - phase * 0.19 + cordShift) * size * 0.00085;
  const radius = baseRadius + wave * amplitude + micro;

  return {
    x: centerX + Math.cos(theta) * radius,
    y: centerY + Math.sin(theta) * radius,
  };
}

export const ZaraVoiceOrb: React.FC<ZaraVoiceOrbProps> = ({ state, level, theme }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const liveRef = useRef({ state, level: clamp(level), theme });
  const particlesRef = useRef<Particle[]>(makeParticles());

  useEffect(() => {
    liveRef.current = { state, level: clamp(level), theme };
  }, [state, level, theme]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    const motionQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    let reducedMotion = Boolean(motionQuery?.matches);
    const updateMotionPreference = () => { reducedMotion = Boolean(motionQuery?.matches); };
    motionQuery?.addEventListener?.('change', updateMotionPreference);

    let cssWidth = 1;
    let cssHeight = 1;
    let dpr = 1;
    let frameId = 0;
    let previousTime = performance.now();
    let energy = 0.045;
    let phase = 0;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      cssWidth = Math.max(1, rect.width);
      cssHeight = Math.max(1, rect.height);
      dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));
      const nextWidth = Math.round(cssWidth * dpr);
      const nextHeight = Math.round(cssHeight * dpr);
      if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
        canvas.width = nextWidth;
        canvas.height = nextHeight;
      }
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.lineCap = 'round';
      context.lineJoin = 'round';
    };

    const resizeObserver = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    resizeObserver?.observe(canvas);
    window.addEventListener('resize', resize);
    resize();

    const drawCord = (
      cord: 0 | 1,
      centerX: number,
      centerY: number,
      size: number,
      currentEnergy: number,
      currentPhase: number,
      color: string,
      glowColor: string,
      opacity: number,
    ) => {
      context.beginPath();
      for (let index = 0; index <= SAMPLE_COUNT; index += 1) {
        const theta = (index / SAMPLE_COUNT) * TAU;
        const point = pointOnCord(theta, cord, centerX, centerY, size, currentEnergy, currentPhase);
        if (index === 0) context.moveTo(point.x, point.y);
        else context.lineTo(point.x, point.y);
      }
      context.closePath();
      context.globalAlpha = opacity;
      context.strokeStyle = color;
      context.lineWidth = cord === 0 ? 1.45 : 1.05;
      context.shadowColor = glowColor;
      context.shadowBlur = 3.5 + currentEnergy * 8.5;
      context.stroke();
      context.shadowBlur = 0;
    };

    const draw = (time: number) => {
      const elapsed = Math.min(0.05, Math.max(0.001, (time - previousTime) / 1000));
      previousTime = time;
      const live = liveRef.current;
      const target = stateTarget(live.state, live.level, reducedMotion);

      // First-order exponential smoothing cannot overshoot the target: no spring bounce, no hard snap.
      const responseRate = target > energy ? 8.4 : 4.6;
      energy += (target - energy) * (1 - Math.exp(-responseRate * elapsed));
      phase += stateSpeed(live.state, live.level, reducedMotion) * elapsed;

      context.clearRect(0, 0, cssWidth, cssHeight);
      const centerX = cssWidth / 2;
      const centerY = cssHeight / 2;
      const size = Math.min(cssWidth, cssHeight);
      const muted = live.state === 'MUTED' || live.state === 'SLEEPING';
      const dark = live.theme === 'dark';

      const palette = dark
        ? {
            primary: 'rgba(177, 207, 164, .98)',
            secondary: 'rgba(226, 235, 222, .86)',
            glow: 'rgba(162, 203, 145, .72)',
            particle: 'rgba(225, 239, 219, .98)',
          }
        : {
            primary: 'rgba(113, 83, 107, .96)',
            secondary: 'rgba(194, 175, 145, .86)',
            glow: 'rgba(150, 108, 140, .58)',
            particle: 'rgba(130, 91, 121, .96)',
          };

      // Only a diffuse outer glow is drawn; there is deliberately no inner orb/circle layer.
      const halo = context.createRadialGradient(
        centerX,
        centerY,
        size * 0.255,
        centerX,
        centerY,
        size * 0.405,
      );
      halo.addColorStop(0, 'rgba(255,255,255,0)');
      halo.addColorStop(0.68, dark ? `rgba(150,190,136,${0.018 + energy * 0.05})` : `rgba(137,96,128,${0.014 + energy * 0.042})`);
      halo.addColorStop(1, 'rgba(255,255,255,0)');
      context.globalAlpha = muted ? 0.3 : 1;
      context.fillStyle = halo;
      context.fillRect(0, 0, cssWidth, cssHeight);

      drawCord(1, centerX, centerY, size, energy * 0.88, phase * 0.91, palette.secondary, palette.glow, muted ? 0.28 : 0.72);
      drawCord(0, centerX, centerY, size, energy, phase, palette.primary, palette.glow, muted ? 0.34 : 0.9);

      const particleSpeed = reducedMotion ? 0 : (0.62 + energy * 1.9);
      particlesRef.current.forEach((particle, index) => {
        particle.angle = (particle.angle + particle.speed * elapsed * particleSpeed) % TAU;
        const particlePhase = phase + particle.phase * 0.08;
        const point = pointOnCord(
          particle.angle,
          particle.cord,
          centerX,
          centerY,
          size,
          energy,
          particlePhase,
        );
        const flicker = 0.72 + Math.sin(time * 0.0035 + particle.phase + index * 0.37) * 0.18;
        const radius = particle.size * (0.86 + energy * 0.48);

        context.beginPath();
        context.globalAlpha = (muted ? 0.12 : particle.alpha) * flicker;
        context.fillStyle = particle.cord === 0 ? palette.particle : palette.secondary;
        context.shadowColor = palette.glow;
        context.shadowBlur = 2 + energy * 5;
        context.arc(point.x, point.y, radius, 0, TAU);
        context.fill();
      });

      context.globalAlpha = 1;
      context.shadowBlur = 0;
      frameId = window.requestAnimationFrame(draw);
    };

    frameId = window.requestAnimationFrame(draw);
    return () => {
      window.cancelAnimationFrame(frameId);
      resizeObserver?.disconnect();
      window.removeEventListener('resize', resize);
      motionQuery?.removeEventListener?.('change', updateMotionPreference);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{ width: '100%', height: '100%', display: 'block' }}
    />
  );
};
