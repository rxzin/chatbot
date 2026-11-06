"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Files, LogOut, PanelLeft, X } from "lucide-react";
import { useChat } from "@/hooks/useChat";
import { useConversation } from "@/hooks/useConversation";
import { useDocuments } from "@/hooks/useDocuments";
import { useVoiceMode } from "@/hooks/useVoiceMode";
import { useLogout } from "@/hooks/useLogout";
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler";
import {
  parseYesNo,
  stripMarkdownForSpeech,
} from "@/lib/voice/speechRecognition";
import { cn } from "@/lib/utils";
import { ChatInput, type InputMode } from "./ChatInput";
import { ConversationList } from "./ConversationList";
import { DocumentPanel } from "./DocumentPanel";
import { MessageList } from "./MessageList";

const VOICE_QUESTION = "Would you like to work in voice mode?";
const VOICE_SEND_DELAY_MS = 3000;

export function ChatShell() {
  const {
    conversations,
    conversationId,
    conversation,
    error: conversationError,
    isLoading: isConversationLoading,
    isReady,
    selectConversation,
    startNewChat,
    conversationKey,
  } = useConversation();
  const {
    documents,
    isLoading: isDocsLoading,
    isUploading,
    deletingId,
    error: docsError,
    refresh: refreshDocs,
    upload,
    remove,
  } = useDocuments(conversationId);

  const isProcessingDocs = documents.some((d) => d.status === "processing");
  const indexedDocumentCount = documents.filter(
    (d) => d.status === "indexed",
  ).length;
  const hasIndexedDocuments = indexedDocumentCount > 0;

  const {
    messages,
    input,
    setInput,
    isLoading,
    isLoadingHistory,
    error,
    sendMessage,
    sendText,
  } = useChat(conversationId, conversationKey);

  const {
    isRecognitionSupported,
    isSpeaking,
    speak,
    stopSpeaking,
    startListening,
    startDebouncedListening,
    stopListening,
  } = useVoiceMode();

  const { isLoggingOut, handleLogout } = useLogout({
    onBeforeLogout: () => {
      stopListening();
      stopSpeaking();
    },
  });
  const [isStartingNew, setIsStartingNew] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [mode, setMode] = useState<InputMode>("text");
  const [voiceStatus, setVoiceStatus] = useState<string | null>(null);

  const hasPromptedRef = useRef(false);
  const playQuestionRef = useRef<HTMLButtonElement>(null);
  const isAwaitingYesNoRef = useRef(false);
  const yesNoRetriedRef = useRef(false);
  const lastSpokenMessageIdRef = useRef<string | null>(null);
  const shouldSpeakNextResponseRef = useRef(false);
  const modeRef = useRef<InputMode>("text");
  const startVoiceMessageListeningRef = useRef<() => void>(() => {});

  const inputDisabled =
    !isReady ||
    isLoading ||
    isLoggingOut ||
    isLoadingHistory ||
    isDocsLoading ||
    isProcessingDocs;

  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  const startVoiceMessageListening = useCallback(() => {
    if (modeRef.current !== "voice" || inputDisabled || isAwaitingYesNoRef.current) {
      return;
    }

    stopListening();
    setVoiceStatus("Listening...");

    startDebouncedListening({
      debounceMs: VOICE_SEND_DELAY_MS,
      onInterim: (transcript) => {
        setInput(transcript);
      },
      onFinal: (transcript) => {
        setInput(transcript);
      },
      onDebouncedFinal: (transcript) => {
        setVoiceStatus(null);
        stopListening();
        shouldSpeakNextResponseRef.current = true;
        void sendText(transcript);
      },
      onError: (message) => {
        setVoiceStatus(message);
      },
      onEnd: () => {
        if (
          modeRef.current === "voice" &&
          !inputDisabled &&
          !isAwaitingYesNoRef.current
        ) {
          startVoiceMessageListeningRef.current();
        }
      },
    });
  }, [
    inputDisabled,
    sendText,
    setInput,
    startDebouncedListening,
    stopListening,
  ]);

  useEffect(() => {
    startVoiceMessageListeningRef.current = startVoiceMessageListening;
  }, [startVoiceMessageListening]);

  const handleYesNoAnswer = useCallback(
    (transcript: string) => {
      const answer = parseYesNo(transcript);
      if (!answer) return false;

      isAwaitingYesNoRef.current = false;
      stopListening();
      setVoiceStatus(null);
      shouldSpeakNextResponseRef.current = false;

      if (answer === "yes") {
        setMode("voice");
      } else {
        setMode("text");
      }

      return true;
    },
    [stopListening],
  );

  const listenForYesNo = useCallback(() => {
    function startAttempt() {
      startListening({
        continuous: true,
        interimResults: true,
        onInterim: (transcript) => {
          handleYesNoAnswer(transcript);
        },
        onFinal: (transcript) => {
          handleYesNoAnswer(transcript);
        },
        onError: (message) => {
          isAwaitingYesNoRef.current = false;
          setVoiceStatus(message);
        },
        onEnd: () => {
          if (!isAwaitingYesNoRef.current || yesNoRetriedRef.current) return;
          yesNoRetriedRef.current = true;
          window.setTimeout(() => {
            if (isAwaitingYesNoRef.current) {
              startAttempt();
            }
          }, 100);
        },
      });
    }

    startAttempt();
  }, [handleYesNoAnswer, startListening]);

  const handlePlayQuestion = useCallback(() => {
    if (!isRecognitionSupported) {
      setVoiceStatus("Voice input requires Chrome. Staying in text mode.");
      return;
    }

    isAwaitingYesNoRef.current = true;
    yesNoRetriedRef.current = false;
    stopListening();
    setMode("text");

    speak(VOICE_QUESTION, () => {
      setVoiceStatus("Listening for yes or no...");
      listenForYesNo();
    });
  }, [isRecognitionSupported, listenForYesNo, speak, stopListening]);

  useEffect(() => {
    if (!isReady || isLoadingHistory || hasPromptedRef.current) return;

    hasPromptedRef.current = true;
    playQuestionRef.current?.click();
  }, [isReady, isLoadingHistory]);

  useEffect(() => {
    if (mode !== "voice" || inputDisabled || isAwaitingYesNoRef.current) {
      stopListening();
      return;
    }

    startVoiceMessageListening();

    return () => {
      stopListening();
    };
  }, [mode, inputDisabled, startVoiceMessageListening, stopListening]);

  useEffect(() => {
    if (mode !== "voice" || isLoading) return;
    if (!shouldSpeakNextResponseRef.current) return;

    const lastAssistant = [...messages]
      .reverse()
      .find((message) => message.role === "model" && message.status === "done");

    if (!lastAssistant || lastAssistant.id === lastSpokenMessageIdRef.current) {
      return;
    }

    shouldSpeakNextResponseRef.current = false;
    lastSpokenMessageIdRef.current = lastAssistant.id;
    stopListening();

    const speechText = stripMarkdownForSpeech(lastAssistant.content);
    if (!speechText) {
      startVoiceMessageListeningRef.current();
      return;
    }

    speak(speechText, () => {
      if (modeRef.current === "voice" && !inputDisabled) {
        startVoiceMessageListeningRef.current();
      }
    });
  }, [
    messages,
    mode,
    isLoading,
    speak,
    stopListening,
    inputDisabled,
  ]);

  const handleModeChange = useCallback(
    (nextMode: InputMode) => {
      if (nextMode === "voice" && !isRecognitionSupported) {
        setVoiceStatus("Voice input requires Chrome. Staying in text mode.");
        setMode("text");
        return;
      }

      isAwaitingYesNoRef.current = false;
      shouldSpeakNextResponseRef.current = false;
      stopListening();
      stopSpeaking();
      setVoiceStatus(null);
      setMode(nextMode);
    },
    [isRecognitionSupported, stopListening, stopSpeaking],
  );

  const handleNewChat = async () => {
    if (isStartingNew) return;
    setIsStartingNew(true);
    try {
      await startNewChat();
      setSidebarOpen(false);
    } finally {
      setIsStartingNew(false);
    }
  };

  const handleSelectConversation = async (id: string) => {
    await selectConversation(id);
    setSidebarOpen(false);
  };

  const displayError = conversationError ?? docsError ?? error;
  const showEmptyState = isReady && !isLoadingHistory && messages.length === 0;
  const isSwitching = isLoadingHistory;

  return (
    <div className="flex h-dvh bg-background">
      {sidebarOpen && (
        <button
          type="button"
          aria-label="Close conversation history"
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {documentsOpen && (
        <button
          type="button"
          aria-label="Close documents"
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm xl:hidden"
          onClick={() => setDocumentsOpen(false)}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-border bg-card shadow-xl transition-transform duration-200 md:static md:z-auto md:shrink-0 md:translate-x-0 md:shadow-none",
          sidebarOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3 md:hidden">
          <span className="text-sm font-medium text-foreground">
            Conversations
          </span>
          <button
            type="button"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
            className="flex h-11 w-11 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        </div>

        <ConversationList
          conversations={conversations}
          activeId={conversationId}
          onSelect={handleSelectConversation}
          onNewChat={handleNewChat}
          isLoading={isConversationLoading}
          isSwitching={isSwitching || isStartingNew}
        />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="shrink-0 border-b border-border px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                onClick={() => setSidebarOpen(true)}
                aria-label="Open conversation history"
                aria-expanded={sidebarOpen}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
              >
                <PanelLeft className="h-5 w-5" aria-hidden />
              </button>
              <div className="min-w-0">
                <h1 className="truncate text-lg font-semibold tracking-tight text-foreground">
                  {conversation?.title ?? "Mistral Assistant"}
                </h1>
                <p className="text-xs text-muted-foreground">
                  {hasIndexedDocuments
                    ? `${indexedDocumentCount} document${indexedDocumentCount === 1 ? "" : "s"} available · auto-routed`
                    : "Streaming via Server-Sent Events"}
                </p>
              </div>
            </div>

            <div className="flex shrink-0 items-center gap-2">
              {conversationId && (
                <p
                  className="hidden max-w-40 truncate font-mono text-xs text-muted-foreground lg:block"
                  title={conversationId}
                >
                  {conversationId}
                </p>
              )}
              <AnimatedThemeToggler
                className={cn(
                  "flex h-11 w-11 items-center justify-center rounded-xl border border-border",
                  "text-muted-foreground transition-colors [&_svg]:h-5 [&_svg]:w-5",
                  "hover:bg-muted hover:text-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
              />
              <button
                type="button"
                onClick={() => setDocumentsOpen(true)}
                aria-label="Open documents"
                aria-expanded={documentsOpen}
                className={cn(
                  "flex h-11 w-11 items-center justify-center rounded-xl border border-border",
                  "text-muted-foreground transition-colors",
                  "hover:bg-muted hover:text-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
              >
                <Files className="h-5 w-5" aria-hidden />
              </button>
              <button
                type="button"
                onClick={handleLogout}
                disabled={isLoggingOut}
                aria-label="Log out"
                className={cn(
                  "flex h-11 w-11 items-center justify-center rounded-xl border border-border",
                  "text-muted-foreground transition-colors",
                  "hover:bg-muted hover:text-foreground",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  "disabled:cursor-not-allowed disabled:opacity-50",
                )}
              >
                <LogOut className="h-5 w-5" aria-hidden />
              </button>
            </div>
          </div>
        </header>

        <main className="flex min-h-0 flex-1 flex-col">
          {isConversationLoading || isLoadingHistory ? (
            <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
              {isConversationLoading
                ? "Loading conversation…"
                : "Loading messages…"}
            </div>
          ) : !isReady ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
              <p className="text-sm text-muted-foreground">
                Select a conversation from the sidebar or start a new chat.
              </p>
              <button
                type="button"
                onClick={handleNewChat}
                disabled={isStartingNew}
                className="rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              >
                {isStartingNew ? "Starting…" : "New Chat"}
              </button>
            </div>
          ) : (
            <MessageList messages={messages} />
          )}
        </main>

        {showEmptyState && (
          <p className="mx-4 mb-2 text-center text-xs text-muted-foreground">
            Send a message to start this conversation.
          </p>
        )}

        {displayError && (
          <div
            className="mx-auto mb-2 max-w-3xl rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive"
            role="alert"
          >
            {displayError}
          </div>
        )}

        <ChatInput
          value={input}
          onChange={setInput}
          onSubmit={sendMessage}
          disabled={inputDisabled}
          onUpload={isReady ? upload : undefined}
          isUploading={isUploading}
          isProcessing={isProcessingDocs}
          mode={mode}
          onModeChange={handleModeChange}
          voiceStatus={voiceStatus}
          isVoiceSupported={isRecognitionSupported}
          onPlayQuestion={handlePlayQuestion}
          playQuestionRef={playQuestionRef}
          onVoiceInputActivate={startVoiceMessageListening}
          isSpeaking={isSpeaking}
          onStopVoice={stopSpeaking}
        />
      </div>

      <aside
        className={cn(
          "fixed inset-y-0 right-0 z-50 w-80 border-l border-border bg-card shadow-xl transition-transform duration-200 xl:static xl:z-auto xl:shrink-0 xl:shadow-none",
          documentsOpen ? "translate-x-0" : "translate-x-full xl:hidden",
        )}
      >
        <DocumentPanel
          onClose={() => setDocumentsOpen(false)}
          documents={documents}
          isLoading={isDocsLoading}
          deletingId={deletingId}
          error={docsError}
          refresh={refreshDocs}
          remove={remove}
        />
      </aside>
    </div>
  );
}
