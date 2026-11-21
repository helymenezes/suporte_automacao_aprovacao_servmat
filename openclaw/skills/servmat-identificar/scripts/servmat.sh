#!/usr/bin/env bash
# Ponte do agente OpenClaw com o painel servmat. Só três operações; o token nunca é impresso.
#   servmat.sh pendentes | catalogo | enviar <arquivo.json>
set -euo pipefail
: "${SERVMAT_URL:?defina SERVMAT_URL (ex.: http://172.17.0.1:8792)}"
: "${SERVMAT_AGENTE_TOKEN:?defina SERVMAT_AGENTE_TOKEN no cofre do OpenClaw}"
AUTH=(-H "Authorization: Bearer ${SERVMAT_AGENTE_TOKEN}" -H "X-Agente: openclaw")

case "${1:-}" in
  pendentes)
    curl -sS --fail-with-body --max-time 30 "${AUTH[@]}" "${SERVMAT_URL%/}/api/agente/pendentes?limite=${2:-10}" ;;
  catalogo)
    curl -sS --fail-with-body --max-time 30 "${AUTH[@]}" "${SERVMAT_URL%/}/api/agente/catalogo" ;;
  enviar)
    f="${2:?uso: servmat.sh enviar <arquivo.json>}"
    [ -f "$f" ] || { echo "arquivo não encontrado: $f" >&2; exit 2; }
    curl -sS --max-time 60 -w '\nHTTP %{http_code}\n' "${AUTH[@]}" -H "Content-Type: application/json" \
      --data-binary @"$f" "${SERVMAT_URL%/}/api/agente/identificacoes" ;;
  *)
    echo "uso: $0 pendentes [limite] | catalogo | enviar <arquivo.json>" >&2; exit 2 ;;
esac
