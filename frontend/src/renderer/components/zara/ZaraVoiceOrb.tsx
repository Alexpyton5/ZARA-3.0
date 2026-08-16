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

interface Filament {
  band: 0 | 1;
  radialOffset: number;
  amplitude: number;
  temporalFrequency: number;
  drift: number;
  phase: number;
  width: number;
  alpha: number;
  harmonicA: number;
  harmonicB: number;
  harmonicC: number;
}

interface Particle {
  angle: number;
  angularSpeed: number;
  radialBase: number;
  radialAmplitude: number;
  radialFrequency: number;
  size: number;
  alpha: number;
  phase: number;
  twinkleSpeed: number;
  spin: number;
  spinSpeed: number;
}

interface Point {
  x: number;
  y: number;
}

const TAU = Math.PI * 2;
const SAMPLE_COUNT = 220;
const PARTICLE_COUNT = 42;

// The two original band radii are preserved. Extra filaments live inside a very small
// envelope around those exact radii so the perceived circle/silhouette does not change.
const FILAMENTS: readonly Filament[] = [
  { band: 0, radialOffset: -0.0022, amplitude: 0.72, temporalFrequency: 0.73, drift: 0.72, phase: 0.28, width: 0.55, alpha: 0.34, harmonicA: 7, harmonicB: 15, harmonicC: 27 },
  { band: 0, radialOffset: 0, amplitude: 1, temporalFrequency: 1.07, drift: 0.91, phase: 1.46, width: 1.12, alpha: 0.92, harmonicA: 6, harmonicB: 13, harmonicC: 23 },
  { band: 0, radialOffset: 0.0024, amplitude: 0.79, temporalFrequency: 1.34, drift: 1.08, phase: 3.18, width: 0.62, alpha: 0.43, harmonicA: 8, harmonicB: 17, harmonicC: 29 },
  { band: 1, radialOffset: -0.0025, amplitude: 0.76, temporalFrequency: 0.82, drift: 0.78, phase: 4.14, width: 0.58, alpha: 0.37, harmonicA: 5, harmonicB: 14, harmonicC: 25 },
  { band: 1, radialOffset: 0, amplitude: 0.91, temporalFrequency: 1.18, drift: 0.96, phase: 2.12, width: 0.92, alpha: 0.72, harmonicA: 7, harmonicB: 16, harmonicC: 26 },
  { band: 1, radialOffset: 0.0021, amplitude: 0.68, temporalFrequency: 1.43, drift: 1.13, phase: 5.37, width: 0.52, alpha: 0.32, harmonicA: 9, harmonicB: 19, harmonicC: 31 },
] as const;

const INNER_CARRIER = FILAMENTS[1];
const OUTER_CARRIER = FILAMENTS[4];

function clamp(value: number, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value));
}

function lerp(a: number, b: number, amount: number) {
  return a + (b - a) * amount;
}

function wrapAngle(angle: number) {
  const wrapped = angle % TAU;
  return wrapped < 0 ? wrapped + TAU : wrapped;
}

function sequenceValue(index: number, salt: number) {
  const value = Math.sin((index + 1) * (12.9898 + salt * 7.233)) * 43758.5453;
  return value - Math.floor(value);
}

function makeParticles(): Particle[] {
  return Array.from({ length: PARTICLE_COUNT }, (_, index) => {
    const a = sequenceValue(index, 0.11);
    const b = sequenceValue(index, 0.37);
    const c = sequenceValue(index, 0.73);
    const d = sequenceValue(index, 1.17);
    const direction = a > 0.47 ? 1 : -1;

    return {
      angle: TAU * b,
      angularSpeed: direction * (0.045 + c * 0.125),
      radialBase: 0.08 + d * 0.84,
      radialAmplitude: 0.09 + a * 0.24,
      radialFrequency: 0.12 + b * 0.26,
      size: 0.48 + c * 0.78,
      alpha: 0.28 + d * 0.58,
      phase: TAU * a,
      twinkleSpeed: 1.25 + b * 2.2,
      spin: TAU * d,
      spinSpeed: direction * (0.18 + c * 0.58),
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

function vibrationSpeed(state: ZaraVoiceState, level: number, reducedMotion: boolean) {
  if (reducedMotion) return 0;
  switch (state) {
    case 'SPEAKING': return 0.86 + clamp(level) * 1.18;
    case 'LISTENING': return 0.64 + clamp(level) * 0.48;
    case 'THINKING':
    case 'PROCESSING': return 0.58;
    case 'MUTED':
    case 'SLEEPING': return 0.08;
    default: return 0.32;
  }
}

function rotationSpeed(state: ZaraVoiceState, level: number, reducedMotion: boolean) {
  if (reducedMotion) return 0;
  const audio = clamp(level);
  switch (state) {
    case 'SPEAKING': return 0.075 + audio * 0.035;
    case 'LISTENING': return 0.064 + audio * 0.018;
    case 'THINKING':
    case 'PROCESSING': return 0.07;
    case 'MUTED':
    case 'SLEEPING': return 0.026;
    default: return 0.052;
  }
}

function filamentRadius(
  theta: number,
  filament: Filament,
  size: number,
  energy: number,
  vibrationClock: number,
  rotation: number,
) {
  const baseRadius = size * (filament.band === 0 ? 0.302 : 0.347);
  const localTheta = theta - rotation * filament.drift;
  const clock = vibrationClock * filament.temporalFrequency + filament.phase;

  // Higher spatial harmonics and much smaller displacement make the lines visibly vibrate
  // instead of bending together like rubber. Every filament owns its own oscillator.
  const wave =
    Math.sin(localTheta * filament.harmonicA + clock) * 0.46 +
    Math.sin(localTheta * filament.harmonicB - clock * 0.71 + filament.phase * 0.37) * 0.31 +
    Math.sin(localTheta * filament.harmonicC + clock * 0.43 - filament.phase * 0.22) * 0.23;

  const micro =
    Math.sin(localTheta * (filament.harmonicC + 8) - clock * 1.31) * 0.58 +
    Math.sin(localTheta * (filament.harmonicB + 13) + clock * 1.67) * 0.42;

  const vibrationAmplitude = size * (0.0007 + energy * 0.0046) * filament.amplitude;
  const microAmplitude = size * (0.00028 + energy * 0.00145) * filament.amplitude;

  return baseRadius + size * filament.radialOffset + wave * vibrationAmplitude + micro * microAmplitude;
}

function pointOnFilament(
  theta: number,
  filament: Filament,
  centerX: number,
  centerY: number,
  size: number,
  energy: number,
  vibrationClock: number,
  rotation: number,
): Point {
  const radius = filamentRadius(theta, filament, size, energy, vibrationClock, rotation);
  return {
    x: centerX + Math.cos(theta) * radius,
    y: centerY + Math.sin(theta) * radius,
  };
}

function particlePoint(
  particle: Particle,
  timeSeconds: number,
  centerX: number,
  centerY: number,
  size: number,
  energy: number,
  vibrationClock: number,
  rotation: number,
): Point {
  const radialTravel = Math.sin(timeSeconds * particle.radialFrequency + particle.phase) * particle.radialAmplitude;
  const transfer = clamp(particle.radialBase + radialTravel, 0.025, 0.975);
  const inner = filamentRadius(particle.angle, INNER_CARRIER, size, energy, vibrationClock, rotation);
  const outer = filamentRadius(particle.angle, OUTER_CARRIER, size, energy, vibrationClock, rotation);
  const crossCurrent = Math.sin(timeSeconds * 0.31 + particle.phase * 1.7) * size * (0.0007 + energy * 0.0012);
  const radius = lerp(inner, outer, transfer) + crossCurrent;

  return {
    x: centerX + Math.cos(particle.angle) * radius,
    y: centerY + Math.sin(particle.angle) * radius,
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
    let vibrationClock = 0;
    let rotation = 0;

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

    const drawFilament = (
      filament: Filament,
      centerX: number,
      centerY: number,
      size: number,
      currentEnergy: number,
      currentClock: number,
      currentRotation: number,
      color: string,
      glowColor: string,
      opacityScale: number,
    ) => {
      context.beginPath();
      for (let index = 0; index <= SAMPLE_COUNT; index += 1) {
        const theta = (index / SAMPLE_COUNT) * TAU;
        const point = pointOnFilament(
          theta,
          filament,
          centerX,
          centerY,
          size,
          currentEnergy,
          currentClock,
          currentRotation,
        );
        if (index === 0) context.moveTo(point.x, point.y);
        else context.lineTo(point.x, point.y);
      }
      context.closePath();
      context.globalAlpha = filament.alpha * opacityScale;
      context.strokeStyle = color;
      context.lineWidth = filament.width;
      context.shadowColor = glowColor;
      context.shadowBlur = 2.4 + currentEnergy * 5.8;
      context.stroke();
      context.shadowBlur = 0;
    };

    const drawLightFlake = (
      particle: Particle,
      point: Point,
      radius: number,
      alpha: number,
      color: string,
      glowColor: string,
    ) => {
      context.save();
      context.translate(point.x, point.y);
      context.rotate(particle.spin);
      context.globalAlpha = alpha;
      context.fillStyle = color;
      context.shadowColor = glowColor;
      context.shadowBlur = 2.2 + radius * 2.2;
      context.beginPath();
      context.moveTo(0, -radius * 1.7);
      context.lineTo(radius * 0.48, -radius * 0.32);
      context.lineTo(radius * 1.45, 0);
      context.lineTo(radius * 0.42, radius * 0.28);
      context.lineTo(0, radius * 1.55);
      context.lineTo(-radius * 0.42, radius * 0.28);
      context.lineTo(-radius * 1.45, 0);
      context.lineTo(-radius * 0.48, -radius * 0.32);
      context.closePath();
      context.fill();
      context.restore();
    };

    const draw = (time: number) => {
      const elapsed = Math.min(0.05, Math.max(0.001, (time - previousTime) / 1000));
      previousTime = time;
      const timeSeconds = time / 1000;
      const live = liveRef.current;
      const target = stateTarget(live.state, live.level, reducedMotion);

      // First-order damping keeps the response organic without spring overshoot.
      const responseRate = target > energy ? 8.4 : 4.6;
      energy += (target - energy) * (1 - Math.exp(-responseRate * elapsed));
      vibrationClock += vibrationSpeed(live.state, live.level, reducedMotion) * elapsed;
      rotation = wrapAngle(rotation + rotationSpeed(live.state, live.level, reducedMotion) * elapsed);

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

      // Preserve the existing diffuse halo and the empty center: no new orb/circle layer.
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

      const opacityScale = muted ? 0.36 : 1;
      FILAMENTS.forEach((filament) => {
        const color = filament.band === 0 ? palette.primary : palette.secondary;
        drawFilament(
          filament,
          centerX,
          centerY,
          size,
          energy,
          vibrationClock,
          rotation,
          color,
          palette.glow,
          opacityScale,
        );
      });

      const particleEnergy = 0.58 + energy * 1.42;
      particlesRef.current.forEach((particle, index) => {
        particle.angle = wrapAngle(particle.angle + particle.angularSpeed * elapsed * particleEnergy);
        particle.spin = wrapAngle(particle.spin + particle.spinSpeed * elapsed * (0.55 + energy * 0.7));

        const point = particlePoint(
          particle,
          timeSeconds,
          centerX,
          centerY,
          size,
          energy,
          vibrationClock,
          rotation,
        );
        const twinkle = 0.73 + Math.sin(timeSeconds * particle.twinkleSpeed + particle.phase + index * 0.19) * 0.19;
        const radius = particle.size * (0.72 + energy * 0.34);
        const alpha = (muted ? 0.1 : particle.alpha) * twinkle;
        const color = index % 4 === 0 ? palette.secondary : palette.particle;

        drawLightFlake(particle, point, radius, alpha, color, palette.glow);
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
