export interface RecorderCallbacks {
  onPcmChunk: (chunk: ArrayBuffer) => void;
  onLevel?: (rms: number) => void;
  onUtteranceStart?: () => void;
  onUtteranceCommit?: () => void;
  onUtteranceCancel?: () => void;
  onVadSpeakingChange?: (speaking: boolean) => void;
}

export interface RecorderOptions {
  autoVad?: boolean;
  speechThreshold?: number;
  silenceCommitMs?: number;
  minSpeechMs?: number;
  preRollCount?: number;
}

function downsampleTo16k(input: Float32Array, inputRate: number): Float32Array {
  if (inputRate === 16000) return input;
  const ratio = inputRate / 16000;
  const outputLength = Math.round(input.length / ratio);
  const output = new Float32Array(outputLength);

  let outIdx = 0;
  let inOffset = 0;
  while (outIdx < outputLength) {
    const nextOffset = Math.round((outIdx + 1) * ratio);
    let sum = 0;
    let count = 0;
    for (let i = inOffset; i < nextOffset && i < input.length; i++) {
      sum += input[i];
      count++;
    }
    output[outIdx] = count > 0 ? sum / count : 0;
    outIdx++;
    inOffset = nextOffset;
  }
  return output;
}

function floatTo16BitPCM(samples: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < samples.length; i++) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(i * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
  return buffer;
}

/**
 * Captures browser microphone audio via Web Audio API and emits 16kHz mono PCM16 chunks,
 * supporting both manual/push-to-talk capture and continuous Auto-VAD hands-free mode.
 */
export class PcmVoiceRecorder {
  private audioCtx: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private processorNode: ScriptProcessorNode | null = null;
  private active = false;

  private autoVad = false;
  private inSpeech = false;
  private speechAccumMs = 0;
  private silenceAccumMs = 0;
  private minSpeechMs = 240;
  private preRoll: ArrayBuffer[] = [];
  private callbacks: RecorderCallbacks | null = null;

  async start(
    callbacks: RecorderCallbacks,
    options: RecorderOptions = {}
  ): Promise<void> {
    if (this.active) return;

    const autoVad = options.autoVad ?? false;
    const speechThreshold = options.speechThreshold ?? 0.015;
    const silenceCommitMs = options.silenceCommitMs ?? 1200;
    const minSpeechMs = options.minSpeechMs ?? 240;
    const preRollCount = options.preRollCount ?? 3;

    this.autoVad = autoVad;
    this.inSpeech = false;
    this.speechAccumMs = 0;
    this.silenceAccumMs = 0;
    this.minSpeechMs = minSpeechMs;
    this.preRoll = [];
    this.callbacks = callbacks;

    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;

    this.audioCtx = new AudioCtx();
    if (this.audioCtx.state === "suspended") {
      await this.audioCtx.resume();
    }
    this.sourceNode = this.audioCtx.createMediaStreamSource(this.mediaStream);
    this.processorNode = this.audioCtx.createScriptProcessor(4096, 1, 1);

    this.processorNode.onaudioprocess = (event: AudioProcessingEvent) => {
      if (!this.active || !this.audioCtx) return;
      const channelData = event.inputBuffer.getChannelData(0);

      let sumSq = 0;
      for (let i = 0; i < channelData.length; i++) {
        sumSq += channelData[i] * channelData[i];
      }
      const rms = Math.sqrt(sumSq / channelData.length);
      callbacks.onLevel?.(rms);

      const resampled = downsampleTo16k(channelData, this.audioCtx.sampleRate);
      const pcmBuffer = floatTo16BitPCM(resampled);

      if (!autoVad) {
        callbacks.onPcmChunk(pcmBuffer);
        return;
      }

      const frameMs = (channelData.length / this.audioCtx.sampleRate) * 1000;
      const isSpeechFrame = rms >= speechThreshold;

      if (!this.inSpeech) {
        this.preRoll.push(pcmBuffer);
        if (this.preRoll.length > preRollCount) {
          this.preRoll.shift();
        }
        if (isSpeechFrame) {
          this.inSpeech = true;
          this.speechAccumMs = frameMs;
          this.silenceAccumMs = 0;
          callbacks.onVadSpeakingChange?.(true);
          callbacks.onUtteranceStart?.();
          for (const frame of this.preRoll) {
            callbacks.onPcmChunk(frame);
          }
          this.preRoll = [];
        }
        return;
      }

      callbacks.onPcmChunk(pcmBuffer);
      if (isSpeechFrame) {
        this.speechAccumMs += frameMs;
        this.silenceAccumMs = 0;
      } else {
        this.silenceAccumMs += frameMs;
      }

      if (this.silenceAccumMs >= silenceCommitMs) {
        const validUtterance = this.speechAccumMs >= minSpeechMs;
        this.inSpeech = false;
        this.speechAccumMs = 0;
        this.silenceAccumMs = 0;
        this.preRoll = [];
        callbacks.onVadSpeakingChange?.(false);
        if (validUtterance) {
          callbacks.onUtteranceCommit?.();
        } else {
          callbacks.onUtteranceCancel?.();
        }
      }
    };

    this.sourceNode.connect(this.processorNode);
    this.processorNode.connect(this.audioCtx.destination);
    this.active = true;
  }

  async stop(): Promise<void> {
    const shouldCommit =
      this.active &&
      this.autoVad &&
      this.inSpeech &&
      this.speechAccumMs >= this.minSpeechMs;
    const cbs = this.callbacks;

    this.active = false;
    this.inSpeech = false;
    this.speechAccumMs = 0;
    this.silenceAccumMs = 0;
    this.preRoll = [];
    cbs?.onVadSpeakingChange?.(false);

    if (this.processorNode) {
      this.processorNode.disconnect();
      this.processorNode = null;
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
    if (this.audioCtx) {
      await this.audioCtx.close();
      this.audioCtx = null;
    }

    if (shouldCommit) {
      cbs?.onUtteranceCommit?.();
    }
    this.callbacks = null;
  }
}
