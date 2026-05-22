const VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "?";
const CHANGELOG_URL =
  "https://github.com/pedrorezendefig/hospital-reunioes/blob/main/docs/spec/CHANGELOG.md";

export function Footer() {
  return (
    <footer className="border-t border-border py-3 text-center text-xs text-text-secondary">
      <a
        href={CHANGELOG_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="hover:text-text-primary transition-colors"
        aria-label={`Versão ${VERSION} — ver histórico de mudanças no GitHub`}
      >
        v{VERSION}
      </a>
    </footer>
  );
}
