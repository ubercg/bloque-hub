'use client';

/**
 * Matterport 360° Virtual Tour Viewer
 * Embeds Matterport iframes with optional pin positioning.
 * When lazy=true, iframe src is set only when the container enters the viewport (IntersectionObserver).
 */

import { useState, useEffect, useRef } from 'react';
import { Maximize2, Minimize2 } from 'lucide-react';

interface MatterportViewerProps {
  url: string;
  pinPosition?: { x: number; y: number; z: number };
  title?: string;
  /** When true, iframe loads only when in viewport (default: true for LCP optimization) */
  lazy?: boolean;
  className?: string;
}

export default function MatterportViewer({
  url,
  pinPosition,
  title = 'Tour Virtual',
  lazy = true,
  className,
}: MatterportViewerProps) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [inView, setInView] = useState(!lazy);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!lazy || !containerRef.current) return;
    const el = containerRef.current;
    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        if (entry?.isIntersecting) setInView(true);
      },
      { rootMargin: '100px', threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [lazy]);

  const buildIframeUrl = () => {
    if (!pinPosition) return url;
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}pin=${pinPosition.x},${pinPosition.y},${pinPosition.z}`;
  };

  const iframeUrl = buildIframeUrl();
  const shouldLoadIframe = inView;

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  return (
    <div
      ref={containerRef}
      className={`relative ${
        isFullscreen
          ? 'fixed inset-0 z-50 bg-black'
          : `w-full h-96 rounded-lg overflow-hidden shadow-lg ${className ?? ''}`.trim()
      }`}
    >
      {/* Header */}
      <div className="absolute top-0 left-0 right-0 z-10 bg-gradient-to-b from-black/70 to-transparent p-4 flex items-center justify-between">
        <h3 className="text-white font-semibold">{title}</h3>
        {shouldLoadIframe && (
          <button
            type="button"
            onClick={toggleFullscreen}
            className="p-2 bg-white/20 hover:bg-white/30 rounded-lg transition backdrop-blur-sm"
            title={isFullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'}
            aria-label={isFullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'}
          >
            {isFullscreen ? (
              <Minimize2 className="w-5 h-5 text-white" />
            ) : (
              <Maximize2 className="w-5 h-5 text-white" />
            )}
          </button>
        )}
      </div>

      {/* Placeholder until in view (lazy) */}
      {!shouldLoadIframe && (
        <div
          className="w-full h-full flex items-center justify-center bg-gray-200 animate-pulse rounded-lg"
          aria-label="Cargando tour virtual"
        >
          <span className="text-gray-500 text-sm">Tour 360° — se cargará al desplazarse</span>
        </div>
      )}

      {/* Matterport Iframe - solo cuando inView o !lazy */}
      {shouldLoadIframe && (
        <iframe
          src={iframeUrl}
          className="w-full h-full border-0"
          allow="vr; xr; accelerometer; magnetometer; gyroscope"
          allowFullScreen
          title={title}
          loading="lazy"
        />
      )}

      {/* Instructions Overlay (only when not fullscreen and iframe loaded) */}
      {!isFullscreen && shouldLoadIframe && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-4">
          <p className="text-white text-sm">
            💡 Click y arrastra para explorar • Usa la rueda del mouse para acercar
          </p>
        </div>
      )}
    </div>
  );
}
