export function EmptyState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-16 text-center">
      <h2 className="font-display text-2xl font-medium tracking-[-0.02em] text-foreground">
        Ask anything
      </h2>
      <p className="mt-2 max-w-sm text-sm leading-relaxed text-muted-foreground">
        Attach a PDF or text file to ask about it. Answers show the sources they used.
      </p>
    </div>
  );
}
