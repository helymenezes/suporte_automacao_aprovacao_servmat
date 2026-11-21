export type Fase = "relatorio" | "nivel" | "whats" | "pedido" | "fim" | "reprovado";
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
  nivel_pos: number | null;
  fase_chave: string;
  fase_nome: string;
  nivel_quem: string;
  nivel_papel: string;
  minha_vez: boolean;
  pode_reclassificar: boolean;
  reprovado_em: string | null;
  versao: number;
  sugerido_por: string;
  trilha: { nivel: string; quem: string; papel: string; estado: string }[];
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
  contrato_avaliado: boolean;
  fase: Fase;
  fase_chave: string;
  fase_nome: string;
  cls: string;
  cls_sub: string;
  mix: string;
  conflito: boolean;
  etapas: Etapa[];
  agora: Agora | null;
  itens: Item[];
}

export interface Painel {
  gerado_em: string;
  rota_versao: number;
  fases: { chave: string; nome: string; quem: string; qtd: number }[];
  aguardando_agente: number;
  servicos: Servico[];
}

export interface Usuario {
  usuario: string;
  nome: string;
  admin: boolean;
  niveis: number[];
}

export interface Envio {
  id: number;
  estado: "PENDENTE" | "ENVIADO" | "FALHOU" | "INCERTO" | "SIMULADO";
  recibo: string;
  motivo: string;
  em: string;
  destino: string;
}

export interface LinhaPedido {
  os: string;
  tipo: "compra" | "contrato";
  cliente: string;
  equipamento: string;
  area: string;
  itens: { id: number; item: string; qtd: string; presumida: boolean; situacao: string; fase: Fase; fase_nome: string }[];
  pedido_num: string;
  vinculo: "" | "a_conferir" | "vinculado" | "nao_localizado";
  aceite: "" | "aguardando" | "aceito" | "parcial" | "recusado";
  aceite_obs: string;
  celso: "" | "aguardando" | "autorizado" | "devolvido" | "reprovado";
  execucao: "" | "a_agendar" | "agendada" | "concluida";
  execucao_meta: string;
  nf: string;
  fonte: string;
  solicitacao: Envio | null;
  cobranca: Envio | null;
  grupo: string;
  todos_aplicados: boolean;
  aguardando: boolean;
  pode_solicitar: boolean;
  pode_cobrar: boolean;
  incertos: number[];
}

export interface Pedidos {
  gerado_em: string;
  grupos: { chave: string; nome: string; qtd: number }[];
  integracoes: { comercial: { ultima_em: string; resumo: string } | null; planilha: { ultima_em: string; resumo: string } | null };
  linhas: LinhaPedido[];
  envio_real: boolean;
  destino: string;
  pode_agir: boolean;
}

export interface Nivel {
  id?: number;
  papel: string;
  usuario: string | null;
  nome?: string;
  compra: boolean;
  contrato: boolean;
  ativo: boolean;
}

export interface Niveis {
  versao: number;
  niveis: Nivel[];
  usuarios: { usuario: string; nome: string }[];
  contratos: { cliente: string; ligado: boolean; tem_catalogo: boolean }[];
  pode_editar: boolean;
}
