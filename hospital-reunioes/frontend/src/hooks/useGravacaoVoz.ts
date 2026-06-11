"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/components/ui/Toast";

/**
 * Comando por voz compartilhado (issue #35 nas Notas, #50 na Ata Guiada): o
 * Facilitador dita; o áudio é gravado pelo MediaRecorder, transcrito pelo
 * serviço existente (`POST /api/notas/transcrever`) e o texto cai **editável**
 * no destino que o consumidor escolher (corpo da Nota, input do chat…). O áudio
 * fica só em memória — nunca persiste. Falha na transcrição → aviso por toast +
 * digitação como fallback (sem travar a tela).
 *
 * O que varia entre telas vira parâmetro:
 *  - `getToken`: como obter o Bearer no momento da transcrição (estado nas
 *    Notas, `getSession` no chat).
 *  - `onTexto`: onde o texto transcrito cai (e a mensagem de sucesso, que muda
 *    de "revise antes de salvar" para "antes de enviar" conforme a tela).
 */
export interface UseGravacaoVozOpts {
  /** Bearer de auth no momento da transcrição. Síncrono ou assíncrono. */
  getToken: () => string | null | Promise<string | null>;
  /** Recebe o texto transcrito — cai editável no destino do consumidor. */
  onTexto: (texto: string) => void;
}

export interface GravacaoVoz {
  gravando: boolean;
  transcrevendo: boolean;
  iniciarGravacao: () => Promise<void>;
  pararGravacao: () => void;
  /** Encerra a gravação DESCARTANDO o áudio e cancela transcrição em voo. */
  abortarGravacao: () => void;
}

export function useGravacaoVoz({ getToken, onTexto }: UseGravacaoVozOpts): GravacaoVoz {
  const { toast } = useToast();

  const [gravando, setGravando] = useState(false);
  const [transcrevendo, setTranscrevendo] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const cancelarGravacaoRef = useRef(false);
  const transcricaoAbortRef = useRef<AbortController | null>(null);

  // "Latest ref": o `onstop` do MediaRecorder é registrado uma vez, mas precisa
  // enxergar o token/destino mais recentes na hora de transcrever — guardamos
  // os callbacks em refs atualizados a cada render para fugir do stale closure.
  const getTokenRef = useRef(getToken);
  const onTextoRef = useRef(onTexto);
  useEffect(() => {
    getTokenRef.current = getToken;
    onTextoRef.current = onTexto;
  });

  const pararStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  // Na saída do componente (ex.: chat fechado no meio da gravação) solta o
  // microfone e cancela o que estiver em voo — sem deixar transcrição fantasma
  // nem o recorder disparando onstop para um destino que já não existe.
  useEffect(
    () => () => {
      cancelarGravacaoRef.current = true;
      const mr = mediaRecorderRef.current;
      if (mr && mr.state !== "inactive") mr.stop();
      transcricaoAbortRef.current?.abort();
      pararStream();
    },
    [pararStream],
  );

  const transcreverAudio = useCallback(
    async (blob: Blob) => {
      const token = await getTokenRef.current();
      if (!token) return;
      if (blob.size === 0) {
        toast("Não captei áudio. Tente de novo ou digite manualmente.", "error");
        return;
      }
      setTranscrevendo(true);
      const ctrl = new AbortController();
      transcricaoAbortRef.current = ctrl;
      try {
        const ext = (blob.type.split("/")[1] || "webm").split(";")[0];
        const form = new FormData();
        form.append("audio", blob, `voz.${ext}`);
        const res = await fetch("/api/notas/transcrever", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: form,
          signal: ctrl.signal,
        });
        if (!res.ok) {
          toast("Não foi possível transcrever o áudio. Digite manualmente.", "error");
          return;
        }
        const data = (await res.json()) as { texto?: string };
        const texto = (data?.texto ?? "").trim();
        if (!texto) {
          toast("Não identifiquei fala no áudio. Tente de novo ou digite manualmente.", "info");
          return;
        }
        // Cai EDITÁVEL no destino: o consumidor anexa ao que já houver e dá o
        // toast de sucesso (a mensagem muda conforme a tela).
        onTextoRef.current(texto);
      } catch (e) {
        if ((e as Error)?.name === "AbortError") return; // tela fechada: descarta sem avisar
        console.error("Erro ao transcrever áudio:", e);
        toast("Erro ao transcrever o áudio. Digite manualmente.", "error");
      } finally {
        setTranscrevendo(false);
      }
    },
    [toast],
  );

  const iniciarGravacao = useCallback(async () => {
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      toast("Seu navegador não permite gravar áudio. Digite manualmente.", "error");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = ["audio/webm", "audio/mp4", "audio/ogg"].find(
        (m) => MediaRecorder.isTypeSupported?.(m),
      );
      const mr = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      chunksRef.current = [];
      cancelarGravacaoRef.current = false;
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || "audio/webm" });
        pararStream();
        if (cancelarGravacaoRef.current) {
          cancelarGravacaoRef.current = false;
          return; // gravação cancelada — descarta o áudio sem transcrever
        }
        void transcreverAudio(blob);
      };
      mr.start();
      mediaRecorderRef.current = mr;
      setGravando(true);
    } catch (e) {
      console.error("Erro ao acessar o microfone:", e);
      pararStream();
      toast("Não foi possível acessar o microfone. Verifique a permissão ou digite manualmente.", "error");
    }
  }, [toast, transcreverAudio, pararStream]);

  const pararGravacao = useCallback(() => {
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== "inactive") mr.stop(); // dispara onstop → transcreve
    setGravando(false);
  }, []);

  const abortarGravacao = useCallback(() => {
    const mr = mediaRecorderRef.current;
    if (mr && mr.state !== "inactive") {
      cancelarGravacaoRef.current = true;
      mr.stop();
    }
    pararStream(); // libera o microfone mesmo se o recorder já estava inativo
    transcricaoAbortRef.current?.abort(); // cancela transcrição em voo (não vaza pra próxima tela)
    setGravando(false);
  }, [pararStream]);

  return { gravando, transcrevendo, iniciarGravacao, pararGravacao, abortarGravacao };
}
