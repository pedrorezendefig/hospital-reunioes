const VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "?";

export function Footer() {
  return (
    <footer className="border-t border-border py-3 pr-4 text-right text-xs text-text-secondary">
      <span aria-label={`Versão ${VERSION}`}>v{VERSION}</span>
    </footer>
  );
}
