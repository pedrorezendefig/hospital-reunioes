### (opcional) review rigorosa — só com `--rigoroso`

Dispara um subagent **independente** (Task/general-purpose) que relê o diff inteiro com critérios mais rígidos que o Gate 1: cobertura de testes (edge cases incluídos), doc strings, naming, e o **baseline de smells do Fowler** abaixo. Reforça o self-approval com uma terceira leitura de outra perspectiva. A checagem de propósito contra a Issue saiu daqui: virou o Gate 1.5, que roda sempre que há issue.

**Baseline Fowler (_Refactoring_, cap. 3).** Duas regras vinculam a lista: um padrão documentado do repo (CLAUDE.md, ADRs) sempre vence a smell; e toda smell é **judgement call** ("possível Feature Envy"), nunca violação dura. Pule o que o tooling já pega (ruff, eslint, tsc). Cada item lê o que é → como resolver:

- **Mysterious Name**: nome de função/variável/tipo que não revela o que faz ou guarda. → renomear; se não vier nome honesto, o design está turvo.
- **Duplicated Code**: a mesma forma de lógica em mais de um hunk ou arquivo do diff. → extrair a forma compartilhada e chamar dos dois lugares.
- **Feature Envy**: método que mexe mais nos dados de outro objeto que nos próprios. → mover o método pra junto dos dados que ele inveja.
- **Data Clumps**: os mesmos campos/params sempre viajando juntos (um tipo querendo nascer). → agrupar num tipo só e passar o tipo.
- **Primitive Obsession**: primitivo ou string no lugar de um conceito de domínio que merece tipo próprio. → dar ao conceito um tipo pequeno.
- **Repeated Switches**: o mesmo switch/cascata de if sobre o mesmo tipo repetido pelo diff. → polimorfismo, ou um map que os dois lugares compartilham.
- **Shotgun Surgery**: uma mudança lógica forçando edits espalhados por muitos arquivos. → juntar o que muda junto num módulo.
- **Divergent Change**: um arquivo/módulo editado por vários motivos não relacionados. → separar pra cada módulo mudar por um motivo só.
- **Speculative Generality**: abstração, parâmetro ou hook pra necessidade que a spec não tem. → apagar; inline de volta até aparecer necessidade real.
- **Message Chains**: navegação longa `a.b().c().d()` de que o caller não deveria depender. → esconder o caminho atrás de um método no primeiro objeto.
- **Middle Man**: classe/função que só delega adiante. → cortar e chamar o alvo real direto.
- **Refused Bequest**: subclasse/implementação que ignora a maior parte do que herda. → trocar herança por composição.

Captura output. Issues `must-fix` → ❌ reportar, comentar no PR, parar.

### (substituída pelo `/tdd`) verificação final com evidência — só com `--rigoroso`

**Imediatamente antes do merge**, verificação com evidência real:
- Roda comando real de teste/build local (não confia em "deve funcionar").
- Lê output literal.
- Só então confirma sucesso — evidência antes de qualquer afirmação de êxito.

Se a verificação falhar → ❌ reportar, parar. Self-approval **não acontece** sem essa camada verde.
