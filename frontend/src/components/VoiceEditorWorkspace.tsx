"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Placeholder from "@tiptap/extension-placeholder";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  Check,
  Copy,
  Eraser,
  HelpCircle,
  Languages,
  RefreshCw,
  Undo2,
} from "lucide-react";

import VoiceOrb from "@/components/VoiceOrb";
import { PcmVoiceRecorder } from "@/lib/audioRecorder";
import { applyTextToTiptap, serializeEditorState } from "@/lib/tiptapSync";
import type {
  PipelineResponse,
  TranslationLanguage,
  WSServerMessage,
} from "@/types/editor";

const STORAGE_KEY = "aqua-voice-uzbek-doc-v1";

function resolveWsUrl(): string {
  const configured = process.env.NEXT_PUBLIC_WS_URL?.trim();
  if (typeof window === "undefined") {
    return configured ?? "ws://localhost:8000/ws/voice";
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  if (configured && !configured.includes("localhost") && !configured.includes("127.0.0.1")) {
    return configured;
  }
  if (window.location.port === "3000") {
    return `${proto}//${window.location.hostname}:8000/ws/voice`;
  }
  return `${proto}//${window.location.host}/ws/voice`;
}

interface SavedWorkspaceState {
  text: string;
  targetLang: TranslationLanguage;
  translatedText: string;
}

export default function VoiceEditorWorkspace() {
  const [wsConnected, setWsConnected] = useState(false);
  const [stageText, setStageText] = useState<string>("");
  const [isListening, setIsListening] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [statusHint, setStatusHint] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);

  const [copiedUz, setCopiedUz] = useState(false);
  const [targetLang, setTargetLang] = useState<TranslationLanguage>("ru");
  const [translatedText, setTranslatedText] = useState("");
  const [isTranslating, setIsTranslating] = useState(false);
  const [translationError, setTranslationError] = useState<string | null>(null);
  const [copiedTranslation, setCopiedTranslation] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<PcmVoiceRecorder | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const translateDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const targetLangRef = useRef<TranslationLanguage>("ru");
  const translatedTextRef = useRef<string>("");
  const isListeningRef = useRef(false);
  const pressStartedAtRef = useRef(0);
  const keyboardPttRef = useRef(false);
  const lastTranslatedKeyRef = useRef<string>("");
  const hydratedRef = useRef(false);

  useEffect(() => {
    targetLangRef.current = targetLang;
  }, [targetLang]);

  useEffect(() => {
    translatedTextRef.current = translatedText;
  }, [translatedText]);

  useEffect(() => {
    isListeningRef.current = isListening;
  }, [isListening]);

  const persistWorkspace = useCallback(
    (text: string, lang: TranslationLanguage, translation: string) => {
      try {
        const payload: SavedWorkspaceState = {
          text,
          targetLang: lang,
          translatedText: translation,
        };
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      } catch {
        // Ignore storage quota errors
      }
    },
    []
  );

  const requestTranslation = useCallback(
    (text: string, langOverride?: TranslationLanguage, force = false) => {
      const clean = text.trim();
      const lang = langOverride ?? targetLangRef.current;

      if (!clean) {
        lastTranslatedKeyRef.current = "";
        setTranslatedText("");
        setTranslationError(null);
        setIsTranslating(false);
        persistWorkspace("", lang, "");
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
        })
      );
    },
    [persistWorkspace]
  );

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Placeholder.configure({
        placeholder:
          "Chapdagi sharni bosib turib o'zbekcha gapiring — matn va tarjima shu yerda jonli paydo bo'ladi...",
      }),
    ],
    content: "",
    editorProps: {
      attributes: {
        class: "tiptap px-6 py-5 text-[15px] sm:text-base text-slate-900",
      },
    },
    onUpdate: ({ editor: activeEd }) => {
      if (translateDebounceRef.current) {
        clearTimeout(translateDebounceRef.current);
      }
      const serialized = serializeEditorState(activeEd);
      persistWorkspace(serialized, targetLangRef.current, translatedTextRef.current);
      translateDebounceRef.current = setTimeout(() => {
        requestTranslation(serialized);
      }, 650);
    },
  });

  const editorRef = useRef(editor);
  useEffect(() => {
    editorRef.current = editor;
    if (editor && !hydratedRef.current) {
      hydratedRef.current = true;
      try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw) as Partial<SavedWorkspaceState>;
          if (parsed.targetLang === "ru" || parsed.targetLang === "en") {
            setTargetLang(parsed.targetLang);
            targetLangRef.current = parsed.targetLang;
          }
          if (parsed.text) {
            applyTextToTiptap(editor, parsed.text);
          }
          if (parsed.translatedText) {
            setTranslatedText(parsed.translatedText);
          }
        }
      } catch {
        // Ignore corrupt localStorage payload
      }
    }
  }, [editor]);

  const getCurrentText = useCallback((): string => {
    if (!editorRef.current) return "";
    return serializeEditorState(editorRef.current);
  }, []);

  const handlePipelineResult = useCallback(
    (payload: PipelineResponse) => {
      setStageText("");
      setErrorMsg(null);
      setStatusHint(null);

      const activeEditor = editorRef.current;
      if (!activeEditor) return;

      if (payload.client_action === "UNDO") {
        activeEditor.chain().focus().undo().run();
        const restored = serializeEditorState(activeEditor);
        requestTranslation(restored, undefined, true);
        return;
      }

      if (payload.client_action === "REDO") {
        activeEditor.chain().focus().redo().run();
        const restored = serializeEditorState(activeEditor);
        requestTranslation(restored, undefined, true);
        return;
      }

      if (payload.diff.changed) {
        applyTextToTiptap(activeEditor, payload.diff.new_text);
        persistWorkspace(payload.diff.new_text, targetLangRef.current, translatedTextRef.current);
        requestTranslation(payload.diff.new_text);
      } else if (payload.note && !payload.raw_transcript) {
        setStatusHint(payload.note);
        setTimeout(() => setStatusHint(null), 2600);
      }
    },
    [persistWorkspace, requestTranslation]
  );

  useEffect(() => {
    let unmounted = false;

    const connect = () => {
      if (unmounted) return;
      const ws = new WebSocket(resolveWsUrl());
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
          if (msg.type === "status") {
            setStageText(msg.stage);
          } else if (msg.type === "result") {
            handlePipelineResult(msg.payload);
          } else if (msg.type === "translation_status") {
            setIsTranslating(true);
            setTranslationError(null);
          } else if (msg.type === "translation_result") {
            if (msg.payload.target_language === targetLangRef.current) {
              setTranslatedText(msg.payload.translated_text);
              setTranslationError(null);
              setIsTranslating(false);
              persistWorkspace(
                getCurrentText(),
                msg.payload.target_language,
                msg.payload.translated_text
              );
            }
          } else if (msg.type === "translation_error") {
            setIsTranslating(false);
            setTranslationError(msg.message);
          } else if (msg.type === "error") {
            setStageText("");
            setErrorMsg(msg.message);
          }
        } catch {
          setErrorMsg("Serverdan kutilmagan javob keldi.");
        }
      };
    };

    connect();

    return () => {
      unmounted = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (translateDebounceRef.current) clearTimeout(translateDebounceRef.current);
      wsRef.current?.close();
      void recorderRef.current?.stop();
    };
  }, [getCurrentText, handlePipelineResult, persistWorkspace]);

  const startHoldToTalk = useCallback(async () => {
    if (isListeningRef.current) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setErrorMsg("Serverga ulanilmagan. Sahifani yangilang yoki serverni tekshiring.");
      return;
    }

    try {
      setErrorMsg(null);
      setStatusHint(null);
      pressStartedAtRef.current = performance.now();
      isListeningRef.current = true;
      setIsListening(true);

      const recorder = new PcmVoiceRecorder();
      recorderRef.current = recorder;
      let startedUtterance = false;
      const pendingChunks: ArrayBuffer[] = [];

      await recorder.start(
        {
          onPcmChunk: (chunk) => {
            if (!isListeningRef.current || ws.readyState !== WebSocket.OPEN) return;
            if (!startedUtterance) {
              pendingChunks.push(chunk);
              return;
            }
            ws.send(chunk);
          },
          onLevel: (rms) => {
            setAudioLevel(Math.min(1, rms * 5.2));
          },
        },
        { autoVad: false }
      );

      // Guard if user released hold-to-talk while getUserMedia prompt/init was resolving
      if (!isListeningRef.current) {
        await recorder.stop();
        return;
      }

      ws.send(
        JSON.stringify({
          type: "start_utterance",
          editor_state: getCurrentText(),
          mime_type: "audio/pcm",
          sample_rate: 16000,
        })
      );
      startedUtterance = true;
      for (const chunk of pendingChunks) {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(chunk);
        }
      }
    } catch (err) {
      isListeningRef.current = false;
      setIsListening(false);
      setAudioLevel(0);
      const message =
        err instanceof Error ? err.message : "Mikrofonga ruxsat berilmadi.";
      setErrorMsg(`Mikrofon: ${message}`);
    }
  }, [getCurrentText]);

  const endHoldToTalk = useCallback(async () => {
    if (!isListeningRef.current) return;
    const heldMs = performance.now() - pressStartedAtRef.current;
    isListeningRef.current = false;
    setIsListening(false);
    setAudioLevel(0);

    await recorderRef.current?.stop();

    if (heldMs < 180) {
      setStatusHint("Gapirish uchun bosib turing");
      setTimeout(() => setStatusHint(null), 1800);
      return;
    }

    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      setStageText("processing");
      ws.send(
        JSON.stringify({
          type: "end_utterance",
          editor_state: getCurrentText(),
        })
      );
    }
  }, [getCurrentText]);

  useEffect(() => {
    const isTypingTarget = (target: EventTarget | null) => {
      if (!(target instanceof HTMLElement)) return false;
      return (
        target.isContentEditable ||
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT"
      );
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.repeat || e.code !== "Space") return;
      const useCtrlSpace = e.ctrlKey;
      const usePlainSpace = !e.ctrlKey && !e.altKey && !e.metaKey && !isTypingTarget(e.target);

      if ((useCtrlSpace || usePlainSpace) && !isListeningRef.current) {
        e.preventDefault();
        keyboardPttRef.current = true;
        void startHoldToTalk();
      }
    };

    const releaseKeyboardPtt = () => {
      if (!keyboardPttRef.current) return;
      keyboardPttRef.current = false;
      void endHoldToTalk();
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (keyboardPttRef.current && (e.code === "Space" || e.key === "Control")) {
        e.preventDefault();
        releaseKeyboardPtt();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", releaseKeyboardPtt);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", releaseKeyboardPtt);
    };
  }, [endHoldToTalk, startHoldToTalk]);

  const handleCopyUzbek = () => {
    const txt = getCurrentText();
    if (!txt.trim()) return;
    void navigator.clipboard.writeText(txt);
    setCopiedUz(true);
    setTimeout(() => setCopiedUz(false), 1500);
  };

  const handleToggleLanguage = () => {
    const next: TranslationLanguage = targetLang === "ru" ? "en" : "ru";
    setTargetLang(next);
    targetLangRef.current = next;
    requestTranslation(getCurrentText(), next, true);
  };

  const handleClear = () => {
    editor?.commands.clearContent(true);
    requestTranslation("");
    setStatusHint(null);
    setErrorMsg(null);
  };

  const orbCaption = errorMsg
    ? errorMsg
    : isListening
    ? "Gapiring... qo'yib yuboring"
    : stageText
    ? "Yozilmoqda..."
    : statusHint
    ? statusHint
    : "Bosib turib gapiring · Space / Ctrl+Space";

  return (
    <div className="min-h-screen flex flex-col">
      {/* Minimal Nest-style Top Bar */}
      <header className="w-full max-w-6xl mx-auto px-5 sm:px-8 pt-6 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-slate-950 text-xs font-bold text-white shadow-sm">
            AV
          </span>
          <span className="text-[15px] font-semibold tracking-tight text-slate-900">
            Aqua Voice
          </span>
        </div>

        <div className="inline-flex items-center gap-2 rounded-full border border-slate-200/90 bg-white/80 px-3 py-1 text-xs font-medium text-slate-600 shadow-sm backdrop-blur">
          <span
            className={`h-2 w-2 rounded-full ${
              wsConnected ? "bg-emerald-500" : "bg-amber-400 animate-pulse"
            }`}
          />
          {wsConnected ? "Tayyor" : "Ulanmoqda..."}
        </div>
      </header>

      {/* Main 2-Column Layout matching sketch */}
      <main className="flex-1 w-full max-w-6xl mx-auto px-5 sm:px-8 py-6 sm:py-10 flex items-center">
        <div className="w-full grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-10 items-center">
          {/* Left Column: Apple Siri Dark Squircle Voice Orb */}
          <div className="lg:col-span-4 flex flex-col items-center justify-center gap-4">
            <VoiceOrb
              isListening={isListening}
              isProcessing={Boolean(stageText)}
              audioLevel={audioLevel}
              disabled={!wsConnected}
              onPressStart={() => void startHoldToTalk()}
              onPressEnd={() => void endHoldToTalk()}
            />
            <p
              className={`text-center text-xs sm:text-sm font-medium transition-colors ${
                errorMsg
                  ? "text-rose-600"
                  : isListening
                  ? "text-sky-700"
                  : "text-slate-500"
              }`}
            >
              {orbCaption}
            </p>
          </div>

          {/* Right Column: 5 Clean Action Buttons + Main Editor & Translation Card */}
          <div className="lg:col-span-8 flex flex-col gap-3.5 relative">
            {/* 5 Top-Right Action Squares (from sketch) */}
            <div className="flex items-center justify-between sm:justify-start gap-2.5">
              {/* 1. Undo */}
              <button
                type="button"
                onClick={() => {
                  editor?.chain().focus().undo().run();
                  if (editor) {
                    requestTranslation(serializeEditorState(editor), undefined, true);
                  }
                }}
                disabled={!editor?.can().undo()}
                title="Bekor qilish (Undo)"
                className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200/90 bg-white/85 text-slate-700 shadow-sm backdrop-blur transition hover:bg-white hover:border-slate-300 disabled:opacity-35"
              >
                <Undo2 className="h-4 w-4" />
              </button>

              {/* 2. Copy Uzbek */}
              <button
                type="button"
                onClick={handleCopyUzbek}
                title="O'zbekcha matnni nusxalash"
                className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200/90 bg-white/85 text-slate-700 shadow-sm backdrop-blur transition hover:bg-white hover:border-slate-300"
              >
                {copiedUz ? (
                  <Check className="h-4 w-4 text-emerald-600" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
              </button>

              {/* 3. Language Toggle RU / EN */}
              <button
                type="button"
                onClick={handleToggleLanguage}
                title="Tarjima tilini almashtirish (Ruscha / Inglizcha)"
                className="inline-flex h-11 px-3.5 items-center justify-center gap-1.5 rounded-2xl border border-slate-200/90 bg-white/85 text-xs font-semibold text-slate-800 shadow-sm backdrop-blur transition hover:bg-white hover:border-slate-300"
              >
                <Languages className="h-4 w-4 text-teal-600" />
                <span>{targetLang.toUpperCase()}</span>
              </button>

              {/* 4. Clear */}
              <button
                type="button"
                onClick={handleClear}
                title="Matnni tozalash"
                className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200/90 bg-white/85 text-slate-700 shadow-sm backdrop-blur transition hover:bg-rose-50 hover:text-rose-600 hover:border-rose-200"
              >
                <Eraser className="h-4 w-4" />
              </button>

              {/* 5. Help / Voice Commands */}
              <button
                type="button"
                onClick={() => setShowHelp((prev) => !prev)}
                title="Ovozli buyruqlar qo'llanmasi"
                className={`inline-flex h-11 w-11 items-center justify-center rounded-2xl border shadow-sm backdrop-blur transition ${
                  showHelp
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200/90 bg-white/85 text-slate-700 hover:bg-white hover:border-slate-300"
                }`}
              >
                <HelpCircle className="h-4 w-4" />
              </button>
            </div>

            {/* Optional Help Popover */}
            {showHelp && (
              <div className="rounded-2xl border border-slate-200/90 bg-white/95 p-4 text-xs text-slate-600 shadow-lg backdrop-blur-xl space-y-1.5">
                <p className="font-semibold text-slate-900">Ovozli buyruqlar:</p>
                <p>
                  • <span className="font-medium text-slate-800">&quot;... so&apos;zini ... deb o&apos;zgartir&quot;</span> — so‘zni almashtiradi
                </p>
                <p>
                  • <span className="font-medium text-slate-800">&quot;oxirgi gapni o&apos;chir&quot;</span> — oxirgi gapni olib tashlaydi
                </p>
                <p>
                  • <span className="font-medium text-slate-800">&quot;oxirgi gapni ro&apos;yxatga aylantir&quot;</span> — ro‘yxatga soladi
                </p>
                <p>
                  • <span className="font-medium text-slate-800">&quot;bekor qil&quot;</span> — oxirgi o‘zgarishni orqaga qaytaradi
                </p>
              </div>
            )}

            {/* Main Frosted Glass Card: Uzbek Editor + Translation Below */}
            <div className="overflow-hidden rounded-[28px] border border-slate-200/85 bg-white/85 shadow-[0_24px_70px_-20px_rgba(15,23,42,0.12)] backdrop-blur-xl">
              {/* Uzbek Editor */}
              <div className="min-h-[210px] max-h-[340px] overflow-y-auto">
                <EditorContent editor={editor} />
              </div>

              {/* Translation Section Underneath */}
              <div className="border-t border-slate-200/75 bg-slate-50/75 px-6 py-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-teal-700">
                    {targetLang === "ru" ? "Ruscha tarjima" : "Inglizcha tarjima"}
                  </span>

                  <div className="flex items-center gap-1.5">
                    {isTranslating && (
                      <span className="text-[11px] text-slate-500 animate-pulse mr-1">
                        Tarjima...
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => requestTranslation(getCurrentText(), targetLang, true)}
                      title="Qayta tarjima"
                      className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-200/60 hover:text-slate-800 transition"
                    >
                      <RefreshCw
                        className={`h-3.5 w-3.5 ${isTranslating ? "animate-spin" : ""}`}
                      />
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
                      title="Tarjimani nusxalash"
                      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-200/60 hover:text-slate-900 disabled:opacity-35 transition"
                    >
                      {copiedTranslation ? (
                        <>
                          <Check className="h-3.5 w-3.5 text-emerald-600" /> Olindi
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
                  <p className="text-xs text-rose-600">{translationError}</p>
                ) : (
                  <div className="min-h-[76px] max-h-40 overflow-y-auto text-[14px] sm:text-[15px] leading-relaxed text-slate-700 whitespace-pre-wrap">
                    {translatedText || (
                      <span className="text-slate-400">
                        {targetLang === "ru"
                          ? "O'zbekcha gapirganingizda ruscha tarjimasi shu yerda chiqadi..."
                          : "O'zbekcha gapirganingizda inglizcha tarjimasi shu yerda chiqadi..."}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
