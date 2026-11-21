export type Fase = "relatorio" | "n1" | "n2" | "whats" | "pedido" | "fim" | "reprovado";
export type Cls = "Contrato HGG" | "Pedido de compra" | "A definir";
export type EstadoEtapa = "feito" | "atual" | "pendente" | "na" | "seminfo" | "reprovado";

export interface Etapa {
  nome: string;
  estado: EstadoEtapa;
  txt: string;
  prox: string;
  quem: string;
}

export interface Agora extends Etapa {
  pos: number;
  total: number;
}

export interface Item {
  id: number;
  os: string;
  item: string;
  natureza: string;
  situacao: string;
  qtd: string;
  presumida: boolean;
  cls: Cls;
  conf: "Alta" | "Média" | "Baixa";
  contrato_item: string;
  val_ok: boolean;
  val_txt: string;
  evidencia: string;
  fase: Fase;
  fase_nome: string;
  reprovado_em: string | null;
  versao: number;
  sugerido_por: string;
  trilha: { nivel: string; quem: string; estado: string }[];
}

export interface Servico {
  os: string;
  cliente: string;
  area: string;
  equipamento: string;
  tipo: string;
  tecnico: string;
  origem: string;
  relato: string;
  utilizou: string;
  prog_txt: string;
  prog_meta: string;
  identificacao: "pendente" | "feita" | "sem_info";
  tem_link: boolean;
  fase: Fase;
  fase_nome: string;
  cls: string;
  cls_sub: string;
  mix: string;
  conflito_n2: boolean;
  etapas: Etapa[];
  agora: Agora | null;
  itens: Item[];
}

export interface Painel {
  gerado_em: string;
  fases: { chave: Fase; nome: string; quem: string; qtd: number }[];
  aguardando_agente: number;
  servicos: Servico[];
}

export interface Usuario {
  usuario: string;
  nome: string;
  nivel: 1 | 2;
}
