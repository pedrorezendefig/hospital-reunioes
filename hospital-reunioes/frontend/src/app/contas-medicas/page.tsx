import { ReceiptText } from "lucide-react";
import { LinkParaOperadoras } from "@/components/contas-medicas/LinkParaOperadoras";

/**
 * A tela de contas de Contas médicas (PRD #1113, ADR 0070).
 *
 * Na fundação (issue #1114) a fila só existe vazia: o envio da conta e do
 * prontuário chega numa fatia seguinte, e é ela que preenche esta lista.
 */
export default function ContasMedicasPage() {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Contas médicas</h1>
        <LinkParaOperadoras />
      </div>
      <p className="text-slate-500 text-sm mt-0.5 mb-6">
        Envie a conta e o prontuário do MV e receba a lista do que corrigir antes de mandar para a
        operadora.
      </p>

      <section
        aria-label="Fila de contas"
        className="bg-white rounded-2xl border border-border shadow-premium p-10 text-center"
      >
        <ReceiptText className="w-8 h-8 text-slate-300 mx-auto mb-3" aria-hidden="true" />
        <p className="text-slate-500 text-sm">Nenhuma conta enviada ainda</p>
      </section>
    </div>
  );
}
