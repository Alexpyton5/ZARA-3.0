import React from 'react';

import './RoutingTelemetryPanel.css';

export interface RoutingTelemetryPanelProps {
  success: boolean;
  latency: number | null;
  fallback: boolean;
  pendingReview: number;
  error?: string | null;
}

export const RoutingTelemetryPanel: React.FC<RoutingTelemetryPanelProps> = ({
  success,
  latency,
  fallback,
  pendingReview,
  error = null,
}) => {
  const safeLatency = Number.isFinite(latency) && Number(latency) >= 0
    ? Math.round(Number(latency))
    : null;
  const safePending = Number.isFinite(pendingReview)
    ? Math.max(0, Math.trunc(pendingReview))
    : 0;
  const errorMessage = typeof error === 'string' && error.trim() ? error.trim() : null;
  const empty = !errorMessage && !success && !fallback && safeLatency === null && safePending === 0;

  let statusText = 'Atenção';
  let statusClass = 'routing-telemetry__value--warning';
  if (errorMessage) {
    statusText = 'Erro';
    statusClass = 'routing-telemetry__value--error';
  } else if (fallback) {
    statusText = 'Fallback ativo';
    statusClass = 'routing-telemetry__value--fallback';
  } else if (success) {
    statusText = 'Saudável';
    statusClass = 'routing-telemetry__value--success';
  } else if (empty) {
    statusText = 'Sem dados';
    statusClass = 'routing-telemetry__value--muted';
  }

  return (
    <section className="routing-telemetry" aria-labelledby="routing-telemetry-title">
      <header className="routing-telemetry__header">
        <div>
          <p className="routing-telemetry__eyebrow">Roteamento adaptativo</p>
          <h2 id="routing-telemetry-title">Telemetria do roteador</h2>
        </div>
        <span className={`routing-telemetry__status ${statusClass}`} role="status" aria-live="polite">
          {statusText}
        </span>
      </header>

      {errorMessage && (
        <p className="routing-telemetry__message routing-telemetry__message--error" role="alert">
          {errorMessage}
        </p>
      )}
      {empty && (
        <p className="routing-telemetry__message">Ainda não há decisões de roteamento para mostrar.</p>
      )}

      <dl className="routing-telemetry__grid" aria-label="Métricas recentes">
        <div className="routing-telemetry__metric">
          <dt>Resultado</dt>
          <dd>{success ? 'Sucesso confirmado' : 'Sem sucesso confirmado'}</dd>
        </div>
        <div className="routing-telemetry__metric">
          <dt>Latência</dt>
          <dd>{safeLatency === null ? 'Não medida' : `${safeLatency} ms`}</dd>
        </div>
        <div className="routing-telemetry__metric">
          <dt>Fallback</dt>
          <dd>{fallback ? 'Usado nesta rota' : 'Não usado'}</dd>
        </div>
        <div className="routing-telemetry__metric">
          <dt>Revisão humana</dt>
          <dd>{safePending === 1 ? '1 candidato pendente' : `${safePending} candidatos pendentes`}</dd>
        </div>
      </dl>
    </section>
  );
};

export default RoutingTelemetryPanel;
