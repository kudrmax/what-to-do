/** Text whose `backticked` parts are commands to type: they show as code. */
export function InlineCode({ text }: { text: string }) {
  const parts = text.split("`");
  if (parts.length % 2 === 0) return <>{text}</>;
  return <>{parts.map((part, index) => (index % 2 === 1 ? <code key={index}>{part}</code> : part))}</>;
}
