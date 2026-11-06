"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getSpeechRecognitionCtor,
  isSpeechRecognitionSupported,
  type SpeechRecognitionLike,
} from "@/lib/voice/speechRecognition";

type ListenOptions = {
  continuous?: boolean;
  interimResults?: boolean;
  onInterim?: (transcript: string) => void;
  onFinal?: (transcript: string) => void;
  onEnd?: () => void;
  onError?: (message: string) => void;
};

type DebouncedListenOptions = ListenOptions & {
  debounceMs: number;
  onDebouncedFinal: (transcript: string) => void;
};

const SPEECH_START_TIMEOUT_MS = 3000;

export function useVoiceMode() {
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const debounceTimerRef = useRef<number | null>(null);
  const accumulatedRef = useRef("");
  const speakEndRef = useRef<(() => void) | null>(null);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const stopListening = useCallback(() => {
    if (debounceTimerRef.current !== null) {
      window.clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }

    accumulatedRef.current = "";
    const recognition = recognitionRef.current;
    recognitionRef.current = null;

    if (recognition) {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      try {
        recognition.abort();
      } catch {
        // Ignore abort errors during cleanup.
      }
    }
  }, []);

  const stopSpeaking = useCallback(() => {
    setIsSpeaking(false);
    if (typeof window === "undefined") return;
    window.speechSynthesis.cancel();
    speakEndRef.current = null;
  }, []);

  const speak = useCallback(
    (text: string, onEnd?: () => void) => {
      if (typeof window === "undefined" || !window.speechSynthesis) {
        onEnd?.();
        return;
      }

      stopSpeaking();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-US";

      const handleEnd = () => {
        if (speakEndRef.current === handleEnd) {
          speakEndRef.current = null;
        }
        setIsSpeaking(false);
        onEnd?.();
      };

      // Browsers can refuse to speak (no user interaction yet, or no voices), and then
      // neither onend nor onerror fires. Give up quietly if it never starts, without
      // running onEnd, so nothing goes on to open the microphone.
      let started = false;
      utterance.onstart = () => {
        started = true;
      };
      window.setTimeout(() => {
        if (started || speakEndRef.current !== handleEnd) return;
        speakEndRef.current = null;
        window.speechSynthesis.cancel();
        setIsSpeaking(false);
      }, SPEECH_START_TIMEOUT_MS);

      utterance.onend = handleEnd;
      utterance.onerror = handleEnd;
      speakEndRef.current = handleEnd;

      setIsSpeaking(true);
      window.speechSynthesis.speak(utterance);
    },
    [stopSpeaking],
  );

  const startListening = useCallback(
    (options: ListenOptions) => {
      const Ctor = getSpeechRecognitionCtor();
      if (!Ctor) {
        options.onError?.("Voice input is not supported in this browser.");
        return;
      }

      stopListening();

      const recognition = new Ctor();
      recognition.continuous = options.continuous ?? false;
      recognition.interimResults = options.interimResults ?? false;
      recognition.lang = "en-US";

      recognition.onresult = (event) => {
        let interim = "";
        let finalText = "";

        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const result = event.results[i];
          const transcript = result[0]?.transcript ?? "";
          if (result.isFinal) {
            finalText += transcript;
          } else {
            interim += transcript;
          }
        }

        if (interim.trim()) {
          options.onInterim?.(interim.trim());
        }

        if (finalText.trim()) {
          options.onFinal?.(finalText.trim());
        }
      };

      recognition.onerror = (event) => {
        if (event.error === "aborted" || event.error === "no-speech") {
          return;
        }
        options.onError?.(event.message ?? event.error);
      };

      recognition.onend = () => {
        if (recognitionRef.current === recognition) {
          recognitionRef.current = null;
        }
        options.onEnd?.();
      };

      recognitionRef.current = recognition;

      try {
        recognition.start();
      } catch (err) {
        recognitionRef.current = null;
        const message =
          err instanceof Error ? err.message : "Failed to start voice input.";
        options.onError?.(message);
      }
    },
    [stopListening],
  );

  const startDebouncedListening = useCallback(
    (options: DebouncedListenOptions) => {
      accumulatedRef.current = "";

      startListening({
        continuous: options.continuous ?? true,
        interimResults: options.interimResults ?? true,
        onInterim: (transcript) => {
          options.onInterim?.(transcript);
        },
        onFinal: (transcript) => {
          accumulatedRef.current = `${accumulatedRef.current} ${transcript}`.trim();
          options.onFinal?.(accumulatedRef.current);

          if (debounceTimerRef.current !== null) {
            window.clearTimeout(debounceTimerRef.current);
          }

          debounceTimerRef.current = window.setTimeout(() => {
            debounceTimerRef.current = null;
            const text = accumulatedRef.current.trim();
            accumulatedRef.current = "";
            if (text) {
              options.onDebouncedFinal(text);
            }
          }, options.debounceMs);
        },
        onEnd: options.onEnd,
        onError: options.onError,
      });
    },
    [startListening],
  );

  useEffect(() => {
    return () => {
      stopListening();
      stopSpeaking();
    };
  }, [stopListening, stopSpeaking]);

  return {
    isRecognitionSupported: isSpeechRecognitionSupported(),
    isSpeaking,
    speak,
    stopSpeaking,
    startListening,
    startDebouncedListening,
    stopListening,
  };
}
