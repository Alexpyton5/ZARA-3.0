import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';

export type VoiceState = 'STANDBY' | 'IDLE' | 'LISTENING' | 'THINKING' | 'SPEAKING' | 'PROCESSING' | 'SLEEPING' | 'MUTED';

interface VoiceParticleSphereProps {
  level: number;
  state: VoiceState;
}

const vertexShader = `
  uniform float uTime;
  uniform float uLevel;
  uniform float uMode;
  attribute float aPhase;
  attribute float aSize;
  varying float vGlow;

  void main() {
    vec3 p = position;
    vec3 n = normalize(p);
    float idle = sin(uTime * 1.45 + aPhase * 6.2831) * 0.018;
    float voice = sin(uTime * 4.4 + aPhase * 11.0 + p.y * 2.8) * (0.035 + uLevel * 0.13);
    float ripple = sin(uTime * 2.25 + length(p.xz) * 8.0 + aPhase * 3.0) * (0.012 + uLevel * 0.045);
    float listeningBoost = step(0.5, uMode) * (voice + ripple);
    p += n * (idle + listeningBoost);

    vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    float depthScale = 190.0 / max(1.0, -mvPosition.z);
    gl_PointSize = clamp((1.1 + aSize * 2.15 + uLevel * 1.6) * depthScale, 1.0, 5.2);
    vGlow = clamp(0.42 + aSize * 0.36 + uLevel * 0.55, 0.0, 1.0);
  }
`;

const fragmentShader = `
  varying float vGlow;
  void main() {
    vec2 c = gl_PointCoord - vec2(0.5);
    float d = length(c);
    if (d > 0.5) discard;
    float core = smoothstep(0.50, 0.05, d);
    float halo = smoothstep(0.50, 0.18, d) * 0.46;
    vec3 emerald = vec3(0.08, 1.0, 0.63);
    vec3 whiteHot = vec3(0.72, 1.0, 0.91);
    vec3 col = mix(emerald, whiteHot, core * 0.68);
    float alpha = (core * 0.88 + halo) * vGlow;
    gl_FragColor = vec4(col, alpha);
  }
`;

export const VoiceParticleSphere: React.FC<VoiceParticleSphereProps> = ({ level, state }) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const levelRef = useRef(level);
  const stateRef = useRef(state);
  const [fallback, setFallback] = useState(false);

  useEffect(() => { levelRef.current = level; }, [level]);
  useEffect(() => { stateRef.current = state; }, [state]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const probe = document.createElement('canvas');
    if (!probe.getContext('webgl2') && !probe.getContext('webgl')) {
      console.error('[ZARA] WebGL unavailable; using CSS voice-core fallback.');
      const fallbackTimer = window.setTimeout(() => setFallback(true), 0);
      return () => window.clearTimeout(fallbackTimer);
    }

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100);
    camera.position.set(0, 0, 5.4);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' });
    } catch (error) {
      console.error('[ZARA] Could not create WebGL renderer:', error);
      const fallbackTimer = window.setTimeout(() => setFallback(true), 0);
      return () => window.clearTimeout(fallbackTimer);
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.7));
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);

    const count = 4100;
    const positions = new Float32Array(count * 3);
    const phases = new Float32Array(count);
    const sizes = new Float32Array(count);

    // Fibonacci sphere + tiny deterministic thickness creates a dense Perplexity-like voice orb.
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < count; i += 1) {
      const y = 1 - (i / (count - 1)) * 2;
      const radius = Math.sqrt(Math.max(0, 1 - y * y));
      const theta = golden * i;
      const shell = 1.0 + Math.sin(i * 12.9898) * 0.018 + Math.cos(i * 4.1414) * 0.012;
      positions[i * 3] = Math.cos(theta) * radius * shell;
      positions[i * 3 + 1] = y * shell;
      positions[i * 3 + 2] = Math.sin(theta) * radius * shell;
      phases[i] = ((i * 0.61803398875) % 1);
      sizes[i] = 0.2 + (((i * 37) % 101) / 100) * 0.8;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('aPhase', new THREE.BufferAttribute(phases, 1));
    geometry.setAttribute('aSize', new THREE.BufferAttribute(sizes, 1));

    const material = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uLevel: { value: 0 },
        uMode: { value: 0 },
      },
      vertexShader,
      fragmentShader,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    const sphere = new THREE.Points(geometry, material);
    sphere.scale.setScalar(1.43);
    scene.add(sphere);

    const glowGeo = new THREE.SphereGeometry(1.45, 48, 32);
    const glowMat = new THREE.MeshBasicMaterial({ color: 0x00d985, transparent: true, opacity: 0.026, side: THREE.BackSide });
    const glow = new THREE.Mesh(glowGeo, glowMat);
    scene.add(glow);

    const clock = new THREE.Clock();
    let raf = 0;
    let smoothLevel = 0;

    const resize = () => {
      const rect = host.getBoundingClientRect();
      const w = Math.max(1, rect.width);
      const h = Math.max(1, rect.height);
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(host);
    resize();

    const animate = () => {
      const t = clock.getElapsedTime();
      const currentState = stateRef.current;
      const reactive = currentState === 'LISTENING' || currentState === 'SPEAKING';
      const target = reactive ? Math.min(1, Math.max(0, levelRef.current)) : 0.035;
      smoothLevel += (target - smoothLevel) * (reactive ? 0.16 : 0.055);

      material.uniforms.uTime.value = t;
      material.uniforms.uLevel.value = smoothLevel;
      material.uniforms.uMode.value = reactive ? 1 : (currentState === 'THINKING' || currentState === 'PROCESSING' ? 0.7 : 0);

      const breath = 1 + Math.sin(t * 1.35) * 0.014;
      const voicePulse = reactive ? 1 + smoothLevel * 0.09 + Math.sin(t * 5.1) * smoothLevel * 0.02 : 1;
      sphere.scale.setScalar(1.43 * breath * voicePulse);
      glow.scale.setScalar(1 + smoothLevel * 0.095 + Math.sin(t * 1.6) * 0.01);
      glowMat.opacity = 0.024 + smoothLevel * 0.075;

      sphere.rotation.y = t * (currentState === 'THINKING' ? 0.12 : 0.045);
      sphere.rotation.x = Math.sin(t * 0.33) * 0.055;
      try {
        renderer.render(scene, camera);
        raf = requestAnimationFrame(animate);
      } catch (error) {
        console.error('[ZARA] WebGL render failed; switching to fallback:', error);
        setFallback(true);
      }
    };
    animate();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      geometry.dispose();
      material.dispose();
      glowGeo.dispose();
      glowMat.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return (
    <div ref={hostRef} className={`voice-orb ${fallback ? 'fallback' : ''}`} aria-label={`ZARA voice core: ${state}`}>
      {fallback && <div className={`voice-orb-fallback state-${state.toLowerCase()}`} style={{ '--voice-level': Math.max(0.03, Math.min(1, level)) } as React.CSSProperties}><i/><i/><i/></div>}
    </div>
  );
};
