import React from 'react';

interface Props { children: React.ReactNode; }
interface State { error: Error | null; }

export class RendererErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ZARA Renderer] Uncaught React error:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <main style={{ minHeight: '100vh', background: '#020604', color: '#d8ffe9', padding: 32, fontFamily: 'Segoe UI, sans-serif' }}>
          <h1 style={{ margin: 0, fontSize: 20, color: '#55ffad' }}>ZARA — falha no renderer</h1>
          <p style={{ maxWidth: 760, opacity: 0.82 }}>
            A janela Electron abriu, mas a interface React encontrou um erro. Esta tela evita um painel completamente preto e preserva o diagnóstico para correção.
          </p>
          <pre style={{ whiteSpace: 'pre-wrap', padding: 16, border: '1px solid rgba(85,255,173,.25)', borderRadius: 10, background: '#06100b' }}>
            {this.state.error.message}
          </pre>
        </main>
      );
    }
    return this.props.children;
  }
}
