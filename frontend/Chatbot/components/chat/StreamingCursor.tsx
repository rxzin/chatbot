/** The caret at the end of a reply that is still streaming: live, so emerald. */
export function StreamingCursor() {
  return (
    <span
      className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-live align-middle motion-reduce:animate-none"
      aria-hidden
    />
  );
}
