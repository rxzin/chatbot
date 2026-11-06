"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Files, LogOut, PanelLeft } from "lucide-react";
import { useChat } from "@/hooks/useChat";
import { useConversation } from "@/hooks/useConversation";
import { useDocuments } from "@/hooks/useDocuments";
import { useVoiceMode } from "@/hooks/useVoiceMode";
import { useLogout } from "@/hooks/useLogout";
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Logo } from "@/components/marketing/Logo";
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
    // Browsers only allow speech after the user has interacted with the page, e.g.
    // clicking Sign in. On a fresh load or reload it would hang, so the question is
    // skipped; the Voice toggle still switches modes.
    const activation = (navigator as Navigator & { userActivation?: { hasBeenActive: boolean } })
      .userActivation;
    if (activation && !activation.hasBeenActive) return;
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
  const isSwitching = isLoadingHistory;
  const headerButton = cn(
    buttonVariants({ variant: "outline", size: "icon" }),
    "rounded-[4px] border-line bg-transparent text-muted-foreground hover:text-foreground",
  );

  const conversationList = (
    <ConversationList
      conversations={conversations}
      activeId={conversationId}
      onSelect={handleSelectConversation}
      onNewChat={handleNewChat}
      isLoading={isConversationLoading}
      isSwitching={isSwitching || isStartingNew}
    />
  );

  return (
    <div className="flex h-dvh bg-background">
      {/* Conversations: a sidebar from md up, a sheet on phones. */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-dashed border-line md:flex">
        <div className="flex h-16 shrink-0 items-center px-4">
          <Logo />
        </div>
        {conversationList}
      </aside>
      <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
        <SheetContent
          side="left"
          className="w-72 gap-0 border-r border-dashed border-line p-0 md:hidden"
        >
          <SheetHeader className="h-16 justify-center px-4 py-0">
            <SheetTitle className="sr-only">Conversations</SheetTitle>
            <SheetDescription className="sr-only">Your past conversations</SheetDescription>
            <Logo />
          </SheetHeader>
          {conversationList}
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-dashed border-line px-4">
          <div className="flex min-w-0 items-center gap-3">
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open conversations"
              aria-expanded={sidebarOpen}
              className={cn(headerButton, "md:hidden")}
            >
              <PanelLeft />
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-medium text-foreground">
                {conversation?.title ?? "New conversation"}
              </h1>
              {hasIndexedDocuments && (
                <p className="text-xs text-muted-foreground">
                  {indexedDocumentCount} document{indexedDocumentCount === 1 ? "" : "s"} ready
                </p>
              )}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setDocumentsOpen(true)}
              aria-label={`Documents${documents.length ? ` (${documents.length})` : ""}`}
              aria-expanded={documentsOpen}
              className={cn(headerButton, "relative")}
            >
              <Files />
              {documents.length > 0 && (
                <span
                  aria-hidden
                  className="absolute -top-1.5 -right-1.5 flex size-4 items-center justify-center rounded-full bg-foreground text-[0.6rem] font-medium text-background tabular-nums"
                >
                  {documents.length}
                </span>
              )}
            </Button>
            <AnimatedThemeToggler className={cn(headerButton, "[&_svg]:size-4")} />
            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={handleLogout}
              disabled={isLoggingOut}
              aria-label="Log out"
              className={headerButton}
            >
              <LogOut />
            </Button>
          </div>
        </header>

        <main className="flex min-h-0 flex-1 flex-col">
          {isConversationLoading || isLoadingHistory ? (
            <p
              role="status"
              className="flex flex-1 items-center justify-center text-sm text-muted-foreground"
            >
              {isConversationLoading ? "Loading conversation…" : "Loading messages…"}
            </p>
          ) : !isReady ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
              <p className="text-sm text-muted-foreground">
                Pick a conversation, or start a new one.
              </p>
              <Button
                type="button"
                onClick={handleNewChat}
                disabled={isStartingNew}
                className="rounded-[4px]"
              >
                {isStartingNew ? "Starting…" : "New chat"}
              </Button>
            </div>
          ) : (
            <MessageList
              messages={messages}
              onSuggestion={(text) => void sendText(text)}
              suggestionsDisabled={inputDisabled}
            />
          )}
        </main>

        {displayError && (
          <div className="shrink-0 px-4 pb-2">
            <p
              role="alert"
              className="mx-auto max-w-3xl rounded-[10px] border border-destructive/40 px-3 py-2 text-sm text-destructive"
            >
              {displayError}
            </p>
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

      <Sheet open={documentsOpen} onOpenChange={setDocumentsOpen}>
        <SheetContent
          side="right"
          className="w-80 gap-0 border-l border-dashed border-line p-0 sm:max-w-sm"
        >
          <SheetHeader className="h-16 justify-center border-b border-dashed border-line px-4 py-0">
            <SheetTitle className="font-display text-base font-medium">Documents</SheetTitle>
            <SheetDescription className="sr-only">
              Files attached to this conversation
            </SheetDescription>
          </SheetHeader>
          <DocumentPanel
            documents={documents}
            isLoading={isDocsLoading}
            deletingId={deletingId}
            error={docsError}
            refresh={refreshDocs}
            remove={remove}
          />
        </SheetContent>
      </Sheet>
    </div>
  );
}
