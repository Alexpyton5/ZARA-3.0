import React from 'react';

export const ZaraHome: React.FC = () => {
  return (
    <div className="zara-panels-grid">
      {/* TELA */}
      <div className="zara-panel-card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '14.5px', fontWeight: 600, color: 'var(--txt-1)', letterSpacing: '-0.012em' }}>Tela</span>
          <div style={{ flexGrow: 1 }} />
          <div style={{ width: '23px', height: '23px', borderRadius: '7px', background: 'rgba(176,208,164,0.09)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--txt-2)" strokeWidth="2.1" strokeLinecap="round"><path d="M3 8V5.5A2.5 2.5 0 0 1 5.5 3H8M16 3h2.5A2.5 2.5 0 0 1 21 5.5V8M21 16v2.5a2.5 2.5 0 0 1-2.5 2.5H16M8 21H5.5A2.5 2.5 0 0 1 3 18.5V16"/></svg>
          </div>
          <div style={{ width: '23px', height: '23px', borderRadius: '7px', background: 'rgba(176,208,164,0.09)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--txt-2)" strokeWidth="2.1" strokeLinecap="round"><rect x="2.5" y="5" width="19" height="14" rx="2"/><path d="M2.5 9.5h19"/></svg>
          </div>
        </div>
        <div style={{ flexGrow: 1, display: 'flex', gap: '8px', minHeight: 0 }}>
          <div style={{ flexGrow: 1, borderRadius: '13px', overflow: 'hidden', position: 'relative', border: '1px solid rgba(176,208,164,0.13)', minWidth: 0 }}>
            <img src="/zara-interface/wallpaper.jpg" alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
            <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(0,0,0,0.26) 0%, transparent 32%, transparent 64%, rgba(0,0,0,0.42) 100%)' }} />
            <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '27px', background: 'rgba(18,24,20,0.55)', backdropFilter: 'blur(16px)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px' }}>
              <div style={{ width: '12px', height: '12px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5px' }}>
                <div style={{ background: 'rgba(235,245,232,0.72)', borderRadius: '1px' }}></div>
                <div style={{ background: 'rgba(235,245,232,0.72)', borderRadius: '1px' }}></div>
                <div style={{ background: 'rgba(235,245,232,0.72)', borderRadius: '1px' }}></div>
                <div style={{ background: 'rgba(235,245,232,0.72)', borderRadius: '1px' }}></div>
              </div>
              <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: 'rgba(120,170,255,0.72)' }}></div>
              <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: 'rgba(235,245,232,0.28)' }}></div>
              <div style={{ width: '12px', height: '12px', borderRadius: '3px', background: 'var(--accent)' }}></div>
            </div>
            <div style={{ position: 'absolute', top: '9px', left: '10px', display: 'flex', alignItems: 'center', gap: '6px', padding: '3px 9px', borderRadius: '999px', background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(14px)', border: '1px solid rgba(176,208,164,0.18)' }}>
              <div style={{ width: '5px', height: '5px', borderRadius: '50%', background: 'var(--accent)' }}></div>
              <span style={{ fontSize: '9px', color: 'rgba(238,246,235,0.9)', fontWeight: 600 }}>Área de trabalho</span>
            </div>
          </div>
          <div style={{ width: '40px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '5px', alignItems: 'center' }}>
            <div style={{ width: '36px', height: '36px', borderRadius: '11px', background: 'rgba(143,193,127,0.20)', border: '1px solid rgba(143,193,127,0.32)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round"><rect x="2.5" y="4" width="19" height="13" rx="2"/><path d="M8.5 21h7"/></svg>
            </div>
            <div style={{ width: '36px', height: '36px', borderRadius: '11px', background: 'rgba(176,208,164,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--txt-3)" strokeWidth="1.8" strokeLinejoin="round"><circle cx="12" cy="11.5" r="3.1"/><path d="M4 8.4A2.2 2.2 0 0 1 6.2 6.2h1.4l1.1-1.7h6.6l1.1 1.7h1.4A2.2 2.2 0 0 1 20 8.4v8.4a2.2 2.2 0 0 1-2.2 2.2H6.2A2.2 2.2 0 0 1 4 16.8Z"/></svg>
            </div>
            <div style={{ width: '36px', height: '36px', borderRadius: '11px', background: 'rgba(176,208,164,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="15" height="15" viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="4" fill="#ff0033" opacity="0.78"/><path d="M10 9.2v5.6l4.6-2.8z" fill="#fff"/></svg>
            </div>
            <div style={{ width: '36px', height: '36px', borderRadius: '11px', background: 'rgba(176,208,164,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--txt-3)" strokeWidth="1.8" strokeLinejoin="round"><path d="M5 3.5h14l-2 17-5 2-5-2z"/><path d="M8.5 8h7l-.5 4.5-3 1-3-1"/></svg>
            </div>
            <div style={{ width: '36px', height: '36px', borderRadius: '11px', background: 'rgba(176,208,164,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--txt-3)" strokeWidth="1.8" strokeLinejoin="round"><rect x="3" y="3" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2"/></svg>
            </div>
          </div>
        </div>
      </div>

      {/* SPOTIFY + REFLEXOS */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '13px', minWidth: 0 }}>
        <div className="zara-panel-card" style={{ flexGrow: 1, padding: '13px', display: 'flex', flexDirection: 'column', gap: '10px', minHeight: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <svg width="17" height="17" viewBox="0 0 24 24"><circle cx="12" cy="12" r="12" fill="#1DB954"/><path d="M6.4 9.6c3.6-1.05 8.1-.75 11.1 1.05M7.2 12.6c3-.9 6.6-.6 9.15.9M8.1 15.45c2.4-.68 5.1-.45 7.05.68" stroke="#0b0f0b" strokeWidth="1.55" strokeLinecap="round" fill="none"/></svg>
            <span style={{ fontSize: '11.5px', fontWeight: 600, color: 'var(--txt-2)' }}>Spotify</span>
            <div style={{ flexGrow: 1 }} />
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#1DB954" strokeWidth="2" strokeLinecap="round"><rect x="4" y="3" width="16" height="14" rx="2"/><path d="M8 21h8"/></svg>
              <span style={{ fontSize: '9.5px', color: '#1DB954', fontWeight: 600 }}>ZARA</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '11px', alignItems: 'center' }}>
            <div style={{ width: '56px', height: '56px', borderRadius: '5px', flexShrink: 0, position: 'relative', overflow: 'hidden', boxShadow: '0 6px 16px rgba(0,0,0,0.5)', background: 'linear-gradient(135deg, #2b1b3d 0%, #7a2f52 44%, #c9603f 100%)' }}>
              <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(28px 28px at 70% 26%, rgba(255,255,255,0.28), transparent 70%)' }} />
            </div>
            <div style={{ minWidth: 0, flexGrow: 1 }}>
              <div style={{ fontSize: '13.5px', fontWeight: 600, color: 'var(--txt-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', letterSpacing: '-0.008em' }}>Take Five</div>
              <div style={{ fontSize: '11.5px', color: 'var(--txt-3)', marginTop: '1px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>The Dave Brubeck Quartet</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginTop: '8px' }}>
                <span style={{ fontSize: '9.5px', color: 'var(--txt-4)', fontVariantNumeric: 'tabular-nums' }}>2:14</span>
                <div style={{ flexGrow: 1, height: '3px', borderRadius: '2px', background: 'rgba(214,230,208,0.18)', position: 'relative' }}>
                  <div style={{ position: 'absolute', inset: '0 59% 0 0', borderRadius: '2px', background: 'rgba(238,246,235,0.92)' }} />
                </div>
                <span style={{ fontSize: '9.5px', color: 'var(--txt-4)', fontVariantNumeric: 'tabular-nums' }}>5:24</span>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px' }}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--txt-3)" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="var(--txt-1)"><path d="M19 5.5v13l-10-6.5z"/><rect x="4.5" y="5.5" width="2.4" height="13" rx="1.2"/></svg>
            <div style={{ width: '33px', height: '33px', borderRadius: '50%', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="#0b0f0b"><rect x="6" y="4.5" width="4" height="15" rx="1.4"/><rect x="14" y="4.5" width="4" height="15" rx="1.4"/></svg>
            </div>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="var(--txt-1)"><path d="M5 5.5v13l10-6.5z"/><rect x="17.1" y="5.5" width="2.4" height="13" rx="1.2"/></svg>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--txt-3)" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M17 2.5 21 6.5l-4 4"/><path d="M3 12.5v-2a4 4 0 0 1 4-4h14"/><path d="M7 21.5 3 17.5l4-4"/><path d="M21 11.5v2a4 4 0 0 1-4 4H3"/></svg>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '13px', height: '82px' }}>
          <div className="zara-panel-card" style={{ padding: '11px', borderRadius: '18px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.9" strokeLinecap="round"><path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5.5 5.5 0 0 1 7 0"/><circle cx="12" cy="19.4" r="1.1" fill="var(--accent)"/></svg>
              <div style={{ width: '29px', height: '17px', borderRadius: '999px', background: 'var(--accent)', position: 'relative' }}>
                <div style={{ position: 'absolute', right: '2px', top: '2px', width: '13px', height: '13px', borderRadius: '50%', background: '#0d150f' }} />
              </div>
            </div>
            <div><div style={{ fontSize: '11.5px', color: 'var(--txt-1)', fontWeight: 500 }}>Wi‑Fi</div><div style={{ fontSize: '9.5px', color: 'var(--txt-4)' }}>NET_5G</div></div>
          </div>
          <div className="zara-panel-card" style={{ padding: '11px', borderRadius: '18px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--txt-3)" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20.5a8.5 8.5 0 1 1 8.2-10.7"/><path d="M17 3.5v5h5"/></svg>
              <div style={{ width: '29px', height: '17px', borderRadius: '999px', background: 'rgba(176,208,164,0.18)', position: 'relative' }}>
                <div style={{ position: 'absolute', left: '2px', top: '2px', width: '13px', height: '13px', borderRadius: '50%', background: 'rgba(214,230,208,0.5)' }} />
              </div>
            </div>
            <div><div style={{ fontSize: '11.5px', color: 'var(--txt-1)', fontWeight: 500 }}>Luz noturna</div><div style={{ fontSize: '9.5px', color: 'var(--txt-4)' }}>Desligada</div></div>
          </div>
        </div>
      </div>

      {/* SOM */}
      <div className="zara-panel-card" style={{ padding: '13px 11px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '9px' }}>
        <div style={{ alignSelf: 'stretch', display: 'flex', alignItems: 'center' }}>
          <span style={{ fontSize: '12.5px', fontWeight: 600, color: 'var(--txt-1)' }}>Som</span>
          <div style={{ flexGrow: 1 }} />
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="var(--txt-3)" strokeWidth="2.2" strokeLinecap="round"><path d="m6 9 6 6 6-6"/></svg>
        </div>
        <div style={{ flexGrow: 1, width: '44px', borderRadius: '999px', background: 'rgba(176,208,164,0.10)', border: '1px solid var(--edge-soft)', position: 'relative', overflow: 'hidden' }}>
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: '62%', background: 'linear-gradient(180deg, var(--accent), #5f8354)' }} />
          <div style={{ position: 'absolute', left: '50%', bottom: '12px', transform: 'translateX(-50%)' }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="#0b120c"><path d="M11 5 6.6 8.6H3.5v6.8h3.1L11 19z"/><path d="M15.4 8.6a4.7 4.7 0 0 1 0 6.8" stroke="#0b120c" strokeWidth="1.9" fill="none" strokeLinecap="round"/></svg>
          </div>
        </div>
        <div style={{ fontSize: '20px', fontWeight: 600, color: 'var(--txt-1)', letterSpacing: '-0.02em', fontVariantNumeric: 'tabular-nums' }}>62<span style={{ fontSize: '11.5px', color: 'var(--txt-3)', fontWeight: 400 }}>%</span></div>
        <div style={{ alignSelf: 'stretch', paddingTop: '8px', borderTop: '1px solid var(--edge-soft)', display: 'flex', alignItems: 'center', gap: '7px' }}>
          <svg width="19" height="19" viewBox="0 0 120 120" fill="none" style={{ flexShrink: 0 }}>
            <path d="M26 64V56a34 34 0 0 1 68 0v8" stroke="rgba(214,230,208,0.8)" strokeWidth="7" strokeLinecap="round"/>
            <rect x="17" y="60" width="18" height="30" rx="8" fill="rgba(214,230,208,0.72)"/>
            <rect x="85" y="60" width="18" height="30" rx="8" fill="rgba(214,230,208,0.72)"/>
          </svg>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: '10.5px', color: 'var(--txt-1)', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>HyperX Cloud II</div>
            <div style={{ fontSize: '9px', color: 'var(--txt-4)' }}>USB</div>
          </div>
        </div>
      </div>

      {/* GALÁXIA DE MEMÓRIA */}
      <div className="zara-panel-card" style={{ padding: '13px', display: 'flex', flexDirection: 'column', gap: '8px', position: 'relative', overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <span style={{ fontSize: '14.5px', fontWeight: 600, color: 'var(--txt-1)', letterSpacing: '-0.012em' }}>Memória</span>
          <div style={{ flexGrow: 1 }} />
          <div style={{ display: 'flex', gap: '4px' }}>
            <div style={{ width: '21px', height: '21px', borderRadius: '7px', background: 'rgba(176,208,164,0.09)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--txt-2)" strokeWidth="2.6" strokeLinecap="round"><path d="M5 12h14"/></svg>
            </div>
            <div style={{ width: '21px', height: '21px', borderRadius: '7px', background: 'rgba(176,208,164,0.09)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--txt-2)" strokeWidth="2.6" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>
            </div>
            <div style={{ width: '21px', height: '21px', borderRadius: '7px', background: 'rgba(176,208,164,0.09)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--txt-2)" strokeWidth="2.2" strokeLinecap="round"><path d="M3 8V5.5A2.5 2.5 0 0 1 5.5 3H8M16 3h2.5A2.5 2.5 0 0 1 21 5.5V8M21 16v2.5a2.5 2.5 0 0 1-2.5 2.5H16M8 21H5.5A2.5 2.5 0 0 1 3 18.5V16"/></svg>
            </div>
          </div>
        </div>
        <div style={{ flexGrow: 1, position: 'relative', borderRadius: '13px', overflow: 'hidden', background: '#26343a' }}>
          <svg width="100%" height="100%" viewBox="0 0 620 620" preserveAspectRatio="xMidYMid slice" style={{ position: 'absolute', inset: 0 }}>
            <g stroke="rgba(163,196,196,0.30)" strokeWidth="0.55" fill="none">
              <line x1="310" y1="310" x2="339" y2="315"/>
              <line x1="310" y1="310" x2="333" y2="328"/>
              <line x1="310" y1="310" x2="322" y2="338"/>
              <line x1="310" y1="310" x2="308" y2="336"/>
              <line x1="310" y1="310" x2="292" y2="338"/>
              <line x1="310" y1="310" x2="287" y2="324"/>
              <line x1="310" y1="310" x2="283" y2="311"/>
              <line x1="310" y1="310" x2="284" y2="298"/>
              <line x1="310" y1="310" x2="292" y2="287"/>
              <line x1="310" y1="310" x2="304" y2="277"/>
              <line x1="310" y1="310" x2="319" y2="283"/>
              <line x1="310" y1="310" x2="333" y2="288"/>
              <line x1="310" y1="310" x2="342" y2="300"/>
            </g>
          </svg>
        </div>
      </div>
    </div>
  );
};