"use client";

import { ArrowUp, Loader2, Paperclip, Square } from "lucide-react";
import { useRef } from "react";
import TextareaAutosize from "react-textarea-autosize";
import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";

export type InputMode = "text" | "voice";

type ChatInputProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  placeholder?: string;
  onUpload?: (file: File) => void;
  isUploading?: boolean;
  isProcessing?: boolean;
  mode?: InputMode;
  onModeChange?: (mode: InputMode) => void;
  voiceStatus?: string | null;
  isVoiceSupported?: boolean;
  onPlayQuestion?: () => void;
  playQuestionRef?: React.RefObject<HTMLButtonElement | null>;
  onVoiceInputActivate?: () => void;
  isSpeaking?: boolean;
  onStopVoice?: () => void;
};

export function ChatInput({
  value,
  onChange,
  onSubmit,
  disabled = false,
  placeholder = "Ask anything…",
  onUpload,
  isUploading = false,
  isProcessing = false,
  mode = "text",
  onModeChange,
  voiceStatus = null,
  isVoiceSupported = false,
  onPlayQuestion,
  playQuestionRef,
  onVoiceInputActivate,
  isSpeaking = false,
  onStopVoice,
}: ChatInputProps) {
  const canSend =
    mode === "text" && value.trim().length > 0 && !disabled && !isProcessing;
  const isBusy = isUploading || isProcessing;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isVoiceMode = mode === "voice";

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (isVoiceMode) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) onSubmit();
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onUpload) {
      onUpload(file);
    }
    if (e.target) {
      e.target.value = "";
    }
  };

  const handleModeChange = (nextMode: string) => {
    if (nextMode === "text" || nextMode === "voice") {
      onModeChange?.(nextMode);
    }
  };

  return (
    <div className="shrink-0 border-t border-dashed border-line bg-background px-4 pt-3 pb-4">
      <div className="mx-auto max-w-3xl">
        {isBusy && (
          <p role="status" className="mb-2 flex items-center gap-2 text-xs text-live">
            <Loader2 aria-hidden className="size-3.5 shrink-0 animate-spin motion-reduce:animate-none" />
            {isUploading ? "Uploading document…" : "Reading the document. You can ask about it in a moment."}
          </p>
        )}

        {(voiceStatus || isSpeaking) && (
          <div
            role="status"
            className="mb-2 flex items-center justify-between gap-3 rounded-[10px] border border-line px-3 py-2 text-xs text-foreground"
          >
            <span>{isSpeaking ? "Speaking…" : voiceStatus}</span>
            {isSpeaking && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onStopVoice}
                className="h-7 rounded-[4px] border-line"
              >
                <Square aria-hidden className="size-3 fill-current" />
                Stop
              </Button>
            )}
          </div>
        )}

        <div className="flex items-end gap-1.5 rounded-[14px] border border-line bg-card p-1.5 transition-colors focus-within:border-muted-foreground/60">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || isBusy || isVoiceMode}
            className="shrink-0 rounded-[4px] text-muted-foreground"
            aria-label="Attach a PDF or text file"
          >
            <Paperclip />
          </Button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            className="hidden"
            accept=".pdf,.txt,application/pdf,text/plain"
          />
          <TextareaAutosize
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={isVoiceMode ? onVoiceInputActivate : undefined}
            onClick={isVoiceMode ? onVoiceInputActivate : undefined}
            minRows={1}
            maxRows={6}
            disabled={disabled}
            readOnly={isVoiceMode}
            aria-label="Message"
            placeholder={isVoiceMode ? "Speak your message…" : placeholder}
            className={cn(
              "min-h-9 flex-1 resize-none bg-transparent px-1 py-2 text-sm text-foreground caret-live outline-none focus-visible:outline-none",
              "placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-60",
              isVoiceMode && "cursor-pointer",
            )}
          />
          <Button
            type="button"
            size="icon"
            onClick={onSubmit}
            disabled={!canSend}
            className="shrink-0 rounded-[4px]"
            aria-label="Send message"
          >
            {(disabled || isBusy) && !canSend ? (
              <Loader2 className="animate-spin motion-reduce:animate-none" />
            ) : (
              <ArrowUp />
            )}
          </Button>
        </div>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <ToggleGroup
            type="single"
            value={mode}
            onValueChange={handleModeChange}
            variant="outline"
            size="sm"
            aria-label="Input mode"
          >
            <ToggleGroupItem value="text" aria-label="Text mode">
              Text
            </ToggleGroupItem>
            <ToggleGroupItem
              value="voice"
              aria-label="Voice mode"
              disabled={!isVoiceSupported}
            >
              Voice
            </ToggleGroupItem>
          </ToggleGroup>

          <p className="text-xs text-muted-foreground">
            {isVoiceMode
              ? "Speak, and it sends 3 seconds after you stop"
              : !isVoiceSupported
                ? "Enter to send · Voice needs Chrome"
                : "Enter to send · Shift+Enter for a new line"}
          </p>
        </div>
      </div>

      <button
        ref={playQuestionRef}
        type="button"
        onClick={onPlayQuestion}
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
      >
        Play question
      </button>
    </div>
  );
}
