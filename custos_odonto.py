# -*- coding: utf-8 -*-
"""
Sistema de Análise de Custos e Precificação de Serviços Odontológicos
=====================================================================

O sistema permite:
  1. Cadastrar custos FIXOS mensais (aluguel, salários, software...) e
     custos VARIÁVEIS por procedimento (materiais, laboratório...).
  2. Ratear os custos fixos pelas horas-clínicas disponíveis no mês
     (custeio absorção) ou usar custo direto + margem (custeio variável).
  3. Calcular o PREÇO SUGERIDO de cada procedimento considerando:
       - Custo do material/insumo
       - Custo de laboratório (prótese, etc.)
       - Hora do dentário/profissional
       - Rateio dos custos fixos (hora-clínica)
       - Margem de lucro desejada (%)
       - Tributação incidente sobre o preço (%)
       - Taxa de cartão / comissão (%)
       - Bônus técnico (% sobre o honorário)
  4. Analisar a saúde financeira: ponto de equilíbrio, margem de
     contribuição, faturamento necessário, DRE simplificada.

Uso rápido:
    from custos_odonto import Consultorio, Procedimento, CustoFixo

    c = Consultorio(nome="Odonto Sorriso", horas_clinicas_mes=160)
    c.adicionar_custo_fixo(CustoFixo("Aluguel", 3500))
    ...
    print(c.analise())
"""

from dataclasses import dataclass, field
from typing import List, Optional


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def brl(valor: float) -> str:
    """Formata número como moeda brasileira."""
    s = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def pct(valor: float) -> str:
    return f"{valor:.1f}%".replace(".", ",")


# ----------------------------------------------------------------------------
# Modelos de dados
# ----------------------------------------------------------------------------
@dataclass
class CustoFixo:
    """Custo fixo mensal do consultório."""
    descricao: str
    valor_mensal: float
    categoria: str = "Geral"          # Estrutura, Pessoal, Marketing, Tecnologia...
    essencial: bool = True            # entra no cálculo do ponto de equilíbrio mínimo?

    def anual(self) -> float:
        return self.valor_mensal * 12


@dataclass
class Material:
    """Insumo utilizado em um procedimento (uso único ou rateado)."""
    nome: str
    preco_unitario: float             # preço de compra unitário
    unidade: str = "un"               # un, ml, gr, embalagem...

    def custo(self, quantidade: float) -> float:
        return self.preco_unitario * quantidade


@dataclass
class UsoMaterial:
    """Vínculo: material X é usado em quantidade Y num procedimento."""
    material: Material
    quantidade: float = 1.0

    @property
    def custo(self) -> float:
        return self.material.custo(self.quantidade)


@dataclass
class Profissional:
    """Profissional que executa/atende (dentista, ASB, recepcionista...)."""
    nome: str
    cargo: str = "Cirurgião-Dentista"
    salario_mensal: float = 0.0       # CLT/pessoal próprio
    horas_trabalhadas_mes: float = 160.0
    valor_hora_autonomo: float = 0.0  # se for prestador autônomo por hora

    @property
    def custo_hora(self) -> float:
        if self.valor_hora_autonomo > 0:
            return self.valor_hora_autonomo
        if self.horas_trabalhadas_mes > 0 and self.salario_mensal > 0:
            return self.salario_mensal / self.horas_trabalhadas_mes
        return 0.0


@dataclass
class Procedimento:
    """Serviço odontológico a ser custeado e precificado."""
    codigo: str
    nome: str
    duracao_minutos: float
    materiais: List[UsoMaterial] = field(default_factory=list)
    custo_laboratorio: float = 0.0
    profissional: Optional[Profissional] = None
    bônus_tecnico_pct: float = 0.0     # % sobre o honorário (se aplicável)
    margem_lucro_pct: float = 30.0     # margem desejada sobre o custo total
    tributacao_pct: float = 6.0        # Simples/S/A/I/CSLL sobre o preço
    taxa_cartao_pct: float = 2.5       # taxa de adquirência/cartão
    concorrencia_preco: Optional[float] = None  # preço praticado pelo mercado

    def adicionar_material(self, material: Material, quantidade: float = 1.0):
        self.materiais.append(UsoMaterial(material, quantidade))
        return self

    # ------------------------- Componentes de custo -------------------------
    @property
    def custo_materiais(self) -> float:
        return sum(u.custo for u in self.materiais)

    @property
    def custo_profissional(self) -> float:
        if self.profissional is None:
            return 0.0
        return self.profissional.custo_hora * (self.duracao_minutos / 60.0)

    def custo_fixo_rateado(self, valor_hora_clinica: float) -> float:
        return valor_hora_clinica * (self.duracao_minutos / 60.0)

    def custo_total(self, valor_hora_clinica: float) -> float:
        """Custo total direto + rateio de indiretos."""
        return (self.custo_materiais
                + self.custo_laboratorio
                + self.custo_profissional
                + self.custo_fixo_rateado(valor_hora_clinica))


# ----------------------------------------------------------------------------
# Núcleo do sistema
# ----------------------------------------------------------------------------
class Consultorio:
    def __init__(self, nome: str, horas_clinicas_mes: float = 160.0,
                 ocupacao_pct: float = 100.0):
        """
        :param horas_clinicas_mes: horas totais da cadeira/sala no mês
        :param ocupacao_pct: percentual real de ocupação das horas
        """
        self.nome = nome
        self.horas_clinicas_mes = horas_clinicas_mes
        self.ocupacao_pct = ocupacao_pct
        self.custos_fixos: List[CustoFixo] = []
        self.materiais: List[Material] = []
        self.profissionais: List[Profissional] = []
        self.procedimentos: List[Procedimento] = []

    # --------------------------- Cadastros ----------------------------------
    def adicionar_custo_fixo(self, cf: CustoFixo):
        self.custos_fixos.append(cf)
        return self

    def adicionar_material(self, m: Material):
        self.materiais.append(m)
        return self

    def adicionar_profissional(self, p: Profissional):
        self.profissionais.append(p)
        return self

    def adicionar_procedimento(self, pr: Procedimento):
        self.procedimentos.append(pr)
        return self

    # --------------------------- Indicadores --------------------------------
    @property
    def total_custos_fixos(self) -> float:
        return sum(c.valor_mensal for c in self.custos_fixos)

    @property
    def horas_efetivas(self) -> float:
        return self.horas_clinicas_mes * (self.ocupacao_pct / 100.0)

    @property
    def valor_hora_clinica(self) -> float:
        """Rateio: quanto cada hora de cadeira 'carrega' de custo fixo."""
        h = self.horas_efetivas
        return self.total_custos_fixos / h if h > 0 else 0.0

    def preco_sugerido(self, pr: Procedimento) -> dict:
        """
        Precifica considerando que tributos, taxa de cartão e bônus técnico
        incidem SOBRE O PREÇO final -> usamos divisor para embuti-los.
        """
        custo_direto = (pr.custo_materiais + pr.custo_laboratorio
                        + pr.custo_profissional)
        custo_indireto = pr.custo_fixo_rateado(self.valor_hora_clinica)
        custo_total = custo_direto + custo_indireto

        lucro = custo_total * (pr.margem_lucro_pct / 100.0)
        preco_bruto = custo_total + lucro

        # Deduções que incidem sobre o preço
        ded_pcts = (pr.tributacao_pct + pr.taxa_cartao_pct
                    + pr.bônus_tecnico_pct) / 100.0
        divisor = 1.0 - ded_pcts
        if divisor <= 0:
            raise ValueError(
                f"A soma de tributos+cartão+bônus de '{pr.nome}' é >= 100%.")

        preco_final = preco_bruto / divisor
        impostos = preco_final * (pr.tributacao_pct / 100.0)
        cartao = preco_final * (pr.taxa_cartao_pct / 100.0)
        bonus = preco_final * (pr.bônus_tecnico_pct / 100.0)
        margem_contribuicao = preco_final - impostos - cartao - bonus - custo_direto
        lucro_real = margem_contribuicao - custo_indireto

        resultado = {
            "procedimento": pr.nome,
            "codigo": pr.codigo,
            "duracao_min": pr.duracao_minutos,
            "custo_materiais": round(pr.custo_materiais, 2),
            "custo_laboratorio": round(pr.custo_laboratorio, 2),
            "custo_profissional": round(pr.custo_profissional, 2),
            "custo_fixo_rateado": round(custo_indireto, 2),
            "custo_total": round(custo_total, 2),
            "margem_lucro_pct": pr.margem_lucro_pct,
            "lucro_alvo": round(lucro, 2),
            "impostos": round(impostos, 2),
            "taxa_cartao": round(cartao, 2),
            "bonus_tecnico": round(bonus, 2),
            "preco_sugerido": round(preco_final, 2),
            "margem_contribuicao": round(margem_contribuicao, 2),
            "lucro_real": round(lucro_real, 2),
            "concorrencia": pr.concorrencia_preco,
        }
        if pr.concorrencia_preco:
            delta = (preco_final - pr.concorrencia_preco) / pr.concorrencia_preco * 100
            resultado["posicionamento"] = (
                f"{delta:+.1f}% vs. concorrência "
                f"({'ACIMA' if delta > 10 else 'ALINHADO' if delta >= -10 else 'ABAIXO'})"
            )
        return resultado

    def ponto_equilibrio(self) -> dict:
        """Quantas consultas/horas são necessárias para cobrir os custos fixos."""
        if not self.procedimentos:
            return {}
        precos = [self.preco_sugerido(p) for p in self.procedimentos]
        mc_media = sum(x["margem_contribuicao"] for x in precos) / len(precos)
        tempo_medio = sum(p.duracao_minutos for p in self.procedimentos) / len(self.procedimentos)
        qtd_pe = self.total_custos_fixos / mc_media if mc_media > 0 else float("inf")
        return {
            "mc_medio_por_atendimento": round(mc_media, 2),
            "tempo_medio_min": round(tempo_medio, 1),
            "qtd_atendimentos_pe": int(qtd_pe) + (1 if qtd_pe % 1 else 0),
            "horas_pe": round(qtd_pe * tempo_medio / 60.0, 1),
            "faturamento_pe": round(qtd_pe * (sum(x["preco_sugerido"] for x in precos) / len(precos)), 2),
        }

    def dre_simplificada(self, volume_mensal: Optional[dict] = None) -> dict:
        """DRE projetada. volume_mensal = {codigo_procedimento: qtd}."""
        if volume_mensal is None:
            volume_mensal = {p.codigo: 10 for p in self.procedimentos}
        receita = 0.0
        variaveis = 0.0
        detalhes = []
        for p in self.procedimentos:
            qtd = volume_mensal.get(p.codigo, 0)
            prec = self.preco_sugerido(p)
            rec = prec["preco_sugerido"] * qtd
            var = (prec["custo_materiais"] + prec["custo_laboratorio"]
                   + prec["custo_profissional"] + prec["impostos"]
                   + prec["taxa_cartao"] + prec["bonus_tecnico"]) * qtd
            receita += rec
            variaveis += var
            detalhes.append((p.nome, qtd, rec, var))
        mc_total = receita - variaveis
        fixos = self.total_custos_fixos
        lucro = mc_total - fixos
        return {
            "receita_bruta": round(receita, 2),
            "custos_variaveis": round(variaveis, 2),
            "margem_contribuicao": round(mc_total, 2),
            "mc_pct": round(mc_total / receita * 100, 1) if receita else 0,
            "custos_fixos": round(fixos, 2),
            "lucro_liquido": round(lucro, 2),
            "margem_liquida_pct": round(lucro / receita * 100, 1) if receita else 0,
            "detalhes": detalhes,
        }

    # --------------------------- Relatórios ---------------------------------
    def analise(self) -> str:
        linhas = []
        sep = "=" * 78
        linhas.append(sep)
        linhas.append(f" ANÁLISE DE CUSTOS E PRECIFICAÇÃO — CONSULTÓRIO {self.nome.upper()}")
        linhas.append(sep)
        linhas.append(f" Horas clínicas/mês .......... {self.horas_clinicas_mes:.1f} h")
        linhas.append(f" Ocupação .................... {pct(self.ocupacao_pct)} ({self.horas_efetivas:.1f} h efetivas)")
        linhas.append(f" Total custos fixos/mês ...... {brl(self.total_custos_fixos)}")
        linhas.append(f" VALOR HORA-CLÍNICA (rateio) . {brl(self.valor_hora_clinica)}/h")
        linhas.append("-" * 78)
        linhas.append(" CUSTOS FIXOS MENSAIS:")
        for c in sorted(self.custos_fixos, key=lambda x: -x.valor_mensal):
            share = c.valor_mensal / self.total_custos_fixos * 100 if self.total_custos_fixos else 0
            linhas.append(f"   • {c.descricao:<32} {brl(c.valor_mensal):>12}  ({share:4.1f}%) [{c.categoria}]")
        linhas.append("-" * 78)
        linhas.append(" PRECIFICAÇÃO DOS PROCEDIMENTOS:")
        cab = (f"   {'Código':<8}{'Procedimento':<30}{'Custo':>10}{'Preço':>11}"
               f"{'MC%':>7}{'Lucro':>10}")
        linhas.append(cab)
        for p in self.procedimentos:
            r = self.preco_sugerido(p)
            mc_pct = r["margem_contribuicao"] / r["preco_sugerido"] * 100 if r["preco_sugerido"] else 0
            linhas.append(f"   {r['codigo']:<8}{r['procedimento'][:29]:<30}"
                          f"{brl(r['custo_total']):>10}{brl(r['preco_sugerido']):>11}"
                          f"{mc_pct:>6.1f}%{brl(r['lucro_real']):>10}")
            if "posicionamento" in r:
                linhas.append(f"     └─ {r['posicionamento']}")
        pe = self.ponto_equilibrio()
        if pe:
            linhas.append("-" * 78)
            linhas.append(" PONTO DE EQUILÍBRIO:")
            linhas.append(f"   MC médio por atendimento: {brl(pe['mc_medio_por_atendimento'])}")
            linhas.append(f"   Tempo médio atendimento:  {pe['tempo_medio_min']} min")
            linhas.append(f"   Consultas p/ empatar:     {pe['qtd_atendimentos_pe']}/mês "
                          f"(~{pe['horas_pe']} h)")
            linhas.append(f"   Faturamento p/ empatar:   {brl(pe['faturamento_pe'])}")
        dre = self.dre_simplificada()
        linhas.append("-" * 78)
        linhas.append(" DRE PROJETADA (10 atendimentos/procedimento por padrão):")
        linhas.append(f"   Receita bruta ............. {brl(dre['receita_bruta'])}")
        linhas.append(f"   Custos variáveis .......... {brl(dre['custos_variaveis'])}")
        linhas.append(f"   Margem de contribuição .... {brl(dre['margem_contribuicao'])} ({dre['mc_pct']}%)")
        linhas.append(f"   Custos fixos .............. {brl(dre['custos_fixos'])}")
        linhas.append(f"   LUCRO LÍQUIDO ............. {brl(dre['lucro_liquido'])} ({dre['margem_liquida_pct']}%)")
        linhas.append(sep)
        return "\n".join(linhas)


# ----------------------------------------------------------------------------
# Exemplo executável
# ----------------------------------------------------------------------------
def exemplo() -> Consultorio:
    c = Consultorio(nome="Odonto Sorriso", horas_clinicas_mes=176, ocupacao_pct=85)

    # Custos fixos típicos
    for d, v, cat in [
        ("Aluguel + condomínio", 3800, "Estrutura"),
        ("Energia/Água/Internet", 750, "Estrutura"),
        ("Secretária (salário + encargos)", 2900, "Pessoal"),
        ("ASB (auxiliar)", 2100, "Pessoal"),
        ("Software odontológico", 350, "Tecnologia"),
        ("Marketing digital", 1200, "Marketing"),
        ("Seguro + contabilidade", 900, "Administrativo"),
        ("Manutenção equipamentos", 500, "Estrutura"),
    ]:
        c.adicionar_custo_fixo(CustoFixo(d, v, cat))

    # Materiais
    luva = Material("Luva de procedimento (par)", 1.20)
    mascara = Material("Máscara triplata", 0.60)
    anestesia = Material("Anestésico lidocaína 2%", 8.50)
    resina = Material("Resina composta (seringa)", 95.00)
    broca_desc = Material("Conjunto descartável/endodontia básico", 42.00)
    profilaxia = Material("Kit profilaxia/jato", 18.00)
    radiografia = Material("Placa/filme radiografia", 6.00)
    alginate = Material("Alginato + gesso (molde)", 25.00)
    cimento = Material("Cimento provisório", 30.00)
    for m in [luva, mascara, anestesia, resina, broca_desc, profilaxia,
              radiografia, alginate, cimento]:
        c.adicionar_material(m)

    dentista = Profissional("Dr(a). Responsável", "Cirurgião-Dentista",
                            salario_mensal=12000, horas_trabalhadas_mes=176)
    c.adicionar_profissional(dentista)

    # Procedimentos
    restauracao = Procedimento("RES-01", "Restauração em resina (1 face)",
                               duracao_minutos=40, profissional=dentista,
                               margem_lucro_pct=35, tributacao_pct=6,
                               taxa_cartao_pct=3.0, concorrencia_preco=180)
    restauracao.adicionar_material(luva, 1).adicionar_material(mascara, 1) \
        .adicionar_material(anestesia, 1).adicionar_material(resina, 0.25) \
        .adicionar_material(radiografia, 1)

    canal = Procedimento("END-01", "Tratamento endodôntico (anterior)",
                         duracao_minutos=90, profissional=dentista,
                         margem_lucro_pct=40, tributacao_pct=6,
                         taxa_cartao_pct=3.0, concorrencia_preco=950)
    canal.adicionar_material(luva, 2).adicionar_material(mascara, 2) \
        .adicionar_material(anestesia, 2).adicionar_material(broca_desc, 1) \
        .adicionar_material(radiografia, 2).adicionar_material(cimento, 0.5)

    coroa = Procedimento("PRO-01", "Coroa unitária em zircônia",
                         duracao_minutos=120, profissional=dentista,
                         custo_laboratorio=450.0, margem_lucro_pct=45,
                         tributacao_pct=6, taxa_cartao_pct=3.5,
                         bônus_tecnico_pct=0, concorrencia_preco=2200)
    coroa.adicionar_material(luva, 2).adicionar_material(mascara, 2) \
        .adicionar_material(anestesia, 1).adicionar_material(alginate, 1) \
        .adicionar_material(cimento, 1).adicionar_material(radiografia, 1)

    limpeza = Procedimento("PER-01", "Profilaxia + aplicação flúor",
                           duracao_minutos=45, profissional=dentista,
                           margem_lucro_pct=50, tributacao_pct=6,
                           taxa_cartao_pct=2.5, concorrencia_preco=150)
    limpeza.adicionar_material(luva, 1).adicionar_material(mascara, 1) \
        .adicionar_material(profilaxia, 1)

    extracao = Procedimento("CIR-01", "Extração simples",
                            duracao_minutos=35, profissional=dentista,
                            margem_lucro_pct=35, tributacao_pct=6,
                            taxa_cartao_pct=2.5)
    extracao.adicionar_material(luva, 1).adicionar_material(mascara, 1) \
        .adicionar_material(anestesia, 1).adicionar_material(radiografia, 1)

    for p in [restauracao, canal, coroa, limpeza, extracao]:
        c.adicionar_procedimento(p)
    return c


if __name__ == "__main__":
    print(exemplo().analise())
