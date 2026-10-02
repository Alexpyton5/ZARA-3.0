import React, { useEffect, useState } from 'react';
import { RoutingTelemetryPanel, RoutingTelemetryPanelProps } from './RoutingTelemetryPanel';

// Define types for the data we expect from IPC
interface ApprovalRequest {
  id: string;
  action: string;
  expires: number; // timestamp
}

interface DiarioSuggestion {
  id: number;
  dia: string; // YYYY-MM-DD
  regra: string; // e.g., 'revisar_acao', 'otimizar', 'revisar_dialogo'
  chave_agregacao: string;
  comando_representativo: string;
  acao: string;
  total_ocorrencias: number;
  sucessos: number;
  falhas: number;
  sugestoes_json: any; // the suggestion object
  review_required: boolean;
  auto_apply: boolean;
  status: string; // e.g., 'pendente'
}

const UnifiedApprovalDiarioTelemetry: React.FC<{ telemetry: RoutingTelemetryPanelProps }> = ({ telemetry }) => {
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [diarioSuggestions, setDiarioSuggestions] = useState<DiarioSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch approval requests if the IPC method exists
        let approvalData: ApprovalRequest[] = [];
        const approvalList = (window.zaraIPC as any)?.approval?.list;
        if (approvalList) {
          approvalData = await approvalList.call(window.zaraIPC);
        } else {
          console.warn('Approval IPC method not available');
        }
        setApprovals(approvalData);

        // Fetch diario suggestions if the IPC method exists
        let suggestionData: DiarioSuggestion[] = [];
        const diarioSuggestionsMethod = (window.zaraIPC as any)?.diario?.suggestions;
        if (diarioSuggestionsMethod) {
          suggestionData = await diarioSuggestionsMethod.call(window.zaraIPC);
        } else {
          console.warn('Diario IPC method not available');
        }
        setDiarioSuggestions(suggestionData);
      } catch (err) {
        setError('Failed to load approval or diario data');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const handleApprove = async (id: string) => {
    const approveMethod = (window.zaraIPC as any)?.approval?.approve;
    if (approveMethod) {
      await approveMethod.call(window.zaraIPC, id);
      // Refetch approvals
      setApprovals(prev => prev.filter(a => a.id !== id));
    }
  };

  const handleReject = async (id: string) => {
    const rejectMethod = (window.zaraIPC as any)?.approval?.reject;
    if (rejectMethod) {
      await rejectMethod.call(window.zaraIPC, id);
      setApprovals(prev => prev.filter(a => a.id !== id));
    }
  };

  if (loading) {
    return <div className="unified-panel">Carregando...</div>;
  }

  if (error) {
    return <div className="unified-panel">Erro: {error}</div>;
  }

  return (
    <div className="unified-panel">
      <section className="unified-section">
        <h2>Telemetria</h2>
        <RoutingTelemetryPanel {...telemetry} />
      </section>

      <section className="unified-section">
        <h2>Aprovação Remota</h2>
        {approvals.length === 0 ? (
          <p>Nenhuma solicitação de aprovação pendente.</p>
        ) : (
          <ul>
            {approvals.map(approval => (
              <li key={approval.id}>
                <strong>{approval.action}</strong>
                <br />
                <small>Expira: {new Date(approval.expires).toLocaleString()}</small>
                <div className="approval-actions">
                  <button onClick={() => handleApprove(approval.id)}>Aprovar</button>
                  <button onClick={() => handleReject(approval.id)}>Rejeitar</button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="unified-section">
        <h2>Sugestões do Diário</h2>
        {diarioSuggestions.length === 0 ? (
          <p>Nenhuma sugestão pendente.</p>
        ) : (
          <ul>
            {diarioSuggestions.map(sug => (
              <li key={sug.id}>
                <strong>{sug.regra}</strong>: {sug.sugestoes_json.descricao}
                <br />
                <small>
                  Comando: {sug.comando_representativo} → Ação: {sug.acao} (
                  {sug.total_ocorrencias} ocorrências, {sug.sucessos} sucessos, {sug.falhas} falhas
                </small>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
};

export default UnifiedApprovalDiarioTelemetry;