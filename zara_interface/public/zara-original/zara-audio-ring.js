(function () {
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const WIRE_COUNT = 220;
  const POINT_COUNT = 58;
  const TIP_POINTS = 10;
  const wires = [];
  let activeSvg = null;
  let microphoneButton = null;
  let analyser = null;
  let stream = null;
  let audioData = null;
  let simulationEnabled = true;
  let externalLevel = 0;
  let lastExternalUpdate = 0;
  let audioLevel = 0;
  let lastFrame = 0;

  function randomFor(index, salt) {
    const value = Math.sin(index * 127.1 + salt * 311.7) * 43758.5453123;
    return value - Math.floor(value);
  }

  function svgPath(className) {
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('class', className);
    return path;
  }

  function smoothPath(points) {
    if (!points.length) return '';
    let d = `M${points[0].x.toFixed(2)},${points[0].y.toFixed(2)}`;
    for (let i = 0; i < points.length - 1; i += 1) {
      const p0 = points[Math.max(0, i - 1)];
      const p1 = points[i];
      const p2 = points[i + 1];
      const p3 = points[Math.min(points.length - 1, i + 2)];
      const c1x = p1.x + (p2.x - p0.x) / 6;
      const c1y = p1.y + (p2.y - p0.y) / 6;
      const c2x = p2.x - (p3.x - p1.x) / 6;
      const c2y = p2.y - (p3.y - p1.y) / 6;
      d += `C${c1x.toFixed(2)},${c1y.toFixed(2)} ${c2x.toFixed(2)},${c2y.toFixed(2)} ${p2.x.toFixed(2)},${p2.y.toFixed(2)}`;
    }
    return d;
  }

  function createWire(index) {
    const upper = index % 2 === 0;
    const strand = Math.floor(index / 2);
    const densityPosition = strand / (WIRE_COUNT / 2 - 1);
    const phase = randomFor(index, 1) * Math.PI * 2;
    const startBase = upper ? Math.PI * 0.94 : Math.PI * 0.075;
    const endBase = upper ? Math.PI * 1.88 : Math.PI * 0.86;
    const start = startBase + randomFor(index, 2) * 0.12 + Math.sin(strand * 0.31) * 0.016;
    const end = endBase - randomFor(index, 3) * 0.13 + Math.cos(strand * 0.27) * 0.018;
    const radialBand = (densityPosition - 0.5) * 15.5;
    const radiusBase = 103 + radialBand + (randomFor(index, 4) - 0.5) * 2.4;
    const centerX = 150 + (randomFor(index, 5) - 0.5) * 2.2;
    const centerY = 150 + (randomFor(index, 6) - 0.5) * 2.6;
    const points = [];

    for (let point = 0; point < POINT_COUNT; point += 1) {
      const u = point / (POINT_COUNT - 1);
      const angle = start + (end - start) * u;
      const longWave = Math.sin(angle * (4.2 + randomFor(index, 7) * 2.4) + phase) * (0.75 + randomFor(index, 8) * 1.05);
      const fineWave = Math.sin(angle * (15 + Math.floor(randomFor(index, 9) * 10)) - phase * 1.8) * (0.22 + randomFor(index, 10) * 0.52);
      const taper = Math.sin(Math.PI * u);
      const radius = radiusBase + longWave + fineWave * (0.42 + taper * 0.58);
      points.push({
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius * 1.035
      });
    }

    return {
      index,
      phase,
      frequency: 7.2 + randomFor(index, 11) * 6.8,
      amplitude: 0.55 + randomFor(index, 12) * 1.45,
      points
    };
  }

  function configureStroke(path, index) {
    const width = 0.28 + randomFor(index, 13) * 0.58;
    const opacity = 0.14 + randomFor(index, 14) * 0.42;
    path.setAttribute('stroke-width', width.toFixed(2));
    path.setAttribute('opacity', opacity.toFixed(2));
  }

  function buildRing(svg) {
    const set = svg.querySelector('#zaraWireSet');
    if (!set) return;
    set.replaceChildren();
    wires.length = 0;

    for (let index = 0; index < WIRE_COUNT; index += 1) {
      const wire = createWire(index);
      const group = document.createElementNS(SVG_NS, 'g');
      group.setAttribute('class', 'zara-wire');
      group.setAttribute('data-wire', String(index));
      const startTip = svgPath('zara-wire-tip');
      const body = svgPath('zara-wire-body');
      const endTip = svgPath('zara-wire-tip');
      configureStroke(startTip, index);
      configureStroke(body, index);
      configureStroke(endTip, index);

      const bodyPoints = wire.points.slice(TIP_POINTS - 2, POINT_COUNT - TIP_POINTS + 2);
      body.setAttribute('d', smoothPath(bodyPoints));
      startTip.setAttribute('d', smoothPath(wire.points.slice(0, TIP_POINTS + 2)));
      endTip.setAttribute('d', smoothPath(wire.points.slice(POINT_COUNT - TIP_POINTS - 2)));
      group.append(startTip, body, endTip);
      set.append(group);
      wire.startTip = startTip;
      wire.endTip = endTip;
      wires.push(wire);
    }
  }

  function ensureScene() {
    const svg = document.getElementById('zaraVectorRing');
    if (svg && svg !== activeSvg) {
      activeSvg = svg;
      buildRing(svg);
    }
    const button = document.getElementById('zaraMicButton');
    if (button && button.dataset.vectorBound !== 'true') {
      microphoneButton = button;
      microphoneButton.dataset.vectorBound = 'true';
      microphoneButton.addEventListener('click', toggleMicrophone);
    }
  }

  async function toggleMicrophone() {
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
      analyser = null;
      microphoneButton.dataset.active = 'false';
      microphoneButton.setAttribute('aria-label', 'Ativar microfone');
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContext();
      const input = audioContext.createMediaStreamSource(stream);
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.66;
      audioData = new Uint8Array(analyser.frequencyBinCount);
      input.connect(analyser);
      microphoneButton.dataset.active = 'true';
      microphoneButton.setAttribute('aria-label', 'Desativar microfone');
    } catch (error) {
      microphoneButton.dataset.active = 'false';
    }
  }

  function simulatedAudio(t) {
    if (!simulationEnabled) return 0;
    const syllable = Math.pow(Math.max(0, Math.sin(t * 4.7) * Math.sin(t * 0.83 + 0.6)), 1.8);
    return 0.28 + Math.sin(t * 1.31) * 0.08 + syllable * 0.34;
  }

  function getLevel(now, t) {
    let microphoneLevel = 0;
    if (analyser && audioData) {
      analyser.getByteFrequencyData(audioData);
      let sum = 0;
      for (let i = 2; i < 108; i += 1) sum += audioData[i];
      microphoneLevel = Math.min(1, sum / (106 * 128));
    }
    const externalIsFresh = now - lastExternalUpdate < 180;
    const target = Math.max(microphoneLevel, externalIsFresh ? externalLevel : 0, simulatedAudio(t));
    audioLevel += (target - audioLevel) * (target > audioLevel ? 0.26 : 0.08);
    return audioLevel;
  }

  function animatedTip(wire, fromStart, t, level) {
    const source = fromStart
      ? wire.points.slice(0, TIP_POINTS + 2)
      : wire.points.slice(POINT_COUNT - TIP_POINTS - 2);
    return source.map((point, localIndex) => {
      const distanceFromEnd = fromStart ? localIndex : source.length - 1 - localIndex;
      const normalized = Math.max(0, 1 - distanceFromEnd / TIP_POINTS);
      const weight = Math.pow(normalized, 2.35);
      const neighborIndex = fromStart
        ? Math.min(wire.points.length - 1, localIndex + 1)
        : Math.max(0, POINT_COUNT - source.length + localIndex - 1);
      const neighbor = wire.points[neighborIndex];
      const tangentX = neighbor.x - point.x;
      const tangentY = neighbor.y - point.y;
      const length = Math.hypot(tangentX, tangentY) || 1;
      const normalX = -tangentY / length;
      const normalY = tangentX / length;
      const directionPhase = fromStart ? 0 : Math.PI * 0.73;
      const vibration = Math.sin(t * wire.frequency * Math.PI * 2 + wire.phase + directionPhase + localIndex * 0.31);
      const overtone = Math.sin(t * wire.frequency * 1.93 * Math.PI * 2 - wire.phase * 1.4) * 0.27;
      const displacement = (vibration + overtone) * wire.amplitude * level * weight;
      return { x: point.x + normalX * displacement, y: point.y + normalY * displacement };
    });
  }

  function animate(timeMs) {
    ensureScene();
    if (timeMs - lastFrame >= 28 && wires.length) {
      lastFrame = timeMs;
      const t = timeMs * 0.001;
      const level = getLevel(timeMs, t);
      wires.forEach((wire) => {
        wire.startTip.setAttribute('d', smoothPath(animatedTip(wire, true, t, level)));
        wire.endTip.setAttribute('d', smoothPath(animatedTip(wire, false, t, level)));
      });
    }
    requestAnimationFrame(animate);
  }

  window.ZaraRing = {
    setSpeakingLevel(value) {
      externalLevel = Math.max(0, Math.min(1, Number(value) || 0));
      lastExternalUpdate = performance.now();
    },
    setSimulation(enabled) { simulationEnabled = Boolean(enabled); },
    getSimulation() { return simulationEnabled; },
    getWireCount() { return wires.length; }
  };

  requestAnimationFrame(animate);
})();
