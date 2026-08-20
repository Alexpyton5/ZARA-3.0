import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import './Chat.css';

/**
 * ZARA Chat — Componente de conversação
 * 
 * Features:
 * - Mensagens do usuário (serifada) vs ZARA (mono/serifada)
 * - Streaming de resposta com cursor piscando
 * - Código com syntax highlighting básico
 * - Copy to clipboard
 * - Regroupamento por autor
 * - Acessível (ARIA live regions)
 * - Virtualização para listas longas
 * - Design tokens
 */

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  /** Metadados opcionais */
  metadata?: {
    model?: string;
    tokens?: number;
    duration?: number;
    error?: boolean;
    toolCalls?: ToolCall[];
  };
}

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
  error?: string;
}

export interface ChatProps {
  /** Lista de mensagens */
  messages: ChatMessage[];
  /** Callback para enviar mensagem */
  onSend: (content: string) => void;
  /** Callback para regenerar última resposta */
  onRegenerate?: () => void;
  /** Callback para copiar mensagem */
  onCopy?: (messageId: string, content: string) => void;
  /** Placeholder do input */
  placeholder?: string;
  /** Desabilita input */
  disabled?: boolean;
  /** Mostra timestamp */
  showTimestamps?: boolean;
  /** Agrupa mensagens consecutivas do mesmo autor */
  groupConsecutive?: boolean;
  /** Máximo de mensagens renderizadas (virtualização) */
  maxMessages?: number;
  /** Auto-scroll para nova mensagem */
  autoScroll?: boolean;
  /** Altura máxima da área de mensagens */
  maxHeight?: number | string;
  /** ClassName adicional */
  className?: string;
  /** Style adicional */
  style?: React.CSSProperties;
  /** Renderizador customizado para mensagem */
  renderMessage?: (message: ChatMessage, index: number) => React.ReactNode;
  /** Renderizador customizador para input */
  renderInput?: (props: ChatInputProps) => React.ReactNode;
}

export interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  disabled: boolean;
  placeholder: string;
  isStreaming: boolean;
}

const DEFAULT_PLACEHOLDER = 'Como posso pensar com você hoje?';
const MAX_MESSAGES_DEFAULT = 100;
const AUTO_SCROLL_THRESHOLD = 100; // px do bottom para auto-scroll

/** Formata timestamp relativo */
function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  
  if (diff < 60000) return 'agora';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}min`;
  if (diff < 86400000) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return date.toLocaleDateString([], { day: '2-digit', month: '2-digit' }) + ' ' + 
         date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/** Detecta blocos de código no markdown simples */
function parseContent(content: string): Array<{ type: 'text' | 'code'; content: string; lang?: string }> {
  const blocks: Array<{ type: 'text' | 'code'; content: string; lang?: string }> = [];
  const codeRegex = /```(\w*)\n([\s\S]*?)\n```/g;
  let lastIndex = 0;
  let match;
  
  while ((match = codeRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      blocks.push({ type: 'text', content: content.slice(lastIndex, match.index) });
    }
    blocks.push({ type: 'code', content: match[2], lang: match[1] || undefined });
    lastIndex = match.index + match[0].length;
  }
  
  if (lastIndex < content.length) {
    blocks.push({ type: 'text', content: content.slice(lastIndex) });
  }
  
  return blocks.length > 0 ? blocks : [{ type: 'text', content }];
}

/** Escape HTML básico */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&')
    .replace(/</g, '<')
    .replace(/>/g, '>')
    .replace(/"/g, '"')
    .replace(/'/g, '&#039;');
}

/** Componente de bloco de código */
const CodeBlock: React.FC<{ code: string; lang?: string; onCopy: () => void }> = ({ 
  code, 
  lang, 
  onCopy 
}) => {
  const [copied, setCopied] = useState(false);
  
  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    onCopy();
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  return (
    <div className="chat__code-block" data-lang={lang}>
      <div className="chat__code-header">
        <span className="chat__code-lang">{lang || 'texto'}</span>
        <button 
          className="chat__copy-btn" 
          onClick={handleCopy}
          aria-label={copied ? 'Copiado!' : 'Copiar código'}
          title={copied ? 'Copiado!' : 'Copiar código'}
        >
          {copied ? '✓' : '⎘'}
        </button>
      </div>
      <pre className="chat__code-pre"><code className={lang ? `language-${lang}` : ''}>{code}</code></pre>
    </div>
  );
};

/** Componente de mensagem individual */
const Message: React.FC<{ 
  message: ChatMessage; 
  showTimestamp: boolean; 
  isLast: boolean;
  groupWithPrevious: boolean;
  groupWithNext: boolean;
  onCopy: (id: string, content: string) => void;
}> = ({ 
  message, 
  showTimestamp, 
  isLast, 
  groupWithPrevious, 
  groupWithNext,
  onCopy 
}) => {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const isError = message.metadata?.error === true;
  const isStreaming = isLast && message.role === 'assistant' && !message.metadata?.error && message.content.endsWith('▊');
  
  const handleCopy = () => {
    onCopy(message.id, message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  
  const blocks = useMemo(() => parseContent(message.content), [message.content]);
  
  const roleLabel = useMemo(() => {
    switch (message.role) {
      case 'user': return 'Você';
      case 'assistant': return 'ZARA';
      case 'system': return 'Sistema';
      case 'tool': return 'Ferramenta';
      default: return message.role;
    }
  }, [message.role]);
  
  return (
    <article 
      className={`chat__message chat__message--${message.role} ${groupWithPrevious ? 'chat__message--grouped-prev' : ''} ${groupWithNext ? 'chat__message--grouped-next' : ''} ${isError ? 'chat__message--error' : ''} ${isStreaming ? 'chat__message--streaming' : ''}`}
      data-message-id={message.id}
      data-role={message.role}
    >
      {!groupWithPrevious && (
        <header className="chat__message-header">
          <strong className="chat__message-author">{roleLabel}</strong>
          {showTimestamp && (
            <time className="chat__message-time" dateTime={new Date(message.timestamp).toISOString()}>
              {formatTime(message.timestamp)}
            </time>
          )}
          {!isUser && !isSystem && !isStreaming && (
            <button 
              className="chat__copy-btn" 
              onClick={handleCopy}
              aria-label={copied ? 'Copiado!' : 'Copiar mensagem'}
            >
              {copied ? '✓' : '⎘'}
            </button>
          )}
        </header>
      )}
      
      <div className="chat__message-content">
        {blocks.map((block, i) => {
          if (block.type === 'code') {
            return (
              <CodeBlock 
                key={i} 
                code={block.content} 
                lang={block.lang} 
                onCopy={handleCopy} 
              />
            );
          }
          
          // Texto simples com quebras de linha preservadas
          return (
            <div key={i} className="chat__text-block" dangerouslySetInnerHTML={{ 
              __html: escapeHtml(block.content).replace(/\n/g, '<br/>') 
            }} />
          );
        })}
        
        {isStreaming && <span className="chat__cursor" aria-hidden="true">▊</span>}
      </div>
      
      {/* Tool calls expandíveis */}
      {message.metadata?.toolCalls && message.metadata.toolCalls.length > 0 && (
        <details className="chat__tool-calls">
          <summary className="chat__tool-calls-summary">
            <span>🔧 {message.metadata.toolCalls.length} ferramenta(s) executada(s)</span>
          </summary>
          <div className="chat__tool-calls-list">
            {message.metadata.toolCalls.map((tool, i) => (
              <div key={i} className="chat__tool-call">
                <div className="chat__tool-call-header">
                  <code>{tool.name}</code>
                  {tool.error && <span className="chat__tool-error">Erro</span>}
                </div>
                <pre className="chat__tool-args"><code>{JSON.stringify(tool.args, null, 2)}</code></pre>
                {tool.result !== undefined && (
                  <pre className="chat__tool-result"><code>{JSON.stringify(tool.result, null, 2)}</code></pre>
                )}
                {tool.error && (
                  <pre className="chat__tool-error-msg"><code>{tool.error}</code></pre>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
      
      {/* Metadados da resposta */}
      {message.metadata && !isUser && !isSystem && !groupWithNext && (
        <footer className="chat__message-meta">
          {message.metadata.model && <span className="chat__meta-model">{message.metadata.model}</span>}
          {message.metadata.tokens && <span className="chat__meta-tokens">{message.metadata.tokens} tokens</span>}
          {message.metadata.duration && <span className="chat__meta-duration">{message.metadata.duration}ms</span>}
        </footer>
      )}
    </article>
  );
};

/** Componente de input */
const ChatInput: React.FC<ChatInputProps> = ({ 
  value, 
  onChange, 
  onSubmit, 
  disabled, 
  placeholder, 
  isStreaming 
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [value]);
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim() || disabled || isStreaming) return;
    onSubmit(e);
  };
  
  return (
    <form className="chat__input-form" onSubmit={handleSubmit}>
      <textarea
        ref={textareaRef}
        className="chat__textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled || isStreaming}
        rows={1}
        aria-label="Mensagem para ZARA"
        aria-disabled={disabled || isStreaming}
      />
      <div className="chat__input-actions">
        <button 
          type="submit" 
          className="chat__send-btn"
          disabled={!value.trim() || disabled || isStreaming}
          aria-label={isStreaming ? 'ZARA está respondendo...' : 'Enviar mensagem'}
        >
          {isStreaming ? (
            <span className="chat__send-spinner" aria-hidden="true">⟳</span>
          ) : (
            '➤'
          )}
        </button>
      </div>
    </form>
  );
};

/** Componente principal Chat */
export const Chat: React.FC<ChatProps> = ({
  messages,
  onSend,
  onRegenerate,
  onCopy,
  placeholder = DEFAULT_PLACEHOLDER,
  disabled = false,
  showTimestamps = true,
  groupConsecutive = true,
  maxMessages = MAX_MESSAGES_DEFAULT,
  autoScroll = true,
  maxHeight = '60vh',
  className = '',
  style,
  renderMessage,
  renderInput,
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const scrollTimeoutRef = useRef<number>();
  
  // Determina agrupamento
  const groupedMessages = useMemo(() => {
    if (!groupConsecutive) return messages.map((m, i) => ({ 
      message: m, 
      index: i, 
      groupWithPrevious: false, 
      groupWithNext: false 
    }));
    
    return messages.map((message, index) => {
      const prev = messages[index - 1];
      const next = messages[index + 1];
      return {
        message,
        index,
        groupWithPrevious: prev?.role === message.role && prev?.role !== 'system',
        groupWithNext: next?.role === message.role && next?.role !== 'system',
      };
    });
  }, [messages, groupConsecutive]);
  
  // Auto-scroll
  const scrollToBottom = useCallback((smooth = true) => {
    messagesEndRef.current?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto' });
  }, []);
  
  useEffect(() => {
    if (autoScroll && messages.length > 0) {
      scrollToBottom();
    }
  }, [messages.length, autoScroll, scrollToBottom]);
  
  // Detecta scroll manual para mostrar botão "ir para o final"
  const handleScroll = useCallback(() => {
    const container = messagesContainerRef.current;
    if (!container) return;
    
    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    
    setShowScrollButton(distanceFromBottom > AUTO_SCROLL_THRESHOLD);
    
    // Limpa timeout anterior
    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    
    // Auto-hide scroll button após 3s se user não interagir
    scrollTimeoutRef.current = window.setTimeout(() => {
      if (distanceFromBottom <= AUTO_SCROLL_THRESHOLD) {
        setShowScrollButton(false);
      }
    }, 3000);
  }, []);
  
  // Regenerar última resposta
  const handleRegenerate = useCallback(() => {
    if (onRegenerate) {
      setIsStreaming(true);
      onRegenerate();
    }
  }, [onRegenerate]);
  
  // Enviar mensagem
  const handleSend = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const content = inputValue.trim();
    if (!content || disabled || isStreaming) return;
    
    setInputValue('');
    setIsStreaming(true);
    onSend(content);
  }, [inputValue, disabled, isStreaming, onSend]);
  
  // Callback quando streaming termina (pode ser chamado externamente)
  // const _handleStreamingEnd = useCallback(() => {
  //   setIsStreaming(false);
  // }, []);
  
  // Renderizador padrão de mensagem
  const defaultRenderMessage = useCallback((msg: ChatMessage, idx: number) => {
    const grouped = groupedMessages.find(g => g.index === idx);
    if (!grouped) return null;
    
    return (
      <Message
        key={msg.id}
        message={msg}
        showTimestamp={showTimestamps}
        isLast={idx === messages.length - 1}
        groupWithPrevious={grouped.groupWithPrevious}
        groupWithNext={grouped.groupWithNext}
        onCopy={onCopy || (() => {})}
      />
    );
  }, [groupedMessages, messages.length, showTimestamps, onCopy]);
  
  // Renderizador padrão de input
    const defaultRenderInput = useCallback((props: ChatInputProps) => (
      <ChatInput {...props} />
    ), []);
  
    const RenderMessage = useMemo(() => renderMessage || defaultRenderMessage, [renderMessage, defaultRenderMessage]);
    const RenderInput = useMemo(() => renderInput || defaultRenderInput, [renderInput, defaultRenderInput]);
  
  // Virtualização simples: só renderiza últimas N mensagens
  const visibleMessages = messages.slice(-maxMessages);
  const offset = messages.length - visibleMessages.length;
  
  return (
    <div 
      className={`chat ${className}`}
      style={{
        maxHeight,
        display: 'flex',
        flexDirection: 'column',
        ...style,
      }}
      data-streaming={isStreaming}
    >
      {/* Área de mensagens */}
      <div 
        ref={messagesContainerRef}
        className="chat__messages"
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Conversa com ZARA"
        style={{ maxHeight: '100%', overflowY: 'auto' }}
      >
        {messages.length === 0 && (
          <div className="chat__empty" role="status">
            <p className="chat__empty-text">Ainda não conversamos hoje.</p>
            <p className="chat__empty-hint">Digite algo abaixo para começar.</p>
          </div>
        )}
        
        {visibleMessages.map((message, i) => 
          RenderMessage(message, i + offset)
        )}
        
        <div ref={messagesEndRef} />
      </div>
      
      {/* Botão scroll para baixo */}
      {showScrollButton && (
        <button
          className="chat__scroll-btn"
          onClick={() => scrollToBottom(true)}
          aria-label="Ir para mensagens recentes"
          title="Novas mensagens"
        >
          ▼
        </button>
      )}
      
      {/* Indicador de streaming */}
      {isStreaming && (
        <div className="chat__streaming-indicator" aria-live="polite" aria-atomic="true">
          <span className="chat__streaming-dots" aria-hidden="true">
            <span>●</span><span>●</span><span>●</span>
          </span>
          <span className="chat__streaming-text">ZARA está pensando...</span>
          {onRegenerate && (
            <button 
              className="chat__regenerate-btn"
              onClick={handleRegenerate}
              disabled={isStreaming}
              aria-label="Regenerar resposta"
            >
              ⟳ Regenerar
            </button>
          )}
        </div>
      )}
      
      {/* Input area */}
      <div className="chat__input-area">
        <RenderInput
          value={inputValue}
          onChange={setInputValue}
          onSubmit={handleSend}
          disabled={disabled}
          placeholder={placeholder}
          isStreaming={isStreaming}
        />
      </div>
    </div>
  );
};

export default Chat;