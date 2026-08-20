import React, { useEffect, useRef, useMemo, useState } from 'react';
import './HUD.css';

/**
 * ZARA HUD — Heads-Up Display com métricas do sistema, status de voz, conexões
 * 
 * Features:
 * - Métricas CPU/RAM/Network/Storage com histórico visual
 * - Status de voz (microfone, TTS, wake word)
 * - Status de conexões (backend, Hermes, Supercérebro)
 * - Engine de IA ativo
 * - Modo compacto para barra lateral / expandido para painel
 * - Atualização em tempo real via props ou callbacks
 * - Design tokens, acessível
 */

export type HUDVariant = 'compact' | 'full' | 'minimal' | 'sidebar';
export type ConnectionStatus = 'connected' | 'connecting' | 'disconnected' | 'error';
export type VoiceStatus = 'standby' | 'idle' | 'listening' | 'speaking' | 'thinking' | 'processing' | 'muted' | 'sleeping';

export interface SystemMetrics {
  cpu: number;        // 0-100
  memory: number;     // 0-100
  network: number;    // 0-100 (bandwidth usage)
  storage: number;    // 0-100
  timestamp: number;
}

export interface ConnectionInfo {
  id: string;
  label: string;
  status: ConnectionStatus;
  latency?: number;   // ms
  details?: string;
}

export interface VoiceInfo {
  status: VoiceStatus;
  level: number;      // 0-1 audio level
  wakeWordActive: boolean;
  ttsActive: boolean;
  engine?: string;    // ex: "Gemini Live • Kore"
}

export interface EngineInfo {
  id: string;
  name: string;
  provider: string;
  isActive: boolean;
  status?: string;
}

export interface HUDProps {
  /** Variante visual */
  variant?: HUDVariant;
  /** Métricas do sistema */
  metrics?: SystemMetrics;
  /** Histórico de métricas (para sparklines) */
  metricsHistory?: SystemMetrics[];
  /** Informações de conexão */
  connections?: ConnectionInfo[];
  /** Info de voz */
  voice?: VoiceInfo;
  /** Engine ativo */
  engine?: EngineInfo;
  /** Engines disponíveis */
  engines?: EngineInfo[];
  /** Callback para trocar engine */
  onEngineChange?: (engineId: string) => void;
  /** Callback para toggle voz */
  onVoiceToggle?: () => void;
  /** Callback para toggle mute */
  onMuteToggle?: () => void;
  /** Callback para toggle Supercérebro */
  onSupercerebroToggle?: () => void;
  /** Supercérebro ativo */
  supercerebroActive?: boolean;
  /** Mostra timestamps */
  showTimestamps?: boolean;
  /** ClassName adicional */
  className?: string;
  /** Style adicional */
  style?: React.CSSProperties;
}

/** Componente de sparkline (mini gráfico) */
const Sparkline: React.FC<{ 
  data: number[]; 
  color: string; 
  width?: number; 
  height?: number;
  showDots?: boolean;
}> = ({ data, color, width = 60, height = 24, showDots = false }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.scale(dpr, dpr);
    
    if (data.length < 2) return;
    
    const max = Math.max(...data, 1);
    const min = Math.min(...data, 0);
    const range = max - min || 1;
    
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    
    data.forEach((value, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((value - min) / range) * height * 0.85 - height * 0.075;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    
    ctx.stroke();
    
    // Área preenchida sutil
    ctx.fillStyle = `${color}20`;
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.fill();
    
    // Ponto atual
    if (showDots && data.length > 0) {
      const lastValue = data[data.length - 1];
      const x = width;
      const y = height - ((lastValue - min) / range) * height * 0.85 - height * 0.075;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, 3, 0, Math.PI * 2);
      ctx.fill();
    }
  }, [data, color, width, height, showDots]);
  
  return <canvas ref={canvasRef} width={width} height={height} aria-hidden="true" />;
};

/** Badge de status */
const StatusBadge: React.FC<{ 
  status: ConnectionStatus | VoiceStatus; 
  label?: string;
  size?: 'sm' | 'md';
}> = ({ status, label, size = 'md' }) => {
  const statusConfig = useMemo(() => {
    switch (status) {
      case 'connected':
      case 'listening':
      case 'speaking':
        return { color: 'var(--color-success, #8FC17F)', bg: 'var(--color-success, #8FC17F)20', dot: true };
      case 'connecting':
      case 'thinking':
      case 'processing':
        return { color: 'var(--color-warning, #D9B45E)', bg: 'var(--color-warning, #D9B45E)20', dot: true, pulse: true };
      case 'disconnected':
      case 'standby':
      case 'idle':
      case 'muted':
      case 'sleeping':
        return { color: 'var(--text-muted)', bg: 'var(--surface-panel)', dot: false };
      case 'error':
        return { color: 'var(--color-danger, #E0705F)', bg: 'var(--color-danger, #E0705F)20', dot: true };
      default:
        return { color: 'var(--text-muted)', bg: 'var(--surface-panel)', dot: false };
    }
  }, [status]);
  
  const statusLabels: Record<string, string> = {
    connected: 'Conectado',
    connecting: 'Conectando...',
    disconnected: 'Desconectado',
    error: 'Erro',
    standby: 'Aguardando',
    idle: 'Ocioso',
    listening: 'Ouvindo',
    speaking: 'Falando',
    thinking: 'Pensando',
    processing: 'Processando',
    muted: 'Silenciado',
    sleeping: 'Dormindo',
  };
  
  const displayLabel = label || statusLabels[status] || status;
  
  return (
    <span 
      className={`hud__badge hud__badge--${size} ${statusConfig.pulse ? 'hud__badge--pulse' : ''}`}
      style={{ 
        '--badge-color': statusConfig.color,
        '--badge-bg': statusConfig.bg,
      } as React.CSSProperties}
    >
      {statusConfig.dot && <span className="hud__badge-dot" aria-hidden="true" />}
      <span className="hud__badge-text">{displayLabel}</span>
    </span>
  );
};

/** Métrica individual */
const Metric: React.FC<{
  label: string;
  value: number;
  unit?: string;
  history?: number[];
  color: string;
  warningThreshold?: number;
  dangerThreshold?: number;
  compact?: boolean;
}> = ({ label, value, unit = '%', history, color, warningThreshold = 70, dangerThreshold = 85, compact = false }) => {
  const [displayValue, setDisplayValue] = useState(value);
  
  // Anima contador
  useEffect(() => {
    const start = displayValue;
    const end = value;
    const duration = 500;
    const startTime = performance.now();
    
    const animate = (now: number) => {
      const progress = Math.min(1, (now - startTime) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayValue(start + (end - start) * eased);
      if (progress < 1) requestAnimationFrame(animate);
    };
    
    requestAnimationFrame(animate);
  }, [value]);
  
  const isWarning = value >= warningThreshold && value < dangerThreshold;
  const isDanger = value >= dangerThreshold;
  const metricColor = isDanger ? 'var(--color-danger)' : isWarning ? 'var(--color-warning)' : color;
  
  if (compact) {
    return (
      <div className="hud__metric hud__metric--compact" style={{ '--metric-color': metricColor } as React.CSSProperties}>
        <span className="hud__metric-label">{label}</span>
        <div className="hud__metric-value-row">
          <span className="hud__metric-value">{Math.round(displayValue)}</span>
          <span className="hud__metric-unit">{unit}</span>
        </div>
        {history && history.length > 1 && (
          <Sparkline data={history} color={metricColor} width={50} height={18} />
        )}
      </div>
    );
  }
  
  return (
    <div className="hud__metric" style={{ '--metric-color': metricColor } as React.CSSProperties}>
      <div className="hud__metric-header">
        <span className="hud__metric-label">{label}</span>
        <span className="hud__metric-value">{Math.round(displayValue)}<span className="hud__metric-unit">{unit}</span></span>
      </div>
      <div className="hud__metric-bar">
        <div 
          className="hud__metric-fill" 
          style={{ width: `${Math.min(100, value)}%`, background: metricColor } as React.CSSProperties}
        />
      </div>
      {history && history.length > 1 && (
        <Sparkline data={history} color={metricColor} width={120} height={30} showDots />
      )}
    </div>
  );
};

/** Componente principal HUD */
export const HUD: React.FC<HUDProps> = ({
  variant = 'full',
  metrics,
  metricsHistory = [],
  connections = [],
  voice,
  engine,
  engines = [],
  onEngineChange,
  onVoiceToggle,
  onMuteToggle,
  onSupercerebroToggle,
  supercerebroActive = false,
  showTimestamps = true,
  className = '',
  style,
}) => {
  const [expanded, setExpanded] = useState(variant === 'full');
  const [hoveredConnection, setHoveredConnection] = useState<string | null>(null);
  
  // Prepara histórico por métrica
  const historyByMetric = useMemo(() => {
    if (!metricsHistory.length) return {};
    return {
      cpu: metricsHistory.map(m => m.cpu),
      memory: metricsHistory.map(m => m.memory),
      network: metricsHistory.map(m => m.network),
      storage: metricsHistory.map(m => m.storage),
    };
  }, [metricsHistory]);
  
  // Voz status derivado
  const voiceStatus = voice?.status || 'standby';
  const voiceLevel = voice?.level || 0;
  const isVoiceActive = voiceStatus === 'listening' || voiceStatus === 'speaking';
  
  if (variant === 'minimal') {
    return (
      <div className={`hud hud--minimal ${className}`} style={style} role="region" aria-label="Status ZARA">
        <StatusBadge status={voiceStatus} size="sm" />
        {metrics && (
          <span className="hud__mini-metric" style={{ '--metric-color': 'var(--accent-primary)' } as React.CSSProperties}>
            CPU {Math.round(metrics.cpu)}%
          </span>
        )}
        {connections.some(c => c.status === 'connected') && (
          <StatusBadge status="connected" size="sm" label="" />
        )}
      </div>
    );
  }
  
  if (variant === 'compact') {
    return (
      <div className={`hud hud--compact ${className}`} style={style} role="region" aria-label="HUD ZARA compacto">
        <div className="hud__row hud__row--voice">
          <StatusBadge status={voiceStatus} label={voice?.engine} />
          {onVoiceToggle && (
            <button 
              className="hud__icon-btn"
              onClick={onVoiceToggle}
              aria-label={isVoiceActive ? 'Parar microfone' : 'Iniciar microfone'}
              aria-pressed={isVoiceActive}
            >
              {isVoiceActive ? '🎙' : '🎤'}
            </button>
          )}
          {onMuteToggle && voice && (
            <button 
              className="hud__icon-btn"
              onClick={onMuteToggle}
              aria-label={voiceStatus === 'muted' ? 'Reativar voz' : 'Silenciar voz'}
              aria-pressed={voiceStatus === 'muted'}
            >
              {voiceStatus === 'muted' ? '🔇' : '🔊'}
            </button>
          )}
        </div>
        
        {metrics && (
          <div className="hud__row hud__row--metrics">
            <Metric 
              label="CPU" 
              value={metrics.cpu} 
              history={historyByMetric.cpu} 
              color="var(--accent-primary)" 
              compact 
            />
            <Metric 
              label="RAM" 
              value={metrics.memory} 
              history={historyByMetric.memory} 
              color="var(--color-info)" 
              compact 
            />
          </div>
        )}
        
        <div className="hud__row hud__row--connections">
          {connections.map(conn => (
            <StatusBadge 
              key={conn.id} 
              status={conn.status} 
              label={conn.label}
              size="sm"
            />
          ))}
        </div>
      </div>
    );
  }
  
  if (variant === 'sidebar') {
    return (
      <div className={`hud hud--sidebar ${className}`} style={style} role="region" aria-label="HUD ZARA lateral">
        <div className="hud__section">
          <h3 className="hud__section-title">Voz</h3>
          <div className="hud__voice-status">
            <div className="hud__voice-main">
              <StatusBadge status={voiceStatus} label={voice?.engine} />
              <div className="hud__voice-level">
                <div 
                  className="hud__voice-bar"
                  style={{ width: `${voiceLevel * 100}%` } as React.CSSProperties}
                />
              </div>
            </div>
            <div className="hud__voice-controls">
              {onVoiceToggle && (
                <button 
                  className={`hud__btn ${isVoiceActive ? 'hud__btn--active' : ''}`}
                  onClick={onVoiceToggle}
                  aria-pressed={isVoiceActive}
                >
                  {isVoiceActive ? 'Parar' : 'Ouvir'}
                </button>
              )}
              {onMuteToggle && (
                <button 
                  className={`hud__btn ${voiceStatus === 'muted' ? 'hud__btn--muted' : ''}`}
                  onClick={onMuteToggle}
                  aria-pressed={voiceStatus === 'muted'}
                >
                  {voiceStatus === 'muted' ? 'Silenciado' : 'Falar'}
                </button>
              )}
            </div>
          </div>
        </div>
        
        {metrics && (
          <div className="hud__section">
            <h3 className="hud__section-title">Sistema</h3>
            <div className="hud__metrics-grid">
              <Metric label="CPU" value={metrics.cpu} history={historyByMetric.cpu} color="var(--accent-primary)" compact />
              <Metric label="RAM" value={metrics.memory} history={historyByMetric.memory} color="var(--color-info)" compact />
              <Metric label="Rede" value={metrics.network} history={historyByMetric.network} color="var(--color-warning)" compact />
              <Metric label="Disco" value={metrics.storage} history={historyByMetric.storage} color="var(--text-muted)" compact />
            </div>
          </div>
        )}
        
        <div className="hud__section">
          <h3 className="hud__section-title">Conexões</h3>
          <div className="hud__connections">
            {connections.map(conn => (
              <div 
                key={conn.id} 
                className="hud__connection"
                onMouseEnter={() => setHoveredConnection(conn.id)}
                onMouseLeave={() => setHoveredConnection(null)}
              >
                <div className="hud__connection-main">
                  <StatusBadge status={conn.status} size="sm" />
                  <span className="hud__connection-label">{conn.label}</span>
                </div>
                {hoveredConnection === conn.id && conn.latency && (
                  <span className="hud__connection-latency">{conn.latency}ms</span>
                )}
              </div>
            ))}
          </div>
        </div>
        
        {engine && engines.length > 1 && (
          <div className="hud__section">
            <h3 className="hud__section-title">Motor IA</h3>
            <select 
              className="hud__engine-select"
              value={engine.id}
              onChange={(e) => onEngineChange?.(e.target.value)}
              aria-label="Selecionar motor de IA"
            >
              {engines.map(e => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </select>
            <span className="hud__engine-status">{engine.name}</span>
          </div>
        )}
        
        {onSupercerebroToggle && (
          <div className="hud__section">
            <label className="hud__supercerebro-toggle">
              <input 
                type="checkbox" 
                checked={supercerebroActive} 
                onChange={onSupercerebroToggle}
                aria-label="Supercérebro Hermes"
              />
              <span className="hud__toggle-slider" />
              <span className="hud__toggle-label">Supercérebro</span>
              <StatusBadge status={supercerebroActive ? 'connected' : 'disconnected'} size="sm" label="" />
            </label>
          </div>
        )}
      </div>
    );
  }
  
  // Variant FULL
  return (
    <div 
      className={`hud hud--full ${expanded ? 'hud--expanded' : ''} ${className}`}
      style={style}
      role="region"
      aria-label="HUD ZARA completo"
    >
      <header className="hud__header">
        <h2 className="hud__title">ZARA HUD</h2>
        <div className="hud__header-actions">
          <StatusBadge status={voiceStatus} label={voice?.engine} />
          <button 
            className="hud__expand-btn"
            onClick={() => setExpanded(!expanded)}
            aria-label={expanded ? 'Compactar' : 'Expandir'}
            aria-expanded={expanded}
          >
            {expanded ? '⛶' : '⛶'}
          </button>
        </div>
      </header>
      
      <div className="hud__grid">
        {/* Voz */}
        <section className="hud__panel hud__panel--voice">
          <h3 className="hud__panel-title">Status de Voz</h3>
          <div className="hud__voice-display">
            <div className="hud__voice-main">
              <StatusBadge status={voiceStatus} label={voice?.engine} />
              <div className="hud__voice-level-large">
                <div className="hud__voice-bars" style={{ '--level': voiceLevel } as React.CSSProperties}>
                  {[...Array(16)].map((_, i) => (
                    <span key={i} className="hud__voice-bar" style={{ '--delay': `${i * 30}ms` } as React.CSSProperties} />
                  ))}
                </div>
              </div>
            </div>
            <div className="hud__voice-controls">
              {onVoiceToggle && (
                <button 
                  className={`hud__btn hud__btn--primary ${isVoiceActive ? 'hud__btn--active' : ''}`}
                  onClick={onVoiceToggle}
                  aria-pressed={isVoiceActive}
                >
                  {isVoiceActive ? '⏹ Parar' : '▶ Ouvir'}
                </button>
              )}
              {onMuteToggle && (
                <button 
                  className={`hud__btn ${voiceStatus === 'muted' ? 'hud__btn--muted' : ''}`}
                  onClick={onMuteToggle}
                  aria-pressed={voiceStatus === 'muted'}
                >
                  {voiceStatus === 'muted' ? '🔇 Silenciado' : '🔊 Falar'}
                </button>
              )}
              {voice?.wakeWordActive && (
                <span className="hud__wake-indicator" aria-live="polite">👂 Wake word ativa</span>
              )}
            </div>
          </div>
        </section>
        
        {/* Sistema */}
        <section className="hud__panel hud__panel--system">
          <h3 className="hud__panel-title">Sistema</h3>
          {metrics && (
            <div className="hud__metrics-full">
              <Metric label="CPU" value={metrics.cpu} history={historyByMetric.cpu} color="var(--accent-primary)" />
              <Metric label="Memória" value={metrics.memory} history={historyByMetric.memory} color="var(--color-info)" />
              <Metric label="Rede" value={metrics.network} history={historyByMetric.network} color="var(--color-warning)" />
              <Metric label="Armazenamento" value={metrics.storage} history={historyByMetric.storage} color="var(--text-muted)" />
            </div>
          )}
          {showTimestamps && metrics && (
            <div className="hud__timestamp">
              Atualizado: {new Date(metrics.timestamp).toLocaleTimeString()}
            </div>
          )}
        </section>
        
        {/* Conexões */}
        <section className="hud__panel hud__panel--connections">
          <h3 className="hud__panel-title">Conexões</h3>
          <div className="hud__connections-full">
            {connections.map(conn => (
              <div 
                key={conn.id} 
                className="hud__connection-full"
                onMouseEnter={() => setHoveredConnection(conn.id)}
                onMouseLeave={() => setHoveredConnection(null)}
              >
                <div className="hud__connection-info">
                  <StatusBadge status={conn.status} size="sm" />
                  <div className="hud__connection-details">
                    <span className="hud__connection-label">{conn.label}</span>
                    {conn.details && <span className="hud__connection-details-text">{conn.details}</span>}
                  </div>
                </div>
                <div className="hud__connection-meta">
                  {conn.latency && <span className="hud__connection-latency">{conn.latency}ms</span>}
                  {hoveredConnection === conn.id && conn.details && (
                    <span className="hud__connection-tooltip">{conn.details}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
        
        {/* Engine & Supercerebro */}
        <section className="hud__panel hud__panel--engine">
          <h3 className="hud__panel-title">Motor de IA</h3>
          {engine && engines.length > 0 && (
            <div className="hud__engine-selector">
              <select 
                className="hud__engine-select"
                value={engine.id}
                onChange={(e) => onEngineChange?.(e.target.value)}
                aria-label="Selecionar motor de IA"
              >
                {engines.map(e => (
                  <option key={e.id} value={e.id} selected={e.id === engine.id}>
                    {e.name} {e.isActive ? '●' : ''}
                  </option>
                ))}
              </select>
              <div className="hud__engine-info">
                <span className="hud__engine-provider">{engine.provider}</span>
                {engine.status && <span className="hud__engine-status">{engine.status}</span>}
              </div>
            </div>
          )}
          
          {onSupercerebroToggle && (
            <div className="hud__supercerebro">
              <label className="hud__supercerebro-toggle">
                <input 
                  type="checkbox" 
                  checked={supercerebroActive} 
                  onChange={onSupercerebroToggle}
                  aria-label="Supercérebro Hermes"
                />
                <span className="hud__toggle-slider" />
                <span className="hud__toggle-label">Supercérebro Hermes</span>
              </label>
              <StatusBadge status={supercerebroActive ? 'connected' : 'disconnected'} label={supercerebroActive ? 'Ativo' : 'Inativo'} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

export default HUD;