import React from 'react';

export const Dashboard: React.FC = () => {
  return (
    <section className="dashboard p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Telegram */}
      <div className="widget bg-white/20 backdrop-blur-lg rounded-xl shadow-lg overflow-hidden">
        <header className="p-2 bg-white/10 text-sm font-medium">Telegram</header>
        <iframe
          src="https://web.telegram.org/k/"
          title="Telegram"
          className="w-full h-56 border-0"
          sandbox="allow-scripts allow-same-origin"
        />
      </div>
      {/* Claude AI */}
      <div className="widget bg-white/20 backdrop-blur-lg rounded-xl shadow-lg overflow-hidden">
        <header className="p-2 bg-white/10 text-sm font-medium">Claude AI</header>
        <iframe
          src="https://claude.ai/"
          title="Claude"
          className="w-full h-56 border-0"
          sandbox="allow-scripts allow-same-origin"
        />
      </div>
      {/* YouTube */}
      <div className="widget bg-white/20 backdrop-blur-lg rounded-xl shadow-lg overflow-hidden">
        <header className="p-2 bg-white/10 text-sm font-medium">YouTube</header>
        <iframe
          src="https://www.youtube.com/embed/dQw4w9WgXcQ"
          title="YouTube"
          className="w-full h-56 border-0"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>
      {/* Spotify */}
      <div className="widget bg-white/20 backdrop-blur-lg rounded-xl shadow-lg overflow-hidden">
        <header className="p-2 bg-white/10 text-sm font-medium">Spotify</header>
        <iframe
          src="https://open.spotify.com/embed/playlist/37i9dQZF1DXcBWIGoYBM5M"
          title="Spotify"
          className="w-full h-56 border-0"
          allow="encrypted-media"
          allowFullScreen
        />
      </div>
    </section>
  );
};
