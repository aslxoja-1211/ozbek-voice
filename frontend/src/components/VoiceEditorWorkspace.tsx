"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Placeholder from "@tiptap/extension-placeholder";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  Bold,
  Check,
  Copy,
  Eraser,
  Heading1,
  Languages,
  List,
  Mic,
  MicOff,
  Redo2,
  RefreshCw,
  Send,
  Sparkles,
  Undo2,
  Wifi,
  WifiOff,
} from "lucide-react";

import { PcmVoiceRecorder } from "@/lib/audioRecorder";
import { applyTextToTiptap, serializeEditorState } from "@/lib/tiptapSync";
import type {
  HistoryEntry,
  PipelineResponse,
  TranslationLanguage,
  WSServerMessage,
} from "@/types/editor";

function resolveWebSocketUrl(): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL?.trim();
  if (configured) {
    return configured;
  }
  if (typeof window !== "undefined") {
    const { protocol, hostname, host, port } = window.location;
    if ((hostname === "localhost" || hostname === "127.0.0.1") && port === "3000") {
      return "ws://localhost:8000/ws/voice";
    }
    const wsProtocol = protocol === "https:" ? "wss:" : "ws:";
    return `${wsProtocol}//${host}/ws/voice`;
  }
  return "ws://localhost:8000/ws/voice";
}

const UZBEK_PRESETS = [
  {
    label: "+ Diktovka",
    cmd: "Men kecha Toshkentda uchrashuv o'tkazdim.",
    tone: "text-sky-300 border-sky-500/30 hover:border-sky-400",
  },
  {
    label: "REPLACE: kecha -> bugun",
    cmd: "kecha so'zini bugun deb o'zgartir",
    tone: "text-amber-300 border-amber-500/30 hover:border-amber-400",
  },
  {
    label: "REPLACE: Toshkent -> Samarqand",
    cmd: "Toshkentni Samarqandga almashtir",
    tone: "text-amber-300 border-amber-500/30 hover:border-amber-400",
  },
  {
    label: "FORMAT: Ro'yxat",
    cmd: "oxirgi gapni ro'yxatga aylantir",
    tone: "text-violet-300 border-violet-500/30 hover:border-violet-400",
  },
  {
    label: "DELETE: Oxirgi gap",
    cmd: "oxirgi gapni o'chir",
    tone: "text-rose-300 border-rose-500/30 hover:border-rose-400",
  },
  {
    label: "UNDO: Bekor qil",
    cmd: "bekor qil",
    tone: "text-slate-300 border-slate-600 hover:border-slate-400",
  },
];

export default function VoiceEditorWorkspace() {
  const [wsConnected, setWsConnected] = useState(false);
  const [stageText, setStageText] = useState<string>("");
  const [activeProviders, setActiveProviders] = useState({
    stt: "auto",
    llm: "auto",
  });
  const [sttOverride, setSttOverride] = useState<string>("");
  const [llmOverride, setLlmOverride] = useState<string>("");
  const [isRecording, setIsRecording] = useState(false);
  const [isHandsFree, setIsHandsFree] = useState(false);
  const [vadSpeaking, setVadSpeaking] = useState(false);
  const [isBrowserListening, setIsBrowserListening] = useState(false);
  const [vuLevel, setVuLevel] = useState(0);
  const [simInput, setSimInput] = useState("");
  const [lastResult, setLastResult] = useState<PipelineResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  const [targetLang, setTargetLang] = useState<TranslationLanguage>("ru");
  const [translatedText, setTranslatedText] = useState("");
  const [isTranslating, setIsTranslating] = useState(false);
  const [translationLatencyMs, setTranslationLatencyMs] = useState<number | null>(null);
  const [translationProvider, setTranslationProvider] = useState<string>("");
  const [translationError, setTranslationError] = useState<string | null>(null);
  const [copiedTranslation, setCopiedTranslation] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<PcmVoiceRecorder | null>(null);
  const speechRecRef = useRef<{ stop: () => void } | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const translateDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const targetLangRef = useRef<TranslationLanguage>("ru");
  const sttOverrideRef = useRef<string>("");
  const llmOverrideRef = useRef<string>("");
  const isRecordingRef = useRef(false);
  const isHandsFreeRef = useRef(false);
  const pttActiveRef = useRef(false);
  const lastTranslatedKeyRef = useRef<string>("");

  useEffect(() => {
    targetLangRef.current = targetLang;
  }, [targetLang]);

  useEffect(() => {
    sttOverrideRef.current = sttOverride;
  }, [sttOverride]);

  useEffect(() => {
    llmOverrideRef.current = llmOverride;
  }, [llmOverride]);

  useEffect(() => {
    isRecordingRef.current = isRecording;
  }, [isRecording]);

  useEffect(() => {
    isHandsFreeRef.current = isHandsFree;
  }, [isHandsFree]);

  const requestTranslation = useCallback(
    (text: string, langOverride?: TranslationLanguage, force = false) => {
      const clean = text.trim();
      const lang = langOverride ?? targetLangRef.current;

      if (!clean) {
        lastTranslatedKeyRef.current = "";
        setTranslatedText("");
        setTranslationLatencyMs(null);
        setTranslationError(null);
        setIsTranslating(false);
        return;
      }

      const key = `${lang}::${clean}`;
      if (!force && lastTranslatedKeyRef.current === key) {
        return;
      }

      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;

      lastTranslatedKeyRef.current = key;
      setTranslationError(null);
      setIsTranslating(true);
      ws.send(
        JSON.stringify({
          type: "translate",
          text: clean,
          target_language: lang,
          provider: llmOverrideRef.current || null,
        })
      );
    },
    []
  );

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Placeholder.configure({
        placeholder:
          "Mikrofonni bosib o'zbekcha gapiring yoki pastdan ovozli buyruq sinab ko'ring...",
      }),
    ],
    content: "",
    editorProps: {
      attributes: {
        class: "tiptap px-6 py-4 text-base text-slate-100",
      },
    },
    onUpdate: ({ editor: activeEd }) => {
      if (translateDebounceRef.current) {
        clearTimeout(translateDebounceRef.current);
      }
      const serialized = serializeEditorState(activeEd);
      translateDebounceRef.current = setTimeout(() => {
        requestTranslation(serialized);
      }, 650);
    },
  });

  const editorRef = useRef(editor);
  useEffect(() => {
    editorRef.current = editor;
  }, [editor]);

  const handlePipelineResult = useCallback((payload: PipelineResponse) => {
    setLastResult(payload);
    setStageText("");
    setErrorMsg(null);
    setActiveProviders({
      stt: payload.providers.stt_provider,
      llm: payload.providers.llm_provider,
    });

    const activeEditor = editorRef.current;
    if (activeEditor) {
      if (payload.client_action === "UNDO") {
        activeEditor.chain().focus().undo().run();
        requestTranslation(serializeEditorState(activeEditor), undefined, true);
      } else if (payload.client_action === "REDO") {
        activeEditor.chain().focus().redo().run();
        requestTranslation(serializeEditorState(activeEditor), undefined, true);
      } else if (payload.diff.changed) {
        applyTextToTiptap(activeEditor, payload.diff.new_text);
        requestTranslation(payload.diff.new_text);
      }
    }

    setHistory((prev) => [
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        timestamp: new Date().toLocaleTimeString(),
        rawTranscript: payload.raw_transcript,
        command: payload.command,
        strategy: payload.diff.applied_strategy,
        totalMs: payload.latency.total_ms,
      },
      ...prev.slice(0, 24),
    ]);
  }, [requestTranslation]);

  useEffect(() => {
    let unmounted = false;

    const connect = () => {
      if (unmounted) return;
      const ws = new WebSocket(resolveWebSocketUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        if (!unmounted) {
          setWsConnected(true);
          setErrorMsg(null);
        }
      };

      ws.onclose = () => {
        if (unmounted) return;
        setWsConnected(false);
        reconnectTimerRef.current = setTimeout(connect, 1800);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WSServerMessage;
          if (msg.type === "connected") {
            setActiveProviders({ stt: msg.active_stt, llm: msg.active_llm });
          } else if (msg.type === "status") {
            setStageText(msg.stage);
          } else if (msg.type === "result") {
            handlePipelineResult(msg.payload);
          } else if (msg.type === "translation_status") {
            setIsTranslating(true);
            setTranslationError(null);
          } else if (msg.type === "translation_result") {
            if (msg.payload.target_language === targetLangRef.current) {
              setTranslatedText(msg.payload.translated_text);
              setTranslationLatencyMs(msg.payload.latency_ms);
              setTranslationProvider(msg.payload.provider);
              setTranslationError(null);
              setIsTranslating(false);
            }
          } else if (msg.type === "translation_error") {
            setIsTranslating(false);
            setTranslationError(msg.message);
          } else if (msg.type === "error") {
            setStageText("");
            setErrorMsg(msg.message);
          }
        } catch {
          setErrorMsg("Serverdan noto'g'ri WebSocket javobi keldi.");
        }
      };
    };

    connect();

    return () => {
      unmounted = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (translateDebounceRef.current) clearTimeout(translateDebounceRef.current);
      wsRef.current?.close();
      speechRecRef.current?.stop();
      void recorderRef.current?.stop();
    };
  }, [handlePipelineResult]);

  const getCurrentText = useCallback((): string => {
    if (!editorRef.current) return "";
    return serializeEditorState(editorRef.current);
  }, []);

  const sendTextCommand = useCallback(
    (transcript: string) => {
      const clean = transcript.trim();
      const ws = wsRef.current;
      if (!clean || !ws || ws.readyState !== WebSocket.OPEN) return;

      setErrorMsg(null);
      ws.send(
        JSON.stringify({
          type: "text_command",
          editor_state: getCurrentText(),
          raw_transcript: clean,
          llm_provider: llmOverride || null,
        })
      );
    },
    [getCurrentText, llmOverride]
  );

  const sendStartUtterance = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(
      JSON.stringify({
        type: "start_utterance",
        editor_state: getCurrentText(),
        mime_type: "audio/pcm",
        sample_rate: 16000,
        stt_provider: sttOverrideRef.current || null,
        llm_provider: llmOverrideRef.current || null,
      })
    );
  }, [getCurrentText]);

  const sendEndUtterance = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(
      JSON.stringify({
        type: "end_utterance",
        editor_state: getCurrentText(),
        stt_provider: sttOverrideRef.current || null,
        llm_provider: llmOverrideRef.current || null,
      })
    );
  }, [getCurrentText]);

  const startManualCapture = useCallback(async () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setErrorMsg("WebSocket serveriga ulanilmagan. Backend ishlayotganini tekshiring.");
      return;
    }
    if (isRecordingRef.current || isHandsFreeRef.current) return;

    try {
      setErrorMsg(null);
      const recorder = new PcmVoiceRecorder();
      recorderRef.current = recorder;
      sendStartUtterance();

      await recorder.start(
        {
          onPcmChunk: (chunk) => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(chunk);
            }
          },
          onLevel: (rms) => {
            setVuLevel(Math.min(100, Math.round(rms * 450)));
          },
        },
        { autoVad: false }
      );
      setIsRecording(true);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Mikrofonga ruxsat olinmadi.";
      setErrorMsg(`Mikrofon xatoligi: ${message}`);
      setIsRecording(false);
    }
  }, [sendStartUtterance]);

  const stopManualCapture = useCallback(async () => {
    if (!isRecordingRef.current) return;
    await recorderRef.current?.stop();
    setIsRecording(false);
    setVuLevel(0);
    sendEndUtterance();
  }, [sendEndUtterance]);

  const toggleRecording = useCallback(async () => {
    if (isHandsFreeRef.current) {
      await recorderRef.current?.stop();
      setIsHandsFree(false);
      setVadSpeaking(false);
      setVuLevel(0);
      return;
    }
    if (!isRecordingRef.current) {
      await startManualCapture();
    } else {
      await stopManualCapture();
    }
  }, [startManualCapture, stopManualCapture]);

  const toggleHandsFree = useCallback(async () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setErrorMsg("WebSocket serveriga ulanilmagan. Backend ishlayotganini tekshiring.");
      return;
    }

    if (isHandsFreeRef.current) {
      await recorderRef.current?.stop();
      setIsHandsFree(false);
      setVadSpeaking(false);
      setVuLevel(0);
      return;
    }

    if (isRecordingRef.current) {
      await stopManualCapture();
    }

    try {
      setErrorMsg(null);
      const recorder = new PcmVoiceRecorder();
      recorderRef.current = recorder;
      await recorder.start(
        {
          onUtteranceStart: () => {
            sendStartUtterance();
          },
          onPcmChunk: (chunk) => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(chunk);
            }
          },
          onUtteranceCommit: () => {
            sendEndUtterance();
          },
          onUtteranceCancel: () => {
            setStageText("");
          },
          onVadSpeakingChange: (speaking) => {
            setVadSpeaking(speaking);
          },
          onLevel: (rms) => {
            setVuLevel(Math.min(100, Math.round(rms * 450)));
          },
        },
        {
          autoVad: true,
          speechThreshold: 0.015,
          silenceCommitMs: 1200,
          minSpeechMs: 240,
          preRollCount: 3,
        }
      );
      setIsHandsFree(true);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Mikrofonga ruxsat olinmadi.";
      setErrorMsg(`Mikrofon xatoligi: ${message}`);
      setIsHandsFree(false);
      setVadSpeaking(false);
    }
  }, [sendEndUtterance, sendStartUtterance, stopManualCapture]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.code === "Space" && !e.repeat) {
        e.preventDefault();
        if (!isRecordingRef.current && !isHandsFreeRef.current) {
          pttActiveRef.current = true;
          void startManualCapture();
        }
      }
    };

    const releasePtt = () => {
      if (!pttActiveRef.current) return;
      pttActiveRef.current = false;
      void stopManualCapture();
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (pttActiveRef.current && (e.code === "Space" || e.key === "Control")) {
        e.preventDefault();
        releasePtt();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", releasePtt);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", releasePtt);
    };
  }, [startManualCapture, stopManualCapture]);

  const toggleBrowserSpeech = useCallback(() => {
    interface BrowserSpeechResultEvent {
      results?: ArrayLike<ArrayLike<{ transcript?: string }>>;
    }
    interface BrowserSpeechErrorEvent {
      error?: string;
    }
    interface BrowserSpeechRecognition {
      lang: string;
      interimResults: boolean;
      continuous: boolean;
      onstart: (() => void) | null;
      onresult: ((e: BrowserSpeechResultEvent) => void) | null;
      onerror: ((e: BrowserSpeechErrorEvent) => void) | null;
      onend: (() => void) | null;
      start: () => void;
      stop: () => void;
    }

    const win = window as unknown as {
      SpeechRecognition?: new () => BrowserSpeechRecognition;
      webkitSpeechRecognition?: new () => BrowserSpeechRecognition;
    };
    const SR = win.SpeechRecognition || win.webkitSpeechRecognition;
    if (!SR) {
      setErrorMsg(
        "Brauzeringiz Web Speech API ni qo'llamaydi (Chrome yoki Edge ishlating)."
      );
      return;
    }

    if (isBrowserListening && speechRecRef.current) {
      speechRecRef.current.stop();
      return;
    }

    const rec = new SR();
    rec.lang = "uz-UZ";
    rec.interimResults = false;
    rec.continuous = false;
    speechRecRef.current = rec;

    rec.onstart = () => {
      setErrorMsg(null);
      setIsBrowserListening(true);
    };
    rec.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript ?? "";
      if (transcript.trim()) sendTextCommand(transcript.trim());
    };
    rec.onerror = (event) => {
      setErrorMsg(`Brauzer ovoz xatoligi: ${event.error ?? "noma'lum"}`);
    };
    rec.onend = () => {
      setIsBrowserListening(false);
    };
    rec.start();
  }, [isBrowserListening, sendTextCommand]);

  const handleSimSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!simInput.trim()) return;
    sendTextCommand(simInput);
    setSimInput("");
  };

  const llmUnderTarget = (lastResult?.latency.llm_ms ?? 0) <= 800;

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-5">
      {/* Header */}
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-800 bg-slate-900/75 px-5 py-4 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-sky-400 to-indigo-600 flex items-center justify-center font-bold text-slate-950 shadow-lg shadow-sky-500/20">
            AV
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-white flex items-center gap-2">
              Aqua Voice Uzbek
              <span className="rounded-md bg-sky-500/15 border border-sky-500/30 px-2 py-0.5 text-[11px] font-medium text-sky-300">
                Tiptap + WebSockets
              </span>
            </h1>
            <p className="text-xs text-slate-400">
              O&apos;zbek tilida jonli ovozli kiritish, Intent Detection va Text Diff Engine
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 ${
              wsConnected
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                : "border-rose-500/30 bg-rose-500/10 text-rose-300"
            }`}
          >
            {wsConnected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
            {wsConnected
              ? stageText
                ? `Holat: ${stageText}...`
                : "WebSocket Ulangan"
              : "Ulanmoqda..."}
          </span>

          <span className="rounded-full border border-slate-700 bg-slate-800/80 px-3 py-1 text-slate-300">
            STT: <strong className="text-sky-300">{activeProviders.stt}</strong> · LLM:{" "}
            <strong className="text-emerald-300">{activeProviders.llm}</strong>
          </span>
        </div>
      </header>

      {/* Main Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left: Rich Text Tiptap Editor */}
        <section className="lg:col-span-7 flex flex-col rounded-2xl border border-slate-800 bg-slate-900/60 overflow-hidden">
          {/* Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 bg-slate-900/90 px-4 py-2.5">
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleBold().run()}
                className={`rounded-lg p-1.5 transition ${
                  editor?.isActive("bold")
                    ? "bg-sky-500/20 text-sky-300"
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
                title="Qalin (Bold)"
              >
                <Bold className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleHeading({ level: 1 }).run()}
                className={`rounded-lg p-1.5 transition ${
                  editor?.isActive("heading", { level: 1 })
                    ? "bg-sky-500/20 text-sky-300"
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
                title="Sarlavha (H1)"
              >
                <Heading1 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => editor?.chain().focus().toggleBulletList().run()}
                className={`rounded-lg p-1.5 transition ${
                  editor?.isActive("bulletList")
                    ? "bg-sky-500/20 text-sky-300"
                    : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                }`}
                title="Ro'yxat (Bullet List)"
              >
                <List className="h-4 w-4" />
              </button>
            </div>

            <div className="flex items-center gap-1.5">
              {lastResult && (
                <span className="rounded-md border border-sky-500/30 bg-sky-500/15 px-2 py-0.5 text-[11px] font-medium text-sky-300">
                  {lastResult.command.action} · {lastResult.diff.applied_strategy}
                </span>
              )}
              <button
                type="button"
                onClick={() => editor?.chain().focus().undo().run()}
                disabled={!editor?.can().undo()}
                className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-300 hover:bg-slate-700 disabled:opacity-35"
                title="Bekor qilish (Undo)"
              >
                <Undo2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => editor?.chain().focus().redo().run()}
                disabled={!editor?.can().redo()}
                className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-300 hover:bg-slate-700 disabled:opacity-35"
                title="Qaytarish (Redo)"
              >
                <Redo2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => {
                  editor?.commands.clearContent(true);
                  requestTranslation("");
                }}
                className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-rose-300 hover:bg-slate-700"
                title="Matnni tozalash"
              >
                <Eraser className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Tiptap Canvas */}
          <div className="flex-1 min-h-[220px] bg-slate-950/30">
            <EditorContent editor={editor} />
          </div>

          {/* Live Translation Panel (RU / EN) */}
          <div className="border-t border-slate-800 bg-slate-900/55 px-5 py-3.5 space-y-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Languages className="h-4 w-4 text-emerald-400" />
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Tarjima
                </span>
                <div className="inline-flex rounded-lg border border-slate-700 bg-slate-950/80 p-0.5 text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      setTargetLang("ru");
                      targetLangRef.current = "ru";
                      requestTranslation(getCurrentText(), "ru", true);
                    }}
                    className={`rounded-md px-2.5 py-1 font-medium transition ${
                      targetLang === "ru"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Ruscha (RU)
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setTargetLang("en");
                      targetLangRef.current = "en";
                      requestTranslation(getCurrentText(), "en", true);
                    }}
                    className={`rounded-md px-2.5 py-1 font-medium transition ${
                      targetLang === "en"
                        ? "bg-sky-500/20 text-sky-300"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Inglizcha (EN)
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-1.5 text-xs">
                {isTranslating && (
                  <span className="text-sky-300 animate-pulse">Tarjima qilinmoqda...</span>
                )}
                {!isTranslating && translationLatencyMs !== null && (
                  <span className="rounded-md bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                    {translationProvider ? `${translationProvider} · ` : ""}
                    {translationLatencyMs.toFixed(0)} ms
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => requestTranslation(getCurrentText(), targetLang, true)}
                  className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-300 hover:bg-slate-700"
                  title="Qayta tarjima qilish"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${isTranslating ? "animate-spin" : ""}`} />
                </button>
                <button
                  type="button"
                  disabled={!translatedText}
                  onClick={() => {
                    if (!translatedText) return;
                    void navigator.clipboard.writeText(translatedText);
                    setCopiedTranslation(true);
                    setTimeout(() => setCopiedTranslation(false), 1500);
                  }}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700 disabled:opacity-35"
                  title="Tarjimani nusxalash"
                >
                  {copiedTranslation ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-400" /> Nusxa olindi
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5" /> Nusxa
                    </>
                  )}
                </button>
              </div>
            </div>

            {translationError ? (
              <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                {translationError}
              </div>
            ) : (
              <div className="min-h-[96px] max-h-48 overflow-y-auto rounded-xl border border-slate-800/90 bg-slate-950/60 px-4 py-3 text-sm leading-relaxed text-slate-200 whitespace-pre-wrap">
                {translatedText || (
                  <span className="text-slate-500">
                    O&apos;zbekcha matn kiritilganda bu yerda avtomatik{" "}
                    {targetLang === "ru" ? "ruscha" : "inglizcha"} tarjimasi chiqadi...
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Voice & Simulation Dock */}
          <div className="border-t border-slate-800 bg-slate-950/80 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => void toggleRecording()}
                  className={`inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition shadow-lg ${
                    isRecording
                      ? "mic-pulse bg-rose-500 text-white hover:bg-rose-400 shadow-rose-500/25"
                      : "bg-sky-500 text-slate-950 hover:bg-sky-400 shadow-sky-500/20"
                  }`}
                >
                  {isRecording ? (
                    <>
                      <MicOff className="h-4 w-4" /> To&apos;xtatish va yuborish
                    </>
                  ) : (
                    <>
                      <Mic className="h-4 w-4" /> Gapirish (Ctrl+Space)
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => void toggleHandsFree()}
                  className={`inline-flex items-center gap-2 rounded-xl border px-3.5 py-2.5 text-sm font-medium transition ${
                    isHandsFree
                      ? vadSpeaking
                        ? "mic-pulse border-emerald-400 bg-emerald-500/25 text-emerald-200"
                        : "border-sky-400/60 bg-sky-500/20 text-sky-200"
                      : "border-violet-500/40 bg-violet-500/15 text-violet-300 hover:bg-violet-500/25"
                  }`}
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      isHandsFree
                        ? vadSpeaking
                          ? "bg-emerald-400 animate-ping"
                          : "bg-sky-400"
                        : "bg-violet-400"
                    }`}
                  />
                  {isHandsFree
                    ? vadSpeaking
                      ? "Gap eshitilmoqda..."
                      : "Hands-Free (Auto-VAD)"
                    : "Hands-Free (Auto-VAD)"}
                </button>

                <button
                  type="button"
                  onClick={toggleBrowserSpeech}
                  className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2.5 text-xs font-medium transition ${
                    isBrowserListening
                      ? "mic-pulse border-rose-400 bg-rose-500/25 text-rose-200"
                      : "border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25"
                  }`}
                >
                  <Mic className="h-3.5 w-3.5" />
                  {isBrowserListening ? "Eshitilmoqda..." : "Brauzer (uz-UZ)"}
                </button>

                <div className="w-20 h-2.5 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-emerald-400 to-sky-400 transition-all duration-75"
                    style={{ width: `${vuLevel}%` }}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs">
                <label className="text-slate-400">STT:</label>
                <select
                  value={sttOverride}
                  onChange={(e) => setSttOverride(e.target.value)}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200"
                >
                  <option value="">auto</option>
                  <option value="gemini">gemini (multimodal)</option>
                  <option value="local_whisper">local_whisper (offline)</option>
                  <option value="mock">mock</option>
                  <option value="mohirpool">mohirpool</option>
                  <option value="openai">openai</option>
                </select>

                <label className="text-slate-400 ml-1">LLM:</label>
                <select
                  value={llmOverride}
                  onChange={(e) => setLlmOverride(e.target.value)}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200"
                >
                  <option value="">auto</option>
                  <option value="mock">mock</option>
                  <option value="gemini">gemini</option>
                  <option value="openai">openai</option>
                </select>
              </div>
            </div>

            <form onSubmit={handleSimSubmit} className="flex gap-2">
              <input
                type="text"
                value={simInput}
                onChange={(e) => setSimInput(e.target.value)}
                placeholder="Ovozli buyruq / transkriptni matn sifatida sinash..."
                className="flex-1 rounded-xl border border-slate-700 bg-slate-900 px-3.5 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
              />
              <button
                type="submit"
                className="inline-flex items-center gap-1.5 rounded-xl border border-sky-500/40 bg-sky-500/15 px-4 py-2 text-sm font-medium text-sky-300 hover:bg-sky-500/25 transition"
              >
                <Send className="h-3.5 w-3.5" /> Yuborish
              </button>
            </form>

            <div className="flex flex-wrap gap-1.5">
              {UZBEK_PRESETS.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => sendTextCommand(preset.cmd)}
                  className={`rounded-lg border bg-slate-900 px-2.5 py-1 text-xs transition ${preset.tone}`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Right: JSON Output Schema, Latency & History */}
        <aside className="lg:col-span-5 space-y-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-sky-400" /> Intent & Diff Inspector
              </h2>
              <span
                className={`rounded-full px-2.5 py-0.5 text-xs font-mono ${
                  lastResult
                    ? llmUnderTarget
                      ? "bg-emerald-500/20 text-emerald-300"
                      : "bg-amber-500/20 text-amber-300"
                    : "bg-slate-800 text-slate-400"
                }`}
              >
                {lastResult ? `${lastResult.latency.total_ms.toFixed(0)} ms` : "0 ms"}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5">
                <div className="text-[11px] text-slate-400">STT</div>
                <div className="text-sm font-mono font-semibold text-sky-300">
                  {lastResult ? `${lastResult.latency.stt_ms.toFixed(1)} ms` : "0 ms"}
                </div>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5">
                <div className="text-[11px] text-slate-400">LLM (&lt;800ms)</div>
                <div className="text-sm font-mono font-semibold text-emerald-300">
                  {lastResult ? `${lastResult.latency.llm_ms.toFixed(1)} ms` : "0 ms"}
                </div>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-2.5">
                <div className="text-[11px] text-slate-400">Umumiy</div>
                <div className="text-sm font-mono font-semibold text-white">
                  {lastResult ? `${lastResult.latency.total_ms.toFixed(1)} ms` : "0 ms"}
                </div>
              </div>
            </div>

            <div>
              <div className="text-xs text-slate-400 mb-1">Xom transkript (`raw_transcript`):</div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/80 px-3 py-2 text-sm text-slate-200 min-h-[38px]">
                {lastResult?.raw_transcript || "—"}
              </div>
            </div>

            <div>
              <div className="text-xs text-slate-400 mb-1">LLM JSON Output Schema:</div>
              <pre className="rounded-xl border border-slate-800 bg-slate-950/90 p-3 text-xs font-mono text-emerald-300 overflow-x-auto">
                {JSON.stringify(
                  lastResult?.command ?? {
                    action: "APPEND",
                    target: "",
                    replacement: "",
                    updated_full_text: null,
                    confidence: 0.0,
                  },
                  null,
                  2
                )}
              </pre>
            </div>

            {(errorMsg || lastResult?.note) && (
              <div
                className={`rounded-xl border px-3 py-2 text-xs ${
                  errorMsg
                    ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
                    : "border-amber-500/30 bg-amber-500/10 text-amber-200"
                }`}
              >
                {errorMsg ?? lastResult?.note}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="text-sm font-semibold text-white mb-2">Amallar Tarixi</h2>
            {history.length === 0 ? (
              <p className="text-xs text-slate-500">Hali amallar bajarilmadi.</p>
            ) : (
              <ul className="space-y-2 max-h-56 overflow-y-auto text-xs">
                {history.map((item) => (
                  <li
                    key={item.id}
                    className="rounded-lg border border-slate-800 bg-slate-950/70 px-3 py-2 flex items-center justify-between gap-2"
                  >
                    <span className="truncate text-slate-200">
                      <strong className="text-sky-300">{item.command.action}</strong> —{" "}
                      {item.rawTranscript}
                    </span>
                    <span className="shrink-0 font-mono text-slate-400">
                      {item.totalMs.toFixed(0)}ms
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
