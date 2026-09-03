"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Megaphone, Paperclip, Trash2 } from "lucide-react";
import { AdminModal } from "@/components/admin/AdminModal";
import {
  agoraParaCampoLocal,
  CANAIS,
  EXTENSOES_ACEITAS,
  montarRegistro,
  VINCULOS,
  type CanalManual,
  type FormularioRegistro,
} from "@/lib/ouvidoria/registro";
import {
  LABEL_TIPO,
  TIPOS_MANIFESTACAO,
  type TipoManifestacao,
} from "@/lib/ouvidoria/taxonomia";

const LIMITE_MB = 20;
const LIMITE_BYTES = LIMITE_MB * 1024 * 1024;

const VAZIO: FormularioRegistro = {
  canal: "telefone",
  contatoEm: "",
  tipoManifestacao: "",
  categoria: "",
  setor: "",
  resumo: "",
  relatoIntegral: "",
  manifestanteNome: "",
  manifestanteContato: "",
  manifestanteVinculo: "",
  anonimo: false,
};

interface NovaManifestacaoModalProps {
  aberto: boolean;
  token: string | null;
  onClose: () => void;
  onRegistrada: () => void;
}

const CAMPO =
  "w-full px-3 py-2 rounded-lg border border-slate-200 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40";
const ROTULO = "block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1";

/**
 * Registro manual da manifestação (issue #321).
 *
 * O que chega por telefone, balcão ou email entra aqui, com a data e hora
 * REAIS do contato: o T0 é quando chegou ao hospital, não quando foi digitado.
 * Os anexos sobem depois que o caso existe, porque cada um se liga ao
 * protocolo já gerado pelo banco.
 */
export function NovaManifestacaoModal({
  aberto,
  token,
  onClose,
  onRegistrada,
}: NovaManifestacaoModalProps) {
  const [form, setForm] = useState<FormularioRegistro>(VAZIO);
  const [arquivos, setArquivos] = useState<File[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [protocolo, setProtocolo] = useState<string | null>(null);
  const [avisoAnexos, setAvisoAnexos] = useState<string | null>(null);
  const [setores, setSetores] = useState<string[]>([]);
  const [listaFalhou, setListaFalhou] = useState(false);

  // A área é lista fechada desde a issue #419: texto livre aqui criava uma
  // Recepção nova a cada erro de digitação, e o relatório da Diretoria contava
  // as duas. A lista é a mesma do seletor da validação.
  useEffect(() => {
    if (!aberto || !token) return;
    let cancelado = false;
    setListaFalhou(false);
    fetch("/api/participantes/setores", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("lista de setores"))))
      .then((lista) => {
        if (!cancelado) setSetores(Array.isArray(lista) ? lista : []);
      })
      .catch(() => {
        // Sem o campo livre, lista que não carrega é telefonema que não vira
        // protocolo. O ouvidor precisa ler o motivo na tela, e não ficar
        // olhando um seletor vazio sem explicação.
        if (cancelado) return;
        setSetores([]);
        setListaFalhou(true);
      });
    return () => {
      cancelado = true;
    };
  }, [aberto, token]);

  useEffect(() => {
    if (aberto) {
      // O padrão é "agora": o registro em tempo real é o caso comum, e o
      // ouvidor recua a data quando está digitando algo de ontem.
      setForm({ ...VAZIO, contatoEm: agoraParaCampoLocal() });
      setArquivos([]);
      setErro(null);
      setProtocolo(null);
      setAvisoAnexos(null);
    }
  }, [aberto]);

  function alterar<K extends keyof FormularioRegistro>(campo: K, valor: FormularioRegistro[K]) {
    setForm((atual) => ({ ...atual, [campo]: valor }));
  }

  function adicionarArquivos(lista: FileList | null) {
    if (!lista) return;
    const escolhidos = Array.from(lista);
    const grandes = escolhidos.filter((a) => a.size > LIMITE_BYTES);
    setAvisoAnexos(
      grandes.length > 0
        ? `${grandes.map((a) => a.name).join(", ")}: passa do limite de ${LIMITE_MB} MB por arquivo.`
        : null
    );
    setArquivos((atuais) => [...atuais, ...escolhidos.filter((a) => a.size <= LIMITE_BYTES)]);
  }

  /**
   * Sobe os anexos um a um e devolve os que não passaram. Nunca levanta: o
   * caso já existe e já tem protocolo, então falha de anexo não pode ser
   * confundida com falha de registro.
   */
  async function enviarAnexos(manifestacaoId: string): Promise<string[]> {
    const recusados: string[] = [];
    for (const arquivo of arquivos) {
      const corpo = new FormData();
      corpo.append("file", arquivo);
      try {
        const res = await fetch(`/api/ouvidoria/manifestacoes/${manifestacaoId}/anexos`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: corpo,
        });
        if (!res.ok) recusados.push(arquivo.name);
      } catch {
        recusados.push(arquivo.name);
      }
    }
    return recusados;
  }

  async function registrar() {
    if (!token || salvando) return;
    setSalvando(true);
    setErro(null);

    // A criação do caso vive sozinha aqui: assim que ela volta, o protocolo já
    // foi gasto, e nada depois pode dizer ao ouvidor que o registro falhou
    // (ele clicaria de novo e o mesmo telefonema viraria dois protocolos).
    let criada: { id: string; protocolo: string };
    try {
      const res = await fetch("/api/ouvidoria/manifestacoes", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(montarRegistro(form)),
      });
      if (!res.ok) {
        setErro(
          res.status === 422
            ? "Confira os campos: relato, tipo, setor e resumo são obrigatórios, e a data do contato não pode estar no futuro."
            : "Não foi possível registrar a manifestação. Tente novamente."
        );
        setSalvando(false);
        return;
      }
      criada = await res.json();
    } catch {
      setErro("Não foi possível registrar a manifestação. Tente novamente.");
      setSalvando(false);
      return;
    }

    // Daqui em diante o botão segue travado: só some quando a tela do
    // protocolo aparece, então não há janela para um segundo clique.
    const recusados = arquivos.length > 0 ? await enviarAnexos(criada.id) : [];
    if (recusados.length > 0) {
      setAvisoAnexos(
        `O caso foi registrado, mas estes anexos não subiram: ${recusados.join(", ")}. Registre outra vez pelo caso, sem criar manifestação nova.`
      );
    }
    setProtocolo(criada.protocolo);
    setSalvando(false);
    onRegistrada();
  }

  const podeRegistrar =
    form.contatoEm.trim() !== "" &&
    form.tipoManifestacao !== "" &&
    form.setor.trim() !== "" &&
    form.resumo.trim() !== "" &&
    form.relatoIntegral.trim() !== "";

  return (
    <AdminModal
      open={aberto}
      onClose={onClose}
      title="Nova manifestação"
      description={protocolo ? "Registro concluído" : "Registro manual da ouvidoria"}
      icon={<Megaphone className="w-5 h-5" />}
      size="lg"
      scrollable
      footer={
        protocolo ? (
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 transition-colors"
          >
            Fechar
          </button>
        ) : (
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide text-slate-600 hover:bg-slate-100 transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={registrar}
              disabled={!podeRegistrar || salvando}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold uppercase tracking-wide bg-primary text-white hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {salvando && <Loader2 className="w-4 h-4 animate-spin" />}
              Registrar manifestação
            </button>
          </div>
        )
      }
    >
      {protocolo ? (
        <div className="text-center py-8">
          <div className="w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center mx-auto mb-3">
            <CheckCircle2 className="w-7 h-7 text-emerald-500" strokeWidth={1.5} />
          </div>
          <p className="text-slate-500 text-sm">Protocolo gerado</p>
          <p className="font-mono text-2xl font-bold text-slate-900 mt-1">{protocolo}</p>
          <p className="text-slate-500 text-sm mt-3">
            Informe este número a quem manifestou. O caso entrou na fila em classificação.
          </p>
          {avisoAnexos && (
            <p className="text-amber-700 text-sm mt-3 px-4 py-2 rounded-lg bg-amber-50 border border-amber-200">
              {avisoAnexos}
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-5">
          {erro && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              {erro}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={ROTULO} htmlFor="canal">
                Canal de origem
              </label>
              <select
                id="canal"
                className={CAMPO}
                value={form.canal}
                onChange={(e) => alterar("canal", e.target.value as CanalManual)}
              >
                {CANAIS.map((c) => (
                  <option key={c.valor} value={c.valor}>
                    {c.rotulo}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={ROTULO} htmlFor="contato-em">
                Data e hora do contato
              </label>
              <input
                id="contato-em"
                type="datetime-local"
                className={CAMPO}
                value={form.contatoEm}
                onChange={(e) => alterar("contatoEm", e.target.value)}
              />
              <p className="text-xs text-slate-400 mt-1">
                Quando a manifestação chegou ao hospital, mesmo que você registre depois.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={ROTULO} htmlFor="tipo-manifestacao">
                Tipo da manifestação
              </label>
              <select
                id="tipo-manifestacao"
                className={CAMPO}
                value={form.tipoManifestacao}
                onChange={(e) => alterar("tipoManifestacao", e.target.value as TipoManifestacao)}
              >
                <option value="">Escolha o tipo</option>
                {TIPOS_MANIFESTACAO.map((valor) => (
                  <option key={valor} value={valor}>
                    {LABEL_TIPO[valor]}
                  </option>
                ))}
              </select>
              <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
                Denúncia e relato de conduta nascem com sigilo reforçado: o caso fica restrito ao
                Ouvidor e à Diretoria Executiva.
              </p>
            </div>
            <div>
              <label className={ROTULO} htmlFor="categoria">
                Rótulo do caso <span className="normal-case">(opcional)</span>
              </label>
              <input
                id="categoria"
                className={CAMPO}
                value={form.categoria}
                onChange={(e) => alterar("categoria", e.target.value)}
                placeholder="Ex.: demora no atendimento"
              />
            </div>
            <div>
              <label className={ROTULO} htmlFor="setor">
                Setor
              </label>
              <select
                id="setor"
                className={CAMPO}
                value={form.setor}
                onChange={(e) => alterar("setor", e.target.value)}
              >
                <option value="">Escolha o setor</option>
                {setores.map((nome) => (
                  <option key={nome} value={nome}>
                    {nome}
                  </option>
                ))}
              </select>
              {listaFalhou && (
                <p className="mt-1 text-xs text-red-600">
                  A lista de setores não carregou. Feche e abra a janela para tentar de novo.
                </p>
              )}
            </div>
          </div>

          <div>
            <label className={ROTULO} htmlFor="resumo">
              Resumo
            </label>
            <input
              id="resumo"
              className={CAMPO}
              value={form.resumo}
              onChange={(e) => alterar("resumo", e.target.value)}
              placeholder="Uma linha sobre o caso, para a fila do painel"
            />
          </div>

          <div>
            <label className={ROTULO} htmlFor="relato">
              Relato integral
            </label>
            <textarea
              id="relato"
              rows={5}
              className={CAMPO}
              value={form.relatoIntegral}
              onChange={(e) => alterar("relatoIntegral", e.target.value)}
              placeholder="O que a pessoa contou, na íntegra e sem edição."
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.anonimo}
              onChange={(e) => alterar("anonimo", e.target.checked)}
              className="w-4 h-4 rounded border-slate-300"
            />
            Manifestação anônima (sem nome e sem contato, não há retorno individual)
          </label>

          {!form.anonimo && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className={ROTULO} htmlFor="nome">
                  Quem manifestou
                </label>
                <input
                  id="nome"
                  className={CAMPO}
                  value={form.manifestanteNome}
                  onChange={(e) => alterar("manifestanteNome", e.target.value)}
                />
              </div>
              <div>
                <label className={ROTULO} htmlFor="contato">
                  Contato
                </label>
                <input
                  id="contato"
                  className={CAMPO}
                  value={form.manifestanteContato}
                  onChange={(e) => alterar("manifestanteContato", e.target.value)}
                  placeholder="Telefone ou email"
                />
              </div>
              <div>
                <label className={ROTULO} htmlFor="vinculo">
                  Vínculo
                </label>
                <select
                  id="vinculo"
                  className={CAMPO}
                  value={form.manifestanteVinculo}
                  onChange={(e) => alterar("manifestanteVinculo", e.target.value)}
                >
                  <option value="">Não informado</option>
                  {VINCULOS.map((v) => (
                    <option key={v.valor} value={v.valor}>
                      {v.rotulo}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          <div>
            <label className={ROTULO} htmlFor="anexos">
              Anexos
            </label>
            <input
              id="anexos"
              type="file"
              multiple
              accept={EXTENSOES_ACEITAS}
              onChange={(e) => {
                adicionarArquivos(e.target.files);
                e.target.value = "";
              }}
              className="block w-full text-sm text-slate-500 file:mr-3 file:px-3 file:py-1.5 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200"
            />
            <p className="text-xs text-slate-400 mt-1">
              Imagem, PDF, áudio ou documento, até {LIMITE_MB} MB por arquivo.
            </p>
            {avisoAnexos && (
              <p className="text-xs text-amber-700 mt-1.5 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200">
                {avisoAnexos}
              </p>
            )}
            {arquivos.length > 0 && (
              <ul className="mt-2 space-y-1">
                {arquivos.map((arquivo, indice) => (
                  <li
                    key={`${arquivo.name}-${indice}`}
                    className="flex items-center gap-2 text-sm text-slate-600 px-3 py-1.5 rounded-lg bg-slate-50"
                  >
                    <Paperclip className="w-3.5 h-3.5 shrink-0 text-slate-400" />
                    <span className="truncate flex-1">{arquivo.name}</span>
                    <button
                      type="button"
                      aria-label={`Remover ${arquivo.name}`}
                      onClick={() => setArquivos((atuais) => atuais.filter((_, i) => i !== indice))}
                      className="text-slate-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </AdminModal>
  );
}

export default NovaManifestacaoModal;
