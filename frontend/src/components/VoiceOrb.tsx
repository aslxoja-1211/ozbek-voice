"use client";

import React, { useEffect, useRef } from "react";

interface VoiceOrbProps {
  isListening: boolean;
  isProcessing: boolean;
  audioLevel: number;
  disabled?: boolean;
  onPressStart: () => void;
  onPressEnd: () => void;
}

/**
 * Interactive 60fps Canvas AI Voice Orb inside an Apple-style dark squircle pod.
 * Reacts organically to live microphone amplitude and supports touch/mouse hold-to-talk.
 */
export default function VoiceOrb({
  isListening,
  isProcessing,
  audioLevel,
  disabled = false,
  onPressStart,
  onPressEnd,
}: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const activePointerIdRef = useRef<number | null>(null);

  const stateRef = useRef({
    isListening,
    isProcessing,
    targetLevel: audioLevel,
    smoothLevel: 0,
  });

  useEffect(() => {
    stateRef.current.isListening = isListening;
    stateRef.current.isProcessing = isProcessing;
    stateRef.current.targetLevel = Math.min(1, Math.max(0, audioLevel));
  }, [isListening, isProcessing, audioLevel]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let rafId = 0;
    const startTime = performance.now();

    // Deterministic micro-particles orbiting the glowing ring
    const particles = Array.from({ length: 68 }, (_, idx) => ({
      angle: (idx / 68) * Math.PI * 2,
      speed: (idx % 2 === 0 ? 1 : -1) * (0.18 + (idx % 7) * 0.04),
      radialOffset: ((idx * 17) % 100) / 100 - 0.5,
      size: 0.8 + (idx % 4) * 0.45,
      phase: idx * 0.9,
    }));

    const render = (now: number) => {
      const t = (now - startTime) * 0.001;
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      const size = Math.max(180, Math.round(rect.width));

      if (canvas.width !== Math.round(size * dpr) || canvas.height !== Math.round(size * dpr)) {
        canvas.width = Math.round(size * dpr);
        canvas.height = Math.round(size * dpr);
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size, size);

      const st = stateRef.current;
      const goal = st.isListening ? Math.max(0.16, st.targetLevel) : st.isProcessing ? 0.35 : 0.05;
      st.smoothLevel += (goal - st.smoothLevel) * 0.16;
      const lv = st.smoothLevel;

      const cx = size / 2;
      const cy = size / 2;
      const baseRadius = size * (0.31 + lv * 0.045 + Math.sin(t * 1.4) * 0.006);

      // Outer ambient halo
      const haloGrad = ctx.createRadialGradient(cx, cy, baseRadius * 0.65, cx, cy, baseRadius * 1.65);
      haloGrad.addColorStop(0, "rgba(0, 0, 0, 0)");
      haloGrad.addColorStop(0.58, `rgba(37, 99, 235, ${0.22 + lv * 0.32})`);
      haloGrad.addColorStop(0.78, `rgba(56, 189, 248, ${0.14 + lv * 0.25})`);
      haloGrad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = haloGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, baseRadius * 1.65, 0, Math.PI * 2);
      ctx.fill();

      ctx.save();
      ctx.globalCompositeOperation = "lighter";

      // Chromatic dispersion ring layers (warm coral fringe + deep blue + ice cyan + white core)
      const ringLayers = [
        {
          color: `rgba(255, 115, 65, ${0.26 + lv * 0.38})`,
          width: 4.5 + lv * 6,
          radiusBias: 3.5 + lv * 4,
          amp: 3.8 + lv * 14,
          freq1: 3,
          freq2: 5,
          phase: t * 1.7,
        },
        {
          color: `rgba(37, 115, 255, ${0.58 + lv * 0.35})`,
          width: 10 + lv * 12,
          radiusBias: 0,
          amp: 3.2 + lv * 13,
          freq1: 4,
          freq2: 6,
          phase: -t * 1.4,
        },
        {
          color: `rgba(56, 210, 255, ${0.65 + lv * 0.32})`,
          width: 5.5 + lv * 7,
          radiusBias: -1.5,
          amp: 2.8 + lv * 11,
          freq1: 5,
          freq2: 3,
          phase: t * 2.2,
        },
        {
          color: `rgba(235, 248, 255, ${0.55 + lv * 0.42})`,
          width: 2.0 + lv * 2.6,
          radiusBias: -2.2,
          amp: 2.2 + lv * 9,
          freq1: 6,
          freq2: 4,
          phase: t * 2.8,
        },
      ];

      const steps = 128;
      for (const layer of ringLayers) {
        ctx.beginPath();
        for (let i = 0; i <= steps; i++) {
          const theta = (i / steps) * Math.PI * 2;
          const wave =
            Math.sin(theta * layer.freq1 + layer.phase) * layer.amp * 0.6 +
            Math.cos(theta * layer.freq2 - layer.phase * 1.3) * layer.amp * 0.4;
          const swirl =
            st.isProcessing
              ? Math.sin(theta * 2 - t * 6.5) * 4.5
              : 0;
          const r = baseRadius + layer.radiusBias + wave + swirl;
          const x = cx + Math.cos(theta) * r;
          const y = cy + Math.sin(theta) * r;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.strokeStyle = layer.color;
        ctx.lineWidth = layer.width;
        ctx.stroke();
      }

      // Fine energetic fibers & particles around the perimeter
      for (const p of particles) {
        const a = p.angle + t * p.speed * (1 + lv * 2.2);
        const ripple = Math.sin(a * 4 + t * 2.5 + p.phase) * (2.5 + lv * 9);
        const pr = baseRadius + p.radialOffset * (8 + lv * 14) + ripple;
        const px = cx + Math.cos(a) * pr;
        const py = cy + Math.sin(a) * pr;
        ctx.fillStyle = `rgba(186, 230, 255, ${0.28 + lv * 0.55})`;
        ctx.beginPath();
        ctx.arc(px, py, p.size * (0.9 + lv * 0.6), 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();

      // Deep obsidian center core with subtle silk wave streaks inside
      const coreGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseRadius * 0.92);
      coreGrad.addColorStop(0, "rgba(3, 6, 14, 0.98)");
      coreGrad.addColorStop(0.75, "rgba(5, 11, 24, 0.94)");
      coreGrad.addColorStop(1, "rgba(15, 45, 95, 0.0)");
      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(cx, cy, baseRadius * 0.92, 0, Math.PI * 2);
      ctx.fill();

      // Subtle inner fluid light ribbons inside dark center
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, baseRadius * 0.84, 0, Math.PI * 2);
      ctx.clip();
      for (let line = 0; line < 4; line++) {
        ctx.beginPath();
        const yOff = (line - 1.5) * 12;
        for (let x = cx - baseRadius; x <= cx + baseRadius; x += 6) {
          const normX = (x - cx) / baseRadius;
          const waveY =
            cy +
            yOff +
            Math.sin(normX * 3.2 + t * (1.3 + line * 0.35) + line) * (7 + lv * 15) * (1 - normX * normX * 0.4);
          if (x === cx - baseRadius) ctx.moveTo(x, waveY);
          else ctx.lineTo(x, waveY);
        }
        ctx.strokeStyle = `rgba(125, 211, 252, ${0.12 + lv * 0.25})`;
        ctx.lineWidth = 1.2 + lv * 1.1;
        ctx.stroke();
      }
      ctx.restore();

      rafId = requestAnimationFrame(render);
    };

    rafId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(rafId);
  }, []);

  const handlePointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (e.button !== 0 && e.pointerType === "mouse") return;
    e.preventDefault();
    activePointerIdRef.current = e.pointerId;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Ignore if pointer capture isn't supported
    }
    onPressStart();
  };

  const finishPress = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (activePointerIdRef.current === null) return;
    if (e.pointerId !== activePointerIdRef.current) return;
    activePointerIdRef.current = null;
    try {
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    } catch {
      // Ignore
    }
    onPressEnd();
  };

  return (
    <button
      type="button"
      onPointerDown={handlePointerDown}
      onPointerUp={finishPress}
      onPointerCancel={finishPress}
      onContextMenu={(e) => e.preventDefault()}
      aria-label="Bosib turib o'zbekcha gapiring"
      className={`group relative flex aspect-square w-56 sm:w-64 items-center justify-center rounded-[48px] bg-[#05070c] border border-white/10 shadow-[0_28px_70px_-18px_rgba(8,38,74,0.45)] transition-transform duration-200 touch-none select-none focus:outline-none focus-visible:ring-4 focus-visible:ring-sky-400/50 ${
        isListening
          ? "scale-[1.03] shadow-[0_32px_80px_-12px_rgba(14,165,233,0.5)]"
          : "hover:scale-[1.015] active:scale-[1.025]"
      }`}
    >
      {/* Subtle Apple-like inner top specular sheen */}
      <span className="pointer-events-none absolute inset-[2px] rounded-[46px] bg-gradient-to-b from-white/[0.08] via-transparent to-transparent" />
      <canvas
        ref={canvasRef}
        className="pointer-events-none h-full w-full rounded-[48px]"
      />
    </button>
  );
}
