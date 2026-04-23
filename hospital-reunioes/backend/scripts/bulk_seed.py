"""
Bulk seed: provisiona 43 contas (40 reais + 3 diretores teste) no Supabase.

Senhas: <primeironome_lowercase_sem_acentos>hospital2026
Sem envio de email. Idempotente (skip se email já existe).

Executar: docker compose exec backend python -m scripts.bulk_seed
"""

import logging
import sys
import unicodedata

from supabase import create_client

from app.config import settings
from app.services.auth_provisioning import provision_auth_user

logging.basicConfig(level=logging.INFO, format="[bulk_seed] %(message)s")
logger = logging.getLogger(__name__)

# ─── Lista dos 40 participantes reais + 3 diretores teste ────────────────────

PARTICIPANTES = [
    # (nome_completo, cargo, email, area, setor, role)
    # ── PRESIDENTE ──
    ("Lauro Menezes", "Presidente", "lauromenezes@hospitalsaomatheus.com.br", "Diretoria", "Presidência", "presidente"),
    # ── DIRETORES ──
    (
        "Caroline Izidorio Drumond da Silva",
        "Diretora Médica Geral",
        "carolizidorio@hospitalsaomatheus.com.br",
        "Assistencial",
        "Diretoria Clínica",
        "diretor",
    ),
    (
        "Caroline Lima",
        "Diretora de Infraestrutura",
        "engenheira.carolinelima@gmail.com",
        "Administrativa",
        "Engenharia Clínica",
        "diretor",
    ),
    (
        "Felipe Malafaia",
        "Diretor Executivo",
        "felipemalafaia@yahoo.com.br",
        "Diretoria",
        "Diretoria Administrativa",
        "diretor",
    ),
    (
        "Jorge Porto Marassi",
        "Diretor Técnico HSM",
        "diretoriamedica@hospitalsaomatheus.com.br",
        "Assistencial",
        "Diretoria Clínica",
        "diretor",
    ),
    (
        "Josiane Alves",
        "Diretora Financeira/ADM",
        "josiane@hospitalsaomatheus.com.br",
        "Administrativa",
        "Diretoria Administrativa",
        "diretor",
    ),
    # ── GERENTES ──
    (
        "Denize dos Anjos da Silva Antunes de Souza",
        "Gerente Financeiro",
        "denize_antunes@hotmail.com",
        "Administrativa",
        "Financeiro",
        "gerente",
    ),
    (
        "Fernando da Silva Carvalho",
        "TST/Gerente de Manutenção",
        "supervisao.manutencao@hospitalsaomatheus.com.br",
        "Administrativa",
        "Engenharia Clínica",
        "gerente",
    ),
    ("José Blanco Landeira", "Gestor de Auditoria", "blandeira@icloud.com", "Administrativa", "Auditoria", "gerente"),
    (
        "Lucas Louro de Souza dos Reis",
        "Gerente de Desenvolvimento de Sistemas",
        "lucaslouro2009@gmail.com",
        "Administrativa",
        "Tecnologia da Informação",
        "gerente",
    ),
    (
        "Rosiane Gomes dos Santos",
        "Gestão Centro Médico",
        "gestal.adm@gmail.com",
        "Assistencial",
        "Centro Médico",
        "gerente",
    ),
    (
        "Simone Cristina Santos de Lira",
        "Gerente de Enfermagem",
        "simoneliraenfa@gmail.com",
        "Assistencial",
        "Enfermagem",
        "gerente",
    ),
    (
        "Thaíssa Penha Silva dos Santos",
        "Gestora de Auditoria",
        "rtandeiraconsultoria@gmail.com",
        "Administrativa",
        "Auditoria",
        "gerente",
    ),
    # ── COORDENADORES / MÉDICOS / OUTROS ──
    (
        "Adriana Araújo Alberto Gonçalves",
        "Coordenador(a) de Faturamento",
        "drika-araujo0223@outlook.com",
        "Administrativa",
        "Faturamento",
        "coordenador",
    ),
    (
        "Camila Vasconcellos Martins",
        "Coordenador de Credenciamento",
        "milamartins@outlook.com",
        "Administrativa",
        "Credenciamento",
        "coordenador",
    ),
    (
        "Carolina Cavalcanti Freire de Souza Maciel",
        "Coordenador(a) de Enfermagem",
        "enfcarolinamaciel@gmail.com",
        "Assistencial",
        "Enfermagem",
        "coordenador",
    ),
    (
        "Cesar Augusto Toigo",
        "Fisioterapeuta coordenador de equipe",
        "catoigo@gmail.com",
        "Assistencial",
        "Fisioterapia",
        "coordenador",
    ),
    (
        "Cristiane Ferreira Xavier",
        "Coordenador(a) de Atendimento",
        "recep_coordenacao@hospitalsaomatheus.com.br",
        "Administrativa",
        "Atendimento",
        "coordenador",
    ),
    (
        "Danielly Alves de Oliveira André",
        "Coordenador(a) de Enfermagem",
        "jdl.monteiroandre@gmail.com",
        "Assistencial",
        "Enfermagem",
        "coordenador",
    ),
    (
        "Dorelene Alves da Cunha",
        "Coordenador(a) de Enfermagem",
        "dore.alves2012@gmail.com",
        "Assistencial",
        "Enfermagem",
        "coordenador",
    ),
    (
        "Eduardo Biosca",
        "Advogado",
        "eduardo.biosca@hospitalsaomatheus.com.br",
        "Administrativa",
        "Jurídico",
        "coordenador",
    ),
    (
        "Evelyn de Souza Santos Teixeira",
        "Coordenador(a) de CCIH",
        "evelyn_souza27@hotmail.com",
        "Assistencial",
        "CCIH",
        "coordenador",
    ),
    (
        "Fabricio Fraklin Costa da Silveira",
        "Coordenador Médico CTI",
        "fabricionash@hotmail.com",
        "Assistencial",
        "CTI",
        "coordenador",
    ),
    (
        "Felipe de Carvalho",
        "Coordenador de Apoio",
        "carvalhofelipe87@gmail.com",
        "Administrativa",
        "Apoio Institucional",
        "coordenador",
    ),
    (
        "Flavia Rodrigues Peixoto de Souza",
        "Coordenador(a) de Recursos de Glosa",
        "flaviarps26@gmail.com",
        "Administrativa",
        "Recursos de Glosa",
        "coordenador",
    ),
    (
        "Giselle Nunes de Vasconcellos",
        "Coordenador(a) de Atendimento",
        "callcenter_adm@hospitalsaomatheus.com.br",
        "Administrativa",
        "Atendimento",
        "coordenador",
    ),
    (
        "Janaina Ferreira",
        "Coordenador(a) de Suprimentos",
        "jlferreira36@hotmail.com",
        "Administrativa",
        "Suprimentos e Compras",
        "coordenador",
    ),
    (
        "Laryssa Silva de Oliveira",
        "Coordenador(a) de Repasse",
        "laryssa.soliveira@hotmail.com",
        "Administrativa",
        "Repasse",
        "coordenador",
    ),
    (
        "Levi dos Santos",
        "Coordenador(a) de DP/RH",
        "coordenacao.dp@hospitalsaomatheus.com.br",
        "Administrativa",
        "Recursos Humanos",
        "coordenador",
    ),
    (
        "Luciana de Souza Moreira",
        "Coordenador(a) de Compras",
        "lumoreira1@yahoo.com.br",
        "Administrativa",
        "Suprimentos e Compras",
        "coordenador",
    ),
    (
        "Maria da Penha Smith",
        "Coordenador de Enfermagem",
        "penhasmithvida@gmail.com",
        "Assistencial",
        "Enfermagem",
        "coordenador",
    ),
    (
        "Milton Fernandes dos Santos Filho",
        "Suporte T.I.",
        "miltonsan@gmail.com",
        "Administrativa",
        "Tecnologia da Informação",
        "coordenador",
    ),
    (
        "Nayani Alves Baptista Lima",
        "Coordenadora Operacional",
        "nayaninllima@gmail.com",
        "Administrativa",
        "Operacional",
        "coordenador",
    ),
    (
        "Oto Xavier de Oliveira Filho",
        "Coordenador(a) de Suprimentos",
        "oxofgp@gmail.com",
        "Administrativa",
        "Suprimentos e Compras",
        "coordenador",
    ),
    (
        "Patrick Brian Candido",
        "Coordenador médico UTI",
        "patrick_candido@yahoo.com.br",
        "Assistencial",
        "UTI",
        "coordenador",
    ),
    (
        "Raphael Zehetmeyer",
        "Anestesiologista",
        "zehetmeyer_rap@hotmail.com",
        "Assistencial",
        "Anestesiologia",
        "coordenador",
    ),
    (
        "Thétis Helena Quirino Jesus de Sousa",
        "Coordenador(a) de Nutrição",
        "thetis_nut@hotmail.com",
        "Assistencial",
        "Nutrição Clínica",
        "coordenador",
    ),
    ("Thiago Moreira Peixoto", "Médico", "tm.peixoto@hotmail.com", "Assistencial", "Corpo Clínico", "coordenador"),
    (
        "Tiago Barbuio Careno",
        "Ortopedista e Trauma",
        "tiagobarbuio@gmail.com",
        "Assistencial",
        "Ortopedia",
        "coordenador",
    ),
    (
        "Zilanda do Vale Cruz",
        "Farmacêutico Responsável Técnico",
        "tavinhasousa37@gmail.com",
        "Assistencial",
        "Farmácia Hospitalar",
        "coordenador",
    ),
    # ── DIRETORES DE TESTE ──
    (
        "Ricardo Diretor Geral",
        "Diretor Geral (teste)",
        "pmrdef+ricardo@gmail.com",
        "Diretoria",
        "Diretoria Administrativa",
        "diretor",
    ),
    (
        "Ana Diretora Clínica",
        "Diretora Clínica (teste)",
        "pmrdef+ana@gmail.com",
        "Assistencial",
        "Diretoria Clínica",
        "diretor",
    ),
    (
        "Joao Diretor Administrativo",
        "Diretor Administrativo (teste)",
        "pmrdef+joao@gmail.com",
        "Administrativa",
        "Diretoria Administrativa",
        "diretor",
    ),
]


def _slugify_primeiro_nome(nome_completo: str) -> str:
    """Extrai primeiro nome, remove acentos, converte pra lowercase."""
    primeiro = nome_completo.strip().split()[0]
    # Remove acentos via NFD decomposition
    nfkd = unicodedata.normalize("NFKD", primeiro)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


def main():
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    total = len(PARTICIPANTES)
    ok = 0
    skip = 0
    erros = 0

    for i, (nome, cargo, email, area, setor, role) in enumerate(PARTICIPANTES, 1):
        email = email.strip().lower()

        # Idempotência: skip se já existe
        existing = supabase.table("participantes").select("id").eq("email", email).execute()
        if existing.data:
            logger.info(f"[{i}/{total}] SKIP (já existe): {email} → {existing.data[0]['id']}")
            skip += 1
            continue

        # Gerar senha: <primeironome>hospital2026
        senha = _slugify_primeiro_nome(nome) + "hospital2026"

        # Criar auth user
        auth_uid = provision_auth_user(supabase, nome, email, role, password=senha)
        if not auth_uid:
            logger.error(f"[{i}/{total}] ERRO auth: {email}")
            erros += 1
            continue

        # Inserir participante
        try:
            result = (
                supabase.table("participantes")
                .insert(
                    {
                        "nome_completo": nome,
                        "cargo": cargo,
                        "email": email,
                        "area": area,
                        "setor": setor,
                        "role": role,
                        "ativo": True,
                        "is_externo": False,
                        "auth_user_id": auth_uid,
                    }
                )
                .execute()
            )

            pid = result.data[0]["id"] if result.data else "?"
            logger.info(f"[{i}/{total}] OK: {email} → {pid} (role={role}, senha={senha})")
            ok += 1
        except Exception as e:
            logger.error(f"[{i}/{total}] ERRO insert: {email} — {e}")
            erros += 1

    logger.info(f"\n{'=' * 60}")
    logger.info(f"RESULTADO: {ok} criados, {skip} já existiam, {erros} erros (total: {total})")
    logger.info(f"{'=' * 60}")

    if erros > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
