import React from 'react';

// Nao usado pelo app real (App.tsx renderiza ZaraHome). O projeto Next.js que
// esta iframe apontava foi movido para _quarentena/interfaces-web-legado-20260904/.
export const ZaraDashboard: React.FC = () => (
  <iframe
    src="about:blank"
    className="w-full h-full"
    title="Zara Interface"
  />
);
